from functools import cached_property
import time
import json
import os

from pymongo import AsyncMongoClient
from pydantic import BaseModel, computed_field
from hatchet_sdk import Context, ParentCondition

from hatching import hatchet

wf = hatchet.workflow(name="nriy_router")

class NriyRouterInput(BaseModel):
    event_json: str

    @cached_property
    def parsed(self) -> dict:
        obj = json.loads(self.event_json)
        return {
            "room": obj["room"],
            "channelId": obj["channelId"],
            "authorName": obj["authorName"],
            "content": obj["content"],
            "logId": obj["logId"],
            "timestamp": time.time_ns() // 1_000_000
        }


@wf.task()
async def insert_message(input: NriyRouterInput, ctx: Context):
    client = AsyncMongoClient(os.environ["MONGO_URI"])
    try:
        collection = client["nriy"]["chats"]
        await collection.update_one(
            {"logId": input.parsed["logId"]},
            {
                "$setOnInsert": {
                    "room": input.parsed["room"],
                    "channelId": input.parsed["channelId"],
                    "authorName": input.parsed["authorName"],
                    "content": input.parsed["content"],
                    "logId": input.parsed["logId"],
                    "timestamp": input.parsed["timestamp"]
                }
            },
            upsert=True
        )
    finally:
        client.close()
    return {}

@wf.task()
async def decide(input: NriyRouterInput, ctx: Context):
    if input.parsed["content"].startswith("/"):
        return {"reply": True}
    else:
        return {"reply": False}

@wf.task(
    parents=[decide],
    skip_if=[
        ParentCondition(
            parent=decide,
            expression="output.reply == false",
        )
    ]
)
async def abandon(input: NriyRouterInput, ctx: Context):
    return {
        "doReply": False
    }

@wf.task(
    parents=[decide],
    skip_if=[
        ParentCondition(
            parent=decide,
            expression="output.reply == true",
        )
    ]
)
async def get_latest_history(input: NriyRouterInput, ctx: Context):
    client = AsyncMongoClient(os.environ["MONGO_URI"])
    try:
        collection = client["nriy"]["chats"]
        history = await collection.find(
            {
                "channelId": input.parsed["channelId"],
                "logId": {
                    "$not": {"$eq": input.parsed["logId"]},
                }
            } 
        ).sort("logId", -1).to_list(15)
    finally:
        client.close()
    
    output = []
    for item in history:
        output.append(f"{item['authorName']}: {item['content']}")
    return {
        "history": "\n".join(output)
    }

@wf.task(
    parents=[get_latest_history]
)
async def generate_reply(input: NriyRouterInput, ctx: Context):
    from hatching.workflows.nriy_v1 import wf as nriy_v1, NriyV1Input

    result = await nriy_v1.aio_run(NriyV1Input(
        history=get_latest_history.output["history"],
        input=input.parsed["content"],
        channel_id=input.parsed["channelId"]
    ))

    return {
        "doReply": True,
        "message": result.output["reply"]
    }

@wf.task(
    parents=[generate_reply]
)
async def insert_reply(input: NriyRouterInput, ctx: Context):
    client = AsyncMongoClient(os.environ["MONGO_URI"])
    try:
        collection = client["nriy"]["chats"]
        await collection.insert_one({
            "room": input.parsed["room"],
            "channelId": input.parsed["channelId"],
            "authorName": "나란잉여",
            "content": input.parsed["message"],
            "logId": f"{input.parsed['logId']}-reply",
            "timestamp": time.time_ns() // 1_000_000
        })
    finally:
        client.close()
    return {}

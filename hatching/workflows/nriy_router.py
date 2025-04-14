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
    room: str
    channel_id: str
    author_name: str
    content: str
    log_id: str
    timestamp: int

@wf.task()
async def insert_message(input: NriyRouterInput, ctx: Context):
    client = AsyncMongoClient(os.environ["MONGO_URI"])
    try:
        collection = client["nriy"]["chats"]
        await collection.update_one(
            {"logId": input.log_id},
            {
                "$setOnInsert": {
                    "room": input.room,
                    "channelId": input.channel_id,
                    "authorName": input.author_name,
                    "content": input.content,
                    "logId": input.log_id,
                    "timestamp": input.timestamp
                }
            },
            upsert=True
        )
    finally:
        client.close()
    return {}

@wf.task()
async def decide(input: NriyRouterInput, ctx: Context):
    if input.content.startswith("/"):
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
async def get_latest_history(input: NriyRouterInput, ctx: Context):
    client = AsyncMongoClient(os.environ["MONGO_URI"])
    try:
        collection = client["nriy"]["chats"]
        history = await collection.find(
            {
                "channelId": input.channel_id,
                "logId": {
                    "$not": {"$eq": input.log_id},
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
        input=input.content,
        channel_id=input.channel_id
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
            "room": input.room,
            "channelId": input.channel_id,
            "authorName": "나란잉여",
            "content": input.message,
            "logId": f"{input.log_id}-reply",
            "timestamp": time.time_ns() // 1_000_000
        })
    finally:
        client.close()
    return {}

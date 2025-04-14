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

@wf.task()
def parse_input(input: NriyRouterInput, ctx: Context):
    event = json.loads(input.event_json)
    return {
        "room": event["room"],
        "channelId": event["channelId"],
        "authorName": event["author"]["name"],
        "content": event["content"],
        "logId": event["logId"],
        "timestamp": time.time_ns() // 1_000_000
    }

@wf.task(
    parents=[parse_input]
)
async def insert_message(input: NriyRouterInput, ctx: Context):
    client = AsyncMongoClient(os.environ["MONGO_URI"])
    parsed = await ctx.task_output(parse_input)
    try:
        collection = client["nriy"]["chats"]
        await collection.update_one(
            {"logId": parsed["logId"]},
            {
                "$setOnInsert": {
                    "room": parsed["room"],
                    "channelId": parsed["channelId"],
                    "authorName": parsed["authorName"],
                    "content": parsed["content"],
                    "logId": parsed["logId"],
                    "timestamp": parsed["timestamp"]
                }
            },
            upsert=True
        )
    finally:
        client.close()
    return {}

@wf.task(
    parents=[insert_message],
)
async def decide(input: NriyRouterInput, ctx: Context):
    parsed = await ctx.task_output(parse_input)
    if parsed["content"].startswith("/"):
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
    parsed = await ctx.task_output(parse_input)
    try:
        collection = client["nriy"]["chats"]
        history = await collection.find(
            {
                "channelId": parsed["channelId"],
                "logId": {
                    "$not": {"$eq": parsed["logId"]},
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
    parsed = await ctx.task_output(parse_input)
    result = await nriy_v1.aio_run(NriyV1Input(
        history=get_latest_history.output["history"],
        input=parsed["content"],
        channel_id=parsed["channelId"]
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
    parsed = await ctx.task_output(parse_input)
    try:
        collection = client["nriy"]["chats"]
        await collection.insert_one({
            "room": parsed["room"],
            "channelId": parsed["channelId"],
            "authorName": "나란잉여",
            "content": parsed["message"],
            "logId": f"{parsed['logId']}-reply",
            "timestamp": time.time_ns() // 1_000_000
        })
    finally:
        client.close()
    return {}

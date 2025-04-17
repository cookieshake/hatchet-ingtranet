from functools import cached_property
from datetime import timedelta
import json
import os

from pymongo import AsyncMongoClient
from pydantic import BaseModel, computed_field
from temporalio import workflow, activity

from temping.workflows.nriy_v1 import NriyV1Workflow, NriyV1Input


class NriyRouterInput(BaseModel):
    room: str
    channel_id: str
    author_name: str
    content: str
    log_id: str
    timestamp: int

@activity.defn
async def insert_message(input: NriyRouterInput) -> None:
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


@activity.defn
async def whether_to_reply(input: NriyRouterInput) -> bool:
    if input.content.startswith("/"):
        return True
    else:
        return False

@activity.defn
async def get_latest_history(input: NriyRouterInput) -> str:
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
    return "\n".join(output)

@activity.defn
async def insert_reply(input: NriyRouterInput, reply_message: str) -> None:
    client = AsyncMongoClient(os.environ["MONGO_URI"])
    try:
        collection = client["nriy"]["chats"]
        log_id = f"{input.log_id}-reply"
        await collection.update_one(
            {"logId": log_id},
            {
                "$setOnInsert": {
                    "room": input.room,
                    "channelId": input.channel_id,
                    "authorName": "나란잉여",
                    "content": message,
                    "logId": log_id,
                    "timestamp": input.timestamp
                }
            },
            upsert=True
        )
    finally:
        client.close()
    return {}


@workflow.defn
class NriyRouterWorkflow:
    @workflow.run
    async def run(self, input: NriyRouterInput):
        await workflow.execute_activity(
            insert_message,
            input,
            start_to_close_timeout=timedelta(seconds=10)
        )

        if not await workflow.execute_activity(
            whether_to_reply,
            input,
            start_to_close_timeout=timedelta(seconds=10)
        ):
            return {
                "reply": False
            }

        history = await workflow.execute_activity(
            get_latest_history,
            input,
            start_to_close_timeout=timedelta(seconds=10)
        )

        generated = await workflow.execute_child_workflow(
            NriyV1Workflow.run,
            NriyV1Input(
                room=input.room,
                channel_id=input.channel_id,
                author_name=input.author_name,
                content=input.content,
                log_id=input.log_id,
                timestamp=input.timestamp,
                history=history
            )
        )
        if generated["skipped"] or generated["message"] == "":
            return {
                "reply": False
            }

        message = generated["message"]
        await workflow.start_activity(
            insert_reply,
            input, message,
            start_to_close_timeout=timedelta(seconds=10)
        )
        return {
            "reply": True,
            "message": message,
        }

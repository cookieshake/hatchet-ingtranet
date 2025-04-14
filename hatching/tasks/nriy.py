import json
import time

from hatchet_sdk import Context
from pydantic import BaseModel

from hatching import hatchet
from hatching.workflows.nriy_router import wf as nriy_router, NriyRouterInput

class NriyTaskInput(BaseModel):
    event_json: str

@hatchet.task(name="nriy", input_validator=NriyTaskInput)
async def task(input: NriyTaskInput, ctx: Context):
    parsed = json.loads(input.event_json)
    router_input = NriyRouterInput(
        room=parsed["room"],
        channel_id=parsed["channelId"],
        author_name=parsed["author"]["name"],
        content=parsed["content"],
        log_id=parsed["logId"],
        timestamp=time.time_ns() // 1_000_000
    )
    result = await nriy_router.aio_run(router_input)
    if result["generate_response"].get("reply", False):
        return {
            "doReply": False,
            "message": ""
        }
    else:
        return {
            "doReply": True,
            "message": result["generate_response"]["message"]
        }
        

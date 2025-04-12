from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from hatching import hatchet

class NriyV1Input(BaseModel):
    history: str
    input: str
    channel_id: str

wf = hatchet.workflow(name="nriy_v1", input_validator=NriyV1Input)

@wf.task()
def get_now_context(input: NriyV1Input):
    return {
        # datetime in KST timezone
        "current_time": datetime.now(timezone(timedelta(hours=9))).strftime("%Y/%m/%d %H:%M"),
    }
import anyio
from temporalio.client import Client
from temporalio.worker import Worker

from temping.workflows.nriy_router import NriyRouterWorkflow
from temping.workflows.nriy_v1 import NriyV1Workflow

from temporalio.contrib.pydantic import pydantic_data_converter

async def main():
    client = await Client.connect("temporal-api.ingtra.net:443", tls=True, data_converter=pydantic_data_converter)
    worker = Worker(
        client,
        task_queue="nriy",
        workflows=[
            NriyRouterWorkflow,
            NriyV1Workflow,
        ]
    )
    await worker.run()

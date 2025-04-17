import anyio
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

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
        ],
        workflow_runner=SandboxedWorkflowRunner(
            restrictions=SandboxRestrictions.default.with_passthrough_all_modules()
        )
    )
    await worker.run()

import anyio
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from temping.workflows.nriy_router import workflows as nriy_router_workflows, activities as nriy_router_activities
from temping.workflows.nriy_v1 import workflows as nriy_v1_workflows, activities as nriy_v1_activities

from temporalio.contrib.pydantic import pydantic_data_converter

async def main():
    client = await Client.connect("temporal-api.ingtra.net:443", tls=True, data_converter=pydantic_data_converter)
    worker = Worker(
        client,
        task_queue="nriy",
        workflows=nriy_router_workflows + nriy_v1_workflows,
        activities=nriy_router_activities + nriy_v1_activities,
        workflow_runner=SandboxedWorkflowRunner(
            restrictions=SandboxRestrictions.default.with_passthrough_all_modules()
        )
    )
    print("Worker started")
    await worker.run()

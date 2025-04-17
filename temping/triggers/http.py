# from importlib import import_module

# from robyn import Robyn, Request
# from robyn.types import PathParams

# from temping import hatchet

# app = Robyn(__file__)

# @app.get("/")
# async def index(request: Request):
#     return {"status": "ok"}

# @app.get("/workflows")
# async def list_workflows(request: Request):
#     workflows = await hatchet._client.workflows.aio_list()
#     return workflows.to_dict()

# @app.post("/workflows/:id")
# async def trigger_workflow(request: Request, path_params: PathParams):
#     """
#     Trigger a workflow by ID.
#     """
#     workflow_id = path_params["id"]
#     ref = await hatchet._client.admin.aio_run_workflow(workflow_id, request.json())
    
#     return await ref.aio_result()

# @app.exception
# async def handle_exception(error: Exception):
#     """
#     Handle exceptions and return a JSON response.
#     """
#     return {
#         "status": "error",
#         "message": str(error)
#     }

# def main():
#     import os
#     app.start(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

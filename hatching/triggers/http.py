from importlib import import_module

from robyn import Robyn, Request
from robyn.types import PathParams

from hatching import hatchet

app = Robyn(__file__)

@app.get("/")
async def index(request: Request):
    return {"status": "ok"}

@app.post("/workflows/:id")
async def trigger_workflow(request: Request, path_params: PathParams):
    """
    Trigger a workflow by ID.
    """
    workflow_id = path_params["id"]
    payload = request.json
    if not payload:
        return {"error": "Payload is required"}, 400

    # Import the workflow module dynamically
    try:
        module = import_module(f"hatching.workflows.{workflow_id}")
    except ImportError:
        return {"error": "Workflow not found"}, 404
    workflow = getattr(module, "wf", None)
    if not workflow:
        return {"error": "Workflow not found"}, 404
    
    result = await workflow.run(payload)
    if result is None:
        return {"error": "Workflow execution failed"}, 50
    
    return result

def main():
    import os
    app.start(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))

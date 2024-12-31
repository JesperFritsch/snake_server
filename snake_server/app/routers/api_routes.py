from fastapi import APIRouter

from snake_server.app.services import api_services
from snake_server.app.services.requests.action_requests import RunRequest
from snake_server.app.services.responses.action_responses import RequestActionResponse

router = APIRouter()

@router.post("/request_run")
async def request_run(run_config: RunRequest) -> RequestActionResponse:
    """ Request a run, return the id of the run """
    try:
        run_id = api_services.request_run(run_config.model_dump())
    except Exception as e:
        return RequestActionResponse(run_id=None, action="request_run", result="error")
    else:
        return RequestActionResponse(run_id=run_id, action="request_run", result="success")


@router.post("/stop_ongoing/{run_id}")
async def stop_ongoing_run(run_id: str) -> RequestActionResponse:
    """ Stop an ongoing run by id """
    try:
        api_services.stop_run(run_id)
    except Exception as e:
        return RequestActionResponse(run_id=run_id, action="stop_ongoing_run", result="error")
    else:
        return RequestActionResponse(run_id=run_id, action="stop_ongoing_run", result="success")


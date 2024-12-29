from fastapi import APIRouter
from pydantic import BaseModel

from snake_server.app.services import api_services

class RequestRunConfig(BaseModel):
    """ Configuration for a run """
    grid_height: int
    grid_width: int
    food: int
    food_decay: int
    snake_count: int
    map: str

class RequestRunResponse(BaseModel):
    """ Response for a run request """
    run_id: str

router = APIRouter()

@router.post("/request_run")
async def request_run(run_config: RequestRunConfig) -> RequestRunResponse:
    """ Request a run, return the id of the run """
    run_id = api_services.request_run(run_config.model_dump())
    return RequestRunResponse(run_id=run_id)

@router.post("/stop_ongoing/{run_id}")
async def stop_ongoing_run(run_id: str):
    """ Stop an ongoing run by id """
    pass

@router.get("/stored/{run_id}")
async def get_stored_run(run_id: str):
    """ Get a stored run by id, returns the data as a file"""
    pass

from pydantic import BaseModel


class RequestActionResponse(BaseModel):
    """ Response for a run request """
    run_id: str
    action: str
    result: str

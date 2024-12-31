from pydantic import BaseModel
from typing import Optional


class RunRequest(BaseModel):
    """ Configuration for a run """
    grid_height: int
    grid_width: int
    food: int
    food_decay: int
    snake_count: int
    map: str
    start_length: int
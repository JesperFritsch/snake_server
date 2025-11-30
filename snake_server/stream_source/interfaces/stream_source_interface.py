import numpy as np
from abc import ABC, abstractmethod
from typing import List
from snake_sim.environment.types import CompleteStepState, EnvMetaData


class IStreamSource(ABC):
    """Interface for stream source classes"""

    @abstractmethod
    def get_step_range(self, start: int, end: int) -> List[CompleteStepState]:
        pass

    @abstractmethod
    def get_step(self, step: int) -> CompleteStepState:
        pass

    @abstractmethod
    def get_map(self, step: int) -> np.ndarray:
        pass

    @abstractmethod
    def get_map_range(self, start: int, end: int) -> List[List[np.ndarray]]:
        pass

    @abstractmethod
    async def get_meta_data(self) -> EnvMetaData:
        pass

    @abstractmethod
    def last_available_step(self) -> int:
        pass

    @abstractmethod
    def is_done(self) -> bool:
        pass

class ILiveStreamSource(IStreamSource):
    """Interface for live stream source classes"""


    @abstractmethod
    def get_run_config(self):
        pass

    @abstractmethod
    def cancel(self):
        pass
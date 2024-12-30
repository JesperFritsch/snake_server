from abc import ABC, abstractmethod
from typing import List
from snake_sim.run_data.run_data import RunData, StepData


class IStreamSource(ABC):
    """Interface for stream source classes"""

    @abstractmethod
    def get_step_range(self, start: int, end: int) -> List[StepData]:
        pass

    @abstractmethod
    def get_full_step(self, step: int) -> StepData:
        pass

    @abstractmethod
    def get_run_data(self) -> RunData:
        pass

    @abstractmethod
    def get_meta_data(self) -> dict:
        pass

    @abstractmethod
    def las_available_step(self) -> int:
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
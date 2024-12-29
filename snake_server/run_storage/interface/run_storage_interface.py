from typing import List
from abc import ABC, abstractmethod
from snake_sim.run_data.run_data import RunData


class IRunStorage(ABC):
    """Interface for run storage classes"""

    @abstractmethod
    def store_run(self, run_data: RunData, source_id: str, config: dict):
        pass

    @abstractmethod
    def get_run(self, run_id: str) -> RunData:
        pass

    @abstractmethod
    def run_exists(self, run_id: str) -> bool:
        pass

    @abstractmethod
    def get_unique_run_id(self) -> str:
        pass

    @abstractmethod
    def get_ids_by_config(self, config_attrs: dict) -> List[str]:
        pass
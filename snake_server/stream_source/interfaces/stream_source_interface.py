from abc import ABC, abstractmethod

class IStreamSource(ABC):
    """Interface for stream source classes"""

    @abstractmethod
    def get_step_range(self, start: int, end: int):
        pass

    @abstractmethod
    def get_full_step(self, step: int):
        pass

    @abstractmethod
    def get_run_data(self):
        pass

    @abstractmethod
    def get_meta_data(self):
        pass


class ILiveStreamSource(IStreamSource):
    """Interface for live stream source classes"""

    @abstractmethod
    def get_run_config(self):
        pass

    @abstractmethod
    def cancel(self):
        pass
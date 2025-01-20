from typing import List

from snake_server.stream_source.interfaces.stream_source_interface import IStreamSource
from snake_sim.run_data.run_data import RunData, StepData

class StoredSource(IStreamSource):
    def __init__(self, run_data: RunData):
        self._run_data: RunData = run_data

    def is_done(self) -> bool:
        return True

    def get_step_range(self, start: int, end: int) -> List[StepData]:
        steps = [self._run_data.steps[i] for i in range(start, end + 1)]
        return steps

    def get_full_step(self, step_nr: int) -> StepData:
        full_state = self._run_data.get_state_dict(step_nr)
        step_data = StepData(full_state['food'], step_nr)
        for snake in full_state['snakes']:
            step_data.add_snake_data(snake)
        return step_data

    def get_run_data(self) -> RunData:
        return self._run_data

    async def get_meta_data(self) -> dict:
        return self._run_data.get_metadata()

    def last_available_step(self) -> int:
        return len(self._run_data.steps) - 1

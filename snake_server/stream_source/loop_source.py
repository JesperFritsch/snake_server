import asyncio
import logging
import numpy as np
import time
from pathlib import Path
from asyncio import Event

from typing import List
from snake_server.stream_source.interfaces.stream_source_interface import ILiveStreamSource
from snake_sim.run_data.run_data import RunData, StepData

log = logging.getLogger(Path(__file__).stem)

class AsyncIPCLoopSource(ILiveStreamSource):
    def __init__(self, pipe, run_config: dict):
        if not pipe.__class__.__name__ in ['Connection', 'PipeConnection']:
            raise ValueError('pipe_conn must be a Connection or PipeConnection object')
        super(ILiveStreamSource, self).__init__()
        self._run_config = run_config
        self._pipe = pipe
        self._run_data: RunData = None
        self._stop_event = Event()
        self._recieve_task = asyncio.create_task(self.recieve_data())
        self._last_recieved_step = 0
        self._is_done = False

    def is_done(self):
        return self._is_done

    def last_available_step(self):
        return self._last_recieved_step

    def get_run_config(self):
        return self._run_config

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
        start_time = time.time()
        while self._run_data is None and time.time() - start_time < 10:
            await asyncio.sleep(0.05)
        if self._run_data is None:
            raise RuntimeError('Source is not ready yet')
        return self._run_data.get_metadata()

    def cancel(self):
        self._stop_event.set()
        self._recieve_task.cancel()

    async def recieve_data(self):
        try:
            while not self._pipe.poll():
                await asyncio.sleep(0.05)
            metadata = self._pipe.recv()
            self._run_data = RunData(
                height = metadata['height'],
                width = metadata['width'],
                base_map = np.array(metadata['base_map'], dtype=np.uint8),
                snake_ids = metadata['snake_ids'],
                food_value = metadata['food_value'],
                free_value = metadata['free_value'],
                blocked_value = metadata['blocked_value'],
                color_mapping = {int(k): tuple(v) for k, v in metadata['color_mapping'].items()},
                snake_values = metadata["snake_values"],
            )
            while not self._stop_event.is_set():
                while not self._pipe.poll():
                    await asyncio.sleep(0.05)
                data = self._pipe.recv()
                if data == "stopped":
                    break
                step_data = StepData.from_dict(data)
                self._last_recieved_step = step_data.step
                self._run_data.add_step(step_data)
        except (BrokenPipeError, EOFError, OSError):
            print("Connection to process lost.")
            # print("TRACEBACK", exc_info=True)
        except asyncio.CancelledError:
            print("Recieve task canceled.")
        finally:
            self._is_done = True
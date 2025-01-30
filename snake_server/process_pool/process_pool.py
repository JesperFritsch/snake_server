import logging
import asyncio
from pathlib import Path
from typing import Dict
from concurrent.futures import ProcessPoolExecutor, Future
from multiprocessing import Pipe, Manager
from uuid import uuid4

from snake_sim.loop_observers.ipc_run_data_observer import IPCRunDataObserver
from snake_sim.environment.snake_loop_control import setup_loop
from snake_sim.utils import DotDict

from snake_server.source_manager.stream_source_manager import StreamSourceManager
from snake_server.stream_source.loop_source import AsyncIPCLoopSource
from snake_server.utils import SingletonMeta

log = logging.getLogger(Path(__file__).stem)

# Singleton class to manage running processes
source_manager = StreamSourceManager()

class RunningProcess:
    def __init__(self, run_id: str, future: Future, stop_event):
        self.run_id = run_id
        self.future = future
        self.stop_event = stop_event

    def stop(self):
        self.stop_event.set()

    def is_done(self):
        return self.future.done()

    def check_result(self):
        if self.is_done():
            try:
                self.future.result()
            except Exception as e:
                log.error(f"Error in process with id {self.run_id}: {e}")
                log.debug("TRACEBACK", exc_info=True)


class SnakeProcessPool(metaclass=SingletonMeta):
    def __init__(self):
        self._process_pool = ProcessPoolExecutor()
        self._running_processes: Dict[str, RunningProcess] = {}
        self._monitor_task = None
        self._manager = Manager()

    def start_monitor(self):
        self._monitor_task = asyncio.create_task(self._monitor_processes())

    async def _monitor_processes(self):
        try:
            while True:
                self._check_processes()
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Unexpected error in process monitoring: {e}")

    def _check_processes(self):
        running_processes = self._running_processes.copy()
        for run_id, process in running_processes.items():
            if process.is_done():
                process.check_result()
                self.finish_proc(run_id)

    def start_run(self, config: dict):
        run_id = str(uuid4())
        child_pipe, pipe = Pipe()
        observer = IPCRunDataObserver(child_pipe)
        loop_source = AsyncIPCLoopSource(pipe, config)
        source_manager.add_source(run_id, loop_source)
        loop_control = setup_loop(DotDict(config))
        loop_control.add_run_data_observer(observer)
        self._submit(loop_control.run, run_id)
        return run_id

    def _submit(self, func, run_id: str):
        stop_event = self._manager.Event()
        future = self._process_pool.submit(func, stop_event)
        self._running_processes[run_id] = RunningProcess(run_id, future, stop_event)

    def finish_proc(self, run_id: str):
        if run_id in self._running_processes:
            self._running_processes[run_id].stop()
            del self._running_processes[run_id]
        try:
            source_manager.finish_live_source(run_id, store=False)
        except ValueError:
            log.warning(f"Could not store source with id {run_id}")
        log.debug("Finished process with id:", run_id)

    async def shutdown(self):
        try:
            for run_id in self._running_processes.copy():
                self.finish_proc(run_id)
            source_manager.cleanup()
            self._process_pool.shutdown(wait=True) # wait=True means that the pool will wait for all processes to finish before shutting down
            if self._monitor_task:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            log.error(f"Error shutting down process pool: {e}")
            log.debug("TRACEBACK", exc_info=True)
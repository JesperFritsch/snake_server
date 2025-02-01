import logging
import asyncio
import atexit
import multiprocessing

from configparser import ConfigParser
from importlib import resources
from pathlib import Path
from typing import Dict
from multiprocessing import Pipe
from uuid import uuid4

from snake_sim.loop_observers.ipc_run_data_observer import IPCRunDataObserver
from snake_sim.environment.snake_loop_control import setup_loop
from snake_sim.utils import DotDict

from snake_server.source_manager.stream_source_manager import StreamSourceManager
from snake_server.stream_source.loop_source import AsyncIPCLoopSource
from snake_server.utils import SingletonMeta
from snake_server.logging import setup_loggers


config = ConfigParser()
with open(resources.files('snake_server').joinpath('config.ini')) as config_file:
    config.read_file(config_file)

log = logging.getLogger(Path(__file__).stem)

# Singleton class to manage running processes
source_manager = StreamSourceManager()

def start_snake_run(loop_control, log_level):
    """
    Function to run in a separate process
    we need this intermediate function to reset the singeltons.
    """
    setup_loggers(log_level)
    loop_control.run()


class RunningProcess:
    def __init__(self, run_id: str, process: multiprocessing.Process):
        self.run_id = run_id
        self.process = process

    def stop(self):
        log.debug("Terminating process with id: %s", self.run_id)
        self.process.terminate()
        self.process.join()
        self.check_result()

    def is_done(self):
        return not self.process.is_alive()

    def check_result(self):
        if self.is_done():
            if self.process.exitcode != 0:
                log.error(f"Error in process with id {self.run_id}: Exit code {self.process.exitcode}")
                log.debug("TRACEBACK", exc_info=True)


class SnakeProcessPool(metaclass=SingletonMeta):
    def __init__(self):
        self._running_processes: Dict[str, RunningProcess] = {}
        self._monitor_task = None
        self._manager = multiprocessing.Manager()

        atexit.register(self.shutdown_sync)

    def shutdown_sync(self):
        """Ensures shutdown runs safely even in a sync environment."""
        try:
            asyncio.run(self.shutdown())  # Runs async shutdown safely
        except RuntimeError:
            pass  # Handles cases where the event loop is already closed

    async def start_monitor(self):
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
        loop_control = setup_loop(DotDict(config))
        loop_control.add_run_data_observer(observer)
        loop_source = AsyncIPCLoopSource(pipe, config)
        source_manager.add_source(run_id, loop_source)
        self._submit(start_snake_run, loop_control, run_id)
        return run_id

    def _submit(self, func, loop_control, run_id: str):
        process = multiprocessing.Process(target=func, args=(loop_control, log.level))
        process.start()
        self._running_processes[run_id] = RunningProcess(run_id, process)

    def finish_proc(self, run_id: str):
        if run_id in self._running_processes:
            self._running_processes[run_id].stop()
            del self._running_processes[run_id]
        try:
            store_source = config.getboolean('runs', 'store_runs')
            source_manager.finish_live_source(run_id, store=store_source)
        except ValueError:
            log.warning(f"Could not store source with id {run_id}")
        log.debug("Finished process with id: %s", run_id)

    async def shutdown(self):
        log.debug("Shutting down process pool")
        try:
            for run_id in self._running_processes.copy():
                self.finish_proc(run_id)
            source_manager.cleanup()
            if self._monitor_task:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            log.error(f"Error shutting down process pool: {e}")
            log.debug("TRACEBACK", exc_info=True)
import logging
import asyncio
import multiprocessing as mp
import ctypes


from configparser import ConfigParser
from importlib import resources
from pathlib import Path
from typing import Dict
from multiprocessing import Pipe
from multiprocessing.sharedctypes import Synchronized
from uuid import uuid4

from snake_sim.loop_observers.ipc_repeater_observer import IPCRepeaterObserver
from snake_sim.environment.snake_loop_control import setup_loop
from snake_sim.environment.types import DotDict

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

def start_snake_run(config: DotDict, stop_event: Synchronized, ipc_observer_pipe=None):
    # in linux the process is forked and inherits the loggers, but on windows we need to set it up again
    if not logging.getLogger().hasHandlers():
        setup_loggers(log.level)
    loop_control = setup_loop(config)
    if ipc_observer_pipe:
        loop_control.add_observer(IPCRepeaterObserver(ipc_observer_pipe))
    loop_control.run(stop_event)


class RunningProcess:
    def __init__(self, run_id: str, process: mp.Process, stop_event: Synchronized):
        self.run_id = run_id
        self.process = process
        self.stop_event = stop_event

    def stop(self):
        log.debug("Terminating process with id: %s", self.run_id)
        if self.is_done():
            log.debug("Process with id: %s is already terminated", self.run_id)
            return
        if self.stop_event:
            log.debug("Setting stop event for process with id: %s", self.run_id)
            self.stop_event.value = True
            # Wait for process to finish gracefully
            log.debug("Waiting for process %s to terminate gracefully", self.run_id)
            self.process.join(timeout=5)
            if self.process.is_alive():
                log.warning("Process %s didn't stop gracefully, terminating", self.run_id)
                self.process.terminate()
                self.process.join()
        else:
            log.warning("No stop event found for process with id: %s, sending SIGTERM", self.run_id)
            self.process.terminate()
            self.process.join()
        log.debug("Process with id: %s terminated", self.run_id)

    def cleanup(self):
        """Clean up process resources"""
        # Ensure process is fully terminated and resources are released
        if self.process.is_alive():
            log.warning("Process %s still alive during cleanup, force terminating", self.run_id)
            self.process.terminate()
            self.process.join(timeout=2)
            if self.process.is_alive():
                log.error("Process %s refusing to terminate", self.run_id)
        
        # Clear references to help garbage collection
        self.stop_event = None
        self.process = None

    def is_done(self):
        return not self.process.is_alive()


class SnakeProcessPool(metaclass=SingletonMeta):
    def __init__(self):
        self._running_processes: Dict[str, RunningProcess] = {}
        self._monitor_task = None
        self._shutdown_called = False
        self._mp_ctx = mp.get_context('spawn')

    def shutdown_sync(self):
        """Ensures shutdown runs safely even in a sync environment."""
        log.debug(f"Shutting down process pool (sync)")
        if self._shutdown_called:
            return
        self._shutdown_called = True
        try:
            asyncio.run(self.shutdown())  # Runs async shutdown safely
        except RuntimeError:
            # If no event loop, do synchronous cleanup
            self._sync_shutdown()

    def _sync_shutdown(self):
        """Synchronous shutdown fallback"""
        log.debug("Performing synchronous shutdown")
        for run_id in list(self._running_processes.keys()):
            running_process = self._running_processes[run_id]
            running_process.stop()
            running_process.cleanup()
            del self._running_processes[run_id]

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
                self.finish_proc(run_id)

    def start_run(self, config: DotDict):
        run_id = str(uuid4())
        child_pipe, pipe = Pipe()
        loop_source = AsyncIPCLoopSource(pipe, config)
        config.inproc_snakes = True
        source_manager.add_source(run_id, loop_source)
        self._submit(start_snake_run, config, child_pipe, run_id)
        return run_id

    def _submit(self, func, config, ipc_observer_pipe, run_id: str):
        stop_event = self._mp_ctx.Value(ctypes.c_bool, False)  # Shared boolean value
        process = self._mp_ctx.Process(target=func, args=(config, stop_event, ipc_observer_pipe))
        process.start()
        self._running_processes[run_id] = RunningProcess(run_id, process, stop_event)

    def finish_proc(self, run_id: str):
        log.debug("Finishing process with id: %s", run_id)
        if run_id in self._running_processes:
            running_process = self._running_processes[run_id]
            running_process.stop()
            running_process.cleanup()
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
            # Stop monitor first to prevent new process checks
            if self._monitor_task:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
            
            # Clean up all running processes
            for run_id in list(self._running_processes.keys()):
                self.finish_proc(run_id)
            
            source_manager.cleanup()
            
        except Exception as e:
            log.error(f"Error shutting down process pool: {e}")
            log.debug("TRACEBACK", exc_info=True)
            raise e
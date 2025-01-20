import uuid
import asyncio
import time
from typing import Optional, Dict
from concurrent.futures import ProcessPoolExecutor, Future
from multiprocessing import Pipe

from snake_sim.main import start_stream_run
from snake_sim.utils import DotDict
from snake_sim.snake_env import StepData

MAX_STREAMS = 5


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class RunningProcess:
    def __init__(self, stream_id: str, future: Future):
        self.stream_id = stream_id
        self.future = future

    def cancel(self):
        self.future.cancel()

    def is_done(self):
        return self.future.done()


class MultiStreamManager(metaclass=SingletonMeta):
    def __init__(self):
        self.process_pool = ProcessPoolExecutor(max_workers=MAX_STREAMS) # None means use all available cores, which is the default just put it here for a reminder
        self.running_processes = {}
        self.step_buffers = {} # the buffers will contain the steps from the simulation
        self.run_configs = {}
        self.run_meta_datas = {}
        self.ready_events: Dict[str, asyncio.Event] = {}

    def can_start_new_stream(self):
        return len(self.running_processes) < MAX_STREAMS

    def is_running(self, stream_id: str):
        return stream_id in self.running_processes

    async def wait_for_ready(self, stream_id: uuid.UUID, timeout: Optional[float] = None):
        if stream_id in self.ready_events:
            event = self.ready_events[stream_id]
            try:
                await asyncio.wait_for(event.wait(), timeout=timeout)
                return True
            except asyncio.TimeoutError:
                return False
        return False

    def cleanup(self):
        try:
            for stream_proc in self.running_processes.values():
                stream_proc.cancel()
            self.process_pool.shutdown()
        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            pass

    def stop_stream(self, stream_id: str):
        if stream_id in self.running_processes:
            process = self.running_processes[stream_id]
            process.cancel()
            del self.running_processes[stream_id]
            del self.step_buffers[stream_id]
            del self.run_configs[stream_id]
            del self.run_meta_datas[stream_id]
            del self.ready_events[stream_id]
            return True
        return False

    def get_current_run_info(self, stream_id: Optional[str] = None):
        if stream_id:
            streams = [stream_id]
        else:
            streams = self.step_buffers.keys()
        data = {}
        for streamid in streams:
            data[streamid] = {
                "steps": len(self.step_buffers[streamid]),
                "config": self.run_configs[streamid]
            }
        return data

    def get_meta_data(self, stream_id: str):
        return self.run_meta_datas.get(stream_id)

    def get_step_buffer(self, stream_id: str):
        return self.step_buffers.get(stream_id)

    def start_stream(self, config: DotDict):
        if self.can_start_new_stream():
            stream_id = str(uuid.uuid4())
            self.ready_events[stream_id] = asyncio.Event()
            asyncio.create_task(self._start_stream(stream_id, config))
            return stream_id
        return None

    async def _start_stream(self, stream_id: str, config: DotDict):
        self.step_buffers[stream_id] = []
        pipe_conn, pipe_conn_other = Pipe()
        future = self.process_pool.submit(start_stream_run, pipe_conn_other, config)
        process = RunningProcess(stream_id, future)
        self.running_processes[stream_id] = process
        self.run_configs[stream_id] = config
        while not pipe_conn.poll():
            await asyncio.sleep(0.05)
        init_data = pipe_conn.recv()
        self.run_meta_datas[stream_id] = init_data
        self.ready_events[stream_id].set()
        while True:
            start_time = time.time()
            while pipe_conn.poll() and time.time() - start_time < 0.05:
                data = pipe_conn.recv()
                if isinstance(data, str):
                    break
                step_obj = StepData.from_dict(data)
                self.step_buffers[stream_id].append(step_obj)
            await asyncio.sleep(0.05)
            if process.is_done():
                break
        self.stop_stream(stream_id)
        pipe_conn.close()

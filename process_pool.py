import uuid
import asyncio
import time
from typing import Optional
from concurrent.futures import ProcessPoolExecutor, Future
from multiprocessing import Pipe

from snake_sim.main import start_stream_run
from snake_sim.utils import DotDict


MAX_STREAMS = 5


class RunningProcess:
    def __init__(self, stream_id: str, future: Future):
        self.stream_id = stream_id
        self.future = future

    def cancel(self):
        self.future.cancel()

    def is_done(self):
        return self.future.done()


class MultiStreamManager:
    def __init__(self):
        self.process_pool = ProcessPoolExecutor(max_workers=MAX_STREAMS) # None means use all available cores, which is the default just put it here for a reminder
        self.running_processes = {}
        self.stream_buffers = {} # the buffers will contain the steps from the simulation
        self.run_configs = {}
        self.run_init_data = {}

    def can_start_new_stream(self):
        return len(self.running_processes) < MAX_STREAMS

    def stop_stream(self, stream_id: uuid.UUID):
        if stream_id in self.running_processes:
            process = self.running_processes[stream_id]
            process.cancel()
            del self.running_processes[stream_id]
            del self.stream_buffers[stream_id]
            del self.run_configs[stream_id]
            del self.run_init_data[stream_id]
            return True
        return False

    def get_current_run_data(self, stream_id: Optional[str] = None):
        if stream_id:
            streams = [stream_id]
        else:
            streams = self.stream_buffers.keys()
        data = {}
        for streamid in streams:
            data[streamid] = {
                "steps": len(self.stream_buffers[streamid]),
                "config": self.run_configs[streamid]
            }
        return data

    def get_stream_init_data(self, stream_id: str):
        return self.run_init_data.get(stream_id)

    def start_stream(self, config: DotDict):
        if self.can_start_new_stream():
            stream_id = str(uuid.uuid4())
            asyncio.create_task(self._start_stream(stream_id, config))
            return stream_id
        return None

    async def _start_stream(self, stream_id: str, config: DotDict):
        self.stream_buffers[stream_id] = []
        pipe_conn, pipe_conn_other = Pipe()
        future = self.process_pool.submit(start_stream_run, pipe_conn_other, config)
        process = RunningProcess(stream_id, future)
        self.running_processes[stream_id] = process
        self.run_configs[stream_id] = config
        while not pipe_conn.poll():
            await asyncio.sleep(0.05)
        init_data = pipe_conn.recv()
        self.run_init_data[stream_id] = init_data
        while True:
            start_time = time.time()
            while pipe_conn.poll() and time.time() - start_time < 0.05:
                data = pipe_conn.recv()
                # print("Data received:", data)
                self.stream_buffers[stream_id].append(data)
            await asyncio.sleep(0.05)
            if process.is_done():
                break
        self.stop_stream(stream_id)
        pipe_conn.close()


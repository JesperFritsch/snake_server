
import asyncio
from collections import deque
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

import logging

log = logging.getLogger(__name__)

class DataStreamHandler:
    def __init__(self, websocket: WebSocket, data_mode: str, on_demand: bool):
        self.data_mode = data_mode
        self.websocket = websocket
        self.on_demand = on_demand
        self.data_end = False
        self.changes_to_send = 0
        self.yield_time = 0.05
        self.data_buffer = deque()
        self.init_data = {}

    def set_init_data(self, data):
        self.init_data = data

    def push_data(self, data):
        self.data_buffer.append(data)

    async def handler(self):
        try:
            while not self.data_end or len(self.data_buffer) > 0:
                if self.on_demand:
                    try:
                        req = await asyncio.wait_for(self.websocket.receive_text(), timeout=self.yield_time)
                        get, nr = req.split(' ')
                        nr_changes = int(nr)
                        log.debug(f"Requested {nr_changes} changes")
                        log.debug(f"Changes buffer size: {len(self.data_buffer)}")
                        self.changes_to_send += nr_changes
                        log.debug(f"Changes to send: {self.changes_to_send}")
                    except asyncio.TimeoutError:
                        pass
                else:
                    self.changes_to_send = len(self.data_buffer)
                    await asyncio.sleep(self.yield_time)
                count = 0
                while count < self.changes_to_send:
                    count += 1
                    if len(self.data_buffer) > 0:
                        data = self.data_buffer.popleft()
                        if self.data_mode == 'steps':
                            await self.websocket.send_json(data)
                        elif self.data_mode == 'pixel_data':
                            await self.websocket.send_bytes(data)
                        self.changes_to_send -= 1
        except WebSocketDisconnect:
            raise
        except Exception as e:
            log.error(e)
            return

async def nonblock_exec(func, *args):
    return await asyncio.to_thread(func, *args)
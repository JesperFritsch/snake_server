
import asyncio
import logging
from collections import deque
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from process_pool import MultiStreamManager

from snake_sim.render.core import FrameBuilder
from snake_sim.snake_env import StepData, RunData
from snake_sim.protobuf.python.sim_msgs_pb2 import MsgWrapper, PixelChanges, RunMetaData, MessageType

log = logging.getLogger(__name__)

stream_manager = MultiStreamManager()

class DataStreamHandler:
    def __init__(self, websocket: WebSocket, data_mode: str, on_demand: bool, stream_id: str):
        self.data_mode = data_mode
        self.stream_id = stream_id
        self.websocket = websocket
        self.on_demand = on_demand
        self.step_buffer = stream_manager.step_buffers.get(stream_id, None)
        self.data_end = False
        self.steps_sent = 0
        self.steps_requested = 0
        self.range_requested = {}
        self.yield_time = 0.05
        self.init_data = {}
        self.frame_builder = None

    def set_init_data(self, data):
        self.init_data = data

    def init_frame_builder(self):
        meta_data = stream_manager.run_meta_datas.get(self.stream_id)
        self.frame_builder = FrameBuilder(run_meta_data=meta_data, expand_factor=2, offset=(1, 1))

    def parse_request(self, req: dict):
        mode = req.get('mode')
        if mode == 'sequential':
            nr = req.get('nr')
            nr_steps = int(nr)
            log.debug(f"Requested {nr_steps} steps")
            self.steps_requested = nr_steps
            log.debug(f"Steps to send: {self.steps_requested}")
        elif mode == 'indexed':
            start, end = map(int, req.get('range').split('-'))
            if end < start:
                log.debug(f"Invalid range: {start}-{end} - end is smaller than start")
                return
            log.debug(f"Requested range: {start}-{end}")
            self.range_requested = {'start': start, 'end': end}

    def create_proto_msgs(self, step_data):
        msgs = []
        if self.data_mode == 'steps':
            step_proto = step_data.to_protobuf()
            wrapper_msg = MsgWrapper(
                type=MessageType.STEP_DATA,
                payload=step_proto.SerializeToString()
            )
            msgs.append(wrapper_msg)
        elif self.data_mode == 'pixel_data':
            changes = self.frame_builder.step_to_pixel_changes(step_data.to_dict())
            msgs = []
            for change in changes:
                payload = PixelChanges()
                for (x, y), color in change:
                    pixel = payload.pixels.add()
                    pixel.coord.x = x
                    pixel.coord.y = y
                    pixel.color.r = color[0]
                    pixel.color.g = color[1]
                    pixel.color.b = color[2]
                wrapper_msg = MsgWrapper(
                    type=MessageType.PIXEL_CHANGES,
                    payload=payload.SerializeToString()
                )
                msgs.append(wrapper_msg)
        return msgs

    def create_meta_data_proto(self):
        run_meta_data = stream_manager.get_meta_data(self.stream_id)
        print(run_meta_data)
        if not run_meta_data:
            log.error(f"Run metadata not found for stream: {self.stream_id}")
            return
        run_meta_data['steps'] = {}
        run_data = RunData.from_dict(run_meta_data)
        run_data_proto = run_data.to_protobuf()
        run_meta_data_proto = run_data_proto.run_meta_data
        return run_meta_data_proto

    async def handler(self):
        if self.data_mode == 'pixel_data':
            self.init_frame_builder()
        run_meta_data_proto = self.create_meta_data_proto()
        wrapper_msg = MsgWrapper(
            type=MessageType.RUN_META_DATA,
            payload=run_meta_data_proto.SerializeToString()
        )
        # Send the run metadata as the first message
        await self.websocket.send_bytes(wrapper_msg.SerializeToString())

        try:
            while not self.data_end:
                if self.on_demand:
                    try:
                        req = await asyncio.wait_for(self.websocket.receive_json(), timeout=self.yield_time)
                        self.parse_request(req)
                    except asyncio.TimeoutError:
                        pass
                else:
                    self.steps_requested = len(self.step_buffer)
                    await asyncio.sleep(self.yield_time)
                while self.steps_requested or self.range_requested:
                    if self.steps_requested:
                        next_step = self.steps_sent + 1
                        if next_step < len(self.step_buffer):
                            step_data: StepData = self.step_buffer[next_step]
                            messages = self.create_proto_msgs(step_data)
                            for msg in messages:
                                await self.websocket.send_bytes(msg.SerializeToString())
                            self.steps_requested -= 1
                            self.steps_sent = next_step
                        elif not self.data_end:
                            await asyncio.sleep(self.yield_time)
                    elif self.range_requested:
                        start = self.range_requested.get('start')
                        end = self.range_requested.get('end')
                        start, end = map(lambda x: min(max(x, 0), (len(self.step_buffer))), (start, end))
                        for i in range(start, end):
                            step_data = self.step_buffer[i]
                            messages = self.create_proto_msgs(step_data)
                            for msg in messages:
                                await self.websocket.send_bytes(msg.SerializeToString())
                        self.range_requested = {}

        except Exception as e:
            log.error(e)
            log.debug("TRACEBACK", exc_info=True)
            return

import asyncio
import logging

from typing import Deque, List, Optional, Union
from collections import deque
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

from process_pool import MultiStreamManager
from snake_sim.render.core import FrameBuilder
from snake_sim.snake_env import StepData, RunData
from snake_sim.protobuf.sim_msgs_pb2 import (
    MsgWrapper,
    PixelChanges,
    RunMetaData,
    MessageType,
    Request,
    RequestType,
    RequestAck,
    StepData as proto_step_data,
    StepDataRequest,
    PixelChangesRequest,
    RunMetaDataRequest
    )

log = logging.getLogger(__name__)

stream_manager = MultiStreamManager()


def create_pixel_change_proto_msg(change, full_state: Optional[bool] = False) -> MsgWrapper:
    payload = PixelChanges()
    payload.full_state = full_state
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
    return wrapper_msg


class DataStreamHandler:
    def __init__(self, websocket: WebSocket, stream_id: str):
        self.stream_id = stream_id
        self.websocket = websocket
        self.step_buffer: List[StepData] = stream_manager.step_buffers.get(stream_id, None)
        self.yield_time = 0.01
        self.frame_builder = None
        self.init_frame_builder()
        self.unhandled_requests: Deque[Request] = deque()
        self.msg_out_buffer: Deque[Message] = deque()
        self.sub_tasks = set()

    async def async_ws_wrapper(self, coroutine, *args, **kwargs):
        try:
            return await coroutine(*args, **kwargs)
        except WebSocketDisconnect:
            log.error(f"Websocket disconnected for stream: {self.stream_id}")
            await self.cancel()
            raise
        except Exception as e:
            log.error(e)
            log.debug("TRACEBACK", exc_info=True)
            raise e

    def init_frame_builder(self):
        meta_data = stream_manager.run_meta_datas.get(self.stream_id)
        self.frame_builder = FrameBuilder(run_meta_data=meta_data, expand_factor=2, offset=(1, 1))

    def split_request(self, req: Request):
        # Split the request into two requests, one for the last available step and one for the rest
        req_type = req.type
        req_payload = req.payload
        if req_type == RequestType.STEP_DATA_REQ:
            orig_req = StepDataRequest()
            orig_req.ParseFromString(req_payload)
            new_req_payload = StepDataRequest()
        elif req_type == RequestType.PIXEL_CHANGES_REQ:
            orig_req = PixelChangesRequest()
            orig_req.ParseFromString(req_payload)
            new_req_payload = PixelChangesRequest()
        new_req_payload.CopyFrom(orig_req)
        last_available_step = self.get_last_available_step()
        orig_req.end_step = last_available_step
        new_req_payload.start_step = last_available_step + 1
        self.unhandled_requests.append(new_req_payload)
        return orig_req

    def get_last_available_step(self):
        return self.step_buffer[-1].step

    def check_last_step(self, step_nr: int):
        return step_nr == self.step_buffer[-1].step and not stream_manager.is_running(self.stream_id)

    def handle_pixel_changes_request(self, req: PixelChangesRequest):
        if req.end_step > self.step_buffer[-1].step:
            # if the full request is not available, split it into two requests, handle the other one later
            req = self.split_request(req)
        start_step = max(0, req.start_step)
        end_step = req.end_step
        if end_step < start_step:
            raise ValueError(f"End step '{end_step}' should be greater than start step '{start_step}'")
        steps = self.step_buffer[start_step-1:end_step]
        if self.frame_builder.last_handled_step != start_step - 1:
            full_state_change = self.frame_builder.full_step_to_pixel_data(self.step_buffer[start_step - 1].to_dict(full_state=True))
            msg = create_pixel_change_proto_msg(full_state_change, full_state=True)
            self.add_msg_to_buffer(msg)
            steps = steps[1:]
        for step in steps:
            changes = self.frame_builder.step_to_pixel_changes(step.to_dict())
            for change in changes:
                msg = create_pixel_change_proto_msg(change)
                self.add_msg_to_buffer(msg)

    def handle_step_data_request(self, req: StepDataRequest):
        if req.end_step > self.step_buffer[-1].step:
            # if the full request is not available, split it into two requests, handle the other one later
            req = self.split_request(req)
        start_step = max(0, req.start_step)
        end_step = req.end_step
        if end_step < start_step:
            raise ValueError(f"End step '{end_step}' should be greater than start step '{start_step}'")
        steps = self.step_buffer[start_step-1:end_step]
        for step in steps:
            step_proto = step.to_protobuf(req.full_state)
            wrapper_msg = MsgWrapper(
                type=MessageType.STEP_DATA,
                payload=step_proto.SerializeToString()
            )
            self.add_msg_to_buffer(wrapper_msg)

    def handle_run_meta_data_request(self):
        log.debug(f"Handling run metadata request for stream: {self.stream_id}")
        run_meta_data = stream_manager.get_meta_data(self.stream_id)
        if not run_meta_data:
            log.error(f"Run metadata not found for stream: {self.stream_id}")
            return
        run_meta_data['steps'] = {}
        run_data = RunData.from_dict(run_meta_data)
        run_data_proto = run_data.to_protobuf()
        run_meta_data_proto = run_data_proto.run_meta_data
        wrapper_msg = MsgWrapper(
            type=MessageType.RUN_META_DATA,
            payload=run_meta_data_proto.SerializeToString()
        )
        self.add_msg_to_buffer(wrapper_msg)

    def process_request(self, req: Union[StepDataRequest, PixelChangesRequest, RunMetaDataRequest]):
        log.debug(f"Processing request: {MessageToDict(req)}")
        try:
            ack = RequestAck()
            if isinstance(req, StepDataRequest):
                self.handle_step_data_request(req)
                ack.type = RequestType.STEP_DATA_REQ
            elif isinstance(req, PixelChangesRequest):
                self.handle_pixel_changes_request(req)
                ack.type = RequestType.PIXEL_CHANGES_REQ
            elif isinstance(req, RunMetaDataRequest):
                self.handle_run_meta_data_request()
            else:
                log.error(f"Unknown request: {req}")
            ack.payload = req.SerializeToString()
            # self.add_msg_to_buffer(ack, priority=True)
        except ValueError as e:
            log.error(e)
            log.debug("TRACEBACK", exc_info=True)

    def recieve_request(self, req: Request):
        req_obj = Request()
        req_obj.ParseFromString(req)
        req_type = req_obj.type
        req_payload = req_obj.payload
        if req_type == RequestType.STEP_DATA_REQ:
            step_req = StepDataRequest()
            step_req.ParseFromString(req_payload)
            self.unhandled_requests.append(step_req)
        elif req_type == RequestType.PIXEL_CHANGES_REQ:
            pixel_req = PixelChangesRequest()
            pixel_req.ParseFromString(req_payload)
            self.unhandled_requests.append(pixel_req)
        elif req_type == RequestType.RUN_META_DATA_REQ:
            meta_req = RunMetaDataRequest()
            meta_req.ParseFromString(req_payload)
            self.unhandled_requests.append(meta_req)
        else:
            log.error(f"Unknown request type: {req_type}")
        log.debug(f"Request received: {req_obj}")

    def add_msg_to_buffer(self, msg: Message, priority: bool = False):
        if priority:
            self.msg_out_buffer.appendleft(msg)
        else:
            self.msg_out_buffer.append(msg)

    async def _request_listener(self):
        while True:
            if not self.websocket.client_state == WebSocketState.CONNECTED:
                break
            try:
                req = await asyncio.wait_for(self.websocket.receive_bytes(), timeout=self.yield_time)
                if req == b'ping':
                    continue
                self.recieve_request(req)
            except asyncio.TimeoutError:
                if not self.websocket.client_state == WebSocketState.CONNECTED:
                    break
            except asyncio.CancelledError:
                break

    async def request_listener(self):
        await self.async_ws_wrapper(self._request_listener)

    async def _msg_pusher(self):
        while True:
            try:
                if self.msg_out_buffer:
                    msg = self.msg_out_buffer.popleft()
                    await self.websocket.send_bytes(msg.SerializeToString())
                else:
                    await asyncio.sleep(self.yield_time)
            except asyncio.CancelledError:
                break

    async def msg_pusher(self):
        await self.async_ws_wrapper(self._msg_pusher)

    async def _request_handler(self):
        while True:
            try:
                if self.unhandled_requests:
                    req = self.unhandled_requests.popleft()
                    self.process_request(req)
                else:
                    await asyncio.sleep(self.yield_time)
            except asyncio.CancelledError:
                break

    async def _heartbeat(self):
        while True:
            try:
                await self.websocket.send_text('ping')
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break

    async def heartbeat(self):
        await self.async_ws_wrapper(self._heartbeat)

    async def request_handler(self):
        await self.async_ws_wrapper(self._request_handler)

    async def cancel(self):
        log.debug("DataStreamHandler task cancelled")
        for task in self.sub_tasks:
            if not task.done():
                try:
                    task.cancel()
                    await task
                except asyncio.CancelledError:
                    pass
        self.sub_tasks.clear()

    async def start(self):
        try:
            self.sub_tasks.add(asyncio.create_task(self.request_listener()))
            self.sub_tasks.add(asyncio.create_task(self.request_handler()))
            self.sub_tasks.add(asyncio.create_task(self.msg_pusher()))
            self.sub_tasks.add(asyncio.create_task(self.heartbeat()))
            await asyncio.gather(*self.sub_tasks)
        finally:
            await self.cancel()



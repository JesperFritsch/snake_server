
import asyncio
import logging

from typing import Deque, List, Optional, Union
from collections import deque
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

from snake_server.stream_source.interfaces.stream_source_interface import IStreamSource
from snake_sim.run_data.run_data import StepData, RunData

from snake_sim.render.core import FrameBuilder
from snake_sim.protobuf.sim_msgs_pb2 import (
    MsgWrapper,
    PixelChanges,
    RunMetaData,
    MessageType,
    Request,
    RequestType,
    StepData as proto_step_data,
    StepDataReq,
    FullStepDataReq,
    PixelChangesReq,
    FullPixelChangesReq,
    RunMetaDataRequest,
    BadRequest,
    RunUpdate
    )

log = logging.getLogger(__name__)


def wrap_message(message) -> MsgWrapper:
    if isinstance(message, RunMetaData):
        msg_type = MessageType.RUN_META_DATA
    elif isinstance(message, proto_step_data):
        msg_type = MessageType.STEP_DATA
    elif isinstance(message, (PixelChanges, FullPixelChangesReq)):
        msg_type = MessageType.PIXEL_CHANGES
    elif isinstance(message, RunUpdate):
        msg_type = MessageType.RUN_UPDATE
    elif isinstance(message, BadRequest):
        msg_type = MessageType.BAD_REQUEST
    else:
        raise ValueError(f"Unknown message type: {message}")
    wrapper_msg = MsgWrapper(
        type=msg_type,
        payload=message.SerializeToString()
    )
    return wrapper_msg


def unwrap_request(req: Request) -> Union[StepDataReq, PixelChangesReq, RunMetaDataRequest, FullStepDataReq, FullPixelChangesReq]:
    if req.type == RequestType.STEP_DATA_REQ:
        request = StepDataReq()
    elif req.type == RequestType.PIXEL_CHANGES_REQ:
        request = PixelChangesReq()
    elif req.type == RequestType.RUN_META_DATA_REQ:
        request = RunMetaDataRequest()
    elif req.type == RequestType.FULL_STEP_DATA_REQ:
        request = FullStepDataReq()
    elif req.type == RequestType.FULL_PIXEL_CHANGES_REQ:
        request = FullPixelChangesReq()
    else:
        raise ValueError(f"Unknown request type: {req.type}")
    request.ParseFromString(req.payload)
    return request


def create_pixel_change_proto_msg(change, full_state: Optional[bool] = False) -> PixelChanges:
    payload = PixelChanges()
    payload.full_state = full_state
    for (x, y), color in change:
        pixel = payload.pixels.add()
        pixel.coord.x = x
        pixel.coord.y = y
        pixel.color.r = color[0]
        pixel.color.g = color[1]
        pixel.color.b = color[2]
    return payload


class DataStreamHandler:
    def __init__(self, websocket: WebSocket, stream_source: IStreamSource, run_id: str):
        self.stream_id = run_id
        self.websocket = websocket
        self._stream_source = stream_source
        self._yield_time = 0.01
        self._frame_builder = None
        self.init_frame_builder()
        self._unhandled_requests: Deque[Request] = deque()
        self._msg_out_buffer: Deque[Message] = deque()
        self.sub_tasks = set()

    def add_request(self, req: Request):
        self._unhandled_requests.append(req)

    async def async_ws_wrapper(self, coroutine, *args, **kwargs):
        try:
            return await coroutine(*args, **kwargs)
        except WebSocketDisconnect:
            log.error(f"Websocket disconnected for stream: {self.websocket}")
            await self.cancel()
            raise
        except Exception as e:
            log.error(e)
            log.debug("TRACEBACK", exc_info=True)
            raise e

    def init_frame_builder(self):
        try:
            meta_data = self._stream_source.get_meta_data()
        except RuntimeError as e:
            log.error(e)
            return
        self._frame_builder = FrameBuilder(run_meta_data=meta_data, expand_factor=2, offset=(1, 1))

    def metadata_to_proto(self, meta_data: dict) -> RunMetaData:
        # If we add an empty dict to the steps key, we can convert the dict to a RunData object
        # and just use the metadata part of the object
        meta_data['steps'] = {}
        run_data = RunData.from_dict(meta_data)
        meta_proto = run_data.to_protobuf()
        return meta_proto.run_meta_data

    def split_request(self, req: Request):
        # Split the request into two requests, one for the last available step and one for the rest
        req_type = req.type
        req_payload = req.payload
        if req_type == RequestType.STEP_DATA_REQ:
            orig_req = StepDataReq()
            orig_req.ParseFromString(req_payload)
            new_req_payload = StepDataReq()
        elif req_type == RequestType.PIXEL_CHANGES_REQ:
            orig_req = PixelChangesReq()
            orig_req.ParseFromString(req_payload)
            new_req_payload = PixelChangesReq()
        new_req_payload.CopyFrom(orig_req)
        last_available_step = self.get_last_available_step()
        orig_req.end_step = last_available_step
        new_req_payload.start_step = last_available_step + 1
        self.add_request(new_req_payload)
        return orig_req

    def get_last_available_step(self):
        return self._stream_source.las_available_step()

    def is_valid_request(self, req: Union[StepDataReq, PixelChangesReq]):
        if req.start_step < 0:
            raise ValueError(f"Start step '{req.start_step}' should be greater than 0")
        if req.end_step < 0:
            raise ValueError(f"End step '{req.end_step}' should be greater than 0")

    def bad_request(self, req: Request, error: str):
        bad_req = BadRequest()
        bad_req.error = error
        bad_req.type = req.type
        wrapped_msg = wrap_message(bad_req)
        self.add_msg_to_buffer(wrapped_msg, priority=True)

    def last_step_update(self):
        last_step = self.get_last_available_step()
        update = RunUpdate()
        update.last_step = last_step
        self.add_msg_to_buffer(update, priority=True)

    def request_out_of_bounds(self, req: Union[StepDataReq, PixelChangesReq, FullStepDataReq, FullPixelChangesReq]):
        if isinstance(req, (FullStepDataReq, FullPixelChangesReq)):
            bound_step = req.step
        elif isinstance(req, (StepDataReq, PixelChangesReq)):
            bound_step = req.end_step
        else:
            raise ValueError(f"Unknown request type: {req}")
        if bound_step > self.get_last_available_step():
            if self._stream_source.is_done():
                self.last_step_update()
            return True
        return False

    def handle_full_pixel_changes_request(self, req: FullPixelChangesReq):
        full_step = self._stream_source.get_full_step(req.step)
        full_state_change = self._frame_builder.full_step_to_pixel_data(full_step.to_dict(full_state=True))
        msg = create_pixel_change_proto_msg(full_state_change, full_state=True)
        self.add_msg_to_buffer(msg)

    def handle_pixel_changes_request(self, req: PixelChangesReq):
        if self.request_out_of_bounds(req):
            req = self.split_request(req)
        start_step = max(0, req.start_step)
        end_step = req.end_step
        steps = self._stream_source.get_step_range(start=start_step, end=end_step)
        for step in steps:
            changes = self._frame_builder.step_to_pixel_changes(step.to_dict())
            for change in changes:
                msg = create_pixel_change_proto_msg(change)
                self.add_msg_to_buffer(msg)

    def handle_full_step_data_request(self, req: FullStepDataReq):
        full_step = self._stream_source.get_full_step(req.step)
        full_step_proto = full_step.to_protobuf(full_state=True)
        wrapper_msg = wrap_message(full_step_proto)
        self.add_msg_to_buffer(wrapper_msg)

    def handle_step_data_request(self, req: StepDataReq):
        if self.request_out_of_bounds(req):
            req = self.split_request(req)
        start_step = max(0, req.start_step)
        end_step = req.end_step
        steps = self._stream_source.get_step_range(start=start_step, end=end_step)
        for step in steps:
            step_proto = step.to_protobuf(full_state=False)
            wrapper_msg = wrap_message(step_proto)
            self.add_msg_to_buffer(wrapper_msg)

    def handle_run_meta_data_request(self):
        try:
            run_meta_data = self._stream_source.get_meta_data()
        except RuntimeError as e:
            log.error(e)
            return
        run_meta_data['steps'] = {}
        run_data = RunData.from_dict(run_meta_data)
        run_data_proto = run_data.to_protobuf()
        run_meta_data_proto = run_data_proto.run_meta_data
        wrapper_msg = wrap_message(run_meta_data_proto)
        self.add_msg_to_buffer(wrapper_msg)

    def process_request(self, req: Union[StepDataReq, PixelChangesReq, RunMetaDataRequest]):
        try:
            if isinstance(req, StepDataReq):
                self.handle_step_data_request(req)
            elif isinstance(req, PixelChangesReq):
                self.handle_pixel_changes_request(req)
            elif isinstance(req, RunMetaDataRequest):
                self.handle_run_meta_data_request()
            else:
                log.error(f"Unknown request: {req}")
        except ValueError as e:
            log.error(e)
            log.debug("TRACEBACK", exc_info=True)

    def recieve_request(self, req: Request):
        req_wrapper = Request()
        req_wrapper.ParseFromString(req)
        try:
            req_obj = unwrap_request(req_wrapper)
            if isinstance(req_obj, (StepDataReq, PixelChangesReq)):
                try:
                    self.is_valid_request(req_obj)
                except Exception as e:
                    self.bad_request(req_obj, str(e))
                    return
            self.add_request(req_obj)
        except ValueError as e:
            log.error(e)
            log.debug("TRACEBACK", exc_info=True)
            return

    def add_msg_to_buffer(self, msg: Message, priority: bool = False):
        if priority:
            self._msg_out_buffer.appendleft(msg)
        else:
            self._msg_out_buffer.append(msg)

    async def _request_listener(self):
        while True:
            try:
                req = await asyncio.wait_for(self.websocket.receive_bytes(), timeout=self._yield_time)
                if req == b'ping':
                    continue
                self.recieve_request(req)
            except asyncio.TimeoutError:
                if (not self.websocket.client_state == WebSocketState.CONNECTED and
                    self.websocket.application_state == WebSocketState.CONNECTED):
                    break
            except asyncio.CancelledError:
                break

    async def request_listener(self):
        await self.async_ws_wrapper(self._request_listener)

    async def _msg_pusher(self):
        while True:
            try:
                if self._msg_out_buffer:
                    msg = self._msg_out_buffer.popleft()
                    await self.websocket.send_bytes(msg.SerializeToString())
                else:
                    await asyncio.sleep(self._yield_time)
            except asyncio.CancelledError:
                break

    async def msg_pusher(self):
        await self.async_ws_wrapper(self._msg_pusher)

    async def _request_handler(self):
        while True:
            try:
                if self._unhandled_requests:
                    req = self._unhandled_requests.popleft()
                    self.process_request(req)
                else:
                    await asyncio.sleep(self._yield_time)
            except asyncio.CancelledError:
                break

    async def _heartbeat(self):
        while True:
            try:
                await self.websocket.send_text('p')
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break

    async def heartbeat(self):
        await self.async_ws_wrapper(self._heartbeat)

    async def request_handler(self):
        await self.async_ws_wrapper(self._request_handler)

    async def cancel(self):
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
            await asyncio.gather(*self.sub_tasks, return_exceptions=True)
        finally:
            await self.cancel()



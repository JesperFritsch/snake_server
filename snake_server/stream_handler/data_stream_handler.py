
import asyncio
import logging

from typing import Deque, List, Set, Optional, Union
from collections import deque
from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from dataclasses import dataclass

from snake_server.stream_source.interfaces.stream_source_interface import IStreamSource
from snake_server.stream_handler.proto_conversion import (
    env_meta_data_to_proto,
    create_pixel_change_proto_msg
)
from snake_server.stream_handler.data_processing import get_diffs, make_color_changes
 
from snake_sim.render.utils import create_color_map

from snake_proto_template.python.sim_msgs_pb2 import (
    MsgWrapper,
    PixelChanges,
    StepPixelChanges,
    RunMetaData,
    MessageType,
    Request,
    RequestType,
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
    elif isinstance(message, StepPixelChanges):
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


def unwrap_request(req: Request) -> Union[PixelChangesReq, RunMetaDataRequest, FullPixelChangesReq]:
    if req.type == RequestType.PIXEL_CHANGES_REQ:
        request = PixelChangesReq()
    elif req.type == RequestType.RUN_META_DATA_REQ:
        request = RunMetaDataRequest()
    elif req.type == RequestType.FULL_PIXEL_CHANGES_REQ:
        request = FullPixelChangesReq()
    else:
        raise ValueError(f"Unknown request type: {req.type}")
    request.ParseFromString(req.payload)
    return request


@dataclass(frozen=True)
class WaitingRequest:
    req: Union[PixelChangesReq, FullPixelChangesReq]
    start_step: int


class DataStreamHandler:
    def __init__(self, websocket: WebSocket, stream_source: IStreamSource, run_id: str):
        self.stream_id = run_id
        self.websocket = websocket
        self._stream_source = stream_source
        self._yield_time = 0.005
        self._unhandled_requests: Deque[Request] = deque()
        self._waiting_requests: List[WaitingRequest] = []
        self._msg_out_buffer: Deque[Message] = deque()
        self.sub_tasks = set()
        self._color_mapping: dict = None

    def add_request(
            self,
            req: Union[
                PixelChangesReq,
                RunMetaDataRequest,
                FullPixelChangesReq
            ]
        ):
        self._unhandled_requests.append(req)

    def add_waiting_request(self, start_step: int, req: Union[PixelChangesReq, FullPixelChangesReq]):
        if self._stream_source.is_done() and start_step > self.get_last_available_step():
            return
        self._waiting_requests.append(WaitingRequest(req=req, start_step=start_step))

    async def async_ws_wrapper(self, coroutine, *args, **kwargs):
        if getattr(self, "_is_canceling", False):
            return
        try:
            return await coroutine(*args, **kwargs)
        except WebSocketDisconnect:
            log.debug(f"Websocket disconnected for stream: {self.stream_id}")
            if not getattr(self, "_is_canceling", False):
                await self.cancel()
        except Exception as e:
            log.error(e)
            log.debug("TRACEBACK", exc_info=True)
            if not getattr(self, "_is_canceling", False):
                await self.cancel()

    def split_request(self, req: Union[PixelChangesReq]):
        # Split the request into two requests, one for the last available step and one for the rest
        last_available_step = self.get_last_available_step()
        if req.start_step > last_available_step:
            self.add_waiting_request(req.start_step, req)
            return None
        new_req_payload = req.__class__()
        new_req_payload.CopyFrom(req)
        req.end_step = last_available_step
        new_req_payload.start_step = last_available_step + 1
        self.add_waiting_request(new_req_payload.start_step, new_req_payload)
        return req

    def get_last_available_step(self):
        return self._stream_source.last_available_step()

    def is_valid_request(self, req: Union[PixelChangesReq]):
        if req.start_step < 0:
            raise ValueError(f"Start step '{req.start_step}' should be greater than 0")
        if req.end_step < 0:
            raise ValueError(f"End step '{req.end_step}' should be greater than 0")
        if req.end_step < req.start_step:
            raise ValueError(f"End step '{req.end_step}' should be greater than start step '{req.start_step}'")

    def bad_request(self, req: Request, error: str):
        bad_req = BadRequest()
        bad_req.error = error
        bad_req.type = req.type
        self.add_msg_to_buffer(bad_req, priority=True)

    def last_step_update(self):
        last_step = self.get_last_available_step()
        update = RunUpdate()
        update.final_step = last_step
        self.add_msg_to_buffer(update, priority=True)

    def request_out_of_bounds(self, req: Union[PixelChangesReq, FullPixelChangesReq]):
        if isinstance(req, FullPixelChangesReq):
            bound_step = req.step
        elif isinstance(req, PixelChangesReq):
            bound_step = req.end_step
        else:
            raise ValueError(f"Unknown request type: {req}")
        if bound_step > self.get_last_available_step():
            if self._stream_source.is_done():
                self.last_step_update()
            return True
        return False

    async def handle_full_pixel_changes_request(self, req: FullPixelChangesReq):
        if not self._color_mapping:
            run_meta_data = await self._stream_source.get_meta_data()
            self._color_mapping = create_color_map(run_meta_data.snake_values)
        if self.request_out_of_bounds(req):
            self.add_waiting_request(req.step, req)
            return
        full_step = self._stream_source.get_map(req.step)
        diffs = get_diffs(None, full_step)
        full_state_change = make_color_changes(diffs, self._color_mapping)
        msg = create_pixel_change_proto_msg(full_state_change, full_state=True)
        step_pixel_changes = StepPixelChanges()
        step_pixel_changes.changes.append(msg)
        step_pixel_changes.step = req.step
        self.add_msg_to_buffer(step_pixel_changes)

    async def handle_pixel_changes_request(self, req: PixelChangesReq):
        if not self._color_mapping:
            run_meta_data = await self._stream_source.get_meta_data()
            self._color_mapping = create_color_map(run_meta_data.snake_values)
        if self.request_out_of_bounds(req):
            req = self.split_request(req)
            if req is None:
                return
        self._stream_source.get_map(req.start_step)
        step_maps = self._stream_source.get_map_range(start=req.start_step, end=req.end_step)
        prev_map = None
        for i, s_maps in enumerate(step_maps):
            step_pixel_changes = StepPixelChanges()
            step_pixel_changes.step = req.start_step + i
            for s_map in s_maps:
                diffs = get_diffs(prev_map, s_map)
                change = make_color_changes(diffs, self._color_mapping)
                msg = create_pixel_change_proto_msg(change)
                step_pixel_changes.changes.append(msg)
                prev_map = s_map
            self.add_msg_to_buffer(step_pixel_changes)

    async def handle_run_meta_data_request(self):
        try:
            run_meta_data = await self._stream_source.get_meta_data()
        except RuntimeError as e:
            log.debug("TRACEBACK", exc_info=True)
            log.error(e)
            return
        if not self._color_mapping:
            self._color_mapping = create_color_map(run_meta_data.snake_values)
        run_meta_data_proto = env_meta_data_to_proto(run_meta_data)
        self.add_msg_to_buffer(run_meta_data_proto)

    async def process_request(
        self,
        req: Union[
            PixelChangesReq,
            RunMetaDataRequest,
            FullPixelChangesReq
            ]
        ):
        try:
            if isinstance(req, PixelChangesReq):
                await self.handle_pixel_changes_request(req)
            elif isinstance(req, FullPixelChangesReq):
                await self.handle_full_pixel_changes_request(req)
            elif isinstance(req, RunMetaDataRequest):
                await self.handle_run_meta_data_request()
            else:
                log.error(f"Unknown request: {req}")
        except ValueError as e:
            log.error(e)
            log.debug("TRACEBACK", exc_info=True)

    def recieve_request(self, req: Request):
        try:
            req_wrapper = Request()
            req_wrapper.ParseFromString(req)
            req_obj = unwrap_request(req_wrapper)
            if isinstance(req_obj, PixelChangesReq):
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

    def add_msg_to_buffer(self, msg, priority: bool = False):
        wrapped_msg = wrap_message(msg)
        if priority:
            self._msg_out_buffer.appendleft(wrapped_msg)
        else:
            self._msg_out_buffer.append(wrapped_msg)

    def _get_processable_waiting_requests(self):
        processable_requests = []
        last_step = self.get_last_available_step()
        for req in self._waiting_requests:
            if req.start_step <= last_step:
                processable_requests.append(req)
        return processable_requests

    async def _request_listener(self):
        while self.websocket.client_state == WebSocketState.CONNECTED and self.websocket.application_state == WebSocketState.CONNECTED:
            try:
                req = await asyncio.wait_for(self.websocket.receive_bytes(), timeout=self._yield_time)
                if req == b'ping':
                    continue
                self.recieve_request(req)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def request_listener(self):
        await self.async_ws_wrapper(self._request_listener)

    async def _msg_pusher(self):
        while self.websocket.client_state == WebSocketState.CONNECTED and self.websocket.application_state == WebSocketState.CONNECTED:
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
                    await self.process_request(req)
                if self._waiting_requests:
                    processable_requests = self._get_processable_waiting_requests()
                    for req in processable_requests:
                        self._waiting_requests.remove(req)
                        self.add_request(req.req)
                await asyncio.sleep(self._yield_time)
            except asyncio.CancelledError:
                break

    async def _heartbeat(self):
        try:
            while self.websocket.client_state == WebSocketState.CONNECTED and self.websocket.application_state == WebSocketState.CONNECTED:
                await asyncio.sleep(0.5)
                await self.websocket.send_text('ping')
        except asyncio.CancelledError:
            log.debug("Heartbeat cancelled")

    async def heartbeat(self):
        await self.async_ws_wrapper(self._heartbeat)

    async def request_handler(self):
        await self.async_ws_wrapper(self._request_handler)

    async def cancel(self):
        if getattr(self, "_is_canceling", False):
            return
        for task in self.sub_tasks:
            if not task.done():
                try:
                    task.cancel()
                    await task
                except asyncio.CancelledError:
                    pass
        self.sub_tasks.clear()
        self._is_canceling = True

    async def start(self):
        log.info(f"DataStreamHandler started for {self.stream_id}")
        try:
            self.sub_tasks.add(asyncio.create_task(self.request_listener()))
            self.sub_tasks.add(asyncio.create_task(self.request_handler()))
            self.sub_tasks.add(asyncio.create_task(self.msg_pusher()))
            self.sub_tasks.add(asyncio.create_task(self.heartbeat()))
            await asyncio.gather(*self.sub_tasks, return_exceptions=True)
        finally:
            await self.cancel()
        log.info(f"DataStreamHandler closed for {self.stream_id}")



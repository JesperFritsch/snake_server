import asyncio
import websockets
import json
import struct
import requests
import logging
from urllib.parse import urljoin, urlencode
from multiprocessing import Pipe, Process
from collections import deque

from snake_sim.render.pygame_render import play_stream
from snake_sim.protobuf.sim_msgs_pb2 import (
    MsgWrapper,
    PixelChanges,
    RunData as proto_run_data,
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
from snake_sim.snake_env import StepData, RunData
from google.protobuf.json_format import MessageToDict

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())

step_queue = deque()
meta_data = None

async def request_meta_data(websocket):
    meta_data_req = Request(
        type=RequestType.RUN_META_DATA_REQ,
        payload=RunMetaDataRequest().SerializeToString()
    )
    await websocket.send(meta_data_req.SerializeToString())
    while meta_data is None:
        await asyncio.sleep(1)


async def reciever(websocket: websockets):
    while True:
        try:
            data = await websocket.recv()
            if data == 'ping':
                await websocket.send('ping'.encode())
            else:
                msg = MsgWrapper()
                msg.ParseFromString(data)
                if msg.type == MessageType.RUN_META_DATA:
                    global meta_data
                    meta_data = RunMetaData()
                    meta_data.ParseFromString(msg.payload)
                elif msg.type == MessageType.STEP_DATA:
                    step_data = proto_step_data()
                    step_data.ParseFromString(msg.payload)
                    step_queue.append(step_data)
        except websockets.exceptions.ConnectionClosed as e:
            print(f"Connection closed: {e}")
            break


async def request_data(websocket):
    last_requested_step = 0
    while True:
        try:
            start_step = last_requested_step + 1
            end_step = start_step + 9
            last_requested_step = end_step
            req = Request(
                type=RequestType.STEP_DATA_REQ,
                payload=StepDataRequest(start_step=start_step, end_step=end_step, full_state=False).SerializeToString()
            )
            await websocket.send(req.SerializeToString())
            print(f"Sending request: {req}")
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("Cancelled")
            break
        except Exception as e:
            print(f"Error: {e}")
            break


async def data_pusher(conn):
    while True:
        if len(step_queue) > 0:
            data = step_queue.popleft()
            step_data = StepData.from_protobuf(data)
            conn.send(step_data.to_dict())
        await asyncio.sleep(0.001)


async def snake_stream():
    base_uri = "ws://localhost:42069/stream"
    request_uri = "http://localhost:42069/api/request_run"
    info_uri = "http://localhost:42069/api/run_info"
    websocket = None
    render_conn, child_conn = Pipe()
    render_p = Process(target=play_stream, args=(child_conn,))
    render_p.start()
    run_config = {
        "width": 32,
        "height": 32,
        "food": 15,
        "snake_count": 1,
        "map": "items",
    }
    try:
        response = requests.post(request_uri, json=run_config)
        run_info = requests.get(info_uri).json()
        run_config_resp = response.json()
        stream_id = run_config_resp["stream_id"]
        # stream_id = "a3516aa2-017b-4448-a706-de7672f0fa39"
        print(run_info)
        stream_uri = '/'.join([base_uri, stream_id])
        print(f"Stream URI: {stream_uri}")
        websocket = await websockets.connect(stream_uri)
        reciever_task = asyncio.create_task(reciever(websocket))
        get_data_task = asyncio.create_task(request_data(websocket))
        await request_meta_data(websocket)
        init_data = MessageToDict(meta_data)
        run_data_proto = proto_run_data()
        run_data_proto.run_meta_data.CopyFrom(meta_data)
        init_data = RunData.from_protobuf(run_data_proto)
        render_conn.send(init_data.to_dict())
        pusher_task = asyncio.create_task(data_pusher(render_conn))
        await pusher_task

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {e}")
    except Exception as e:
        print(f"Error: {e}")
        log.error(e)
        log.debug("TRACE: ", exc_info=True)

    finally:
        if "get_data_task" in locals():
            get_data_task.cancel()
        if "reciever_task" in locals():
            reciever_task.cancel()
        if "pusher_task" in locals():
            pusher_task.cancel()
        if websocket is not None:
            await websocket.close()
            print("WebSocket closed.")
    while render_p.is_alive():
        pass

async def main():
    await snake_stream()

if __name__ == '__main__':
    # Run the main function in the asyncio event loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user")

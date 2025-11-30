import asyncio
import websockets
import requests
import logging
from urllib.parse import urljoin, urlencode
from multiprocessing import Pipe, Process
from collections import deque

from snake_sim.render.pygame_render import play_stream
from snake_proto_template.python.sim_msgs_pb2 import (
    MsgWrapper,
    PixelChanges,
    RunData as proto_run_data,
    RunMetaData,
    MessageType,
    Request,
    RequestType,
    StepData as proto_step_data,
    StepDataReq,
    PixelChangesReq,
    RunMetaDataRequest,
    RunUpdate,
    BadRequest
)
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
                elif msg.type == MessageType.BAD_REQUEST:
                    bad_req = BadRequest()
                    bad_req.ParseFromString(msg.payload)
                    log.error(f"Bad request: {bad_req}")
                elif msg.type == MessageType.RUN_UPDATE:
                    update = RunUpdate()
                    update.ParseFromString(msg.payload)
                    log.info(f"Run update: {update}")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"Connection closed: {e}")
            break


async def request_data(websocket):
    last_requested_step = 0
    while True:
        try:
            start_step = last_requested_step
            end_step = start_step + 10
            last_requested_step = end_step
            req = Request(
                type=RequestType.STEP_DATA_REQ,
                payload=StepDataReq(start_step=start_step, end_step=end_step).SerializeToString()
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
    base_uri = "ws://localhost:42069/ws/watch"
    request_uri = "http://localhost:42069/api/request_run"
    websocket = None
    render_conn, child_conn = Pipe()
    render_p = Process(target=play_stream, args=(child_conn,))
    render_p.start()
    run_config = {
        "grid_width": 32,
        "grid_height": 32,
        "food": 15,
        "food_decay": 0,
        "snake_count": 1,
        "map": "items",
        "start_length": 5
    }
    try:
        response = requests.post(request_uri, json=run_config)
        resp = response.json()
        if response.status_code != 200:
            raise Exception(f"Error requesting run: {resp}")
        if resp['result'] != 'success':
            raise Exception(f"Error requesting run: {resp['error']}")
        stream_id = resp["run_id"]
        # stream_id = "45f9cc23-4f5d-4efb-87b3-bdb9e2f62920"
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
        if input("Press q to quit: ") == 'q':
            render_p.terminate()
            break

async def main():
    await snake_stream()

if __name__ == '__main__':
    # Run the main function in the asyncio event loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user")

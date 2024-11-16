import asyncio
import websockets
import json
import struct
import requests
import logging
from urllib.parse import urljoin, urlencode
from multiprocessing import Pipe, Process

from snake_sim.render.pygame_render import play_stream
from snake_sim.protobuf.python import sim_msgs_pb2
from snake_sim.snake_env import StepData
from google.protobuf.json_format import MessageToDict

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())

async def request_data(websocket):
    req = {
        "mode": "sequential",
        "nr": 1
    }
    while True:
        try:
            await websocket.send(json.dumps(req))
            print(f"Sending request: {req}")
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            print("Cancelled")
            break
        except Exception as e:
            print(f"Error: {e}")
            break

async def snake_stream():
    base_uri = "ws://localhost:42069/stream"
    request_uri = "http://localhost:42069/api/request_run"
    info_uri = "http://localhost:42069/api/run_info"
    websocket = None
    render_conn, child_conn = Pipe()
    render_p = Process(target=play_stream, args=(child_conn,))
    render_p.start()
    data_mode = "pixel_data"
    data_on_demand = True
    run_config = {
        "width": 32,
        "height": 32,
        "food": 15,
        "snake_count": 1,
        "map": "items",
        "as_proto": True,
        "full_step_state": True,
    }
    try:
        params = {
            "data_mode": data_mode,
            "data_on_demand": data_on_demand
        }
        # response = requests.post(request_uri, json=run_config)
        run_info = requests.get(info_uri).json()
        # run_config_resp = response.json()
        # stream_id = run_config_resp["stream_id"]
        stream_id = "a3516aa2-017b-4448-a706-de7672f0fa39"
        as_proto = run_info.get(stream_id, {}).get('config', {}).get("as_proto", False)
        print(run_info)
        if as_proto:
            sim_msg_pb = sim_msgs_pb2.StepData()
        stream_uri = '/'.join([base_uri, stream_id]) + '?' + urlencode(params)
        print(f"Stream URI: {stream_uri}")
        websocket = await websockets.connect(stream_uri)
        init_data = await websocket.recv()
        print(init_data)
        render_conn.send(json.loads(init_data))
        if data_on_demand:
            get_data_task = asyncio.create_task(request_data(websocket))
        while render_p.is_alive():
            data = await websocket.recv()
            if data == "END":
                break
            print(data)
            if as_proto:
                sim_msg_pb.ParseFromString(data)
                step_data = StepData.from_protobuf(sim_msg_pb)
                converted_data = step_data.to_dict()
            else:
                converted_data = json.loads(data)
            render_conn.send(converted_data)
            print(f"Data received: {converted_data}")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {e}")
    except Exception as e:
        log.error(e)
        log.debug("TRACE: ", exc_info=True)

    finally:
        if "get_data_task" in locals():
            get_data_task.cancel()
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

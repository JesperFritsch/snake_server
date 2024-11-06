import json
import sys
import uuid
import time
import os
import asyncio
import logging
import pkg_resources

from typing import List
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.websockets import WebSocketState
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from multiprocessing import Pipe, Process, Queue, get_context

from snake_sim.snake_env import SnakeEnv
from snake_sim.render.core import FrameBuilder
from snake_sim.main import start_stream_run
from snake_sim.utils import DotDict
from snake_sim.render.core import FrameBuilder

from process_pool import MultiStreamManager
from data_stream_handler import DataStreamHandler

MAX_STREAMS = 5

stream_connections = {}

log = logging.getLogger('main')
log.setLevel(logging.DEBUG)

if not os.path.exists('logs'):
    os.makedirs('logs')

# Create handler
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler = RotatingFileHandler('logs/app.log', maxBytes=20000, backupCount=5)
stdout_handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
stdout_handler.setFormatter(formatter)
stdout_handler.setLevel(logging.DEBUG)
# Add handler to log
log.addHandler(handler)
log.addHandler(stdout_handler)

app = FastAPI()

stream_manager = MultiStreamManager()

app.mount("/client", StaticFiles(directory="client"), name="client")

def get_default_config():
    config_json = pkg_resources.resource_filename('snake_sim', 'config/default_config.json')
    with open(config_json, 'r') as f:
        default_config = json.load(f)
    return DotDict(default_config)

@app.get("/")
async def root():
    file_path = "client/index.html"
    return FileResponse(file_path)

@app.get("/api/config_data")
async def get_config_data(conf: List[str] = Query([])):
    unhandled = conf.copy()
    resp = {}
    if 'maps' in conf:
        maps = list(SnakeEnv.get_map_files().keys())
        resp['maps'] = maps
        unhandled.remove('maps')

    for key in unhandled:
        resp[key] = 'Not implemented'
    return JSONResponse(content=resp)


@app.get("/api/stop_stream")
async def stop_stream(stream_id: uuid.UUID):
    str_stream_id = str(stream_id)
    print(f"Stopping stream: {str_stream_id}")
    stopped = stream_manager.stop_stream(str_stream_id)
    if stopped:
        return JSONResponse(content={'status': 'stopped'})
    else:
        return JSONResponse(content={'status': 'not found'}, status_code=404)

@app.post("/api/request_run")
async def request_run(request: Request):
    config = get_default_config()
    config_dict = await request.json()
    config.update(config_dict)
    stream_id = stream_manager.start_stream(config)
    if stream_id:
        return JSONResponse(content={'stream_id': stream_id})
    else:
        return JSONResponse(content={'error': 'Maximum number of streams reached'}, status_code=503)


@app.get("/api/run_info")
async def get_run_info():
    data = stream_manager.get_current_run_data()
    return JSONResponse(content=data)


@app.websocket("/stream/{stream_id}")
async def get_stream_data(websocket: WebSocket, stream_id: str):
    # Maybe some condition to accept or reject the connection
    await websocket.accept()
    if not stream_id in stream_manager.stream_buffers:
        log.error(f"Stream not found: {stream_id}")
        await websocket.send_json({'error': 'Stream not found'})
        await websocket.close(code=1003)
        return
    try:
        ready_event = stream_manager.ready_events.get(stream_id)
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=5)
        except asyncio.TimeoutError:
            await websocket.send_json({'error': 'Stream not ready'})
            await websocket.close(code=1003)
            return
        data_mode = websocket.query_params.get('data_mode', 'pixel_data')
        data_on_demand_str = websocket.query_params.get('data_on_demand', False)
        data_on_demand = True if data_on_demand_str == 'True' else False
        stream_init_data = stream_manager.get_stream_init_data(stream_id)
        stream_buffer = stream_manager.stream_buffers[stream_id]
        if data_mode == 'pixel_data':
            frame_builder = FrameBuilder(run_meta_data=stream_init_data, expand_factor=2, offset=(1, 1))
        else:
            frame_builder = None

        # first send the init data
        await websocket.send_json(stream_init_data)

        # Use the streamhandler so that the client can chose how often and how much data is sent
        data_stream = DataStreamHandler(websocket, data_mode, data_on_demand)
        data_stream_task = asyncio.create_task(data_stream.handler())
        step_count = 0
        while True:
            try:
                if step_count >= len(stream_buffer):
                    await asyncio.sleep(0.1)
                    continue
                data = stream_buffer[step_count]
                step_count += 1
                if data == 'stopped':
                    break
                if data_mode == 'steps':
                    data_stream.push_data(data)
                elif data_mode == 'pixel_data':
                    changes = frame_builder.step_to_pixel_changes(data)
                    for change in changes:
                        flattened_payload = [value for sublist in change for sublist_pair in sublist for value in sublist_pair]
                        payload = bytes(flattened_payload)
                        data_stream.push_data(payload)
            except EOFError:
                break
        data_stream.data_end = True
        await data_stream_task
    except WebSocketDisconnect as e:
        log.info(f"Connection closed by client")
        try:
            data_stream_task.cancel()
        except:
            pass

    except Exception as e:
        log.error(e)
        log.debug(f"TRACEBACK: ", exc_info=True)

    finally:
        if websocket.application_state == WebSocketState.CONNECTED and websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text('END')
            await websocket.close()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global stream_connections
    nr_of_streams = len(stream_connections)
    stream_id = uuid.uuid4()
    log.info(f"incoming connection nr: {stream_id}")
    log.info(f'Nr of active streams: {nr_of_streams}')
    if nr_of_streams < MAX_STREAMS:
        await websocket.accept()
        stream_connections[stream_id] = websocket
        log.info(f'Accepted connection nr: {stream_id}')
    else:
        await websocket.close()
        log.info(f'Rejected connection nr: {stream_id}')
        return
        # Receive initial configuration data
    try:
        config = get_default_config()
        run_metadata = await websocket.receive_json()
        config.update(run_metadata)
        data_mode = config.get('data_mode', 'steps')
        data_on_demand = config.get('data_on_demand', False)
        ack = 'ACK'
        log.info(f'sending {ack} to client')
        await websocket.send_text(ack)
        mp_context = get_context('spawn')
        snake_sim_pipe, snake_sim_pipe_other = Pipe()
        env_p = mp_context.Process(target=start_stream_run, args=(snake_sim_pipe_other, config))
        env_p.start()
        init_data = await nonblock_exec(snake_sim_pipe.recv)
        # pass init data to client
        await websocket.send_json(init_data)
        if data_mode == 'pixel_data':
            frame_builder = FrameBuilder(run_meta_data=init_data, expand_factor=2, offset=(0, 0))
        data_stream = DataStreamHandler(websocket, data_mode, data_on_demand)
        data_stream_task = asyncio.create_task(data_stream.handler())
        log.info(f'Sending data with mode: {data_mode}')
        while env_p.is_alive():
            if websocket.application_state == WebSocketState.DISCONNECTED or websocket.client_state == WebSocketState.DISCONNECTED:
                raise WebSocketDisconnect
            if snake_sim_pipe.poll(timeout=0.1):
                try:
                    step_data = await nonblock_exec(snake_sim_pipe.recv)
                    if step_data == 'stopped':
                        break
                    # Depending on the config, decide what data to send
                    if data_mode == 'steps':
                        payload = step_data
                        data_stream.push_data(payload)
                    elif data_mode == 'pixel_data':
                        changes = frame_builder.step_to_pixel_changes(step_data)
                        for change in changes:
                            flattened_payload = [value for sublist in change for sublist_pair in sublist for value in sublist_pair]
                            payload = bytes(flattened_payload)
                            data_stream.push_data(payload)
                except EOFError:
                    break
        data_stream.data_end = True
        log.info('sending remaining data')
        await data_stream_task

    except WebSocketDisconnect as e:
        log.info(f"Connection closed by client")
        try:
            data_stream_task.cancel()
        except:
            pass

    except Exception as e:
        log.error(e)
        log.debug("TRACEBACK", exc_info=True)

    finally:
        if websocket.application_state == WebSocketState.CONNECTED and websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text('END')
            await websocket.close()
        stream_connections.pop(stream_id)

        log.info(f'Cleaning up {stream_id} ...')
        try:
            snake_sim_pipe.send('stop')
            env_p.join()
        except Exception as e:
            log.error(e)
        print(f"Session over: {stream_id}")

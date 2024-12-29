import json
import sys
import uuid
import time
import os
import asyncio
import logging

import utils

from pathlib import Path
from contextlib import asynccontextmanager
from typing import List
from logging.handlers import RotatingFileHandler
from importlib.resources import files

from fastapi import FastAPI, WebSocket, Query, Request
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from snake_sim.snake_env import SnakeEnv
from snake_sim.utils import DotDict

from process_pool import MultiStreamManager
from server.data_stream_handler import DataStreamHandler

MAX_STREAMS = 5

stream_connections = {}


log = logging.getLogger('main')
logging.getLogger().setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG)

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
# log.addHandler(stdout_handler)

stream_manager = MultiStreamManager()
task_manager = utils.TaskManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        log.info("life span cleanup")
        await task_manager.cancel_all()
        stream_manager.cleanup()


app = FastAPI(lifespan=lifespan)

protodir = files('snake_sim').joinpath('protobuf')
app.mount("/client", StaticFiles(directory="../client"), name="client")
app.mount("/static", StaticFiles(directory=protodir), name="static")

def get_default_config():
    config_json = files('snake_sim').joinpath('config/default_config.json')
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
    log.debug(f"Stopping stream: {str_stream_id}")
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
    data = stream_manager.get_current_run_info()
    return JSONResponse(content=data)


@app.websocket("/stream/{stream_id}")
async def get_stream_data(websocket: WebSocket, stream_id: str):
    # Maybe some condition to accept or reject the connection
    await websocket.accept()
    if not stream_manager.is_running(stream_id):
        log.error(f"Stream not found: {stream_id}")
        # await websocket.send_json({'error': 'Stream not found'})
        await websocket.close(code=1003)
        return
    try:
        if not await stream_manager.wait_for_ready(stream_id, timeout=5):
            # await websocket.send_json({'error': 'Stream not ready'})
            log.error(f"Stream not ready: {stream_id}")
            await websocket.close(code=1003)
            return
        # Use the streamhandler so that the client can chose how often and how much data is sent
        data_stream = DataStreamHandler(websocket, stream_id)
        data_stream_task = asyncio.create_task(data_stream.start())
        task_manager.add_task(data_stream_task)
        await data_stream_task

    except WebSocketDisconnect as e:
        log.info(f"Connection closed by client")

    except Exception as e:
        log.error(e)
        log.debug(f"TRACEBACK: ", exc_info=True)

    finally:
        await data_stream.cancel()
        data_stream_task.cancel()
        if websocket.client_state == WebSocketState.CONNECTED and websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close()

import logging
import asyncio
from pathlib import Path
from configparser import ConfigParser
from importlib import resources

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState

from snake_server.process_pool.process_pool import SnakeProcessPool
from snake_server.source_manager.stream_source_manager import StreamSourceManager
from snake_server.stream_handler.data_stream_handler import DataStreamHandler

config = ConfigParser()

with open(resources.files('snake_server').joinpath('config.ini')) as config_file:
    config.read_file(config_file)

log = logging.getLogger(Path(__file__).stem)

source_manager = StreamSourceManager()
process_pool = SnakeProcessPool()

async def start_stream(websocket: WebSocket, run_id: str):
    # Maybe some condition to accept or reject the connection
    await websocket.accept()
    data_stream_task = None
    try:
        stream_source = source_manager.get_source(run_id)
        data_stream = DataStreamHandler(websocket, stream_source, run_id)
        await data_stream.init_frame_builder()
        log.info(f"Starting stream for {run_id}")
        data_stream_task = asyncio.create_task(data_stream.start())
        await data_stream_task

    except KeyboardInterrupt:
        pass

    finally:
        if data_stream_task and not data_stream_task.done():
            data_stream_task.cancel()
            try:
                await data_stream_task
            except asyncio.CancelledError:
                pass
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except RuntimeError as e:
                pass
        if config.getboolean('snake_process', 'cleanup_on_disconnect'):
            log.debug(f"Stopping source: {run_id}")
            process_pool.finish_proc(run_id)
        log.info(f"Stream closed for {run_id}")
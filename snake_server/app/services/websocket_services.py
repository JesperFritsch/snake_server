import logging
import asyncio
from pathlib import Path

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState

from snake_server.source_manager.stream_source_manager import StreamSourceManager
from snake_server.stream_handler.data_stream_handler import DataStreamHandler

log = logging.getLogger(Path(__file__).stem)

source_manager = StreamSourceManager()

async def start_stream(websocket: WebSocket, run_id: str):
    # Maybe some condition to accept or reject the connection
    await websocket.accept()
    data_stream_task = None
    try:
        stream_source = source_manager.get_source(run_id)
        data_stream = DataStreamHandler(websocket, stream_source, run_id)
        await data_stream.init_frame_builder()
        data_stream_task = asyncio.create_task(data_stream.start())
        await data_stream_task

    except WebSocketDisconnect as e:
        log.info(f"Connection closed by client")

    except Exception as e:
        log.error(e)
        log.debug(f"TRACEBACK: ", exc_info=True)

    except asyncio.CancelledError:
        log.info(f"Stream for run {run_id} cancelled")

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
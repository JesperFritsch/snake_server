from fastapi import APIRouter, WebSocket
from snake_server.app.services import websocket_services

router = APIRouter()

@router.websocket("/watch/{run_id}")
async def watch_websocket(websocket: WebSocket, run_id: str):
    """ Provided a run id, if the run is available as either ongoing or stored, send the data to the client """
    await websocket_services.start_stream(websocket, run_id)
import asyncio
import websockets
import json
from multiprocessing import Pipe, Process

from snake_sim.render.pygame_render import play_stream

async def snake_stream():
    uri = "ws://homeserver:42069/ws"
    websocket = None
    parent_conn, child_conn = Pipe()
    render_p = Process(target=play_stream, args=(child_conn,))
    render_p.start()
    try:
        websocket = await websockets.connect(uri)
        await websocket.send('{"grid_width": 5, "grid_height": 5, "food_count": 15, "nr_of_snakes": 7}')
        ack = await websocket.recv()
        print(ack)
        while render_p.is_alive():
            data = await websocket.recv()
            print(f"Received data: {data}, type: {type(data)}")
            data_dict = json.loads(data)
            parent_conn.send(data_dict)
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
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

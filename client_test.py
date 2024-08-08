import asyncio
import websockets
import json
import struct
from multiprocessing import Pipe, Process

from snake_sim.render.pygame_render import play_stream

async def request_data(websocket):
    while True:
        try:
            await websocket.send("GET 1")
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            print("Cancelled")
            break

async def snake_stream():
    uri = "ws://homeserver:42069/ws"
    websocket = None
    render_conn, child_conn = Pipe()
    render_p = Process(target=play_stream, args=(child_conn,))
    render_p.start()
    data_mode = "steps"
    data_on_demand = False
    run_config = {
        "grid_width": 20,
        "grid_height": 20,
        "food_count": 15,
        "nr_of_snakes": 7,
        "data_mode": data_mode,
        "data_on_demand": data_on_demand
    }
    try:
        websocket = await websockets.connect(uri)
        await websocket.send(json.dumps(run_config))
        ack = await websocket.recv()
        init_data = await websocket.recv()
        render_conn.send(json.loads(init_data))
        if data_on_demand:
            get_data_task = asyncio.create_task(request_data(websocket))
        print(ack)
        while render_p.is_alive():
            data = await websocket.recv()
            if data == "END":
                break
            if data_mode == "steps":
                converted_data = json.loads(data)
            else:
                converted_data = [((x, y), (r, g, b)) for x, y, r, g, b in struct.iter_unpack("BBBBB", data)]
            render_conn.send(converted_data)
            print(f"Data received: {converted_data}")

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {e}")
    except Exception as e:
        print(f"Error: {e}")
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

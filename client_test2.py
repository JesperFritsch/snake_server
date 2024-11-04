import asyncio
import websockets
import json
import struct
import httpx
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

async def receive_stream(task_id: str):
    url = f"http://localhost:42069/stream/{task_id}?data_mode=steps"  # Replace with your server's URL
    render_conn, child_conn = Pipe()
    render_p = Process(target=play_stream, args=(child_conn,))
    render_p.start()
    count = 0
    async with httpx.AsyncClient() as client:
        # Send a GET request to the streaming endpoint
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                print(f"Failed to connect: {response.status_code}")
                return

            # Read each chunk as it arrives
            async for chunk in response.aiter_bytes():
                if not chunk:
                    # End of stream
                    break
                try:
                    render_conn.send(json.loads(chunk))
                except json.JSONDecodeError:
                    print(f"Failed to decode chunk: {chunk}")
                    render_conn.send('stopped')
                # Here you can process the binary data (chunk) as needed

async def main():
    task_id = "d3020a82-06a5-437b-9494-9b27c3333c01"
    task_id = "90bf370e-e75d-4984-b56d-d551c10882a7"
    await receive_stream(task_id)
# Run the receive_stream coroutine
if __name__ == "__main__":
    asyncio.run(main())
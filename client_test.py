import asyncio
import websockets
import json

async def snake_stream():
    uri = "ws://localhost:4200/ws"
    websocket = None
    try:
        websocket = await websockets.connect(uri)
        await websocket.send('{"grid_width": 32, "grid_height": 32, "food_count": 15, "nr_of_snakes": 7}')
        ack = await websocket.recv()
        print(ack)
        while True:
            data = await websocket.recv()
            data_dict = json.loads(data)
            print(data_dict)
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed with error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if websocket is not None:
            await websocket.close()
            print("WebSocket closed.")

async def main():
    await snake_stream()

if __name__ == '__main__':
    # Run the main function in the asyncio event loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user")

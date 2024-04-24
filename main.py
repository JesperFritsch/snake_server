import json
import sys
import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from multiprocessing import Pipe, Process, Queue

from snake_sim.snake_env import SnakeEnv
from snake_sim.snakes.autoSnake4 import AutoSnake4
from snake_sim.default_config import snake_configs

MAX_STREAMS = 5

app = FastAPI()
nr_of_streams = 0


async def nonblock_exec(func, *args):
    return await asyncio.to_thread(func, *args)

def start_stream_run(conn, config):
    sys.stdout = open(os.devnull, 'w')
    nr_of_snakes = config.get('nr_of_snakes', 7)
    grid_height = config.get('grid_height', 32)
    grid_width = config.get('grid_width', 32)
    food_count = config.get('food_count', 15)
    env = SnakeEnv(grid_width, grid_height, food_count)
    count = 0
    for config in snake_configs:
        count += 1
        env.add_snake(AutoSnake4(**config['snake']), **config['env'])
        if count == nr_of_snakes:
            break
    env.stream_run(conn,)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global nr_of_streams
    if nr_of_streams < MAX_STREAMS:
        await websocket.accept()
        nr_of_streams += 1
    else:
        return
    # Receive initial configuration data
    try:
        config = await websocket.receive_json()
        ack = 'ACK'
        await websocket.send_text(ack)
        parent_conn, child_conn = Pipe()
        env_p = Process(target=start_stream_run, args=(child_conn, config))
        env_p.start()

        while env_p.is_alive():
            # Depending on the config, decide what data to send
            try:
                step_data = await nonblock_exec(parent_conn.recv)
            except EOFError:
                break
            step_json = json.dumps(step_data)
            await websocket.send_json(step_json)
    except WebSocketDisconnect as e:
        print(f"Connection closed with error: {e}")

    except Exception as e:
        print(e)

    finally:
        nr_of_streams -= 1
        env_p.terminate()
        await websocket.close()
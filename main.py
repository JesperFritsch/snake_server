import json
import sys
import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from multiprocessing import Pipe, Process, Queue

from snake_sim.snake_env import SnakeEnv
from snake_sim.render.core import FrameBuilder
from snake_sim.snakes.autoSnake4 import AutoSnake4

MAX_STREAMS = 5

app = FastAPI()
nr_of_streams = 0

config_json = os.path.join(os.path.dirname(__file__), '..', 'snake_sim', 'default_config.json')

with open(config_json, 'r') as f:
    snake_defalut_config = json.load(f)


async def nonblock_exec(func, *args):
    return await asyncio.to_thread(func, *args)

def start_stream_run(conn, config):
    # sys.stdout = open(os.devnull, 'w')
    nr_of_snakes = config.get('nr_of_snakes', 7)
    grid_height = config.get('grid_height', 32)
    grid_width = config.get('grid_width', 32)
    food_count = config.get('food_count', 15)
    env = SnakeEnv(grid_width, grid_height, food_count)
    env.store_runs = False
    count = 0
    for snake_config in snake_defalut_config['snake_configs']:
        count += 1
        env.add_snake(AutoSnake4(**snake_config['snake']), **snake_config['env'])
        if count == nr_of_snakes:
            break
    env.stream_run(conn,)
    conn.close()
    print('Stream run finished')

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global nr_of_streams
    if nr_of_streams < MAX_STREAMS:
        await websocket.accept()
        nr_of_streams += 1
        print('Accepted connection nr:', nr_of_streams)
    else:
        return
    # Receive initial configuration data
    try:
        config = await websocket.receive_json()
        data_mode = config.get('data_mode', 'steps')
        ack = 'ACK'
        print('sending', ack)
        await websocket.send_text(ack)
        parent_conn, child_conn = Pipe()
        env_p = Process(target=start_stream_run, args=(child_conn, config))
        env_p.start()
        if data_mode == 'pixel_data':
            init_data = await nonblock_exec(parent_conn.recv)
            frame_builder = FrameBuilder(run_meta_data=init_data, expand_factor=2)
        print('Sending data with mode: ', data_mode)
        while env_p.is_alive():
            # Depending on the config, decide what data to send
            if parent_conn.poll(timeout=0.1):
                try:
                    step_data = await nonblock_exec(parent_conn.recv)
                except EOFError:
                    break
                if data_mode == 'steps':
                    payload = step_data
                elif data_mode == 'pixel_data':
                    payload = frame_builder.step_to_pixel_changes(step_data)
                await websocket.send_json(payload)
    except WebSocketDisconnect as e:
        print(f"Connection closed with error: {e}")

    except Exception as e:
        print(e)

    finally:
        print('Closing connection')
        nr_of_streams -= 1
        env_p.terminate()
        await websocket.close()
import json
import sys
import uuid
import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from multiprocessing import Pipe, Process, Queue, get_context
from collections import deque

from snake_sim.snake_env import SnakeEnv
from snake_sim.render.core import FrameBuilder
from snake_sim.snakes.autoSnake4 import AutoSnake4

MAX_STREAMS = 5

log = logging.getLogger('main')
log.setLevel(logging.DEBUG)

if not os.path.exists('logs'):
    os.makedirs('logs')

# Create handler
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler = RotatingFileHandler('logs/app.log', maxBytes=20000, backupCount=5)
stdout_handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
stdout_handler.setFormatter(formatter)
# stdout_handler.setLevel(logging.INFO)
# Add handler to log
log.addHandler(handler)
log.addHandler(stdout_handler)

app = FastAPI()
stream_connections = {}

config_json = os.path.join(os.path.dirname(__file__), '..', 'snake_sim', 'snake_sim', 'config', 'default_config.json')

with open(config_json, 'r') as f:
    snake_defalut_config = json.load(f)


class DataOnDemand:
    def __init__(self, websocket: WebSocket, data_mode: str, on_demand: bool):
        self.data_mode = data_mode
        self.websocket = websocket
        self.on_demand = on_demand
        self.data_end = False
        self.changes_to_send = 0
        self.yield_time = 0.01
        self.data_buffer = deque()

    def push_data(self, data):
        self.data_buffer.append(data)

    async def handler(self):
        try:
            while not self.data_end or len(self.data_buffer) > 0:
                if self.on_demand:
                    req = await self.websocket.receive_text()
                    get, nr = req.split(' ')
                    nr_changes = int(nr)
                    log.debug(f"Requested {nr_changes} changes")
                    log.debug(f"Changes buffer size: {len(self.data_buffer)}")
                    self.changes_to_send += nr_changes
                    log.debug(f"Changes to send: {self.changes_to_send}")
                else:
                    nr_changes = 1
                    await asyncio.sleep(self.yield_time)
                count = 0
                while count < self.changes_to_send:
                    count += 1
                    if len(self.data_buffer) > 0:
                        data = self.data_buffer.popleft()
                        if self.data_mode == 'steps':
                            await self.websocket.send_json(data)
                        elif self.data_mode == 'pixel_data':
                            await self.websocket.send_bytes(data)
                        self.changes_to_send -= 1
        except WebSocketDisconnect:
            raise
        except Exception as e:
            log.error(e)
            return

async def nonblock_exec(func, *args):
    return await asyncio.to_thread(func, *args)


def start_stream_run(conn, config):
    sys.stdout = open(os.devnull, 'w')
    nr_of_snakes = config.get('nr_of_snakes', 7)
    grid_height = config.get('grid_height', 32)
    grid_width = config.get('grid_width', 32)
    food_count = config.get('food_count', 15)
    calc_timeout = config.get('calc_timeout', 1000)
    env = SnakeEnv(grid_width, grid_height, food_count)
    env.store_runs = False
    count = 0
    for snake_config in snake_defalut_config['snake_configs']:
        count += 1
        env.add_snake(AutoSnake4(**snake_config['snake'], calc_timeout=calc_timeout), **snake_config['env'])
        if count == nr_of_snakes:
            break
    env.stream_run(conn,)
    conn.close()
    log.info('Stream run finished')

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global stream_connections
    nr_of_streams = len(stream_connections)
    stream_id = uuid.uuid4()
    log.info(f"incoming connection nr: {stream_id}")
    log.info(f'Nr of active streams: {nr_of_streams}')
    if nr_of_streams < MAX_STREAMS:
        await websocket.accept()
        stream_connections[stream_id] = websocket
        log.info(f'Accepted connection nr: {stream_id}')
    else:
        await websocket.close()
        log.info(f'Rejected connection nr: {stream_id}')
        return
        # Receive initial configuration data
    try:
        config = await websocket.receive_json()
        data_mode = config.get('data_mode', 'steps')
        data_on_demand = config.get('data_on_demand', False)
        ack = 'ACK'
        log.info(f'sending {ack} to client')
        await websocket.send_text(ack)
        mp_context = get_context('spawn')
        snake_sim_pipe, snake_sim_pipe_other = Pipe()
        env_p = mp_context.Process(target=start_stream_run, args=(snake_sim_pipe_other, config))
        env_p.start()
        init_data = await nonblock_exec(snake_sim_pipe.recv)
        # pass init data to client
        await websocket.send_json(init_data)
        if data_mode == 'pixel_data':
            frame_builder = FrameBuilder(run_meta_data=init_data, expand_factor=2, offset=(1, 1))
        dod = DataOnDemand(websocket, data_mode, data_on_demand)
        dod_task = asyncio.create_task(dod.handler())
        log.info(f'Sending data with mode: {data_mode}')
        while env_p.is_alive():
            if websocket.application_state == WebSocketState.DISCONNECTED or websocket.client_state == WebSocketState.DISCONNECTED:
                raise WebSocketDisconnect
            if snake_sim_pipe.poll(timeout=0.1):
                try:
                    step_data = await nonblock_exec(snake_sim_pipe.recv)
                    # Depending on the config, decide what data to send
                    if data_mode == 'steps':
                        payload = step_data
                        dod.push_data(payload)
                    elif data_mode == 'pixel_data':
                        changes = frame_builder.step_to_pixel_changes(step_data)
                        for change in changes:
                            flattened_payload = [value for sublist in change for sublist_pair in sublist for value in sublist_pair]
                            payload = bytes(flattened_payload)
                            dod.push_data(payload)
                except EOFError:
                    break
        dod.data_end = True
        log.info('sending remaining data')
        await dod_task

    except WebSocketDisconnect as e:
        log.info(f"Connection closed by client")
        try:
            dod_task.cancel()
        except:
            pass

    except Exception as e:
        log.error(e)

    finally:
        if websocket.application_state == WebSocketState.CONNECTED and websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text('END')
            await websocket.close()
        stream_connections.pop(stream_id)

        log.info(f'Cleaning up {stream_id} ...')
        try:
            snake_sim_pipe.send('stop')
            env_p.join()
        except Exception as e:
            log.error(e)
        print(f"Session over: {stream_id}")

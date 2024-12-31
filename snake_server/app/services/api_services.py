import json
from importlib import resources

from snake_sim.utils import DotDict

from snake_server.process_pool.process_pool import SnakeProcessPool

with resources.open_text('snake_sim.config', 'default_config.json') as config_file:
    default_config = DotDict(json.load(config_file))

pool = SnakeProcessPool()

def request_run(config: dict) -> str:
    """ Request a run, return the id of the run """
    config = {**default_config, **config}
    return pool.start_run(DotDict(config))

def stop_run(run_id: str):
    """ Stop an ongoing run by id """
    pool.finish_proc(run_id)

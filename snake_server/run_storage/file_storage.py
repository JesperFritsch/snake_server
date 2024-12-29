import re
import logging
from uuid import uuid4
from pathlib import Path
from typing import List, Optional

from snake_server.run_storage.interface.run_storage_interface import IRunStorage
from snake_sim.run_data.run_data import RunData

log = logging.getLogger(Path(__file__).stem)

class RunFileStorage(IRunStorage):
    name_template = "{height}x{width}_{food}_{food_decay}_{snake_count}_{map_name}_{run_id}.pb"
    name_parts_re = re.compile(r'(?P<height>\d+)x(?P<width>\d+)_(?P<food>\d+)_(?P<food_decay>\d+)_(?P<snake_count>\d+)_(?P<map_name>\w+)_(?P<run_id>.+)\.pb')
    def __init__(self, storage_root: Optional[str] = ''):
        storage_root = storage_root or Path(__file__).parent.joinpath('file_store')
        storage_root_path = Path(storage_root)
        if not storage_root_path.exists():
            storage_root_path.mkdir(parents=True)
        self.storage_root = storage_root_path
        self.reserved_ids = set()

    def store_run(self, run_data: RunData, run_id: str, run_config: dict):
        try:
            self.reserved_ids.discard(run_id)
            filepath = self._generate_filepath(run_config, run_id)
            file_dir = filepath.parent
            filename = filepath.name
            run_data.write_to_file(output_dir=file_dir, filename=filename)
        except Exception as e:
            log.error(f"Error storing run data: {e}")
            log.debug("TRACEBACK", exc_info=True)

    def run_exists(self, run_id: str) -> bool:
        return self._id_conflict(run_id)

    def get_unique_run_id(self) -> str:
        run_id = str(uuid4())
        while self._id_conflict(run_id):
            run_id = str(uuid4())
        self.reserved_ids.add(run_id)
        return run_id

    def get_run(self, run_id: str) -> RunData:
        files = self.storage_root.glob(f"*{run_id}.*")
        if not files:
            return None
        file = files[0]
        try:
            if file.suffix == '.pb':
                return RunData.from_protobuf_file(file)
            elif file.suffix == '.json':
                return RunData.from_json_file(file)
        except Exception as e:
            log.error(f"Error loading run data: {e}")
            log.debug("TRACEBACK", exc_info=True)

    def get_ids_by_config(self, config_attrs: dict) -> List[str]:
        matching_files = self._get_matching_filenames(config_attrs)
        run_ids = []
        for filename in matching_files:
            match = self.name_parts_re.match(filename)
            run_id = match.group('run_id')
            run_ids.append(run_id)
        return run_ids

    def _generate_filepath(self, run_config: dict, run_id: str) -> Path:
        height = run_config['grid_height']
        width = run_config['grid_width']
        food = run_config['food']
        food_decay = run_config['food_decay']
        snake_count = run_config['snake_count']
        map_name = run_config['map']
        filename = self.name_template.format(
            height=height,
            width=width,
            food=food,
            food_decay=food_decay,
            snake_count=snake_count,
            map_name=map_name,
            run_id=run_id
        )
        return self.storage_root.joinpath(filename)

    def _get_matching_filenames(self, config_attrs: dict) -> List[str]:
        height = config_attrs.get('grid_height', '*')
        width = config_attrs.get('grid_width', '*')
        food = config_attrs.get('food', '*')
        food_decay = config_attrs.get('food_decay', '*')
        snake_count = config_attrs.get('snake_count', '*')
        map_name = config_attrs.get('map', '*')
        pattern = self.name_template.format(
            height=height,
            width=width,
            food=food,
            food_decay=food_decay,
            snake_count=snake_count,
            map_name=map_name,
            run_id='*'
        )
        matching_files = []
        for file in self.storage_root.glob(pattern):
            matching_files.append(file.name)
        return matching_files

    def _id_conflict(self, run_id: str) -> bool:
        all_ids = self.get_ids_by_config({})
        all_ids += self.reserved_ids
        return run_id in all_ids
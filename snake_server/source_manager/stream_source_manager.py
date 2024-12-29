import logging
from typing import Dict
from pathlib import Path

from snake_server.stream_source.interfaces.stream_source_interface import IStreamSource, ILiveStreamSource
from snake_server.run_storage.interface.run_storage_interface import IRunStorage
from snake_server.stream_source.stored_source import StoredSource
from snake_server.run_storage.file_storage import RunFileStorage
from snake_server.utils import SingletonMeta

log = logging.getLogger(Path(__file__).stem)

class StreamSourceManager(metaclass=SingletonMeta):
    def __init__(self):
        self._live_sources: Dict[str, ILiveStreamSource] = {}
        self._stored_sources: IRunStorage = RunFileStorage()

    def add_source(self, source_id, source: ILiveStreamSource):
        self._live_sources[source_id] = source

    def get_source(self, source_id) -> IStreamSource:
        if not self.source_exists(source_id):
            raise ValueError(f"Source with id {source_id} not found")
        if source_id in self._live_sources:
            return self._live_sources[source_id]
        else:
            return StoredSource(self._stored_sources.get_run(source_id))

    def source_exists(self, source_id):
        return source_id in self.get_live_source_ids() or self._stored_sources.run_exists(source_id)

    def get_live_source_ids(self):
        return list(self._live_sources.keys())

    def _store_live_source(self, source_id):
        log.debug(f"Storing live source with id {source_id}")
        run_data = self._live_sources[source_id].get_run_data()
        config = self._live_sources[source_id].get_run_config()
        self._stored_sources.store_run(run_data, source_id, config)

    def finish_live_source(self, source_id, store=True):
        if source_id in self._live_sources:
            source_obj = self._live_sources[source_id]
            source_obj.cancel()
            if store:
                self._store_live_source(source_id)
            del self._live_sources[source_id]
        else:
            raise ValueError(f"Source with id {source_id} not found")

    def cleanup(self, store=True):
        if store:
            for source_id in self.get_live_source_ids():
                self._store_live_source(source_id)
        self._live_sources = {}
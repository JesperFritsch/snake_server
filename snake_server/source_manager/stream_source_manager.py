import logging
from typing import Dict
from pathlib import Path

from snake_server.stream_source.interfaces.stream_source_interface import IStreamSource, ILiveStreamSource
from snake_server.utils import SingletonMeta

log = logging.getLogger(Path(__file__).stem)

class StreamSourceManager(metaclass=SingletonMeta):
    def __init__(self):
        self._live_sources: Dict[str, ILiveStreamSource] = {}

    def add_source(self, source_id, source: ILiveStreamSource):
        self._live_sources[source_id] = source

    def get_source(self, source_id) -> IStreamSource:
        if not self.source_exists(source_id):
            raise ValueError(f"Source with id {source_id} not found")
        if source_id in self._live_sources:
            return self._live_sources[source_id]
        else:
            raise NotImplementedError("Stored source retrieval not implemented yet")

    def source_exists(self, source_id):
        return source_id in self.get_live_source_ids()

    def get_live_source_ids(self):
        return list(self._live_sources.keys())

    def finish_live_source(self, source_id, store=True):
        if source_id in self._live_sources:
            source_obj = self._live_sources[source_id]
            source_obj.cancel()
            if store:
                raise NotImplementedError("Storing live sources is not implemented yet")
            del self._live_sources[source_id]
        else:
            raise ValueError(f"Source with id {source_id} not found, could not finish")

    def cleanup(self, store=True):
        self._live_sources = {}
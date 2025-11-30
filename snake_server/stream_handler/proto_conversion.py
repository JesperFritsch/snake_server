
import numpy as np
from snake_sim.render.utils import create_color_map
from snake_sim.environment.types import CompleteStepState, EnvMetaData, Coord

from snake_proto_template.python.sim_msgs_pb2 import (
    PixelChanges,
    StepPixelChanges,
    RunMetaData,
)


def env_meta_data_to_proto(env_meta: EnvMetaData) -> RunMetaData:
    """ Convert EnvMetaData to RunMetaData protobuf message """
    proto = RunMetaData()
    proto.width = env_meta.base_map.shape[1]
    proto.height = env_meta.base_map.shape[0]
    proto.free_value = env_meta.free_value
    proto.blocked_value = env_meta.blocked_value
    proto.food_value = env_meta.food_value
    for s_id, s_val in env_meta.snake_values.items():
        snake_proto = proto.snake_values[s_id]
        proto.snake_ids.append(s_id)
        snake_proto.head_value = s_val['head_value']
        snake_proto.body_value = s_val['body_value']
    proto.base_map_dtype = str(env_meta.base_map_dtype)
    proto.base_map = env_meta.base_map.tobytes()
    color_map = create_color_map(env_meta.snake_values)
    for value, color in color_map.items():
        color_proto = proto.color_mapping[value]
        color_proto.r = color[0]
        color_proto.g = color[1]
        color_proto.b = color[2]
    return proto


def create_pixel_change_proto_msg(change, full_state: bool = False) -> PixelChanges:
    payload = PixelChanges()
    payload.full_state = full_state
    for (x, y), color in change:
        pixel = payload.pixels.add()
        pixel.coord.x = x
        pixel.coord.y = y
        pixel.color.r = color[0]
        pixel.color.g = color[1]
        pixel.color.b = color[2]
    return payload
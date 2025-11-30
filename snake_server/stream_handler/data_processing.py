import numpy as np

from typing import List, Tuple


def get_diffs(old: np.ndarray, new: np.ndarray) -> List[Tuple[int, int, int]]:
    """ Get the differences between two maps as a list of (x, y, value) tuples """
    diffs = []
    if old is None:
        old = np.full_like(new, -1, dtype=int)  # Assume -1 is not a valid value in the map
    if old.shape != new.shape:
        raise ValueError("Old and new maps must have the same shape to compute diffs")
    changed_positions = np.argwhere(old != new)
    for pos in changed_positions:
        y, x = pos
        diffs.append((x, y, int(new[x, y])))
    return diffs


def make_color_changes(diffs: List[tuple[int, int, int]], color_map: dict) -> List[tuple[tuple[int, int], tuple[int, int, int]]]:
    """ Convert diffs to color changes using the provided color map """
    color_changes = []
    for x, y, value in diffs:
        color = color_map.get(value, (0, 0, 0))  # Default to black if value not in color map
        color_changes.append(((x, y), color))
    return color_changes
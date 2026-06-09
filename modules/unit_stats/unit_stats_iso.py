"""Structures data from `modules.data_iso.UNIT_CLASSES`."""

from __future__ import annotations

import math
from typing import Self

from modules.data_iso import UNIT_CLASSES

from .unit_stats_generic import _UnitStatsGeneric


def get_unit_cost(unit_cls_str: str) -> int:
    """Returns the cost of a unit before it is instantiated, e.g pre-purchase."""
    unit_stats = UnitStatsIso.from_data(unit_cls_str)
    return unit_stats.cost


def get_unit_size(unit_cls_str: str) -> tuple[int, int]:
    """Returns the size of a unit before it is instantiated, e.g pre-purchase."""
    unit_stats = UnitStatsIso.from_data(unit_cls_str)
    return unit_stats.size


class UnitStatsIso(_UnitStatsGeneric, frozen=True):
    """Static unit stats, specialized for the isometric game."""

    # optional:
    height: int = 0
    hull_rotation_speed: float = math.inf
    turret_rotation_speed: float = math.inf
    rifle_length: float = 2.0
    rifle_thickness: float = 0.4
    turret_width: int = 0
    turret_depth: int = 0
    turret_height: int = 0
    barrel_length: int = 0
    barrel_width: int = 0
    barrel_height: int = 0
    turret_offset_x: int = 0
    turret_offset_y: int = 0
    rocket_length: float = 0
    rocket_thickness: float = 0

    @classmethod
    def from_data(cls, unit_type_str: str) -> Self:
        return cls._from_mapping(UNIT_CLASSES[unit_type_str])

"""Structures data from `modules.data_2d.UNIT_CLASSES`."""

from __future__ import annotations

from typing import Self

from modules.data_2d import UNIT_CLASSES
from modules.unit_stats.unit_stats import UnitStats


def get_unit_cost(unit_cls_str: str) -> int:
    """Returns the cost of a unit before it is instantiated, e.g pre-purchase."""
    unit_stats = UnitStats2d.from_data(unit_cls_str)
    return unit_stats.cost


def get_unit_size(unit_cls_str: str) -> tuple[int, int]:
    """Returns the size of a unit before it is instantiated, e.g pre-purchase."""
    unit_stats = UnitStats2d.from_data(unit_cls_str)
    return unit_stats.size


class UnitStats2d(UnitStats, frozen=True):
    """Static unit stats, specialized for the isometric game."""

    @classmethod
    def from_data(cls, unit_type_str: str) -> Self:
        return cls._from_mapping(UNIT_CLASSES[unit_type_str])

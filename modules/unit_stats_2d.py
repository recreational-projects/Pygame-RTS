"""Structures data in `modules.data_2d.UNIT_CLASSES`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from dataclass_wizard import fromdict  # handles structuring from nested dicts
from dataclass_wizard.serial_json import JSONWizard

from modules.data_2d import UNIT_CLASSES


@dataclass(kw_only=True, frozen=True)
class WeaponStats:
    """Static unit stats for a weapon."""

    name: str
    damage: int
    fire_rate: float
    projectile_speed: int
    projectile_length: int
    projectile_width: int
    cooldown: int = 0


def get_unit_cost(unit_cls_str: str) -> int:
    """Returns the cost of a unit before it is instantiated, e.g pre-purchase."""
    unit_stats = UnitStats.from_data(unit_cls_str)
    return unit_stats.cost


def get_unit_size(unit_cls_str: str) -> tuple[int, int]:
    """Returns the size of a unit before it is instantiated, e.g pre-purchase."""
    unit_stats = UnitStats.from_data(unit_cls_str)
    return unit_stats.size


@dataclass(kw_only=True, frozen=True)
class UnitStats(JSONWizard):
    """Static unit stats.

    Inherits from JSONWizard to allow structuring from nested dicts.
    """

    cost: int
    hp: int
    starting_credits: int = 0  # HQ only?
    speed: float
    attack_range: int
    sight_range: int
    size: tuple[int, int]  # TODO: ideally would use IntPoint here, but needs custom structuring
    # optional:
    is_building: bool = False
    air: bool = False
    income: int | None = None
    income_interval: int = 300
    fly_height: int | None = None
    production_time: int | None = None
    gate_width: int = 20
    half_door_offset: int = 15
    door_color: tuple[int, int, int] = (60, 60, 60)
    # TODO: ideally would use ColorLike here, but needs custom structuring
    weapons: list[WeaponStats] = field(default_factory=list)
    producible: list[str] = field(default_factory=list)

    @classmethod
    def from_data(cls, unit_type_str: str) -> Self:
        return cls._from_dict(UNIT_CLASSES[unit_type_str])

    @classmethod
    # pyrefly: ignore [implicit-any-type-argument]
    def _from_dict(cls, o: dict) -> Self:
        instance = fromdict(cls, o)
        if instance.air and (instance.fly_height is None or instance.fly_height <= 0):
            raise ValueError("`air` units must have a `fly_height` > 0")

        return instance

"""Structures data from `modules.data_2d.UNIT_CLASSES`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, Field

from modules.data_2d import UNIT_CLASSES

if TYPE_CHECKING:
    from collections.abc import Mapping


class WeaponStats(BaseModel, frozen=True):
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


class UnitStats(BaseModel, frozen=True):
    """Static unit stats."""

    cost: int
    hp: int
    starting_credits: int = 0  # HQ only?
    speed: float
    attack_range: int
    sight_range: int
    size: tuple[int, int]  # TODO: ideally would use IntPoint here, but needs custom structuring
    # optional:
    is_building: bool = False
    is_air: bool = Field(alias="air", default=False)
    income: int | None = None
    income_interval: int = 300
    fly_height: int | None = None
    production_time: int | None = None
    gate_width: int = 20
    half_door_offset: int = 15
    door_color: tuple[int, int, int] = (60, 60, 60)
    # TODO: ideally would use ColorLike here, but needs custom structuring
    weapons: list[WeaponStats] = Field(default_factory=list)
    producible: list[str] = Field(default_factory=list)
    turret_offset: tuple[int, int] = (0, -3)  # TODO: ideally would use IntPoint here
    barrel_offset: tuple[int, int] = (10, 0)  # TODO: ideally would use IntPoint here

    def __post_init__(self) -> None:
        if self.is_air and (self.fly_height is None or self.fly_height <= 0):
            raise ValueError("`air` units must have a `fly_height` > 0")

        if not self.is_building and self.producible:
            raise ValueError("Non `is-building` units cannot have non-empty `producible`")

        if not self.is_building and self.income is not None:
            raise ValueError("Non `is-building` units cannot have non-`None` `income`")

    @classmethod
    def from_data(cls, unit_type_str: str) -> Self:
        return cls._from_mapping(UNIT_CLASSES[unit_type_str])

    @classmethod
    def _from_mapping(cls, mapping: Mapping[str, Any]) -> Self:
        return cls.model_validate(mapping, strict=True, extra="forbid")

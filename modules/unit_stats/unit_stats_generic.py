"""Implements a generic data structure for read-only unit stats."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, Field

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


class _UnitStatsGeneric(BaseModel, ABC, frozen=True):
    """Static unit stats."""

    cost: int
    hp: int
    speed: float
    attack_range: int
    sight_range: int
    size: tuple[int, int]  # TODO: ideally would use IntPoint here, but needs custom structuring

    # optional:
    starting_credits: int = 0  # HQ only?
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
    def _from_mapping(cls, mapping: Mapping[str, Any]) -> Self:
        return cls.model_validate(mapping, strict=True, extra="forbid")

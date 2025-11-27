from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.constants import (
    GDI_COLOR,
    NOD_COLOR,
    Team,
)
from src.game_objects.buildings.barracks import Barracks
from src.game_objects.buildings.building import Building
from src.game_objects.buildings.power_plant import PowerPlant
from src.game_objects.buildings.war_factory import WarFactory
from src.game_objects.units.harvester import Harvester
from src.game_objects.units.infantry import Infantry
from src.game_objects.units.tank import Tank
from src.geometry import (
    calculate_formation_positions,
    is_valid_building_position,
    snap_to_grid,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    import pygame as pg

    from src.game_objects.game_object import GameObject

BASE_POWER = 300
BASE_PRODUCTION_TIME = 180


class Headquarters(Building):
    """Main base building, resource storage, production hub."""

    # Override base class(es):
    COST = 2000
    SIZE = 80, 80

    def __init__(
        self, *, position: pg.typing.SequenceLike, team: Team, font: pg.Font
    ) -> None:
        super().__init__(
            position=position,
            team=team,
            color=GDI_COLOR if team == Team.GDI else NOD_COLOR,
            font=font,
        )
        self.max_health = 1200
        self.health = self.max_health
        self.iron: int = 1500
        self.production_queue: list[type[GameObject]] = []
        self.production_timer: float = 0
        self.pending_building: type[Building] | None = None
        self.pending_building_pos: pg.typing.SequenceLike | None = None

        # Calculated every update():
        self.power_usage: int = 0
        self.power_output: int = 0

    def _power_output(self, *, friendly_buildings: Iterable[Building]) -> int:
        return BASE_POWER + sum(
            b.POWER_OUTPUT
            for b in friendly_buildings
            if isinstance(b, PowerPlant) and b.health > 0
        )

    def _power_usage(
        self,
        *,
        friendly_units: Iterable[GameObject],
        friendly_buildings: Iterable[Building],
    ) -> int:
        return sum(u.POWER_USAGE for u in friendly_units) + sum(
            b.POWER_USAGE for b in friendly_buildings if b != self
        )

    @property
    def has_enough_power(self) -> bool:
        return self.power_output >= self.power_usage

    def get_production_time(
        self, *, unit_class: type[GameObject], friendly_buildings: Iterable[Building]
    ) -> float:
        if unit_class == Infantry:
            barracks_count = len(
                [
                    b
                    for b in friendly_buildings
                    if isinstance(b, Barracks) and b.health > 0
                ]
            )
            return BASE_PRODUCTION_TIME * (0.9**barracks_count)

        if unit_class in [Tank, Harvester]:
            warfactory_count = len(
                [
                    b
                    for b in friendly_buildings
                    if isinstance(b, WarFactory) and b.health > 0
                ]
            )
            return BASE_PRODUCTION_TIME * (0.9**warfactory_count)

        return BASE_PRODUCTION_TIME

    def update(
        self,
        particles: pg.sprite.Group[Any],
        friendly_units: pg.sprite.Group[Any],
        friendly_buildings: Iterable[Any],
        all_units: pg.sprite.Group[Any],
        *args,
        **kwargs,
    ) -> None:
        super().update(particles, *args, **kwargs)
        self.power_output = self._power_output(friendly_buildings=friendly_buildings)
        self.power_usage = self._power_usage(
            friendly_units=friendly_units, friendly_buildings=friendly_buildings
        )
        if (
            self.production_queue
            and not self.production_timer
            and self.has_enough_power
        ):
            self.production_timer = self.get_production_time(
                unit_class=self.production_queue[0],
                friendly_buildings=friendly_buildings,
            )

        if self.production_queue:
            self.production_timer -= 1 if self.has_enough_power else 0.5
            if self.production_timer <= 0:
                unit_cls = self.production_queue.pop(0)
                if issubclass(unit_cls, Building):
                    self.pending_building = unit_cls
                    self.pending_building_pos = None

                else:
                    spawn_building: Building = self
                    if unit_cls == Infantry:
                        barracks = [
                            b
                            for b in friendly_buildings
                            if isinstance(b, Barracks) and b.health > 0
                        ]
                        if not barracks:
                            return

                        spawn_building = min(
                            barracks,
                            key=lambda b: self.distance_to(b.position),
                        )

                    elif unit_cls in [Tank, Harvester]:
                        warfactories = [
                            b
                            for b in friendly_buildings
                            if isinstance(b, WarFactory) and b.health > 0
                        ]
                        if not warfactories:
                            return

                        spawn_building = min(
                            warfactories, key=lambda b: self.distance_to(b.position)
                        )
                    spawn_pos = (
                        spawn_building.rect.right + 20,
                        spawn_building.position.y,
                    )
                    new_units = [
                        Harvester(
                            position=spawn_pos,
                            team=self.team,
                            hq=self,
                            font=self.font,
                        )
                        if unit_cls == Harvester
                        else unit_cls(position=spawn_pos, team=self.team)
                    ]
                    formation_positions = calculate_formation_positions(
                        center=spawn_pos,
                        target=None,
                        num_units=len(new_units),
                        direction=0,
                    )
                    for unit, pos in zip(new_units, formation_positions):
                        unit.rect.center = pos
                        unit.formation_target = pos
                        friendly_units.add(unit)
                        all_units.add(unit)

                self.production_timer = (
                    self.get_production_time(
                        unit_class=self.production_queue[0],
                        friendly_buildings=friendly_buildings,
                    )
                    if self.production_queue and self.has_enough_power
                    else 0
                )

    def place_building(
        self,
        *,
        position: pg.typing.SequenceLike,
        unit_cls: type[Building],
        all_buildings: pg.sprite.Group[Any],
    ) -> None:
        snapped_pos = snap_to_grid(position)
        if is_valid_building_position(
            position=snapped_pos,
            team=self.team,
            new_building_cls=unit_cls,
            buildings=all_buildings,
        ):
            all_buildings.add(
                unit_cls(position=snapped_pos, team=self.team, font=self.font)
            )
            self.pending_building = None
            self.pending_building_pos = None
            if self.production_queue and self.has_enough_power:
                self.production_timer = self.get_production_time(
                    unit_class=self.production_queue[0],
                    friendly_buildings=[
                        b for b in all_buildings if b.team == self.team
                    ],
                )

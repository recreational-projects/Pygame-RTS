from __future__ import annotations

from typing import TYPE_CHECKING

from src import geometry
from src.constants import (
    GDI_COLOR,
    NOD_COLOR,
)
from src.game_objects.buildings.barracks import Barracks
from src.game_objects.buildings.building import Building
from src.game_objects.buildings.power_plant import PowerPlant
from src.game_objects.buildings.war_factory import WarFactory
from src.game_objects.units.harvester import Harvester
from src.game_objects.units.infantry import Infantry
from src.game_objects.units.tank import Tank
from src.team import Faction, Team

if TYPE_CHECKING:
    from collections.abc import Iterable

    import pygame as pg

    from src.game import Game
    from src.game_objects.game_object import GameObject


class Headquarters(Building):
    """Main base building, resource storage, production hub."""

    # Override base class(es):
    COST = 2000
    SIZE = 80, 80
    # Class-specific:
    BASE_POWER = 300

    def __init__(self, *, position: pg.typing.Point, team: Team, font: pg.Font) -> None:
        super().__init__(
            position=position,
            team=team,
            color=GDI_COLOR if team.faction == Faction.GDI else NOD_COLOR,
            font=font,
        )
        self.max_health = 1200
        self.health = self.max_health
        self.iron: int = 1500
        self.production_queue: list[type[GameObject]] = []
        self.production_timer: float = 0
        self.pending_building: type[Building] | None = None
        self.pending_building_pos: pg.typing.Point | None = None

        # Calculated every update():
        self.power_usage: int = 0
        self.power_output: int = 0

    @classmethod
    def _power_output(cls, *, friendly_buildings: Iterable[Building]) -> int:
        return cls.BASE_POWER + sum(
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

    def update(self, *args, game: Game, **kwargs) -> None:
        super().update(*args, **kwargs)
        _friendly_buildings = game.team_buildings(self.team)
        _friendly_units = game.team_units(self.team)
        self.power_output = self._power_output(friendly_buildings=_friendly_buildings)
        self.power_usage = self._power_usage(
            friendly_units=_friendly_units, friendly_buildings=_friendly_buildings
        )
        if (
            self.production_queue
            and not self.production_timer
            and self.has_enough_power
        ):
            self.production_timer = game.get_production_time(
                cls=self.production_queue[0], team=self.team
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
                            b for b in _friendly_buildings if isinstance(b, Barracks)
                        ]
                        if not barracks:
                            return

                        spawn_building = min(
                            barracks,
                            key=lambda b: self.distance_to(b.position),
                        )

                    elif unit_cls in [Tank, Harvester]:
                        warfactories = [
                            b for b in _friendly_buildings if isinstance(b, WarFactory)
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
                    formation_positions = geometry.calculate_formation_positions(
                        center=spawn_pos,
                        target=None,
                        num_units=len(new_units),
                        direction=0,
                    )
                    for unit, pos in zip(new_units, formation_positions):
                        unit.rect.center = pos
                        unit.formation_target = pos
                        game.objects.add(unit)

                self.production_timer = (
                    game.get_production_time(
                        cls=self.production_queue[0],
                        team=self.team,
                    )
                    if self.production_queue and self.has_enough_power
                    else 0
                )

    def place_building(
        self,
        *,
        position: pg.typing.Point,
        unit_cls: type[Building],
        game: Game,
    ) -> None:
        """
        Args:
            position:
                Position of new `Building`.
                Function handles snapping to tile grid.
            unit_cls:
                Type of new `Building`.
            game:
        """

        snapped_pos = geometry.snap_to_grid(position)
        if game.is_valid_building_position(
            position=snapped_pos, new_building_class=unit_cls, team=self.team
        ):
            game.objects.add(
                unit_cls(position=snapped_pos, team=self.team, font=self.font)
            )
            self.pending_building = None
            self.pending_building_pos = None
            if self.production_queue and self.has_enough_power:
                self.production_timer = game.get_production_time(
                    cls=self.production_queue[0], team=self.team
                )

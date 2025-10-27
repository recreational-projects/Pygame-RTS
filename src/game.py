from __future__ import annotations

import math
import random
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, Any

import pygame as pg

from src.constants import (
    BASE_PRODUCTION_TIME,
    BUILDING_CONSTRUCTION_RANGE,
    MAP_HEIGHT,
    MAP_WIDTH,
)
from src.game_objects.buildings.barracks import Barracks
from src.game_objects.buildings.building import Building
from src.game_objects.buildings.war_factory import WarFactory
from src.game_objects.units.harvester import Harvester
from src.game_objects.units.infantry import Infantry
from src.game_objects.units.tank import Tank
from src.geometry import Coordinate
from src.particle import Particle
from src.projectile import Projectile

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.game_objects.game_object import GameObject
    from src.team import Team

_Unit = Harvester | Infantry | Tank


@dataclass(kw_only=True)
class Game:
    """Holds game-scoped information (i.e. state) and methods."""

    objects: set[GameObject] = dataclass_field(init=False, default_factory=set)
    """All `GameObject`s. Not other sprites at present."""
    selected_units: set[_Unit] = dataclass_field(init=False, default_factory=set)
    """The currently selected player units."""
    selected_building: Building | None = dataclass_field(init=False, default=None)
    """The currently selected player building.
    NB: only one building can be selected at a time."""

    @property
    def buildings(self) -> set[Building]:
        return {o for o in self.objects if isinstance(o, Building) and o.health > 0}

    @property
    def units(self) -> set[_Unit]:
        return {o for o in self.objects if isinstance(o, _Unit) and o.health > 0}

    def team_buildings(self, team: Team) -> set[Building]:
        return {b for b in self.buildings if b.team == team}

    def team_units(self, team: Team) -> set[_Unit]:
        return {u for u in self.units if u.team == team}

    def handle_collisions(self) -> None:
        """Check for all collisions between units and move them accordingly."""
        for unit in self.units:
            for other in self.units:
                if unit != other and unit.rect.colliderect(other.rect):
                    dist = unit.distance_to(other.position)
                    if dist > 0:
                        push = (
                            0.3
                            if isinstance(unit, Harvester)
                            and isinstance(other, Harvester)
                            else 0.5
                        )
                        d = unit.displacement_to(other.position)
                        unit.rect.x += push * d.x / dist
                        other.rect.y -= push * d.y / dist

    def get_production_time(self, *, cls: type[GameObject], team: Team) -> float:
        _friendly_buildings = self.team_buildings(team)
        if cls == Infantry:
            barracks_count = len(
                [b for b in _friendly_buildings if isinstance(b, Barracks)]
            )
            return BASE_PRODUCTION_TIME * (0.9**barracks_count)

        if cls in [Tank, Harvester]:
            warfactory_count = len(
                [b for b in _friendly_buildings if isinstance(b, WarFactory)]
            )
            return BASE_PRODUCTION_TIME * (0.9**warfactory_count)

        return BASE_PRODUCTION_TIME

    def handle_attacks(
        self,
        *,
        team: Team,
        opposing_team: Team,
        projectiles: pg.sprite.Group[Any],
        particles: pg.sprite.Group[Any],
    ) -> None:
        for unit in self.team_units(team):
            if isinstance(unit, (Tank, Infantry)) and unit.cooldown_timer == 0:
                closest_target, min_dist = None, float("inf")
                if unit.target_object and unit.target_object.health > 0:
                    dist = unit.distance_to(unit.target_object.position)
                    if dist <= unit.ATTACK_RANGE:
                        closest_target, min_dist = unit.target_object, dist

                if not closest_target:
                    for obj in (
                        *self.team_units(opposing_team),
                        *self.team_buildings(opposing_team),
                    ):
                        dist = unit.distance_to(obj.position)
                        if dist <= unit.ATTACK_RANGE and dist < min_dist:
                            closest_target, min_dist = obj, dist

                if closest_target:
                    unit.target_object = closest_target
                    unit.target = closest_target.position
                    if isinstance(unit, Tank):
                        d = unit.displacement_to(closest_target.position)
                        unit.angle = math.degrees(
                            math.atan2(d.y, d.x)
                        )  # Updated to match Tank's angle calculation
                        projectiles.add(
                            Projectile(
                                unit.position,
                                closest_target,
                                unit.attack_damage,
                                unit.team,
                            )
                        )
                        unit.recoil = 5
                        barrel_angle = math.radians(unit.angle)
                        smoke_x = unit.position.x + math.cos(barrel_angle) * (
                            unit.rect.width // 2 + 12
                        )
                        smoke_y = unit.position.y + math.sin(barrel_angle) * (
                            unit.rect.width // 2 + 12
                        )
                        for _ in range(5):
                            particles.add(
                                Particle(
                                    (smoke_x, smoke_y),
                                    random.uniform(-1.5, 1.5),
                                    random.uniform(-1.5, 1.5),
                                    random.randint(6, 10),
                                    pg.Color(100, 100, 100),
                                    20,
                                )
                            )
                    else:
                        closest_target.health -= unit.attack_damage
                        closest_target.under_attack = True
                        for _ in range(3):
                            particles.add(
                                Particle(
                                    unit.position,
                                    random.uniform(-1, 1),
                                    random.uniform(-1, 1),
                                    4,
                                    pg.Color(255, 200, 100),
                                    10,
                                )
                            )
                        if closest_target.health <= 0:
                            closest_target.kill()
                            unit.target = unit.target_object = None

                    unit.cooldown_timer = unit.ATTACK_COOLDOWN_PERIOD

    def handle_projectiles(
        self,
        projectiles: Iterable[Projectile],
        particles: pg.sprite.Group[Any],
    ) -> None:
        for projectile in projectiles:
            # Check collision with all enemy units and buildings, not just the target
            enemy_units = [u for u in self.units if u.team != projectile.team]
            enemy_buildings = [b for b in self.buildings if b.team != projectile.team]
            for e in enemy_units + enemy_buildings:
                if projectile.rect.colliderect(e.rect):
                    e.health -= projectile.damage
                    e.under_attack = True  # Set under_attack when damage is applied
                    for _ in range(5):
                        particles.add(
                            Particle(
                                projectile.position,
                                random.uniform(-2, 2),
                                random.uniform(-2, 2),
                                6,
                                pg.Color(255, 200, 100),
                                15,
                            )
                        )
                    projectile.kill()
                    if e.health <= 0:
                        e.kill()

                    break

    @staticmethod
    def _rect_is_within_map(rect: pg.typing.RectLike) -> bool:
        """Return whether `rect` is within the map."""
        map_rect = pg.Rect(0, 0, MAP_WIDTH, MAP_HEIGHT)
        return map_rect.contains(rect)

    def _is_near_friendly_building(
        self, *, position: pg.typing.Point, team: Team
    ) -> bool:
        """Return whether `position` is within construction range of `team`'s buildings."""
        pos = Coordinate(position)
        return any(
            pos.distance_to(building.position) < BUILDING_CONSTRUCTION_RANGE
            for building in self.team_buildings(team)
        )

    def _rect_collides_with_building(
        self,
        *,
        rect: pg.Rect,
    ) -> bool:
        """Return whether `rect` collides with any building."""
        return any(rect.colliderect(building.rect) for building in self.buildings)

    def is_valid_building_position(
        self,
        *,
        position: pg.typing.Point,
        new_building_class: type[Building],
        team: Team,
    ) -> bool:
        new_building_footprint = pg.Rect(position, new_building_class.SIZE)
        return all(
            (
                self._rect_is_within_map(new_building_footprint),
                self._is_near_friendly_building(position=position, team=team),
                not self._rect_collides_with_building(rect=new_building_footprint),
            )
        )

    def delete_selected_building(self) -> None:
        """Delete the selected building."""
        if self.selected_building:
            self.objects.remove(self.selected_building)
            self.selected_building = None

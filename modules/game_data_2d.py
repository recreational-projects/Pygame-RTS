"""Implements GameData for 2d game."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pygame as pg
from pygame.math import Vector2

from modules.geometry import check_collision, closest_point_on_rect
from modules.particles import create_explosion_2d
from modules.team import Team
from modules.units_2d import Infantry
from modules.world_2d import find_free_spawn_position

if TYPE_CHECKING:
    from pygame.typing import IntPoint

    from modules.ai_2d import AI
    from modules.camera.camera_2d import Camera2d
    from modules.fog_of_war import FogOfWar2d
    from modules.particles import GenericParticle
    from modules.production_interface_2d import ProductionInterface
    from modules.projectile.projectile_2d import Projectile2d
    from modules.spatial_hash import SpatialHash2d
    from modules.units_2d import Headquarters, Unit2d


@dataclass(kw_only=True)
class GameData2d:
    """Global game data for 2d game."""

    ai_units: pg.sprite.Group[Unit2d]
    global_units: pg.sprite.Group[Unit2d]
    global_buildings: pg.sprite.Group[Unit2d]
    projectiles: pg.sprite.Group[Projectile2d]
    particles: pg.sprite.Group[GenericParticle]
    selected_units: pg.sprite.Group[Unit2d]
    unit_groups: dict[Team, Any] = field(default_factory=dict)
    hqs: dict[Team, Any] = field(default_factory=dict)
    player_team: Team | None
    player_allies: frozenset[Team] = field(default_factory=frozenset)
    alliances: dict[Team, frozenset[Team]] = field(default_factory=dict)
    fog_of_war: FogOfWar2d
    camera: Camera2d
    map_color: pg.Color
    map_width: int
    map_height: int
    game_mode: str
    ais: list[AI] = field(default_factory=list)
    interface_rect: pg.Rect
    teams: list[Team] = field(default_factory=list)

    # optional:
    player_hq: Headquarters | None = field(default=None)
    interface: ProductionInterface | None = field(default=None)
    spectator_mode: bool = field(default=False)

    # internal:
    player_units: pg.sprite.Group[Unit2d] = field(init=False)
    selected_building: Any = field(init=False, default=None)
    selecting: bool = field(init=False, default=False)
    select_start: IntPoint | None = field(init=False, default=None)
    select_rect: pg.Rect | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.player_units = pg.sprite.Group()
        for team in self.teams:
            units = pg.sprite.Group()
            for _ in range(3):
                _hq = self.hqs[team]
                offset = find_free_spawn_position(
                    target_pos=_hq.position, global_buildings=self.global_buildings, global_units=self.global_units
                )
                units.add(Infantry(position=offset, team=team, hq=_hq))

            self.unit_groups[team] = units

        if not self.spectator_mode:
            self.player_units = self.unit_groups[Team.RED]
            for team in self.teams:
                if team != Team.RED:
                    self.ai_units.add(self.unit_groups[team])
        else:
            for team in self.teams:
                self.ai_units.add(self.unit_groups[team])

        for ug in self.unit_groups.values():
            self.global_units.add(ug)
        for hq in self.hqs.values():
            self.global_buildings.add(hq)

    def cleanup_dead_entities(self) -> None:
        """Removes dead entities from groups, cleans up particles."""
        group = self.global_units
        dead = [obj for obj in group if obj.health <= 0]
        for d in dead:
            group.remove(d)
            if hasattr(d, "plasma_burn_particles"):
                for p in d.plasma_burn_particles:
                    if hasattr(p, "kill"):
                        p.kill()

                d.plasma_burn_particles = []

        # Cleanup dead buildings
        group = self.global_buildings
        dead = [obj for obj in group if obj.health <= 0]
        for d in dead:
            group.remove(d)
            if hasattr(d, "plasma_burn_particles"):
                for p in d.plasma_burn_particles:
                    if hasattr(p, "kill"):
                        p.kill()

                d.plasma_burn_particles = []

        # Cleanup unit groups
        for ug in self.unit_groups.values():
            dead = [u for u in ug if u.health <= 0]
            for d in dead:
                ug.remove(d)
                if hasattr(d, "plasma_burn_particles"):
                    for p in d.plasma_burn_particles:
                        if hasattr(p, "kill"):
                            p.kill()

                    # pyrefly: ignore [implicit-any-empty-container]
                    d.plasma_burn_particles = []

    def handle_projectiles(self) -> None:
        """Updates projectiles, checks hits on enemies, applies damage/explosions."""
        for projectile in self.projectiles:
            proj_allies = self.alliances[projectile.team]
            enemy_units = [u for u in self.global_units if u.team not in proj_allies and u.health > 0]
            enemy_buildings = [b for b in self.global_buildings if b.team not in proj_allies and b.health > 0]

            hit = False
            for e in enemy_units + enemy_buildings:
                if check_collision(entity=e, projectile=projectile):
                    if e.take_damage(projectile.damage):
                        create_explosion_2d(position=e.position, particles=self.particles, team=e.team)
                        attacker_hq = self.hqs[projectile.team]
                        if e.hq:
                            if e.is_building:
                                e.hq.game_stats["buildings_lost"] += 1
                                attacker_hq.game_stats["buildings_destroyed"] += 1
                            else:
                                e.hq.game_stats["units_lost"] += 1
                                attacker_hq.game_stats["units_destroyed"] += 1

                            self.global_units.remove(e)
                            for ug in self.unit_groups.values():
                                if e in ug:
                                    ug.remove(e)

                        elif e in self.global_buildings:
                            self.global_buildings.remove(e)

                    hit = True
                    break

            if hit:
                projectile.kill()

    def handle_attacks(
        self,
        *,
        team: Team,
        unit_hash: SpatialHash2d,
        building_hash: SpatialHash2d,
        allied_teams: frozenset[Team],
    ) -> None:
        """For a team, finds targets in sight range and shoots if in attack range; handles chasing.

        :param team: Attacking team.
        :param particles: Group to add particles to.
        :param unit_hash: Unit spatial hash.
        :param building_hash: Building spatial hash.
        :param allied_teams: Team alliances.
        """
        armed_entities = [u for u in self.global_units if u.team == team and u.health > 0]
        armed_entities.extend(b for b in self.global_buildings if b.team == team and b.weapons and b.health > 0)

        for entity in armed_entities:
            if entity.last_shot_time != 0:
                continue

            closest_unit_in_range = None
            min_unit_dist_in_range = float("inf")
            closest_building_in_range = None
            min_building_dist_in_range = float("inf")
            closest_overall = None
            min_overall_dist = float("inf")
            candidates = unit_hash.query(entity.position, entity.sight_range) + building_hash.query(
                entity.position, entity.sight_range
            )
            for obj in candidates:
                if obj.team not in allied_teams and obj.health > 0:
                    if obj.is_building:
                        closest_pt = closest_point_on_rect(rect=obj.rect, pos=entity.position)
                        dist = Vector2(closest_pt).distance_to(entity.position)
                    else:
                        dist = entity.distance_to(obj.position)
                    if dist <= entity.sight_range:
                        if dist < min_overall_dist:
                            closest_overall, min_overall_dist = obj, dist

                        if dist <= entity.attack_range:
                            if not obj.is_building:  # unit
                                if dist < min_unit_dist_in_range:
                                    closest_unit_in_range, min_unit_dist_in_range = obj, dist
                            elif dist < min_building_dist_in_range:  # building
                                closest_building_in_range, min_building_dist_in_range = obj, dist

            if closest_unit_in_range:
                closest_target = closest_unit_in_range
            elif closest_building_in_range:
                closest_target = closest_building_in_range
            elif closest_overall:
                closest_target = closest_overall
            else:
                closest_target = None

            if closest_target:
                entity.attack_target = closest_target
                if closest_target.is_building:
                    closest_pt = closest_point_on_rect(rect=closest_target.rect, pos=entity.position)
                    dir_c = Vector2(closest_pt) - entity.position
                    dist_to_target = dir_c.length()
                else:
                    dist_to_target = entity.distance_to(closest_target.position)
                # Shoot if in range
                if dist_to_target <= entity.attack_range:
                    entity.shoot(target=closest_target, projectiles=self.projectiles, particles=self.particles)

                elif not entity.is_building:
                    # Chase the target
                    if closest_target.is_building:
                        chase_pos = entity.get_chase_position_for_building(closest_target)
                        entity.move_target = chase_pos if chase_pos is not None else None
                    else:
                        entity.move_target = closest_target.position

"""Implements GameData for isometric game."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pygame.math import Vector2

from modules.geometry import check_collision, closest_point_on_rect
from modules.particles import create_explosion_iso

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    import pygame as pg
    from pygame.typing import IntPoint

    from modules.ai_iso import AI
    from modules.camera.camera_iso import CameraIso
    from modules.fog_of_war import FogOfWarIso
    from modules.particles import GenericParticle
    from modules.production_interface_iso import ProductionInterface
    from modules.projectile.projectile_iso import ProjectileIso
    from modules.spatial_hash import SpatialHashIso
    from modules.team import Team
    from modules.terrain_feature_iso import TerrainFeature
    from modules.units_iso import Headquarters, UnitIso


@dataclass(kw_only=True)
class GameDataIso:
    """Global game data for isometric game."""

    player_units: pg.sprite.Group[UnitIso]
    ai_units: pg.sprite.Group[UnitIso]
    global_units: pg.sprite.Group[UnitIso]
    global_buildings: pg.sprite.Group[UnitIso]
    projectiles: pg.sprite.Group[ProjectileIso]
    particles: pg.sprite.Group[GenericParticle]
    selected_units: pg.sprite.Group[UnitIso]
    unit_groups: MutableMapping[Team, Any] = field(default_factory=dict)
    hqs: dict[Team, Any] = field(default_factory=dict)
    player_team: Team | None
    player_allies: frozenset[Team] = field(default_factory=frozenset)
    alliances: dict[Team, frozenset[Team]] = field(default_factory=dict)
    fog_of_war: FogOfWarIso
    camera: CameraIso
    map_color: pg.Color
    map_width: int
    map_height: int
    game_mode: str
    ais: list[AI]
    interface_rect: pg.Rect
    teams: list[Team]

    tile_timer: int
    num_tx: int
    num_ty: int
    tile_ownership: list[list[Any]]
    terrain_features: list[TerrainFeature]
    previous_fitness: dict[Team, int]
    current_fitness: dict[Team, int]
    fitness_deltas: dict[Team, int]

    # optional:
    player_hq: Headquarters | None = field(default=None)
    interface: ProductionInterface | None = field(default=None)
    spectator_mode: bool = field(default=False)

    # internal:
    selected_building: Any = field(init=False, default=None)
    selecting: bool = field(init=False, default=False)
    select_start: IntPoint | None = field(init=False, default=None)
    select_rect: pg.Rect | None = field(init=False, default=None)

    def cleanup_dead_entities(self) -> None:
        group = self.global_units
        dead = [obj for obj in group if obj.health <= 0]
        for d in dead:
            group.remove(d)
            if hasattr(d, "plasma_burn_particles"):
                for p in d.plasma_burn_particles:
                    if hasattr(p, "kill"):
                        p.kill()

                d.plasma_burn_particles.clear()

        group = self.global_buildings
        dead = [obj for obj in group if obj.health <= 0]
        for d in dead:
            group.remove(d)
            if hasattr(d, "plasma_burn_particles"):
                for p in d.plasma_burn_particles:
                    if hasattr(p, "kill"):
                        p.kill()

                d.plasma_burn_particles.clear()

        for ug in self.unit_groups.values():
            dead = [u for u in ug if u.health <= 0]
            for d in dead:
                ug.remove(d)
                if hasattr(d, "plasma_burn_particles"):
                    for p in d.plasma_burn_particles:
                        if hasattr(p, "kill"):
                            p.kill()

                    d.plasma_burn_particles.clear()

    def handle_projectiles(self) -> None:
        from modules.units_iso import UnitIso  # TODO: refactor

        for projectile in self.projectiles:
            proj_allies = self.alliances[projectile.team]
            enemy_units = [u for u in self.global_units if u.team not in proj_allies and u.health > 0]
            enemy_buildings = [b for b in self.global_buildings if b.team not in proj_allies and b.health > 0]
            hit = False
            for e in enemy_units + enemy_buildings:
                if check_collision(entity=e, projectile=projectile):
                    if e.take_damage(projectile.damage):
                        create_explosion_iso(position=e.position, particles=self.particles, team=e.team)
                        attacker_hq = self.hqs[projectile.team]
                        if e.hq:
                            if e.is_building:
                                e.hq.game_stats["buildings_lost"] += 1
                                attacker_hq.game_stats["buildings_destroyed"] += 1
                            else:
                                e.hq.game_stats["units_lost"] += 1
                                attacker_hq.game_stats["units_destroyed"] += 1

                        if e in self.global_units:
                            self.global_units.remove(e)
                            if isinstance(e, UnitIso):
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
        unit_hash: SpatialHashIso,
        building_hash: SpatialHashIso,
        allied_teams: frozenset[Team],
    ) -> None:
        """For a team, finds targets in sight range and shoots if in attack range; handles chasing.

        :param team: Attacking team.
        :param unit_hash: Unit spatial hash.
        :param building_hash: Building spatial hash.
        :param allied_teams: Team alliances.
        """
        armed_entities = [u for u in self.global_units if u.team == team and u.weapons and u.health > 0]
        armed_entities.extend(b for b in self.global_buildings if b.team == team and b.weapons and b.health > 0)
        for entity in armed_entities:
            closest_unit_in_range = None
            min_unit_dist = float("inf")
            closest_building_in_range = None
            min_building_dist = float("inf")
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
                            closest_overall = obj
                            min_overall_dist = dist

                        if dist <= entity.attack_range:
                            if not obj.is_building:
                                if dist < min_unit_dist:
                                    closest_unit_in_range = obj
                                    min_unit_dist = dist
                            elif dist < min_building_dist:
                                closest_building_in_range = obj
                                min_building_dist = dist

            if closest_unit_in_range:
                closest_target = closest_unit_in_range
            elif closest_building_in_range:
                closest_target = closest_building_in_range
            elif closest_overall:
                closest_target = closest_overall
            else:
                continue

            entity.attack_target = closest_target
            if closest_target.is_building:
                closest_pt = closest_point_on_rect(rect=closest_target.rect, pos=entity.position)
                dir_vec = Vector2(closest_pt) - entity.position
                dist_to_target = dir_vec.length()
            else:
                dir_vec = Vector2(closest_target.position) - entity.position
                dist_to_target = dir_vec.length()

            if dir_vec.length() > 0:
                entity.target_turret_angle = math.atan2(dir_vec.y, dir_vec.x)

            if dist_to_target <= entity.attack_range:
                entity.shoot(target=closest_target, projectiles=self.projectiles, particles=self.particles)

            elif not entity.is_building:
                if closest_target.is_building:
                    chase_pos = entity.get_chase_position_for_building(closest_target)
                    entity.move_target = chase_pos if chase_pos is not None else None
                else:
                    entity.move_target = closest_target.position

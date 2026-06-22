"""Implements GameData for isometric game."""

from __future__ import annotations

import math
import random
from dataclasses import InitVar, dataclass, field
from typing import TYPE_CHECKING, Any

import pygame as pg
from pygame.math import Vector2

from modules.ai import AiIso
from modules.camera.camera_iso import CameraIso
from modules.data_iso import (
    CONSOLE_HEIGHT,
    MAP_HEIGHT,
    MAP_WIDTH,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    STARTING_POSITIONS_EDGE_OFFSET,
    TILE_SIZE,
)
from modules.fog_of_war import FogOfWarIso
from modules.game_data.game_data_generic import determine_sides, get_starting_positions
from modules.geometry import check_collision, closest_point_on_rect
from modules.particle import create_explosion_iso
from modules.production_interface import ProductionInterfaceIso
from modules.team import Team
from modules.terrain_feature_iso import generate_terrain_features
from modules.units.units_iso import Headquarters, Infantry

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from pygame.typing import IntPoint, Point

    from modules.particle import Particle
    from modules.projectile import ProjectileIso
    from modules.spatial_hash import SpatialHashIso
    from modules.terrain_feature_iso import TerrainFeature
    from modules.units import UnitIso


@dataclass(kw_only=True)
class GameDataIso:
    """Global game data for isometric game."""

    # init-only:
    game_mode: InitVar[str]
    map_name: InitVar[str]

    # init:
    map_color: pg.Color
    map_width: int
    map_height: int

    # optional:
    spectator_mode: bool = field(default=False)

    # internal:
    teams: list[Team] = field(init=False, default_factory=list)  # currently, order is important
    alliances: dict[Team, frozenset[Team]] = field(init=False, default_factory=dict)
    global_units: pg.sprite.Group[UnitIso] = field(init=False, default_factory=pg.sprite.Group)
    global_buildings: pg.sprite.Group[UnitIso] = field(init=False, default_factory=pg.sprite.Group)
    ai_units: pg.sprite.Group[UnitIso] = field(init=False, default_factory=pg.sprite.Group)
    unit_groups: MutableMapping[Team, pg.sprite.Group[UnitIso]] = field(init=False, default_factory=dict)
    hqs: dict[Team, Any] = field(default_factory=dict)
    camera: CameraIso = field(init=False)
    player_team: Team | None = field(init=False, default=None)
    player_hq: Headquarters | None = field(init=False, default=None)
    player_units: pg.sprite.Group[UnitIso] = field(init=False, default_factory=pg.sprite.Group)
    ais: list[AiIso] = field(init=False, default_factory=list)
    player_allies: frozenset[Team] = field(init=False, default_factory=frozenset)
    interface: ProductionInterfaceIso | None = field(init=False, default=None)
    interface_rect: pg.Rect = field(init=False)
    fog_of_war: FogOfWarIso = field(init=False)
    selected_building: Any = field(init=False, default=None)
    selecting: bool = field(init=False, default=False)
    select_start: IntPoint | None = field(init=False, default=None)
    select_rect: pg.Rect | None = field(init=False, default=None)
    projectiles: pg.sprite.Group[ProjectileIso] = field(init=False, default_factory=pg.sprite.Group)
    particles: pg.sprite.Group[Particle] = field(init=False, default_factory=pg.sprite.Group)
    selected_units: pg.sprite.Group[UnitIso] = field(init=False, default_factory=pg.sprite.Group)

    terrain_features: list[TerrainFeature] = field(init=False, default_factory=list)
    num_tx: int = field(init=False)
    num_ty: int = field(init=False)
    tile_ownership: list[list[Any]] = field(init=False, default_factory=list)
    tile_timer: int = field(init=False, default=0)
    current_fitness: dict[Team, int] = field(init=False, default_factory=dict)
    previous_fitness: dict[Team, int] = field(init=False, default_factory=dict)
    fitness_deltas: dict[Team, int] = field(init=False, default_factory=dict)

    def __post_init__(self, *, game_mode: str, map_name: str) -> None:
        self.camera = CameraIso(
            map_width=self.map_width, map_height=self.map_height, width=SCREEN_WIDTH, height=SCREEN_HEIGHT
        )
        player_side, enemy_side = determine_sides(game_mode)
        teams = player_side + enemy_side
        start_positions = get_starting_positions(
            map_width=self.map_width,
            map_height=self.map_height,
            num_players=len(teams),
            edge_dist=STARTING_POSITIONS_EDGE_OFFSET,
        )
        for i, team in enumerate(teams):
            pos = start_positions[i]
            hq = Headquarters(position=pos, team=team)
            hq.map_width = self.map_width
            hq.map_height = self.map_height
            hq.game_stats["buildings_constructed"] += 1
            hq.rally_point = Vector2(pos[0] + (100 if pos[0] < self.map_width / 2 else -100), pos[1])
            self.hqs[team] = hq
            if team in set(player_side):
                self.alliances[team] = frozenset(player_side)
            else:
                self.alliances[team] = frozenset(enemy_side)

            if not self.spectator_mode and team == Team.RED:
                continue

            center_x = self.map_width / 2
            center_y = self.map_height / 2
            build_dir = math.atan2(center_y - pos[1], center_x - pos[0])
            random.seed(team.value * 12345)
            self.ais.append(AiIso(hq=self.hqs[team], preferred_build_direction=build_dir, allies=self.alliances[team]))

        for team in self.teams:
            self._add_initial_infantry(team)

        if not self.spectator_mode:
            self.player_hq = self.hqs[Team.RED]
            self.player_team = Team.RED
            self.player_allies = self.alliances[self.player_team]
            self.interface = ProductionInterfaceIso(hq=self.player_hq)
            self.interface_rect = pg.Rect(SCREEN_WIDTH - 200, 0, 200, SCREEN_HEIGHT - CONSOLE_HEIGHT)
            self.player_units = self.unit_groups[Team.RED]
            for team in self.teams:
                if team != Team.RED:
                    self.ai_units.add(self.unit_groups[team])
        else:
            self.interface_rect = pg.Rect(0, 0, 0, 0)
            self.camera.rect.center = (self.map_width / 2, self.map_height / 2)
            for team in self.teams:
                self.ai_units.add(self.unit_groups[team])

        for ug in self.unit_groups.values():
            self.global_units.add(ug)

        for hq in self.hqs.values():
            self.global_buildings.add(hq)

        self.fog_of_war = FogOfWarIso(
            map_width=self.map_width,
            map_height=self.map_height,
            tile_size=TILE_SIZE,
            spectator_mode=self.spectator_mode,
        )
        self.previous_fitness = dict.fromkeys(self.teams, 0)
        self.terrain_features = generate_terrain_features(
            map_name=map_name, map_width=self.map_width, map_height=self.map_height
        )
        self.num_tx = self.map_width // TILE_SIZE
        self.num_ty = self.map_height // TILE_SIZE
        self.tile_ownership = [[None] * self.num_ty for _ in range(self.num_tx)]

    def _add_initial_infantry(self, team: Team) -> None:
        units = pg.sprite.Group()
        _hq = self.hqs[team]
        for _ in range(3):
            offset = self._find_free_spawn_position(
                target_pos=_hq.position,
                map_width=self.map_width,
                map_height=self.map_height,
            )
            unit = Infantry(position=offset, team=team, hq=_hq)
            unit.map_width = self.map_width
            unit.map_height = self.map_height
            units.add(unit)
            _hq.game_stats["units_created"] += 1

        self.unit_groups[team] = units

    def _find_free_spawn_position(
        self,
        *,
        target_pos: Point,
        unit_size: IntPoint = (40, 40),
        map_width: int = MAP_WIDTH,
        map_height: int = MAP_HEIGHT,
    ) -> Point:
        for _ in range(20):
            offset_x = random.uniform(-60, 60)
            offset_y = random.uniform(-60, 60)
            pos_x = max(0, min(target_pos[0] + offset_x, map_width))
            pos_y = max(0, min(target_pos[1] + offset_y, map_height))
            unit_rect = pg.Rect(pos_x - unit_size[0] / 2, pos_y - unit_size[1] / 2, unit_size[0], unit_size[1])
            # pyrefly: ignore [missing-attribute]
            overlaps_building = any(b.rect.colliderect(unit_rect) for b in self.global_buildings if b.health > 0)
            overlaps_unit = any(
                # pyrefly: ignore [missing-attribute]
                u.rect.colliderect(unit_rect)
                for u in self.global_units
                if u.health > 0 and not u.is_air
            )
            if not overlaps_building and not overlaps_unit:
                return pos_x, pos_y

        return max(0, min(target_pos[0], map_width)), max(0, min(target_pos[1], map_height))

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
        from modules.units import UnitIso  # noqa: PLC0415 ; TODO refactor

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
                        # pyrefly: ignore [bad-argument-type]
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
                # pyrefly: ignore [bad-argument-type]
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

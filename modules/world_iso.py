"""Functions which require access to buildings/units, specific to isometric game."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any

import pygame as pg
from pygame.math import Vector2

from modules.data_iso import MAP_HEIGHT, MAP_WIDTH
from modules.geometry import check_collision, closest_point_on_rect
from modules.particles import create_explosion_iso
from modules.unit_stats.unit_stats_iso import get_unit_size

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, MutableSequence

    from pygame.typing import IntPoint, Point

    from modules.particles import GenericParticle
    from modules.projectile.projectile_iso import ProjectileIso
    from modules.spatial_hash import SpatialHashIso
    from modules.team import Team
    from modules.units_iso import UnitIso


def is_valid_building_position(
    *,
    position: Point,
    team: Team | None,
    new_building_cls: type,
    buildings: Iterable[UnitIso],
    map_width: int = MAP_WIDTH,
    map_height: int = MAP_HEIGHT,
    building_range: int = 200,
    margin: int = 60,
) -> bool:
    width, height = get_unit_size(new_building_cls.__name__)
    half_w_n, half_h_n = width / 2, height / 2
    temp_rect = pg.Rect(position[0] - half_w_n, position[1] - half_h_n, width, height)
    if not (
        temp_rect.left >= 0 and temp_rect.right <= map_width and temp_rect.top >= 0 and temp_rect.bottom <= map_height
    ):
        return False

    proposed_center = position
    has_nearby_friendly = False
    for building in buildings:
        if building.team == team and building.health > 0:
            half_w_e, half_h_e = building.size[0] / 2, building.size[1] / 2
            min_dist = max(half_w_n + half_w_e, half_h_n + half_h_e) + margin
            dist = math.hypot(proposed_center[0] - building.position.x, proposed_center[1] - building.position.y)
            if dist < min_dist:
                return False

            if dist <= building_range:
                has_nearby_friendly = True

        # pyrefly: ignore [missing-attribute]
        if building.health > 0 and building.rect.colliderect(temp_rect):
            return False

    return has_nearby_friendly or new_building_cls.__name__ == "Headquarters"


def find_free_spawn_position(
    *,
    target_pos: Point,
    global_buildings: Iterable[UnitIso],
    global_units: Iterable[UnitIso],
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
        overlaps_building = any(b.rect.colliderect(unit_rect) for b in global_buildings if b.health > 0)
        # pyrefly: ignore [missing-attribute]
        overlaps_unit = any(u.rect.colliderect(unit_rect) for u in global_units if u.health > 0 and not u.is_air)
        if not overlaps_building and not overlaps_unit:
            return pos_x, pos_y

    return max(0, min(target_pos[0], map_width)), max(0, min(target_pos[1], map_height))


def handle_attacks(
    *,
    team: Team,
    all_units: Iterable[UnitIso],
    all_buildings: Iterable[UnitIso],
    projectiles: pg.sprite.Group[ProjectileIso],
    particles: pg.sprite.Group[GenericParticle],
    unit_hash: SpatialHashIso,
    building_hash: SpatialHashIso,
    alliances: dict[Team, frozenset[Team]],
) -> None:
    unit_allies = alliances[team]
    armed_entities = [u for u in all_units if u.team == team and u.weapons and u.health > 0]
    armed_entities.extend(b for b in all_buildings if b.team == team and b.weapons and b.health > 0)
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
            if hasattr(obj, "team") and obj.team not in unit_allies and hasattr(obj, "health") and obj.health > 0:
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
            entity.shoot(target=closest_target, projectiles=projectiles, particles=particles)
        elif not entity.is_building:
            if closest_target.is_building:
                chase_pos = entity.get_chase_position_for_building(closest_target)
                entity.move_target = chase_pos if chase_pos is not None else None
            else:
                entity.move_target = closest_target.position


def cleanup_dead_entities(g: Mapping[str, Any]) -> None:
    for group_name in ["global_units"]:
        group = g[group_name]
        dead = [obj for obj in group if obj.health <= 0]
        for d in dead:
            group.remove(d)
            if hasattr(d, "plasma_burn_particles"):
                for p in d.plasma_burn_particles:
                    if hasattr(p, "kill"):
                        p.kill()

                d.plasma_burn_particles.clear()

    for group_name in ["global_buildings"]:
        group = g[group_name]
        dead = [obj for obj in group if hasattr(obj, "health") and obj.health <= 0]
        for d in dead:
            group.remove(d)
            if hasattr(d, "plasma_burn_particles"):
                for p in d.plasma_burn_particles:
                    if hasattr(p, "kill"):
                        p.kill()

                d.plasma_burn_particles.clear()

    for ug in g["unit_groups"].values():
        dead = [u for u in ug if u.health <= 0]
        for d in dead:
            ug.remove(d)
            if hasattr(d, "plasma_burn_particles"):
                for p in d.plasma_burn_particles:
                    if hasattr(p, "kill"):
                        p.kill()

                d.plasma_burn_particles.clear()


def handle_projectiles(
    *,
    projectiles: Iterable[ProjectileIso],
    all_units: MutableSequence[UnitIso],
    all_buildings: MutableSequence[UnitIso],
    particles: pg.sprite.Group[GenericParticle],
    g: Mapping[str, Any],
) -> None:
    from modules.units_iso import UnitIso  # TODO: refactor

    for projectile in list(projectiles):
        proj_allies = g["alliances"][projectile.team]
        enemy_units = [u for u in all_units if u.team not in proj_allies and u.health > 0]
        enemy_buildings = [b for b in all_buildings if b.team not in proj_allies and b.health > 0]
        hit = False
        for e in enemy_units + enemy_buildings:
            if check_collision(entity=e, projectile=projectile):
                if e.take_damage(projectile.damage):
                    create_explosion_iso(position=e.position, particles=particles, team=e.team)
                    attacker_hq = g["hqs"][projectile.team]
                    if hasattr(e, "hq") and e.hq:
                        if e.is_building:
                            e.hq.game_stats["buildings_lost"] += 1
                            attacker_hq.game_stats["buildings_destroyed"] += 1
                        else:
                            e.hq.game_stats["units_lost"] += 1
                            attacker_hq.game_stats["units_destroyed"] += 1

                    if e in all_units:
                        all_units.remove(e)
                        if isinstance(e, UnitIso):
                            for ug in g["unit_groups"].values():
                                if e in ug:
                                    ug.remove(e)

                    elif e in all_buildings:
                        all_buildings.remove(e)

                hit = True
                break

        if hit:
            projectile.kill()

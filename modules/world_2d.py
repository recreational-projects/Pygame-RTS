from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame as pg
from pygame.math import Vector2

from modules.data_2d import MAP_HEIGHT as MAP_HEIGHT_2D
from modules.data_2d import MAP_WIDTH as MAP_WIDTH_2D
from modules.data_2d import UNIT_CLASSES
from modules.geometry import closest_point_on_rect
from modules.unit_stats_2d import UnitStats

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pygame.typing import IntPoint, Point

    from modules.game_data import GameData
    from modules.spatial_hash import SpatialHash2d
    from modules.team import Team


def is_valid_building_position(
    *,
    position: Point,
    team: Team,
    new_building_cls: type,
    # pyrefly: ignore [implicit-any-type-argument]
    buildings: Iterable,
    map_width: int = MAP_WIDTH_2D,
    map_height: int = MAP_HEIGHT_2D,
    building_range: int = 200,
    margin: int = 60,  # Passage margin for units
) -> bool:
    """
    Validates if a building can be placed at position: checks bounds, overlaps, proximity to friendly buildings.

    :param position: Proposed center position for the building.
    :param team: The team placing the building.
    :param new_building_cls: The class of the building to place.
    :param buildings: List of existing buildings.
    :param map_width: Map width for bounds check.
    :param map_height: Map height for bounds check.
    :param building_range: Max distance to nearest friendly building (HQ requires this).
    :param margin: Minimum distance margin between buildings.
    :return: True if placement is valid.
    """
    _cls_stats = UnitStats.from_dict(UNIT_CLASSES[new_building_cls.__name__])
    width, height = _cls_stats.size[0], _cls_stats.size[1]
    temp_rect = pg.Rect(position[0] - width / 2, position[1] - height / 2, width, height)
    if not (
        0 <= temp_rect.left and temp_rect.right <= map_width and 0 <= temp_rect.top and temp_rect.bottom <= map_height
    ):
        return False

    proposed_center = position

    has_nearby_friendly = False
    for building in buildings:
        if building.team == team and building.health > 0:
            # Dynamic min_dist based on sizes + margin
            half_w_e, half_h_e = building.size[0] / 2, building.size[1] / 2
            min_dist = max(width / 2 + half_w_e, height / 2 + half_h_e) + margin
            dist = math.hypot(proposed_center[0] - building.position.x, proposed_center[1] - building.position.y)
            if dist < min_dist:
                return False

            if dist <= building_range:
                has_nearby_friendly = True

        if building.health > 0 and building.rect.colliderect(temp_rect):
            return False

    return has_nearby_friendly or new_building_cls.__name__ == "Headquarters"


def find_free_spawn_position(
    *,
    target_pos: Point,
    # pyrefly: ignore [implicit-any-type-argument]
    global_buildings: Iterable,
    # pyrefly: ignore [implicit-any-type-argument]
    global_units: Iterable,
    unit_size: IntPoint = (40, 40),
) -> Point:
    """
    Finds a nearby free position for spawning units, avoiding overlaps with buildings/units.

    :param target_pos: Preferred target position (e.g., rally point).
    :param global_buildings: List or group of all buildings.
    :param global_units: List or group of all units.
    :param unit_size: Size of the unit to spawn (default: (40, 40)).
    :return: A free position tuple, or target_pos if no free spot found.
    """
    # Finds a nearby free position for spawning units, avoiding overlaps with buildings/units.
    for _ in range(20):
        offset_x = random.uniform(-60, 60)
        offset_y = random.uniform(-60, 60)
        pos_x = target_pos[0] + offset_x
        pos_y = target_pos[1] + offset_y
        unit_rect = pg.Rect(pos_x - unit_size[0] / 2, pos_y - unit_size[1] / 2, unit_size[0], unit_size[1])
        overlaps_building = any(b.rect.colliderect(unit_rect) for b in global_buildings if b.health > 0)
        overlaps_unit = any(u.rect.colliderect(unit_rect) for u in global_units if u.health > 0 and not u.air)
        if not overlaps_building and not overlaps_unit:
            return pos_x, pos_y

    return target_pos


# pyrefly: ignore [implicit-any-type-argument]
def handle_unit_collisions(all_units: list, unit_hash: SpatialHash2d) -> None:
    """
    Resolves overlaps between ground units using simple repulsion.

    :param all_units: List of all units.
    :param unit_hash: SpatialHash2d for nearby queries.
    """
    # Resolves overlaps between ground units using simple repulsion.
    for i, unit in enumerate(all_units):
        if unit.health <= 0 or unit.is_air:
            continue

        nearby = unit_hash.query(unit.position, max(unit.rect.width, unit.rect.height))
        for other in nearby:
            if other is unit or other.health <= 0 or other.is_air or id(other) <= id(unit):
                continue

            if unit.rect.colliderect(other.rect):
                dx = other.position.x - unit.position.x
                dy = other.position.y - unit.position.y
                dist = math.hypot(dx, dy)
                if dist > 0:
                    r1 = max(unit.rect.width, unit.rect.height) / 2
                    r2 = max(other.rect.width, other.rect.height) / 2
                    overlap = max(0, r1 + r2 - dist)
                    if overlap > 0:
                        push = overlap * 0.5
                        direction_x = dx / dist
                        direction_y = dy / dist
                        unit.position.x -= direction_x * push
                        unit.position.y -= direction_y * push
                        other.position.x += direction_x * push
                        other.position.y += direction_y * push


# pyrefly: ignore [implicit-any-type-argument]
def handle_unit_building_collisions(*, all_units: list, building_hash: SpatialHash2d) -> None:
    """
    Pushes units away from building overlaps.

    :param all_units: List of units.
    :param building_hash: SpatialHash2d for buildings.
    """
    # Pushes units away from building overlaps.
    for unit in [u for u in all_units if u.health > 0 and not u.is_air]:
        nearby_builds = building_hash.query(unit.position, max(unit.rect.width, unit.rect.height) + 50)
        for building in [b for b in nearby_builds if b.health > 0]:
            if unit.rect.colliderect(building.rect):
                dx = building.position.x - unit.position.x
                dy = building.position.y - unit.position.y
                dist = math.hypot(dx, dy)
                if dist > 0:
                    r1 = max(unit.rect.width, unit.rect.height) / 2
                    r2 = max(building.rect.width, building.rect.height) / 2
                    overlap = max(0, r1 + r2 - dist)
                    if overlap > 0:
                        direction_x = dx / dist
                        direction_y = dy / dist
                        unit.position.x -= direction_x * overlap
                        unit.position.y -= direction_y * overlap


def handle_attacks(
    *,
    team: Team,
    # pyrefly: ignore [implicit-any-type-argument]
    all_units: list,
    # pyrefly: ignore [implicit-any-type-argument]
    all_buildings: list,
    # pyrefly: ignore [implicit-any-parameter]
    projectiles,  # noqa: ANN001
    unit_hash: SpatialHash2d,
    building_hash: SpatialHash2d,
    alliances: dict[Team, set[Team]],
) -> None:
    """
    For a team, finds targets in sight range and shoots if in attack range; handles chasing.

    :param team: Attacking team.
    :param all_units: All units.
    :param all_buildings: All buildings.
    :param projectiles: Projectile group.
    :param unit_hash: Unit spatial hash.
    :param building_hash: Building spatial hash.
    :param alliances: Team alliances dict.
    """
    # For a team, finds targets in sight range and shoots if in attack range; handles chasing.
    unit_allies = alliances[team]
    armed_entities = []
    # Mobile units
    for u in all_units:
        if u.team == team and u.weapons and u.health > 0:
            armed_entities.append(u)

    # Buildings
    for b in all_buildings:
        if b.team == team and b.weapons and b.health > 0:
            armed_entities.append(b)

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
            if hasattr(obj, "team") and obj.team not in unit_allies and hasattr(obj, "health") and obj.health > 0:
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
                        else:  # building
                            if dist < min_building_dist_in_range:
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
                entity.shoot(closest_target, projectiles)
            else:
                if not entity.is_building:
                    # Chase the target
                    if closest_target.is_building:
                        chase_pos = entity.get_chase_position_for_building(closest_target)
                        entity.move_target = chase_pos if chase_pos is not None else None
                    else:
                        entity.move_target = closest_target.position


def cleanup_dead_entities(game_data: GameData) -> None:
    """
    Removes dead entities from groups, cleans up particles.

    :param game_data: Game data dict.
    """
    # Removes dead entities from groups, cleans up particles.
    # Cleanup dead units
    group = game_data.global_units
    dead = [obj for obj in group if hasattr(obj, "health") and obj.health <= 0]
    for d in dead:
        group.remove(d)
        if hasattr(d, "plasma_burn_particles"):
            for p in d.plasma_burn_particles:
                if hasattr(p, "kill"):
                    p.kill()

            # pyrefly: ignore [implicit-any-empty-container]
            d.plasma_burn_particles = []

    # Cleanup dead buildings
    group = game_data.global_buildings
    dead = [obj for obj in group if hasattr(obj, "health") and obj.health <= 0]
    for d in dead:
        group.remove(d)
        if hasattr(d, "plasma_burn_particles"):
            for p in d.plasma_burn_particles:
                if hasattr(p, "kill"):
                    p.kill()

            # pyrefly: ignore [implicit-any-empty-container]
            d.plasma_burn_particles = []

    # Cleanup unit groups
    for team, ug in game_data.unit_groups.items():
        dead = [u for u in ug if hasattr(u, "health") and u.health <= 0]
        for d in dead:
            ug.remove(d)
            if hasattr(d, "plasma_burn_particles"):
                for p in d.plasma_burn_particles:
                    if hasattr(p, "kill"):
                        p.kill()

                # pyrefly: ignore [implicit-any-empty-container]
                d.plasma_burn_particles = []

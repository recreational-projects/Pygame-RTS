from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame as pg
from pygame.math import Vector2

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from pygame.typing import IntPoint, Point

    from modules.projectile_2d import Projectile


def snap_to_grid(*, pos: Point, grid_size: int) -> tuple[int, int]:
    """Rounds a world position to the nearest grid cell for aligned building placement.

    :param pos: World position.
    :param grid_size: Size of the grid cell.
    :return: Snapped position tuple.
    """
    # Rounds a world position to the nearest grid cell for aligned building placement.
    return round(pos[0] / grid_size) * grid_size, round(pos[1] / grid_size) * grid_size


def calculate_formation_positions_2d(*, center: Point, num_units: int) -> list[tuple[float, float]]:
    """Computes a grid formation around a center point for group movement.

    :param center: Center position for the formation.
    :param num_units: Number of units in the formation.
    :return: List of position tuples for the formation.
    """
    # Computes a grid formation around a center point for group movement.
    if num_units == 0:
        return []

    positions = []
    spacing = 30
    cols = max(1, int(math.sqrt(num_units)))
    for i in range(num_units):
        row, col = i // cols, i % cols
        x = center[0] + (col - cols / 2) * spacing
        y = center[1] + (row - num_units / cols / 2) * spacing
        positions.append((x, y))

    return positions


def calculate_formation_positions_iso(
    *,
    center: Point,
    target: Point,
    num_units: int,
    formation_type: str = "line",
    spacing: float = 40.0,
) -> list[tuple[float, float]]:
    if num_units == 0:
        return []

    positions = []
    if formation_type == "line":
        cols = max(1, int(math.sqrt(num_units)))
        rows = (num_units + cols - 1) // cols
        for i in range(num_units):
            row, col = i // cols, i % cols
            x = center[0] + (col - cols / 2) * spacing
            y = center[1] + (row - rows / 2) * spacing
            x += random.uniform(-spacing * 0.1, spacing * 0.1)
            y += random.uniform(-spacing * 0.1, spacing * 0.1)
            positions.append((x, y))

    elif formation_type == "v":
        apex = Vector2(target)
        base = Vector2(center)
        dir_to_target = (apex - base).normalize() if (apex - base).length() > 0 else Vector2(1, 0)
        perp = dir_to_target.rotate_rad(math.pi / 2)
        half = (num_units - 1) / 2
        for i in range(num_units):
            offset = (i - half) * spacing * 0.5
            depth = spacing * (i / num_units) * 0.7
            pos = base + perp * offset + dir_to_target * depth
            pos += Vector2(random.uniform(-5, 5), random.uniform(-5, 5))
            positions.append((pos.x, pos.y))

    return positions


def get_starting_positions(
    *, map_width: int, map_height: int, num_players: int, edge_dist: int
) -> Sequence[tuple[float, float]]:
    """Generates balanced starting positions around the map edges for multiple players.

    :param map_width: Width of the map.
    :param map_height: Height of the map.
    :param num_players: Number of players.
    :param edge_dist: Distance from the edge.
    :return: List of starting position tuples.
    """
    # Generates balanced starting positions around the map edges for multiple players.
    half_w = map_width / 2
    half_h = map_height / 2

    base_positions = [
        (half_w, edge_dist),
        (map_width - edge_dist, edge_dist),
        (map_width - edge_dist, half_h),
        (map_width - edge_dist, map_height - edge_dist),
        (half_w, map_height - edge_dist),
        (edge_dist, map_height - edge_dist),
        (edge_dist, half_h),
        (edge_dist, edge_dist),
    ]

    step = max(1, 8 // num_players)
    selected_positions = base_positions[::step][:num_players]

    while len(selected_positions) < num_players:
        selected_positions.append(base_positions[len(selected_positions) % 8])

    return selected_positions


def absolute_world_to_iso(*, world_pos: Point, zoom: float) -> tuple[float, float]:
    dx, dy = world_pos
    iso_x = (dx - dy) * (zoom / 2)
    iso_y = (dx + dy) * (zoom / 2)
    return iso_x, iso_y


def closest_point_on_rect(*, rect: pg.Rect, pos: Point) -> tuple[float, float]:
    """Computes the closest point on the rect to the position.

    :param rect: Pygame Rect.
    :param pos: Position.
    :return: Closest point on rect.
    """
    # Computes the closest point on the rect to the position.
    return max(rect.left, min(pos[0], rect.right)), max(rect.top, min(pos[1], rect.bottom))


def find_free_spawn_position_2d(
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


def check_collision_2d(
    # pyrefly: ignore [implicit-any-parameter]
    entity,  # noqa: ANN001
    projectile: Projectile,
) -> bool:
    """
    Detects collision between entity and projectile using rect or radius approximation.

    :param entity: Entity to check against.
    :param projectile: Projectile to check.
    :return: True if collision detected.
    """
    # Detects collision between entity and projectile using rect or radius approximation.
    proj_rect = pg.Rect(
        projectile.position.x - projectile.length / 2,
        projectile.position.y - projectile.width / 2,
        projectile.length,
        projectile.width,
    )
    if hasattr(entity, "radius"):
        dist = entity.distance_to(projectile.position)
        return dist < (entity.radius + max(projectile.length, projectile.width) / 2)

    return entity.rect.colliderect(proj_rect)

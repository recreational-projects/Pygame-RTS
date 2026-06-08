"""Geometry functions."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame as pg
from pygame.math import Vector2

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pygame.typing import Point

    from modules.projectile.generic_projectile import GenericProjectile
    from modules.units_2d import Unit2d
    from modules.units_iso import UnitIso


def snap_to_grid(*, pos: Point, grid_size: int) -> tuple[int, int]:
    """Rounds a world position to the nearest grid cell for aligned building placement.

    :param pos: World position.
    :param grid_size: Size of the grid cell.
    :return: Snapped position tuple.
    """
    return round(pos[0] / grid_size) * grid_size, round(pos[1] / grid_size) * grid_size


def calculate_formation_positions_2d(*, center: Point, num_units: int) -> list[tuple[float, float]]:
    """Computes a grid formation around a center point for group movement.

    :param center: Center position for the formation.
    :param num_units: Number of units in the formation.
    :return: List of position tuples for the formation.
    """
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


def closest_point_on_rect(*, rect: pg.FRect | pg.Rect, pos: Point) -> tuple[float, float]:
    """Computes the closest point on the rect to the position.

    :param rect: Pygame Rect.
    :param pos: Position.
    :return: Closest point on rect.
    """
    return max(rect.left, min(pos[0], rect.right)), max(rect.top, min(pos[1], rect.bottom))


def check_collision(*, entity: Unit2d | UnitIso, projectile: GenericProjectile) -> bool:
    """Detects collision between entity and projectile using rect or radius approximation.

    :param entity: Entity to check against.
    :param projectile: GenericProjectile to check.
    :return: True if collision detected.
    """
    proj_rect = pg.Rect(
        projectile.position.x - projectile.length / 2,
        projectile.position.y - projectile.width / 2,
        projectile.length,
        projectile.width,
    )
    if hasattr(entity, "radius"):
        dist = entity.distance_to(projectile.position)
        return dist < (entity.radius + max(projectile.length, projectile.width) / 2)

    # pyrefly: ignore [missing-attribute]
    return entity.rect.colliderect(proj_rect)


def get_iso_bounds(*, map_w: int, map_h: int, zoom: float = 1.0) -> tuple[float, float, float, float]:
    corners = [(0, 0), (map_w, 0), (map_w, map_h), (0, map_h)]
    isos = [absolute_world_to_iso(world_pos=c, zoom=zoom) for c in corners]
    min_x = min(ix for ix, iy in isos)
    max_x = max(ix for ix, iy in isos)
    min_y = min(iy for ix, iy in isos)
    max_y = max(iy for ix, iy in isos)
    return min_x, max_x, min_y, max_y


def absolute_world_to_iso(*, world_pos: Point, zoom: float) -> tuple[float, float]:
    dx, dy = world_pos
    iso_x = (dx - dy) * (zoom / 2)
    iso_y = (dx + dy) * (zoom / 2)
    return iso_x, iso_y

"""Pathfinding functions for isometric game."""

from __future__ import annotations

import heapq
import math
from typing import TYPE_CHECKING

from pygame.math import Vector2

from modules.data_iso import MAP_HEIGHT, MAP_WIDTH, TILE_SIZE

if TYPE_CHECKING:
    from pygame.typing import IntPoint, Point


def astar(
    *,
    start: Vector2,
    goal: Vector2,
    blocked: set[IntPoint],
    tile_size: int = TILE_SIZE,
    map_width: int = MAP_WIDTH,
    map_height: int = MAP_HEIGHT,
) -> list[Vector2]:
    start_tile = (int(start.x // tile_size), int(start.y // tile_size))
    goal_tile = (int(goal.x // tile_size), int(goal.y // tile_size))
    num_tiles_x = map_width // tile_size
    num_tiles_y = map_height // tile_size
    open_set = []
    heapq.heappush(open_set, (0.0, start_tile))
    came_from: dict[IntPoint, IntPoint] = {}
    g_score = {start_tile: 0.0}
    f_score = {start_tile: _heuristic(start_tile, goal_tile)}
    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal_tile:
            path = []
            while current in came_from:
                tile_center = Vector2(current[0] * tile_size + tile_size / 2, current[1] * tile_size + tile_size / 2)
                path.append(tile_center)
                current = came_from[current]

            path.append(start)
            path.reverse()
            return path

        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor in blocked or not (0 <= neighbor[0] < num_tiles_x and 0 <= neighbor[1] < num_tiles_y):
                continue

            tentative_g = g_score[current] + (1.414 if dx != 0 and dy != 0 else 1)
            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score[neighbor] = tentative_g + _heuristic(neighbor, goal_tile)
                heapq.heappush(open_set, (f_score[neighbor], neighbor))

    return [start, goal]


def _heuristic(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])

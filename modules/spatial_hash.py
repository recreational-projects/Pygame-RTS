"""Implements a simple grid-based spatial index for efficient nearby object queries."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pygame.math import Vector2
    from pygame.typing import IntPoint


class SpatialHash2d:
    """Simple grid-based spatial index for efficient nearby object queries.

    Uses a dictionary of grid cells to bucket objects by position.
    """

    def __init__(self, cell_size: int = 200) -> None:
        """Initializes the hash with a grid cell size for bucketing objects.

        :param cell_size: Size of each grid cell (default: 200).
        """
        # Initializes the hash with a grid cell size for bucketing objects.
        self.cell_size = cell_size
        self.grid: dict[IntPoint, list] = {}

    def query(self, pos: Vector2, radius: float) -> list:
        """Returns all objects within radius of pos, checking neighboring cells.

        :param pos: Query position (Vector2).
        :param radius: Search radius.
        :return: List of nearby objects.
        """
        # Returns all objects within radius of pos, checking neighboring cells.
        cx = int(pos.x // self.cell_size)
        cy = int(pos.y // self.cell_size)
        keys = set()
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                keys.add((cx + dx, cy + dy))

        nearby = []
        for k in keys:
            if k in self.grid:
                for o in self.grid[k]:
                    if o.distance_to(pos) <= radius:
                        nearby.append(o)

        return nearby

    def add(self, obj) -> None:
        """Adds an object to its corresponding grid cell.

        :param obj: Object with a 'position' attribute (Vector2).
        """
        # Adds an object to its corresponding grid cell.
        key = self._get_key(obj.position)
        if key not in self.grid:
            self.grid[key] = []

        self.grid[key].append(obj)

    def _get_key(self, pos: Vector2) -> tuple[int, int]:
        """Computes the grid cell key for a position.

        :param pos: Vector2 position.
        :return: Tuple (cell_x, cell_y) key.
        """
        # Computes the grid cell key for a position.
        return int(pos.x // self.cell_size), int(pos.y // self.cell_size)


class SpatialHashIso:
    def __init__(self, cell_size: int = 250) -> None:
        self.cell_size = cell_size
        self.grid: dict[IntPoint, list] = {}

    def query(self, pos: Vector2, radius: float) -> list:
        cx = int(pos.x // self.cell_size)
        cy = int(pos.y // self.cell_size)
        keys = set()
        r = int(radius / self.cell_size) + 1
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                keys.add((cx + dx, cy + dy))

        nearby = []
        r2 = radius * radius
        for k in keys:
            if k in self.grid:
                for o in self.grid[k]:
                    dx = o.position.x - pos.x
                    dy = o.position.y - pos.y
                    if dx * dx + dy * dy <= r2:
                        nearby.append(o)

        return nearby

    def add(self, obj) -> None:
        key = self._get_key(obj.position)
        if key not in self.grid:
            self.grid[key] = []

        self.grid[key].append(obj)

    def _get_key(self, pos: Vector2) -> tuple[int, int]:
        return int(pos.x // self.cell_size), int(pos.y // self.cell_size)

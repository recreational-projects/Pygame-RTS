from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING

import pygame as pg

from src.constants import MAP_HEIGHT, MAP_WIDTH, TILE_SIZE
from src.geometry import Coordinate

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.camera import Camera
    from src.game_objects.buildings.building import Building
    from src.game_objects.game_object import GameObject

UNIT_EXPLORATION_RADIUS = 150
BUILDING_EXPLORATION_RADIUS = 200


@dataclass(kw_only=True)
class FogOfWar:
    explored: list[list[bool]] = dataclass_field(init=False, default_factory=list)
    visible: list[list[bool]] = dataclass_field(init=False, default_factory=list)
    surface: pg.Surface = dataclass_field(init=False)

    def __post_init__(self) -> None:
        self.explored = [
            [False] * (MAP_HEIGHT // TILE_SIZE) for _ in range(MAP_WIDTH // TILE_SIZE)
        ]
        self.visible = [
            [False] * (MAP_HEIGHT // TILE_SIZE) for _ in range(MAP_WIDTH // TILE_SIZE)
        ]
        self.surface = pg.Surface((MAP_WIDTH, MAP_HEIGHT), pg.SRCALPHA)
        self.surface.fill((0, 0, 0, 255))

    @staticmethod
    def _tile(position: pg.typing.SequenceLike) -> tuple[int, int]:
        """Return tile."""
        pos = Coordinate(position)
        return int(pos.x // TILE_SIZE), int(pos.y // TILE_SIZE)

    def _reveal(self, center: pg.typing.SequenceLike, radius: float) -> None:
        """Set tiles within `radius` of `center` as explored and visible."""
        center_pos = Coordinate(center)
        tile_x, tile_y = self._tile(center_pos)
        radius_tiles = int(radius // TILE_SIZE)
        for y in range(
            max(0, tile_y - radius_tiles),
            min(len(self.explored[0]), tile_y + radius_tiles + 1),
        ):
            for x in range(
                max(0, tile_x - radius_tiles),
                min(len(self.explored), tile_x + radius_tiles + 1),
            ):
                if (
                    (center_pos.x - (x * TILE_SIZE + TILE_SIZE // 2)) ** 2
                    + (center_pos.y - (y * TILE_SIZE + TILE_SIZE // 2)) ** 2
                ) <= radius**2:
                    self.explored[x][y] = True
                    self.visible[x][y] = True

    def update(
        self, *, units: Iterable[GameObject], buildings: Iterable[Building]
    ) -> None:
        """Update fog of war around `units` and `buildings`."""
        self.visible = [
            [False] * len(self.explored[0]) for _ in range(len(self.explored))
        ]  # Reset visible, but keep explored
        for unit in units:
            self._reveal(center=unit.position, radius=150)

        for building in buildings:
            self._reveal(center=building.position, radius=200)

    def is_visible(self, position: pg.typing.SequenceLike) -> bool:
        """Return whether `position` is in a visible tile."""
        tile_x, tile_y = self._tile(position)
        if 0 <= tile_x < len(self.visible) and 0 <= tile_y < len(self.visible[0]):
            return self.visible[tile_x][tile_y]

        return False

    def is_explored(self, position: pg.typing.SequenceLike) -> bool:
        """Return whether `position` is in an explored tile."""
        tile_x, tile_y = self._tile(position)
        if 0 <= tile_x < len(self.explored) and 0 <= tile_y < len(self.explored[0]):
            return self.explored[tile_x][tile_y]

        return False

    def draw(self, *, surface: pg.Surface, camera: Camera) -> None:
        """Draw opaque (unexplored) and semi-transparent (explored but not visible)
        fog tiles to `surface`.

        NB: drawn over buildings; under units.
        """
        for y in range(len(self.explored[0])):
            for x in range(len(self.explored)):
                if self.explored[x][y]:
                    alpha = 0 if self.visible[x][y] else 100
                    pg.draw.rect(
                        self.surface,
                        (0, 0, 0, alpha),
                        (x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE),
                    )

        surface.blit(source=self.surface, dest=camera.map_offset)

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame as pg

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pygame.typing import Point

    from modules.camera.camera_2d import Camera2d
    from modules.camera.camera_iso import CameraIso
    from modules.units_2d import Unit2d
    from modules.units_iso import UnitIso


class FogOfWar2d:
    """Manages explored/visible tiles on a grid, revealing areas based on unit sight ranges.

    Uses 2D boolean grids for explored and currently visible tiles.
    """

    def __init__(self, *, map_width: int, map_height: int, tile_size: int, spectator: bool = False) -> None:
        """Initializes 2D grids for explored and visible tiles.

        :param map_width: Map width in pixels.
        :param map_height: Map height in pixels.
        :param tile_size: Size of each fog tile (default: TILE_SIZE).
        :param spectator: If True, reveals entire map.
        """
        self.tile_size = tile_size
        num_tiles_x = map_width // tile_size
        num_tiles_y = map_height // tile_size
        self.explored = [[False] * num_tiles_y for _ in range(num_tiles_x)]
        self.visible = [[False] * num_tiles_y for _ in range(num_tiles_x)]
        if spectator:
            self.explored = [[True] * num_tiles_y for _ in range(num_tiles_x)]
            self.visible = [[True] * num_tiles_y for _ in range(num_tiles_x)]

    def update_visibility(
        self, ally_units: Iterable[Unit2d], ally_buildings: Iterable[Unit2d], global_buildings: Iterable[Unit2d]
    ) -> None:
        """Resets visible grid and reveals from ally sight ranges; marks buildings as seen if visible.

        :param ally_units: Ally units for sight revelation.
        :param ally_buildings: Ally buildings for sight revelation.
        :param global_buildings: All buildings to update 'is_seen' flag.
        """
        if not ally_units and not ally_buildings:
            return

        num_tiles_x = len(self.visible)
        num_tiles_y = len(self.visible[0])
        self.visible = [[False] * num_tiles_y for _ in range(num_tiles_x)]
        for unit in ally_units:
            self._reveal(unit.position, unit.sight_range)

        for building in ally_buildings:
            if building.health > 0:
                self._reveal(building.position, building.sight_range)

        for building in global_buildings:
            if building.health > 0:
                tx, ty = (
                    int(building.position[0] // self.tile_size),
                    int(building.position[1] // self.tile_size),
                )
                if 0 <= tx < num_tiles_x and 0 <= ty < num_tiles_y:
                    building.is_seen = building.is_seen or self.visible[tx][ty]

    def _reveal(self, center: Point, radius: int) -> None:
        """Reveals tiles within radius of center as both explored and visible.

        :param center: Center position (x, y) to reveal around.
        :param radius: Reveal radius in pixels.
        """
        cx, cy = center
        tile_x, tile_y = int(cx // self.tile_size), int(cy // self.tile_size)
        radius_tiles = radius // self.tile_size
        for ty in range(max(0, tile_y - radius_tiles), min(len(self.explored[0]), tile_y + radius_tiles + 1)):
            for tx in range(max(0, tile_x - radius_tiles), min(len(self.explored), tile_x + radius_tiles + 1)):
                tile_center_x = tx * self.tile_size + self.tile_size // 2
                tile_center_y = ty * self.tile_size + self.tile_size // 2
                if math.sqrt((cx - tile_center_x) ** 2 + (cy - tile_center_y) ** 2) <= radius:
                    self.explored[tx][ty] = True
                    self.visible[tx][ty] = True

    def is_visible(self, pos: Point) -> bool:
        """Checks if a position's tile is currently visible.

        :param pos: Position (x, y) to check.
        :return: True if visible.
        """
        tx, ty = int(pos[0] // self.tile_size), int(pos[1] // self.tile_size)
        if 0 <= tx < len(self.visible) and 0 <= ty < len(self.visible[0]):
            return self.visible[tx][ty]

        return False

    def is_explored(self, pos: Point) -> bool:
        """Checks if a position's tile has been explored (visible in the past).

        :param pos: Position (x, y) to check.
        :return: True if explored.
        """
        tx, ty = int(pos[0] // self.tile_size), int(pos[1] // self.tile_size)
        if 0 <= tx < len(self.explored) and 0 <= ty < len(self.explored[0]):
            return self.explored[tx][ty]

        return False

    def draw(self, surface: pg.Surface, camera: Camera2d) -> None:
        """Renders semi-transparent black overlay on non-visible tiles (full black if unexplored).

        :param surface: Surface to draw fog on.
        :param camera: Camera2d for viewport culling.
        """
        start_tx = max(0, camera.rect.x // self.tile_size)
        start_ty = max(0, camera.rect.y // self.tile_size)
        end_tx = min(len(self.visible), start_tx + (camera.rect.width // self.tile_size) + 2)
        end_ty = min(len(self.visible[0]), start_ty + (camera.rect.height // self.tile_size) + 2)
        zoom = camera.zoom
        tile_sw = self.tile_size * zoom
        tile_sh = self.tile_size * zoom
        fog_overlay = pg.Surface((camera.width, camera.height), pg.SRCALPHA)
        fog_overlay.fill((0, 0, 0, 0))
        for tx in range(start_tx, end_tx):
            wx = tx * self.tile_size
            sx = (wx - camera.rect.x) * zoom
            if sx < -tile_sw or sx > camera.width:
                continue

            for ty in range(start_ty, end_ty):
                wy = ty * self.tile_size
                sy = (wy - camera.rect.y) * zoom
                if sy < -tile_sh or sy > camera.height:
                    continue

                if not self.visible[tx][ty]:
                    alpha = 255 if not self.explored[tx][ty] else 100
                    pg.draw.rect(fog_overlay, (0, 0, 0, alpha), (sx, sy, tile_sw, tile_sh))

        surface.blit(fog_overlay, (0, 0))


class FogOfWarIso:
    def __init__(self, *, map_width: int, map_height: int, tile_size: int, spectator: bool = False) -> None:
        self.tile_size = tile_size
        num_tiles_x = map_width // tile_size
        num_tiles_y = map_height // tile_size
        self.explored = [[False] * num_tiles_y for _ in range(num_tiles_x)]
        self.visible = [[False] * num_tiles_y for _ in range(num_tiles_x)]
        if spectator:
            self.explored = [[True] * num_tiles_y for _ in range(num_tiles_x)]
            self.visible = [[True] * num_tiles_y for _ in range(num_tiles_x)]

    def update_visibility(
        self, ally_units: Iterable[UnitIso], ally_buildings: Iterable[UnitIso], global_buildings: Iterable[UnitIso]
    ) -> None:
        if not ally_units and not ally_buildings:
            return

        num_tiles_x = len(self.visible)
        num_tiles_y = len(self.visible[0])
        self.visible = [[False] * num_tiles_y for _ in range(num_tiles_x)]
        for unit in ally_units:
            self._reveal(unit.position, unit.sight_range)

        for building in ally_buildings:
            if building.health > 0:
                self._reveal(building.position, building.sight_range)

        for building in global_buildings:
            if building.health > 0:
                tx, ty = (
                    int(building.position[0] // self.tile_size),
                    int(building.position[1] // self.tile_size),
                )
                if 0 <= tx < num_tiles_x and 0 <= ty < num_tiles_y:
                    building.is_seen = building.is_seen or self.visible[tx][ty]

    def _reveal(self, center: Point, radius: int) -> None:
        cx, cy = center
        tile_x, tile_y = int(cx // self.tile_size), int(cy // self.tile_size)
        radius_tiles = radius // self.tile_size
        for ty in range(max(0, tile_y - radius_tiles), min(len(self.explored[0]), tile_y + radius_tiles + 1)):
            for tx in range(max(0, tile_x - radius_tiles), min(len(self.explored), tile_x + radius_tiles + 1)):
                tile_center_x = tx * self.tile_size + self.tile_size // 2
                tile_center_y = ty * self.tile_size + self.tile_size // 2
                if math.sqrt((cx - tile_center_x) ** 2 + (cy - tile_center_y) ** 2) <= radius:
                    self.explored[tx][ty] = True
                    self.visible[tx][ty] = True

    def is_visible(self, pos: Point) -> bool:
        tx, ty = int(pos[0] // self.tile_size), int(pos[1] // self.tile_size)
        if 0 <= tx < len(self.visible) and 0 <= ty < len(self.visible[0]):
            return self.visible[tx][ty]

        return False

    def is_explored(self, pos: Point) -> bool:
        tx, ty = int(pos[0] // self.tile_size), int(pos[1] // self.tile_size)
        if 0 <= tx < len(self.explored) and 0 <= ty < len(self.explored[0]):
            return self.explored[tx][ty]

        return False

    def draw(self, surface: pg.Surface, camera: CameraIso) -> None:
        min_wx, max_wx, min_wy, max_wy = camera.get_render_bounds(self.tile_size)
        start_tx = max(0, int(min_wx // self.tile_size))
        start_ty = max(0, int(min_wy // self.tile_size))
        end_tx = min(len(self.visible), int(max_wx // self.tile_size) + 2)
        end_ty = min(len(self.visible[0]), int(max_wy // self.tile_size) + 2)
        zoom = camera.zoom
        fog_overlay = pg.Surface((camera.width, camera.height), pg.SRCALPHA)
        fog_overlay.fill((0, 0, 0, 0))
        for tx in range(start_tx, end_tx):
            wx = tx * self.tile_size
            for ty in range(start_ty, end_ty):
                wy = ty * self.tile_size
                if not self.visible[tx][ty]:
                    alpha = 255 if not self.explored[tx][ty] else 100
                    color = (0, 0, 0, alpha)
                    c1 = (wx, wy)
                    c2 = (wx + self.tile_size, wy)
                    c3 = (wx + self.tile_size, wy + self.tile_size)
                    c4 = (wx, wy + self.tile_size)
                    iso1 = camera.world_to_iso(c1, zoom)
                    iso2 = camera.world_to_iso(c2, zoom)
                    iso3 = camera.world_to_iso(c3, zoom)
                    iso4 = camera.world_to_iso(c4, zoom)
                    pg.draw.polygon(fog_overlay, color, [iso1, iso2, iso3, iso4])

        surface.blit(fog_overlay, (0, 0))

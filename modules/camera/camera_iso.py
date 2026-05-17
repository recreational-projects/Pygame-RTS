from dataclasses import field
from typing import override

import pygame as pg
from pygame.typing import Point

from modules.camera.camera import Camera
from modules.constants_iso import (
    PAN_EDGE,
    PAN_SPEED,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TILE_SIZE,
)


class CameraIso(Camera):
    """Camera for isometric game."""

    target_rect: pg.Rect = field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.target_rect = pg.Rect(0, 0, self.width, self.height)

    @override
    def get_screen_rect(self, world_rect: pg.Rect) -> pg.Rect:
        corners = [
            (world_rect.left, world_rect.top),
            (world_rect.right, world_rect.top),
            (world_rect.right, world_rect.bottom),
            (world_rect.left, world_rect.bottom),
        ]
        iso_corners = [self.world_to_iso(corner, self.zoom) for corner in corners]
        xs = [p[0] for p in iso_corners]
        ys = [p[1] for p in iso_corners]
        return pg.Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def world_to_iso(self, world_pos: Point, zoom: float) -> tuple[float, float]:
        dx = world_pos[0] - self.rect.x
        dy = world_pos[1] - self.rect.y
        iso_x = (dx - dy) * (zoom / 2)
        iso_y = (dx + dy) * (zoom / 4)
        return iso_x, iso_y

    @override
    def update(self, selected_units: list, mouse_pos: Point, interface_rect: pg.Rect, keys=None) -> None:
        if keys is None:
            keys = pg.key.get_pressed()

        pressed_pan = keys[pg.K_w] or keys[pg.K_a] or keys[pg.K_s] or keys[pg.K_d]
        mx, my = mouse_pos
        pan_delta = PAN_SPEED / self.zoom

        if mx < PAN_EDGE:
            self.rect.x += pan_delta
            self.rect.y -= pan_delta
        if mx > SCREEN_WIDTH - PAN_EDGE and self.rect.right < self.map_width:
            self.rect.x -= pan_delta
            self.rect.y += pan_delta
        if my < PAN_EDGE:
            self.rect.x += 2 * pan_delta
            self.rect.y += 2 * pan_delta
        if my > SCREEN_HEIGHT - PAN_EDGE and self.rect.bottom < self.map_height:
            self.rect.x -= 2 * pan_delta
            self.rect.y -= 2 * pan_delta
        if keys[pg.K_w]:
            self.rect.x += 2 * pan_delta
            self.rect.y += 2 * pan_delta
        if keys[pg.K_s]:
            self.rect.x -= 2 * pan_delta
            self.rect.y -= 2 * pan_delta
        if keys[pg.K_a]:
            self.rect.x += pan_delta
            self.rect.y -= pan_delta
        if keys[pg.K_d]:
            self.rect.x -= pan_delta
            self.rect.y += pan_delta
        if interface_rect.collidepoint(mx, my):
            self.clamp()
            return

        if selected_units and not pressed_pan:
            avg_x = sum(u.position[0] for u in selected_units) / len(selected_units)
            avg_y = sum(u.position[1] for u in selected_units) / len(selected_units)
            target_point = (avg_x, avg_y)
            self.target_rect.x = target_point[0] - (self.width / 0.1)
            self.target_rect.y = target_point[1] - (self.height / 0.1)
            self.snap_to_point(target_point)
            self.target_rect.x = self.rect.x
            self.target_rect.y = self.rect.y
            lerp_alpha = 0.1
            self.rect.x = self.rect.x + (self.target_rect.x - self.rect.x) * lerp_alpha
            self.rect.y = self.rect.y + (self.target_rect.y - self.rect.y) * lerp_alpha

        self.clamp()

    def snap_to_point(self, world_point: Point) -> None:
        sc_x, sc_y = self.width / 2, self.height / 2
        dx_sc = (sc_x + 2 * sc_y) / self.zoom
        dy_sc = (2 * sc_y - sc_x) / self.zoom
        self.rect.x = world_point[0] - dx_sc
        self.rect.y = world_point[1] - dy_sc

    def update_zoom(self, delta: float, mouse_screen_pos: Point | None = None) -> None:
        if mouse_screen_pos is None:
            mouse_screen_pos = (self.width / 2, self.height / 2)

        sx, sy = mouse_screen_pos
        old_dx = (sx + 2 * sy) / self.zoom
        old_dy = (2 * sy - sx) / self.zoom
        old_world_x = self.rect.x + old_dx
        old_world_y = self.rect.y + old_dy
        if delta > 0:
            self.zoom = min(self.zoom * 1.1, 3.0)
        else:
            self.zoom = max(self.zoom / 1.1, 0.5)

        self.update_view_size()
        new_dx = (sx + 2 * sy) / self.zoom
        new_dy = (2 * sy - sx) / self.zoom
        self.rect.x = old_world_x - new_dx
        self.rect.y = old_world_y - new_dy
        self.target_rect.x = self.rect.x
        self.target_rect.y = self.rect.y
        self.clamp()

    def clamp(self) -> None:
        self.rect.x = min(self.rect.x, self.map_width - self.rect.width)
        self.rect.y = min(self.rect.y, self.map_height - self.rect.height)
        self.target_rect.x = min(self.target_rect.x, self.map_width - self.target_rect.width)
        self.target_rect.y = min(self.target_rect.y, self.map_height - self.target_rect.height)

    def world_to_iso_3d(self, world_x: float, world_y: float, world_z: float, zoom: float) -> tuple[float, float]:
        dx = world_x - self.rect.x
        dy = world_y - self.rect.y
        iso_x = (dx - dy) * (zoom / 2)
        iso_y = (dx + dy) * (zoom / 4) - world_z * (zoom / 2)
        return iso_x, iso_y

    def get_render_bounds(self, tile_size: int = TILE_SIZE) -> tuple[float, float, float, float]:
        screen_corners = [(0, 0), (self.width, 0), (self.width, self.height), (0, self.height)]
        world_corners = [self.screen_to_world(c) for c in screen_corners]
        min_wx = min(p[0] for p in world_corners) - tile_size
        max_wx = max(p[0] for p in world_corners) + tile_size
        min_wy = min(p[1] for p in world_corners) - tile_size
        max_wy = max(p[1] for p in world_corners) + tile_size
        return min_wx, max_wx, min_wy, max_wy

    @override
    def screen_to_world(self, screen_pos: Point) -> tuple[float, float]:
        iso_x, iso_y = screen_pos
        dx = (iso_x + 2 * iso_y) / self.zoom
        dy = (2 * iso_y - iso_x) / self.zoom
        return self.rect.x + dx, self.rect.y + dy

from __future__ import annotations

from typing import TYPE_CHECKING, override

import pygame as pg

from modules.camera.camera import _Camera
from modules.data_2d import PAN_EDGE, PAN_SPEED, SCREEN_HEIGHT, SCREEN_WIDTH

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pygame.typing import Point

    from modules.game_object.game_object import GameObject


class Camera2d(_Camera):
    """Camera for 2d game."""

    @override
    def screen_to_world(self, screen_pos: Point) -> tuple[float, float]:
        """Converts screen coordinates to world coordinates.

        :param screen_pos: Tuple (x, y) in screen space.
        :return: Tuple (x, y) in world space.
        """
        # Converts screen coordinates to world coordinates.
        return self.rect.x + screen_pos[0] / self.zoom, self.rect.y + screen_pos[1] / self.zoom

    @override
    def get_screen_rect(self, world_rect: pg.Rect) -> pg.Rect:
        """Transforms a world Rect to screen coordinates.

        :param world_rect: Rect in world space.
        :return: Transformed Rect in screen space.
        """
        # Transforms a world Rect to screen coordinates.
        screen_left = int((world_rect.left - self.rect.x) * self.zoom)
        screen_top = int((world_rect.top - self.rect.y) * self.zoom)
        screen_w = int(world_rect.width * self.zoom)
        screen_h = int(world_rect.height * self.zoom)
        return pg.Rect(screen_left, screen_top, screen_w, screen_h)

    def update_zoom(self, delta: float, mouse_world_pos: Point | None = None) -> None:
        """Zooms in/out by 20% steps, clamped between 0.5x and 3x; centers on mouse if provided.

        :param delta: Zoom direction (+1 zoom in, -1 zoom out).
        :param mouse_world_pos: Optional world position to center zoom on.
        """
        # Zooms in/out by 20% steps, clamped between 0.5x and 3x; centers on mouse if provided.
        old_zoom = self.zoom
        old_center = self.rect.center
        if delta > 0:
            self.zoom = min(self.zoom * 1.2, 3.0)
        else:
            self.zoom = max(self.zoom / 1.2, 0.5)

        if self.zoom != old_zoom:
            self.update_view_size()
            if mouse_world_pos:
                self.rect.center = mouse_world_pos
            else:
                self.rect.center = old_center

            self.clamp()

    @override
    def update_view_size(self) -> None:
        """Updates the view rectangle size based on current zoom."""
        # Updates the view rectangle size based on current zoom.
        view_w = self.width / self.zoom
        view_h = self.height / self.zoom
        self.rect.size = (view_w, view_h)

    def world_to_screen(self, world_pos: Point) -> tuple[float, float]:
        """Converts world coordinates to screen-relative coordinates.

        :param world_pos: Tuple (x, y) in world space.
        :return: Tuple (x, y) in screen space.
        """
        # Converts world coordinates to screen-relative coordinates.
        dx = world_pos[0] - self.rect.x
        dy = world_pos[1] - self.rect.y
        return dx * self.zoom, dy * self.zoom

    @override
    def update(
        self,
        selected_units: Sequence[GameObject],
        mouse_pos: Point,
        interface_rect: pg.Rect,
        keys=None,  # pyrefly: ignore[implicit-any-parameter]
    ) -> None:
        """Handles panning via keys, edge-scrolling, and centering on selected units.

        :param selected_units: List of selected units to center camera on.
        :param mouse_pos: Current mouse position for edge panning.
        :param interface_rect: Rect of UI interface to ignore panning in.
        :param keys: Pygame key states (default: get_pressed()).
        """
        # Handles panning via keys, edge-scrolling, and centering on selected units.
        if keys is None:
            keys = pg.key.get_pressed()

        pressed_pan = keys[pg.K_w] or keys[pg.K_a] or keys[pg.K_s] or keys[pg.K_d]
        mx, my = mouse_pos

        if mx < PAN_EDGE and self.rect.left > 0:
            self.rect.x -= PAN_SPEED
        if mx > SCREEN_WIDTH - PAN_EDGE and self.rect.right < self.map_width:
            self.rect.x += PAN_SPEED
        if my < PAN_EDGE and self.rect.top > 0:
            self.rect.y -= PAN_SPEED
        if my > SCREEN_HEIGHT - PAN_EDGE and self.rect.bottom < self.map_height:
            self.rect.y += PAN_SPEED

        if keys[pg.K_w] and self.rect.top > 0:
            self.rect.y -= PAN_SPEED
        if keys[pg.K_s] and self.rect.bottom < self.map_height:
            self.rect.y += PAN_SPEED
        if keys[pg.K_a] and self.rect.left > 0:
            self.rect.x -= PAN_SPEED
        if keys[pg.K_d] and self.rect.right < self.map_width:
            self.rect.x += PAN_SPEED

        if interface_rect.collidepoint(mx, my):
            self.clamp()
            return

        if selected_units and not pressed_pan:
            avg_x = sum(u.position[0] for u in selected_units) / len(selected_units)
            avg_y = sum(u.position[1] for u in selected_units) / len(selected_units)
            self.rect.centerx = avg_x
            self.rect.centery = avg_y

        self.clamp()

    def clamp(self) -> None:
        """Ensures camera view stays within map bounds."""
        # Ensures camera view stays within map bounds.
        self.rect.x = max(0, min(self.rect.x, self.map_width - self.rect.width))
        self.rect.y = max(0, min(self.rect.y, self.map_height - self.rect.height))

    def apply(self, rect: pg.Rect) -> pg.Rect:
        """Moves a rect relative to camera offset (used internally if needed).

        :param rect: Input Rect.
        :return: Offset Rect.
        """
        # Moves a rect relative to camera offset (used internally if needed).
        return rect.move(-self.rect.x, -self.rect.y)

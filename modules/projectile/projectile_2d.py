"""Implements Projectile for 2d game."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame as pg

from modules.data_2d import PROJECTILE_LIFETIME
from modules.team import team_to_color

from .projectile_generic import ProjectileGeneric

if TYPE_CHECKING:
    from pygame.math import Vector2
    from pygame.typing import Point

    from modules.camera import Camera2d
    from modules.team import Team
    from modules.unit_stats.unit_stats_generic import WeaponStats


class Projectile2d(ProjectileGeneric):
    """Projectile for 2d game."""

    def __init__(self, *, position: Point, direction: Vector2, team: Team, weapon: WeaponStats) -> None:
        """Initializes projectile with tapered image, trail deque for fading tail.

        :param position: Starting position (x, y).
        :param direction: Normalized direction Vector2.
        :param team: Firing team.
        :param weapon: Weapon dict with projectile params.
        """
        super().__init__(
            position=position,
            direction=direction,
            team=team,
            weapon=weapon,
            lifetime=PROJECTILE_LIFETIME * 30,
            trail_length=15,
        )

    def draw(self, surface: pg.Surface, camera: Camera2d) -> None:
        """Draws trail segments with fading intensity, then the main projectile.

        :param surface: Surface to draw on.
        :param camera: Camera2d for transformation.
        """
        if not isinstance(self.rect, pg.Rect):
            raise TypeError("self.rect` is unexpected non-`Rect` type")

        screen_rect = camera.get_screen_rect(self.rect)
        if not screen_rect.colliderect((0, 0, camera.width, camera.height)):
            return

        screen_pos = camera.world_to_screen(self.position)
        if len(self.trail) > 1:
            trail_positions = [camera.world_to_screen(pos) for pos in self.trail]
            num_segments = len(trail_positions) - 1
            for i in range(num_segments):
                p1 = trail_positions[i]
                p2 = trail_positions[i + 1]
                age_factor = i / max(1, num_segments - 1)
                c = pg.Color(team_to_color[self.team])
                intensity = 0.3 + 0.7 * age_factor
                trail_color = (int(c.r * intensity), int(c.g * intensity), int(c.b * intensity))
                trail_width = max(1, int(self.width * camera.zoom * (0.2 + 0.3 * age_factor)))
                pg.draw.line(surface, trail_color, p1, p2, trail_width)

        scaled_length = int(self.length * camera.zoom)
        scaled_width = int(self.width * camera.zoom)
        if self.image is None:
            raise TypeError("self.image` is unexpectedly `None`")

        if scaled_length > 0 and scaled_width > 0:
            scaled_image = pg.transform.smoothscale(self.image, (scaled_length, scaled_width))
            rotated_image = pg.transform.rotate(scaled_image, -math.degrees(self.angle))
            rot_rect = rotated_image.get_rect(center=screen_pos)
            surface.blit(rotated_image, rot_rect.topleft)

from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING, Any

import pygame as pg
from pygame.math import Vector2

from modules.data_2d import PROJECTILE_LIFETIME
from modules.team import team_to_color

if TYPE_CHECKING:
    from pygame.typing import Point

    from modules.camera.camera_2d import Camera2d
    from modules.team import Team


class Projectile(pg.sprite.Sprite):
    """Projectile class for bullets/rockets; handles trailing effect and collision detection.

    Creates a tapered image with a fading trail deque.
    """

    def __init__(self, pos: Point, direction: Vector2, damage: int, team: Team, weapon: dict[str, Any]) -> None:
        """Initializes projectile with tapered image, trail deque for fading tail.

        :param pos: Starting position (x, y).
        :param direction: Normalized direction Vector2.
        :param damage: Damage value.
        :param team: Firing team.
        :param weapon: Weapon dict with projectile params.
        """
        super().__init__()
        self.position = Vector2(pos)
        self.direction = direction.normalize() if direction.length() > 0 else Vector2(1, 0)
        self.damage = damage
        self.team = team
        self.speed = weapon["projectile_speed"]
        self.lifetime = PROJECTILE_LIFETIME * 30
        self.age = 0
        self.length = weapon["projectile_length"]
        self.width = weapon["projectile_width"]
        self.angle = math.atan2(self.direction.y, self.direction.x)
        self.image = pg.Surface((self.length, self.width), pg.SRCALPHA)
        color = team_to_color[team]

        if self.image is not None:  # TODO: type guard - not sure why needed
            for i in range(self.length):
                alpha = int(255 * (i / self.length))
                pg.draw.line(self.image, (color.r, color.g, color.b, alpha), (i, 0), (i, self.width), 1)

            self.rect = self.image.get_rect(center=self.position)

        self.trail = deque(maxlen=15)

    def update(self) -> None:
        """Advances position, adds to trail, kills after lifetime."""
        self.trail.append(self.position.copy())
        self.position += self.direction * self.speed
        self.age += 1
        if self.rect is not None:  # TODO: type guard - not sure why this can be None
            self.rect.center = self.position

        if self.age >= self.lifetime:
            self.kill()

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
        if self.image is not None:  # TODO: type guard - not sure why this can be None
            if scaled_length > 0 and scaled_width > 0:
                scaled_image = pg.transform.smoothscale(self.image, (scaled_length, scaled_width))
                rotated_image = pg.transform.rotate(scaled_image, -math.degrees(self.angle))
                rot_rect = rotated_image.get_rect(center=screen_pos)
                surface.blit(rotated_image, rot_rect.topleft)

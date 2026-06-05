from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING, Any, override

import pygame as pg
from pygame.math import Vector2

from modules.team import team_to_color

if TYPE_CHECKING:
    from pygame.typing import Point

    from modules.team import Team
    from modules.unit_stats.unit_stats import WeaponStats


class GenericProjectile(pg.sprite.Sprite):
    """GenericProjectile class for bullets/rockets; handles trailing effect and collision detection.

    Creates a tapered image with a fading trail deque.
    """

    def __init__(
        self,
        *,
        position: Point,
        direction: Vector2,
        team: Team,
        weapon: WeaponStats,
        lifetime: float,
        trail_length: int,
    ) -> None:
        """Initializes projectile with tapered image, trail deque for fading tail.

        :param position: Starting position (x, y).
        :param direction: Normalized direction Vector2.
        :param team: Firing team.
        :param weapon: Weapon dict with projectile params.
        """
        super().__init__()
        self.position = Vector2(position)
        self.direction = direction.normalize() if direction.length() > 0 else Vector2(1, 0)
        self.damage = weapon.damage
        self.team = team
        self.speed = weapon.projectile_speed
        self.length = weapon.projectile_length
        self.width = weapon.projectile_width
        self.lifetime = lifetime
        self.trail = deque(maxlen=trail_length)

        self.angle = math.atan2(self.direction.y, self.direction.x)
        self.age = 0
        # pyrefly: ignore [missing-override-decorator]
        self.image = pg.Surface((self.length, self.width), pg.SRCALPHA)
        if self.image is None:  # TODO: type guard - not sure why needed
            raise ValueError("self.image` is unexpectedly `None`")

        _color = team_to_color[team]
        for i in range(self.length):
            alpha = int(255 * (i / self.length))
            pg.draw.line(self.image, (_color.r, _color.g, _color.b, alpha), (i, 0), (i, self.width), 1)

        # pyrefly: ignore [missing-override-decorator]
        self.rect = self.image.get_rect(center=self.position)

    @override
    def update(self, *args: Any, **kwargs: Any) -> None:
        """Advances position, adds to trail, kills after lifetime."""
        self.trail.append(self.position.copy())
        self.position += self.direction * self.speed
        self.age += 1
        if not isinstance(self.rect, pg.Rect):  # TODO: type guard - not sure why needed
            raise TypeError("self.rect` is unexpected non-`Rect` type")

        self.rect.center = self.position

        if self.age >= self.lifetime:
            self.kill()

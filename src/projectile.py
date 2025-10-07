from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any

import pygame as pg

from src.geometry import Coordinate
from src.particle import Particle

if TYPE_CHECKING:
    from src.camera import Camera
    from src.constants import Team
    from src.game_object import GameObject

HIT_RADIUS = 3
SPEED: float = 6
SMOKE_INTERVAL = 2
"""Emit a smoke particle every `n` frames, to form a trail."""


class Projectile(pg.sprite.Sprite):
    def __init__(
        self,
        position: pg.typing.SequenceLike,
        target_obj: GameObject,
        damage: int,
        team: Team,
    ) -> None:
        """Initialize the projectile.

        target_obj:
            Target. Will move towards while it exists, otherwise self-destruct

        """
        super().__init__()
        self.target_obj = target_obj
        d = target_obj.position - self.position
        angle = math.atan2(d.y, d.x)
        self.image: pg.Surface = pg.transform.rotate(
            pg.Surface((10, 5), pg.SRCALPHA), -math.degrees(angle)
        )
        self.rect: pg.Rect = self.image.get_rect(center=position)
        pg.draw.ellipse(self.image, (255, 200, 0), (0, 0, 10, 5))
        self.velocity = pg.Vector2(SPEED, 0).rotate(angle)
        self.damage = damage
        self.team = team
        self.age = 0

        pg.draw.ellipse(self.image, (255, 200, 0), (0, 0, 10, 5))

    @property
    def position(self) -> Coordinate:
        return Coordinate(self.rect.center)

    def smoke(self) -> Particle:
        return Particle(
            self.position,
            self.velocity.normalize() * random.uniform(0.5, 1.5),
            5,
            pg.Color(255, 255, 150),
            15,
        )

    def explosion(self) -> list[Particle]:
        return [
            Particle(
                self.position,
                (random.uniform(-2, 2), random.uniform(-2, 2)),
                6,
                pg.Color(255, 100, 0),
                15,
            )
            for _ in range(5)
        ]

    def update(self, particles: pg.sprite.Group[Any]) -> None:
        if self.target_obj and self.target_obj.health > 0:
            if self.position.distance_to(self.target_obj.position) > HIT_RADIUS:
                self.rect.x += self.velocity.x
                self.rect.y += self.velocity.y
                if self.age % SMOKE_INTERVAL == 0:
                    particles.add(self.smoke())
                    self.age += 1
            else:
                particles.add(*self.explosion())
                self.kill()

        else:
            self.kill()

    def draw(self, *, surface: pg.Surface, camera: Camera) -> None:
        surface.blit(self.image, camera.apply(self.rect).topleft)

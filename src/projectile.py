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


class Projectile(pg.sprite.Sprite):
    SPEED: float = 6

    def __init__(
        self,
        position: pg.typing.SequenceLike,
        target_unit: GameObject,
        damage: int,
        team: Team,
    ) -> None:
        super().__init__()
        self.image: pg.Surface = pg.Surface((10, 5), pg.SRCALPHA)
        self.rect: pg.Rect = self.image.get_rect(center=position)
        self.target_unit = target_unit
        self.damage = damage
        self.team = team
        self.particle_timer = 2

        pg.draw.ellipse(self.image, (255, 200, 0), (0, 0, 10, 5))

    @property
    def position(self) -> Coordinate:
        return Coordinate(self.rect.center)

    def update(self, particles: pg.sprite.Group[Any]) -> None:
        if self.target_unit and self.target_unit.health > 0:
            if self.position.distance_to(self.target_unit.position) > HIT_RADIUS:
                d = self.target_unit.position - self.position
                angle = math.atan2(d.y, d.x)
                self.image = pg.transform.rotate(
                    pg.Surface((10, 5), pg.SRCALPHA), -math.degrees(angle)
                )
                pg.draw.ellipse(self.image, (255, 200, 0), (0, 0, 10, 5))
                self.rect.x += self.SPEED * math.cos(angle)
                self.rect.y += self.SPEED * math.sin(angle)
                if self.particle_timer <= 0:
                    particles.add(
                        Particle(
                            self.position,
                            -math.cos(angle) * random.uniform(0.5, 1.5),
                            -math.sin(angle) * random.uniform(0.5, 1.5),
                            5,
                            pg.Color(255, 255, 150),
                            15,
                        )
                    )
                    self.particle_timer = 2
                else:
                    self.particle_timer -= 1
            else:
                self.kill()
                for _ in range(5):
                    particles.add(
                        Particle(
                            self.position,
                            random.uniform(-2, 2),
                            random.uniform(-2, 2),
                            6,
                            pg.Color(255, 100, 0),
                            15,
                        )
                    )  # Orange explosion
        else:
            self.kill()

    def draw(self, *, surface: pg.Surface, camera: Camera) -> None:
        surface.blit(source=self.image, dest=camera.to_screen(self.rect.topleft))

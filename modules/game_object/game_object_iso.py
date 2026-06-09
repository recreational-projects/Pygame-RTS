"""Implements generic Gameobject for isometric game."""

from __future__ import annotations

import random
from abc import ABC
from typing import TYPE_CHECKING

import pygame as pg

from modules.data_iso import MAP_HEIGHT, MAP_WIDTH, PLASMA_BURN_DURATION, PLASMA_BURN_PARTICLE_COUNT
from modules.particle import PlasmaBurnParticle
from modules.team import team_to_color

from .game_object_generic import GameObjectGeneric

if TYPE_CHECKING:
    from pygame.typing import Point

    from modules.team import Team


class GameObjectIso(GameObjectGeneric, ABC):
    """Abstract base for isometric entities."""

    def __init__(self, *, position: Point, team: Team) -> None:
        super().__init__(position=position, team=team)
        # self.body_angle = 0
        self.plasma_burn_particles: list[PlasmaBurnParticle] = []
        self.map_width = MAP_WIDTH
        self.map_height = MAP_HEIGHT
        self.image = pg.Surface((32, 32))
        if self.image is not None:  # TODO: type guard - not sure why this can be None
            self.rect = self.image.get_rect(center=position)

    def distance_to(self, other_pos: Point) -> float:
        return self.position.distance_to(other_pos)

    def take_damage(self, damage: int) -> bool:
        self.health -= damage
        self.under_attack = True
        self.under_attack_timer = 120
        if self.health < self.max_health * 0.7 and random.random() < 0.3:
            color = team_to_color[self.team]
            for _ in range(PLASMA_BURN_PARTICLE_COUNT):
                self.plasma_burn_particles.append(PlasmaBurnParticle(self.position, self, color, PLASMA_BURN_DURATION))

        return self.health <= 0

import pygame as pg

from src.constants import MAP_HEIGHT, MAP_WIDTH, Team
from src.game_objects.game_object import GameObject
from src.geometry import Coordinate

ARRIVAL_RADIUS = 5


class Unit(GameObject):
    """Base class for all units. Mobile."""

    def __init__(self, position: Coordinate, team: Team) -> None:
        super().__init__(position=position, team=team)
        self.speed: float = 2

    def move_toward(self) -> None:
        if self.target and self.target_unit and self.target_unit.health > 0:
            dist = self.distance_to(self.target)
            if dist > self.ATTACK_RANGE:
                if dist > ARRIVAL_RADIUS:
                    direction = self.displacement_to(self.target).normalize()
                    self.position += self.speed * direction

                self.rect.clamp_ip(pg.Rect(0, 0, MAP_WIDTH, MAP_HEIGHT))
            else:
                self.target = None

        elif self.formation_target:
            dist = self.distance_to(self.formation_target)
            if dist > ARRIVAL_RADIUS:
                direction = self.displacement_to(self.formation_target).normalize()
                self.position += self.speed * direction

            self.rect.clamp_ip(pg.Rect(0, 0, MAP_WIDTH, MAP_HEIGHT))

        elif self.target:
            dist = self.distance_to(self.target)
            if dist > ARRIVAL_RADIUS:
                direction = self.displacement_to(self.target).normalize()
                self.position += self.speed * direction

            self.rect.clamp_ip(pg.Rect(0, 0, MAP_WIDTH, MAP_HEIGHT))

    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)
        self.move_toward()

        if self.cooldown_timer > 0:
            self.cooldown_timer -= 1

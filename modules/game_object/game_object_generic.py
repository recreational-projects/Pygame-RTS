"""Implements generic Gameobject."""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

import pygame as pg
from pygame.math import Vector2

if TYPE_CHECKING:
    from pygame.typing import Point

    from modules.team import Team


class GameObjectGeneric(pg.sprite.Sprite, ABC):
    """Abstract generic base for all entities.

    :param position: Initial position (x, y).
    :param team: Team enum.
    """

    def __init__(self, *, position: Point, team: Team) -> None:
        super().__init__()
        self.position = Vector2(position)
        self.team = team
        self.health = 100  # TODO
        self.max_health = 100  # TODO
        self.under_attack = False
        self.under_attack_timer = 0
        self.selected = False
        self.is_seen = False

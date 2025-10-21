from __future__ import annotations

import pygame as pg

from src.constants import Team
from src.game_objects.buildings.building import Building
from src.geometry import Coordinate


class Barracks(Building):
    """Produces infantry units."""

    # Override base class(es):
    COST = 500
    POWER_USAGE = 25

    def __init__(
        self, *, position: pg.typing.SequenceLike, team: Team, font: pg.Font
    ) -> None:
        super().__init__(
            position=Coordinate(position),
            team=team,
            color=pg.Color(150, 150, 0) if team == Team.GDI else pg.Color(150, 0, 0),
            font=font,
        )
        self.max_health = 600
        self.health = self.max_health

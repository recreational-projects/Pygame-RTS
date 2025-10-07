from __future__ import annotations

from typing import TYPE_CHECKING

import pygame as pg

from src.building import Building

if TYPE_CHECKING:
    from src.team import Team


class Barracks(Building):
    # Override base class(es):
    COST = 500
    POWER_USAGE = 25

    def __init__(
        self, *, position: pg.typing.SequenceLike, team: Team, font: pg.Font
    ) -> None:
        super().__init__(
            position=position,
            team=team,
            font=font,
        )
        self.color = (
            pg.Color(150, 150, 0) if self.team == "GDI" else pg.Color(150, 0, 0),
        )
        self.max_health = 600
        self.health = self.max_health

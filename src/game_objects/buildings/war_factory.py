from __future__ import annotations

from typing import TYPE_CHECKING

import pygame as pg

from src.building import Building

if TYPE_CHECKING:
    from src.team import Team


class WarFactory(Building):
    # Override base class(es):
    COST = 1000
    POWER_USAGE = 35

    def __init__(
        self, *, position: pg.typing.SequenceLike, team: Team, font: pg.Font
    ) -> None:
        super().__init__(
            position=position,
            team=team,
            font=font,
        )
        self.color = pg.Color(170, 170, 0) if team == "GDI" else pg.Color(170, 0, 0)
        self.max_health = 800
        self.health = self.max_health

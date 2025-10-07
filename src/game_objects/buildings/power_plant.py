from __future__ import annotations

from typing import TYPE_CHECKING

import pygame as pg

from src.building import Building

if TYPE_CHECKING:
    from src.team import Team


class PowerPlant(Building):
    # Override base class(es):
    COST = 300
    POWER_OUTPUT = 100
    POWER_USAGE = 0

    def __init__(
        self, *, position: pg.typing.SequenceLike, team: Team, font: pg.Font
    ) -> None:
        super().__init__(
            position=position,
            team=team,
            font=font,
        )
        self.color = pg.Color(130, 130, 0) if team == "GDI" else pg.Color(130, 0, 0)
        self.max_health = 500
        self.health = self.max_health

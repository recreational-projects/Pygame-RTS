from __future__ import annotations

import pygame as pg

from src.constants import Team
from src.game_objects.buildings.building import Building


class PowerPlant(Building):
    """Provides power."""

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
            color=pg.Color(130, 130, 0) if team == Team.GDI else pg.Color(130, 0, 0),
            font=font,
        )
        self.max_health = 500
        self.health = self.max_health

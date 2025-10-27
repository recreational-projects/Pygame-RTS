from __future__ import annotations

import pygame as pg

from src.game_objects.buildings.building import Building
from src.team import Faction, Team


class Barracks(Building):
    """Produces infantry units."""

    # Override base class(es):
    COST = 500
    POWER_USAGE = 25

    def __init__(self, *, position: pg.typing.Point, team: Team, font: pg.Font) -> None:
        super().__init__(
            position=position,
            team=team,
            color=pg.Color(150, 150, 0)
            if team.faction == Faction.GDI
            else pg.Color(150, 0, 0),
            font=font,
        )
        self.max_health = 600
        self.health = self.max_health

"""Constants used by `src/` modules."""

from __future__ import annotations

from enum import Enum

import pygame as pg

SCREEN_WIDTH, SCREEN_HEIGHT = 1920, 1080
MAP_WIDTH, MAP_HEIGHT = 1600, 800
TILE_SIZE = 32
CONSOLE_HEIGHT = 200
BUILDING_CONSTRUCTION_RANGE = 160


class Team(Enum):
    GDI = "GDI"
    NOD = "NOD"


COLORS = {
    Team.GDI: pg.Color(200, 150, 0),
    Team.NOD: pg.Color(200, 0, 0),
}

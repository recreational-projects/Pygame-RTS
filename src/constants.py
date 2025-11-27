"""Constants used by `src/` modules."""

from __future__ import annotations

from enum import Enum

import pygame as pg

SCREEN_WIDTH, SCREEN_HEIGHT = 1920, 1080
MAP_WIDTH, MAP_HEIGHT = 1600, 800
TILE_SIZE = 32
BUILDING_CONSTRUCTION_RANGE = 160

GDI_COLOR = pg.Color(200, 150, 0)
NOD_COLOR = pg.Color(200, 0, 0)


class Team(Enum):
    GDI = "gdi"
    NOD = "nod"

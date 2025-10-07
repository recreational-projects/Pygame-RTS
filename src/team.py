from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pygame as pg


@dataclass
class Team:
    COLOR = {"GDI": (200, 0, 0), "NOD": (200, 150, 0)}

    name: Literal["GDI", "NOD"]

    @classmethod
    def gdi(cls) -> Team:
        return Team("GDI")

    @classmethod
    def nod(cls) -> Team:
        return Team("NOD")

    def __post_init__(self) -> None:
        self.color = pg.Color(Team.COLOR[self.name])

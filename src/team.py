from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Faction(Enum):
    GDI = "GDI"
    NOD = "NOD"


@dataclass(kw_only=True)
class Team:
    """Holds information about a team."""

    faction: Faction
    iron: int

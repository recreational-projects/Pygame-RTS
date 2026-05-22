from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pygame as pg
    from pygame.sprite import Group
    from pygame.typing import IntPoint

    from modules.camera.camera_2d import Camera2d
    from modules.fog_of_war import FogOfWar2d
    from modules.game_console import GameConsole
    from modules.production_interface_2d import ProductionInterface
    from modules.team import Team
    from modules.units_2d import Headquarters


@dataclass(kw_only=True)
class GameData:
    """Global game data."""

    player_units: Group  # pyrefly: ignore [implicit-any-type-argument]
    ai_units: Group  # pyrefly: ignore [implicit-any-type-argument]
    global_units: Group  # pyrefly: ignore [implicit-any-type-argument]
    global_buildings: Group  # pyrefly: ignore [implicit-any-type-argument]
    projectiles: Group  # pyrefly: ignore [implicit-any-type-argument]
    particles: Group  # pyrefly: ignore [implicit-any-type-argument]
    selected_units: Group  # pyrefly: ignore [implicit-any-type-argument]
    unit_groups: dict = field(default_factory=dict)  # pyrefly: ignore [implicit-any-type-argument]
    hqs: dict = field(default_factory=dict)  # pyrefly: ignore [implicit-any-type-argument]
    player_team: Team | None
    player_allies: frozenset[Team] = field(default_factory=frozenset)
    alliances: dict = field(default_factory=dict)  # pyrefly: ignore [implicit-any-type-argument]
    console: GameConsole
    fog_of_war: FogOfWar2d
    camera: Camera2d
    map_color: pg.Color
    map_width: int
    map_height: int
    game_mode: str
    ais: list[Any] = field(default_factory=list)
    interface_rect: pg.Rect
    teams: list[Team] = field(default_factory=list)
    # optional:
    player_hq: Headquarters | None = field(default=None)
    interface: ProductionInterface | None = field(default=None)
    spectator_mode: bool = field(default=False)
    # internal:
    selected_building: Any = field(init=False, default=None)
    selecting: bool = field(init=False, default=False)
    select_start: IntPoint | None = field(init=False, default=None)
    select_rect: pg.Rect | None = field(init=False, default=None)

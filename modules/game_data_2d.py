"""Implements GameData for 2d game."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pygame as pg
    from pygame.typing import IntPoint

    from modules.ai_2d import AI
    from modules.camera.camera_2d import Camera2d
    from modules.fog_of_war import FogOfWar2d
    from modules.particles import GenericParticle
    from modules.production_interface_2d import ProductionInterface
    from modules.projectile.projectile_2d import Projectile2d
    from modules.team import Team
    from modules.units_2d import Headquarters, Unit2d


@dataclass(kw_only=True)
class GameData:
    """Global game data."""

    player_units: pg.sprite.Group[Unit2d]
    ai_units: pg.sprite.Group[Unit2d]
    global_units: pg.sprite.Group[Unit2d]
    global_buildings: pg.sprite.Group[Unit2d]
    projectiles: pg.sprite.Group[Projectile2d]
    particles: pg.sprite.Group[GenericParticle]
    selected_units: pg.sprite.Group[Unit2d]
    unit_groups: dict[Team, Any] = field(default_factory=dict)
    hqs: dict[Team, Any] = field(default_factory=dict)
    player_team: Team | None
    player_allies: frozenset[Team] = field(default_factory=frozenset)
    alliances: dict[Team, frozenset[Team]] = field(default_factory=dict)
    fog_of_war: FogOfWar2d
    camera: Camera2d
    map_color: pg.Color
    map_width: int
    map_height: int
    game_mode: str
    ais: list[AI] = field(default_factory=list)
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

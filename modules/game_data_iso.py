"""Implements GameData for isometric game."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    import pygame as pg
    from pygame.typing import IntPoint

    from modules.ai_iso import AI
    from modules.camera.camera_iso import CameraIso
    from modules.fog_of_war import FogOfWarIso
    from modules.particles import GenericParticle
    from modules.production_interface_iso import ProductionInterface
    from modules.projectile.projectile_iso import ProjectileIso
    from modules.team import Team
    from modules.terrain_feature_iso import TerrainFeature
    from modules.units_iso import Headquarters, UnitIso


class GameDataIso(TypedDict):
    """Global game data."""

    player_units: pg.sprite.Group[UnitIso]
    ai_units: pg.sprite.Group[UnitIso]
    global_units: pg.sprite.Group[UnitIso]
    global_buildings: pg.sprite.Group[UnitIso]
    projectiles: pg.sprite.Group[ProjectileIso]
    particles: pg.sprite.Group[GenericParticle]
    selected_units: pg.sprite.Group[UnitIso]
    unit_groups: MutableMapping[Team, Any]
    hqs: dict[Team, Any]
    player_team: Team | None
    player_allies: frozenset[Team]
    player_hq: Headquarters | None
    alliances: dict[Team, frozenset[Team]]
    fog_of_war: FogOfWarIso
    camera: CameraIso
    map_color: pg.Color
    map_width: int
    map_height: int
    game_mode: str
    ais: list[AI]
    interface: ProductionInterface | None
    interface_rect: pg.Rect
    teams: list[Team]
    spectator_mode: bool
    selected_building: Any
    selecting: bool
    select_start: IntPoint | None
    select_rect: pg.Rect | None
    tile_timer: int
    num_tx: int
    num_ty: int
    tile_ownership: list[list[Any]]
    terrain_features: list[TerrainFeature]
    previous_fitness: dict[Team, int]
    current_fitness: dict[Team, int]
    fitness_deltas: dict[Team, int]

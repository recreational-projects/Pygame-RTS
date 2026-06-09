"""Implements generic Camera."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame as pg

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pygame.typing import Point

    from modules.game_object import GameObjectGeneric


@dataclass(kw_only=True)
class _CameraGeneric(ABC):
    """Abstract generic camera. Handles viewport transformation, zooming, panning, and clamping to map bounds.

    Manages the visible rectangle in world coordinates.
    """

    map_width: int
    map_height: int
    width: int
    height: int
    zoom: float = field(init=False, default=1.0)
    rect: pg.Rect = field(init=False)

    def __post_init__(self) -> None:
        """Initializes camera with default map and screen dimensions."""
        self.rect = pg.Rect(0, 0, self.width, self.height)
        self.update_view_size()

    def update_view_size(self) -> None:
        """Updates the view rectangle size based on current zoom."""
        view_w = self.width / self.zoom
        view_h = self.height / self.zoom
        self.rect.size = (view_w, view_h)

    @abstractmethod
    def screen_to_world(self, screen_pos: Point) -> tuple[float, float]:
        """Converts screen coordinates to world coordinates."""

    @abstractmethod
    def get_screen_rect(self, world_rect: pg.Rect) -> pg.Rect:
        """Transforms a world Rect to screen coordinates."""

    @abstractmethod
    def update(
        self,
        *,
        selected_units: Sequence[GameObjectGeneric],
        mouse_pos: Point,
        interface_rect: pg.Rect,
        keys=None,  # pyrefly: ignore[implicit-any-parameter]
    ) -> None:
        """Handles panning via keys, edge-scrolling, and centering on selected units."""

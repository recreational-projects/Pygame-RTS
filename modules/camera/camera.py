from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pygame as pg
from pygame.typing import Point


@dataclass(kw_only=True)
class Camera(ABC):
    """Generic camera. Handles viewport transformation, zooming, panning, and clamping to map bounds.

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
    def update(self, selected_units: list, mouse_pos: Point, interface_rect: pg.Rect, keys=None) -> None:
        """Handles panning via keys, edge-scrolling, and centering on selected units."""

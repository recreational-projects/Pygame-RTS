"""Implements generic ProductionInterface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

import pygame as pg

from modules.data_2d import CONSOLE_HEIGHT, SCREEN_HEIGHT
from modules.fonts import FONT_MEDIUM


@dataclass(kw_only=True)
class _ProductionInterfaceGeneric:
    """Dataclass for production sidebar UI layout and colors.

    Manages the right-hand UI panel for building/production.
    """

    WIDTH: ClassVar = 200
    MARGIN_X: ClassVar = 20
    CREDITS_POS_Y: ClassVar = 10
    POWER_POS_Y: ClassVar = 35
    TOP_BUTTONS_POS_Y: ClassVar = 60
    TOP_BUTTON_WIDTH: ClassVar = 55
    TOP_BUTTON_HEIGHT: ClassVar = 25
    TOP_BUTTON_SPACING: ClassVar = 5
    PROD_ITEMS_START_Y: ClassVar = 100
    ITEM_HEIGHT: ClassVar = 50
    ITEM_BUTTON_HEIGHT: ClassVar = 40
    PRODUCTION_QUEUE_POS_Y: ClassVar = 300
    BUTTON_SPACING_Y: ClassVar = 10
    BUTTON_RADIUS: ClassVar = 5
    ACTION_BUTTON_HEIGHT: ClassVar = 40
    FILL_COLOR: ClassVar = pg.Color(60, 60, 60)
    LINE_COLOR: ClassVar = pg.Color(100, 100, 100)
    ACTIVE_TAB_COLOR: ClassVar = pg.Color(0, 200, 200)
    INACTIVE_TAB_COLOR: ClassVar = pg.Color(50, 50, 50)
    ACTION_ALLOWED_COLOR: ClassVar = pg.Color(0, 200, 0)
    ACTION_BLOCKED_COLOR: ClassVar = pg.Color(200, 0, 0)
    MAX_PRODUCTION_QUEUE_LENGTH: ClassVar = 5
    _BUTTON_WIDTH = WIDTH - 2 * MARGIN_X

    top_rects: dict[str, pg.Rect] = field(init=False, default_factory=dict)
    item_rects: dict[str, pg.Rect] = field(init=False, default_factory=dict)
    producible_items: list[str] = field(default_factory=list)
    """Currently producible items based on `producer` class."""

    def __post_init__(self) -> None:
        """Post-init: creates surface, top buttons, labels, defaults to HQ producer."""
        self.surface = pg.Surface((self.WIDTH, SCREEN_HEIGHT - CONSOLE_HEIGHT))
        self._create_top_buttons()

    def _create_top_buttons(self) -> None:
        """Creates rects for Repair/Sell/Map buttons."""
        self.top_rects.clear()
        start_x = self.MARGIN_X
        for i, label in enumerate(["Repair", "Sell", "Map"]):
            x = start_x + i * (self.TOP_BUTTON_WIDTH + self.TOP_BUTTON_SPACING)
            rect = pg.Rect(x, self.TOP_BUTTONS_POS_Y, self.TOP_BUTTON_WIDTH, self.TOP_BUTTON_HEIGHT)
            self.top_rects[label] = rect

    def _draw_top_buttons(self) -> None:
        for label, rect in self.top_rects.items():
            color = self.INACTIVE_TAB_COLOR
            pg.draw.rect(self.surface, color, rect, border_radius=self.BUTTON_RADIUS)
            pg.draw.rect(self.surface, self.LINE_COLOR, rect, 1)
            text_surf = FONT_MEDIUM.render(label, True, pg.Color("white"))
            text_rect = text_surf.get_rect(center=rect.center)
            self.surface.blit(text_surf, text_rect)

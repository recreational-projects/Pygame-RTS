from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

import pygame as pg

from modules.data import UNIT_BUTTON_LABELS
from modules.data_2d import CONSOLE_HEIGHT, SCREEN_HEIGHT, SCREEN_WIDTH
from modules.fonts import FONT_MEDIUM
from modules.unit_stats.unit_stats_2d import get_unit_cost
from modules.units_2d import (
    Barracks,
    BlackMarket,
    Hangar,
    Headquarters,
    OilDerrick,
    PowerPlant,
    Refinery,
    ShaleFracker,
    Turret,
    WarFactory,
)

if TYPE_CHECKING:
    from pygame.typing import Point

    from modules.units_2d import Unit2d


@dataclass(kw_only=True)
class ProductionInterface:
    """
    Dataclass for production sidebar UI layout and colors.

    Manages the right-hand UI panel for building/production.
    """

    _STR_TO_BUILDING_CLASS: ClassVar = {
        "Barracks": Barracks,
        "WarFactory": WarFactory,
        "Hangar": Hangar,
        "PowerPlant": PowerPlant,
        "Turret": Turret,
        "OilDerrick": OilDerrick,
        "Refinery": Refinery,
        "ShaleFracker": ShaleFracker,
        "BlackMarket": BlackMarket,
    }  # Don't move to data for now as it contains class references

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

    hq: Headquarters
    surface: pg.Surface = field(init=False)
    top_rects: dict[str, pg.Rect] = field(init=False, default_factory=dict)
    item_rects: dict[str, pg.Rect] = field(init=False, default_factory=dict)
    placing_cls: type | None = field(init=False, default=None)
    producer: Barracks | WarFactory | Hangar | Headquarters = field(init=False)
    """Current (selected) producing building. Defaults to HQ."""
    producible_items: list[str] = field(default_factory=list)
    """Currently producible items based on `producer` class."""
    production_timer: float | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """
        Post-init: creates surface, top buttons, labels, defaults to HQ producer.
        """
        self.surface = pg.Surface((self.WIDTH, SCREEN_HEIGHT - CONSOLE_HEIGHT))
        self.producer = self.hq
        self._create_top_buttons()
        self.update_producer(self.hq)

    def _create_top_buttons(self) -> None:
        """
        Creates rects for Repair/Sell/Map buttons.
        """
        self.top_rects.clear()
        start_x = self.MARGIN_X
        for i, label in enumerate(["Repair", "Sell", "Map"]):
            x = start_x + i * (self.TOP_BUTTON_WIDTH + self.TOP_BUTTON_SPACING)
            rect = pg.Rect(x, self.TOP_BUTTONS_POS_Y, self.TOP_BUTTON_WIDTH, self.TOP_BUTTON_HEIGHT)
            self.top_rects[label] = rect

    def update_producer(self, building: Unit2d | None) -> None:
        """
        Updates producible items based on `building`.
        """
        if building is None:
            raise ValueError("Building must be provided.")

        if isinstance(building, (Barracks, WarFactory, Hangar)):
            self.producer = building
        else:
            self.producer = self.hq

        self.producible_items = building.producible_items

        self.item_rects = {}
        y = self.PROD_ITEMS_START_Y
        for i, item in enumerate(self.producible_items):
            rect = pg.Rect(self.MARGIN_X, y + i * self.ITEM_HEIGHT, self._BUTTON_WIDTH, self.ITEM_BUTTON_HEIGHT)
            self.item_rects[item] = rect

    def draw(self, surface_: pg.Surface) -> None:
        """
        Renders sidebar: credits/power, buttons, queue with progress.

        :param surface_: Main screen surface.
        """
        self.surface.fill(self.FILL_COLOR)
        pg.draw.rect(self.surface, self.LINE_COLOR, self.surface.get_rect(), width=2)

        self.surface.blit(
            FONT_MEDIUM.render(f"Credits: ${self.hq.credits}", True, pg.Color("white")),
            (self.MARGIN_X, self.CREDITS_POS_Y),
        )

        power_color = pg.Color("green") if self.hq.has_enough_power else pg.Color("red")
        self.surface.blit(
            FONT_MEDIUM.render(
                f"Power: {self.hq.power_output}/{self.hq.power_usage}",
                True,
                power_color,
            ),
            (self.MARGIN_X, self.POWER_POS_Y),
        )

        for label, rect in self.top_rects.items():
            color = self.INACTIVE_TAB_COLOR
            pg.draw.rect(self.surface, color, rect, border_radius=self.BUTTON_RADIUS)
            pg.draw.rect(self.surface, self.LINE_COLOR, rect, 1)
            text_surf = FONT_MEDIUM.render(label, True, pg.Color("white"))
            text_rect = text_surf.get_rect(center=rect.center)
            self.surface.blit(text_surf, text_rect)

        for item, rect in self.item_rects.items():
            cost = get_unit_cost(item)
            label = UNIT_BUTTON_LABELS.get(item, item)
            can_produce = self.hq.credits >= cost
            color = self.ACTION_ALLOWED_COLOR if can_produce else self.ACTION_BLOCKED_COLOR
            pg.draw.rect(self.surface, color, rect, border_radius=self.BUTTON_RADIUS)
            label_surf = FONT_MEDIUM.render(label, True, pg.Color("white"))
            label_rect = label_surf.get_rect(x=rect.x + 5, y=rect.y + 5)
            self.surface.blit(label_surf, label_rect)
            cost_surf = FONT_MEDIUM.render(f"({cost})", True, pg.Color("white"))
            cost_rect = cost_surf.get_rect(x=rect.x + 5, y=rect.y + 25)
            self.surface.blit(cost_surf, cost_rect)

        if hasattr(self.producer, "production_queue") and self.producer.production_queue:
            queue_y = self.PRODUCTION_QUEUE_POS_Y
            self.surface.blit(
                FONT_MEDIUM.render("Queue:", True, pg.Color("white")),
                (self.MARGIN_X, queue_y),
            )
            queue_y += 20
            for i, item in enumerate(self.producer.production_queue):
                unit_type = item["unit_type"] if "unit_type" in item else item["cls"].__name__
                repeat_text = " [R]" if item["repeat"] else ""
                text = f"{UNIT_BUTTON_LABELS.get(unit_type, unit_type)}{repeat_text}"
                self.surface.blit(
                    FONT_MEDIUM.render(text, True, pg.Color("white")),
                    (self.MARGIN_X + 10, queue_y),
                )
                repeat_rect = pg.Rect(self.MARGIN_X + 150, queue_y, 20, 20)
                repeat_color = self.ACTION_ALLOWED_COLOR if item["repeat"] else self.INACTIVE_TAB_COLOR
                pg.draw.rect(self.surface, repeat_color, repeat_rect, border_radius=2)
                if item["repeat"]:
                    self.surface.blit(
                        FONT_MEDIUM.render("R", True, pg.Color("white")),
                        (repeat_rect.x + 6, repeat_rect.y + 3),
                    )
                if i == 0 and self.producer.production_timer is not None:
                    progress = (
                        1 - (self.producer.production_timer / 90.0)
                        if "Hangar" in str(type(self.producer))
                        else 1 - (self.producer.production_timer / 60.0)
                    )
                    bar_width = 100 * progress
                    pg.draw.rect(
                        self.surface,
                        self.ACTION_ALLOWED_COLOR,
                        (self.MARGIN_X + 10, queue_y + 20, bar_width, 5),
                    )
                    pg.draw.rect(self.surface, self.LINE_COLOR, (self.MARGIN_X + 10, queue_y + 20, 100, 5), 1)
                queue_y += 25

        surface_.blit(self.surface, (SCREEN_WIDTH - self.WIDTH, 0))

    def handle_click(self, screen_pos: Point) -> bool | tuple[str, Unit2d]:
        """
        Handles clicks on buttons: repair, sell, queue items, start placement.

        :param screen_pos: Mouse position.
        :return: True if handled, or tuple ('sell', building) for sell action.
        """
        # Handles clicks on buttons: repair, sell, queue items, start placement.
        local_pos = (screen_pos[0] - (SCREEN_WIDTH - self.WIDTH), screen_pos[1])

        for label, rect in self.top_rects.items():
            if rect.collidepoint(local_pos):
                if label == "Repair":
                    if self.producer != self.hq:
                        missing = self.producer.max_health - self.producer.health
                        if missing > 0:
                            cost = missing * 1
                            if self.hq.credits >= cost:
                                self.hq.credits -= cost
                                self.producer.health = self.producer.max_health

                elif label == "Sell":
                    if self.producer != self.hq:
                        return "sell", self.producer

                elif label == "Map":
                    pass

                return True

        for item, rect in self.item_rects.items():
            if rect.collidepoint(local_pos):
                cost = get_unit_cost(item)
                if self.hq.credits >= cost:
                    if isinstance(self.producer, Headquarters):
                        self.placing_cls = self._STR_TO_BUILDING_CLASS[item]
                    else:
                        if len(self.producer.production_queue) < self.MAX_PRODUCTION_QUEUE_LENGTH:
                            self.producer.production_queue.append({"unit_type": item, "repeat": False})
                            self.hq.credits -= cost
                        return True

                return False

        return False

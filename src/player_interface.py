from __future__ import annotations

from dataclasses import InitVar, dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, ClassVar

import pygame as pg

from src import geometry
from src.constants import (
    GDI_COLOR,
    NOD_COLOR,
    PRODUCTION_INTERFACE_WIDTH,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)
from src.draw_utils import draw_progress_bar
from src.game_objects.buildings.barracks import Barracks
from src.game_objects.buildings.headquarters import Headquarters
from src.game_objects.buildings.power_plant import PowerPlant
from src.game_objects.buildings.turret import Turret
from src.game_objects.buildings.war_factory import WarFactory
from src.game_objects.units.harvester import Harvester
from src.game_objects.units.infantry import Infantry
from src.game_objects.units.tank import Tank
from src.team import Faction, Team

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from src.camera import Camera
    from src.game import Game
    from src.game_objects.buildings.building import Building
    from src.game_objects.game_object import GameObject


@dataclass(kw_only=True)
class PlayerInterface:
    """Interface for player."""

    WIDTH: ClassVar = PRODUCTION_INTERFACE_WIDTH
    MARGIN_X: ClassVar = 20
    """Margin on left and right."""
    IRON_POS_Y: ClassVar = 20
    """y position of iron value."""
    POWER_POS_Y: ClassVar = 45
    """... power value."""
    TAB_BUTTONS_POS_Y: ClassVar = 70
    """... first tab button."""
    BUY_BUTTONS_POS_Y: ClassVar = 190
    """... first buy button."""
    SELL_BUTTON_POS_Y: ClassVar = 390
    """... sell button."""
    PRODUCTION_QUEUE_POS_Y: ClassVar = 460
    """... production queue."""
    BUTTON_SPACING_Y: ClassVar = 10
    BUTTON_RADIUS: ClassVar = 5
    TAB_BUTTON_HEIGHT: ClassVar = 30
    ACTION_BUTTON_HEIGHT: ClassVar = 40
    FILL_COLOR: ClassVar = pg.Color(60, 60, 60)
    LINE_COLOR: ClassVar = pg.Color(100, 100, 100)
    ACTIVE_TAB_COLOR: ClassVar = pg.Color(0, 200, 200)
    INACTIVE_TAB_COLOR: ClassVar = pg.Color(50, 50, 50)
    ACTION_ALLOWED_COLOR: ClassVar = pg.Color(0, 200, 0)
    ACTION_BLOCKED_COLOR: ClassVar = pg.Color(200, 0, 0)
    MAX_PRODUCTION_QUEUE_LENGTH: ClassVar = 5
    PLACEMENT_VALID_COLOR = (0, 255, 0)
    PLACEMENT_INVALID_COLOR = (255, 0, 0)

    _BUTTON_WIDTH = WIDTH - 2 * MARGIN_X

    team: Team
    hq: Headquarters
    surface: pg.Surface = dataclass_field(init=False)
    tab_buttons: dict[str, pg.Rect] = dataclass_field(init=False, default_factory=dict)
    buy_buttons: dict[
        str,
        dict[
            type[GameObject],
            tuple[
                pg.Rect,
                Callable,
            ],
        ],
    ] = dataclass_field(init=False, default_factory=dict)
    sell_button: pg.Rect = dataclass_field(init=False)
    current_tab = "Units"
    production_timer: float | None = dataclass_field(init=False, default=None)
    all_buildings: InitVar[Iterable[Building]]
    font: pg.Font

    def __post_init__(self, all_buildings: Iterable[Building]) -> None:
        self.surface = pg.Surface((PlayerInterface.WIDTH, SCREEN_HEIGHT))

        tab_button_base = pg.Rect(
            (self.MARGIN_X, self.TAB_BUTTONS_POS_Y),
            (self._BUTTON_WIDTH, self.TAB_BUTTON_HEIGHT),
        )
        for i, tab_name in enumerate(["Units", "Buildings", "Defensive"]):
            self.tab_buttons[tab_name] = tab_button_base.move(
                0, i * (self.TAB_BUTTON_HEIGHT + self.BUTTON_SPACING_Y)
            )
            self.buy_buttons[tab_name] = {}

        action_button_base = pg.Rect(
            (self.MARGIN_X, 0),
            (self._BUTTON_WIDTH, self.ACTION_BUTTON_HEIGHT),
        )
        buy_button_base = action_button_base.move(0, self.BUY_BUTTONS_POS_Y)
        for i, (cls, req) in enumerate(
            [
                (
                    Tank,
                    lambda: any(
                        b.team == self.hq.team and isinstance(b, WarFactory)
                        for b in all_buildings
                    ),
                ),
                (
                    Infantry,
                    lambda: any(
                        b.team == self.team and isinstance(b, Barracks)
                        for b in all_buildings
                    ),
                ),
                (
                    Harvester,
                    lambda: any(
                        b.team == self.team and isinstance(b, WarFactory)
                        for b in all_buildings
                    ),
                ),
            ]
        ):
            self.buy_buttons["Units"][cls] = (
                buy_button_base.move(
                    0, i * (self.ACTION_BUTTON_HEIGHT + self.BUTTON_SPACING_Y)
                ),
                lambda: req,
            )

        for i, cls in enumerate([Barracks, WarFactory, PowerPlant, Headquarters]):
            self.buy_buttons["Buildings"][cls] = (
                buy_button_base.move(
                    0, i * (self.ACTION_BUTTON_HEIGHT + self.BUTTON_SPACING_Y)
                ),
                lambda: True,
            )
        self.buy_buttons["Defensive"] = {Turret: (buy_button_base, lambda: True)}
        self.sell_button = action_button_base.move(0, self.SELL_BUTTON_POS_Y)
        self.object_button_labels = {
            Tank: "Tank",
            Infantry: "Infantry",
            Harvester: "Harvester",
            Barracks: "Barracks",
            WarFactory: "War Factory",
            PowerPlant: "Power Plant",
            Headquarters: "Headquarters",
            Turret: "Turret",
        }

    @staticmethod
    def _local_pos(screen_pos: pg.typing.IntPoint) -> tuple[int, int]:
        """Convert screen position to local position."""
        return screen_pos[0] - SCREEN_WIDTH + PlayerInterface.WIDTH, screen_pos[1]

    def _draw_iron(self, *, y_pos: int) -> None:
        _label = self.font.render(
            f"Iron: {self.team.iron}",
            color=pg.Color("white"),
            antialias=True,
        )
        self.surface.blit(source=_label, dest=(self.MARGIN_X, y_pos))

    def _draw_power(self, *, y_pos: int) -> None:
        color_ = pg.Color("green") if self.hq.has_enough_power else pg.Color("red")
        self.surface.blit(
            self.font.render(
                f"Power: {self.hq.power_output}/{self.hq.power_usage}",
                color=color_,
                antialias=True,
            ),
            (self.MARGIN_X, y_pos),
        )

    def _draw_tab_button(self, *, rect: pg.Rect, label: str) -> None:
        pg.draw.rect(
            self.surface,
            self.ACTIVE_TAB_COLOR
            if label == self.current_tab
            else self.INACTIVE_TAB_COLOR,
            rect,
            border_radius=self.BUTTON_RADIUS,
        )
        self.surface.blit(
            self.font.render(label, color=pg.Color("white"), antialias=True),
            (rect.x + 10, rect.y + 10),
        )

    def _draw_buy_button(
        self, *, rect: pg.Rect, cls: type[GameObject], req_fn: Callable
    ) -> None:
        can_produce = self.team.iron >= cls.COST and req_fn
        buy_fill_color = (
            self.ACTION_ALLOWED_COLOR if can_produce else self.ACTION_BLOCKED_COLOR
        )
        pg.draw.rect(
            self.surface, buy_fill_color, rect, border_radius=self.BUTTON_RADIUS
        )
        self.surface.blit(
            self.font.render(
                f"{self.object_button_labels[cls]} ({cls.COST})",
                color=pg.Color("white"),
                antialias=True,
            ),
            (rect.x + 10, rect.y + 10),
        )

    def _draw_sell_button(self, *, rect: pg.Rect, game: Game) -> None:
        sell_fill_color = (
            self.ACTION_ALLOWED_COLOR
            if game.selected_building
            else self.ACTION_BLOCKED_COLOR
        )
        pg.draw.rect(
            self.surface,
            sell_fill_color,
            rect,
            border_radius=self.BUTTON_RADIUS,
        )
        self.surface.blit(
            self.font.render("Sell", color=pg.Color("white"), antialias=True),
            (self.sell_button.x + 10, self.sell_button.y + 10),
        )

    def _draw_production_queue(self, *, y_pos: int, game: Game) -> None:
        if self.hq.production_timer and self.hq.production_queue:
            progress = 1 - self.hq.production_timer / game.get_production_time(
                cls=self.hq.production_queue[0], team=self.team
            )
            draw_progress_bar(
                surface=self.surface,
                bar_color=pg.Color("green"),
                rect=pg.Rect(
                    (self.MARGIN_X, y_pos),
                    (self._BUTTON_WIDTH, 10),
                ),
                progress=progress,
            )

        for i, cls in enumerate(self.hq.production_queue[:5]):
            self.surface.blit(
                self.font.render(
                    f"{cls.__name__} ({cls.COST})",
                    color=pg.Color("white"),
                    antialias=True,
                ),
                (self.MARGIN_X, (y_pos + 20) + i * 25),
            )

    def _draw_pending_building(
        self,
        *,
        surface_: pg.Surface,
        mouse_pos: pg.typing.IntPoint,
        game: Game,
        camera: Camera,
    ) -> None:
        if not self.hq.pending_building_class:
            raise TypeError("No pending building")

        world_pos = geometry.snap_to_grid(camera.to_world(mouse_pos))
        temp_surface = pg.Surface(self.hq.pending_building_class.SIZE, pg.SRCALPHA)
        temp_surface.fill(GDI_COLOR if self.team.faction == Faction.GDI else NOD_COLOR)
        temp_surface.set_alpha(100)
        color_ = self.PLACEMENT_INVALID_COLOR
        if game.is_valid_building_position(
            position=world_pos,
            new_building_class=self.hq.pending_building_class,
            team=self.hq.team,
        ):
            color_ = self.PLACEMENT_VALID_COLOR

        pg.draw.rect(
            temp_surface,
            color_,
            ((0, 0), self.hq.pending_building_class.SIZE),
            width=3,
        )
        surface_.blit(
            temp_surface,
            (
                mouse_pos[0] - self.hq.pending_building_class.SIZE[0] // 2,
                mouse_pos[1] - self.hq.pending_building_class.SIZE[1] // 2,
            ),
        )

    def draw(self, *, surface: pg.Surface, game: Game, camera: Camera) -> None:
        """Draw to the `surface_`."""
        self.surface.fill(self.FILL_COLOR)
        pg.draw.rect(self.surface, self.LINE_COLOR, self.surface.get_rect(), width=2)
        self._draw_iron(y_pos=self.IRON_POS_Y)
        self._draw_power(y_pos=self.POWER_POS_Y)

        for tab_name, rect in self.tab_buttons.items():
            self._draw_tab_button(rect=rect, label=tab_name)

        for cls, info in self.buy_buttons[self.current_tab].items():
            rect, req_fn = info
            self._draw_buy_button(rect=rect, cls=cls, req_fn=req_fn)

        self._draw_production_queue(y_pos=self.PRODUCTION_QUEUE_POS_Y, game=game)
        self._draw_sell_button(rect=self.sell_button, game=game)

        if self.hq.pending_building_class:
            self._draw_pending_building(
                surface_=surface, mouse_pos=pg.mouse.get_pos(), game=game, camera=camera
            )

        surface.blit(
            source=self.surface, dest=(SCREEN_WIDTH - PlayerInterface.WIDTH, 0)
        )

    def handle_click(self, *, screen_pos: pg.typing.IntPoint, game: Game) -> bool:
        local_pos = self._local_pos(screen_pos)
        for tab_name, rect in self.tab_buttons.items():
            if rect.collidepoint(local_pos):
                self.current_tab = tab_name
                return True

        if len(self.hq.production_queue) >= self.MAX_PRODUCTION_QUEUE_LENGTH:
            return False

        for cls, info in self.buy_buttons[self.current_tab].items():
            rect, req_fn = info
            if rect.collidepoint(local_pos) and self.team.iron >= cls.COST and req_fn():
                self.hq.production_queue.append(cls)
                self.team.iron -= cls.COST
                if not self.hq.production_timer:
                    self.production_timer = game.get_production_time(
                        cls=cls, team=self.team
                    )
                return True

        if self.sell_button.collidepoint(local_pos) and game.selected_building:
            self.team.iron += game.selected_building.COST // 2
            game.delete_selected_building()
            return True

        return False

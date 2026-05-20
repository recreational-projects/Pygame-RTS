from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import pygame as pg

from modules.data_2d import MAPS
from modules.fonts import FONT_LARGE, FONT_MEDIUM
from modules.team import team_to_color, team_to_name

if TYPE_CHECKING:
    from pygame.typing import IntPoint

    from modules.team import Team


def _get_team_enum(name: str) -> Team | None:
    """Maps team name to enum.

    :param name: Team name string.
    :return: Team enum or None.
    """
    for t, n in team_to_name.items():
        if n == name:
            return t

    return None


@dataclass
class _MenuButton:
    """Simple clickable button with hover effect.

    :param rect: Define button dimensions.
    :param text: Button text.
    :param color: Normal color.
    :param hover_color: Hover color.
    """

    rect: pg.Rect
    text: str
    color: pg.Color
    hover_color: pg.Color
    current_color: pg.Color = field(init=False)

    def update(self, mouse_pos: IntPoint) -> None:
        """Updates button color based on hover.

        :param mouse_pos: Mouse position.
        """
        self.current_color = self.hover_color if self.rect.collidepoint(mouse_pos) else self.color

    def draw(self, surface: pg.Surface) -> None:
        """Draws button and text.

        :param surface: Surface to draw on.
        """
        pg.draw.rect(surface, self.current_color, self.rect, border_radius=10)
        text_surf = FONT_MEDIUM.render(self.text, True, pg.Color("white"))
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

    def is_clicked(self, mouse_pos: IntPoint) -> bool:
        """Checks if button is clicked.

        :param mouse_pos: Mouse position.
        :return: True if clicked.
        """
        return self.rect.collidepoint(mouse_pos)


@dataclass
class MainMenu:
    """Main menu with Single Player and Quit buttons."""

    screen_size: InitVar[IntPoint]

    def __post_init__(self, screen_size: IntPoint) -> None:

        self.skirmish_btn = _MenuButton(
            pg.Rect(screen_size[0] // 2 - 100, screen_size[1] // 2 - 60, 200, 60),
            "Single Player",
            pg.Color(50, 150, 50),
            pg.Color(100, 200, 100),
        )
        self.quit_btn = _MenuButton(
            pg.Rect(screen_size[0] // 2 - 100, screen_size[1] // 2 + 40, 200, 60),
            "Quit",
            pg.Color(150, 50, 50),
            pg.Color(200, 100, 100),
        )

    def handle_event(self, event: pg.Event) -> str | None:
        """Handles menu events.

        :param event: Pygame event.
        :return: Transition string or None.
        """
        if event.type == pg.MOUSEBUTTONDOWN:
            if self.skirmish_btn.is_clicked(event.pos):
                return "skirmish_setup"

            if self.quit_btn.is_clicked(event.pos):
                return "quit"

        return None

    def update(self, mouse_pos: IntPoint) -> None:
        """Updates button hovers.

        :param mouse_pos: Mouse position.
        """
        self.skirmish_btn.update(mouse_pos)
        self.quit_btn.update(mouse_pos)

    def draw(self, surface: pg.Surface) -> None:
        """Draws menu.

        :param surface: Surface to draw on.
        """
        surface.fill(pg.Color(40, 40, 40))
        title = FONT_LARGE.render("RTS GAME", True, pg.Color(0, 255, 200))
        title_rect = title.get_rect(center=(surface.width // 2, 100))
        surface.blit(title, title_rect)
        self.skirmish_btn.draw(surface)
        self.quit_btn.draw(surface)


@dataclass
class SkirmishSetup:
    """Setup menu for mode, size, map selection."""

    screen_size: InitVar[IntPoint]

    map_choice: str = ""
    game_mode: Literal["1v1", "2v2", "3v3", "4v4", "4ffa"] | None = None
    size_choice: Literal["tiny", "small", "medium", "large", "huge"] | None = None
    map_buttons: dict[str, _MenuButton] = field(default_factory=dict)

    def __post_init__(self, screen_size: IntPoint) -> None:

        self.mode_1v1 = _MenuButton(
            pg.Rect(screen_size[0] // 2 - 300, 150, 80, 50),
            "1v1",
            pg.Color(50, 100, 150),
            pg.Color(100, 150, 200),
        )
        self.mode_2v2 = _MenuButton(
            pg.Rect(screen_size[0] // 2 - 200, 150, 80, 50),
            "2v2",
            pg.Color(50, 100, 150),
            pg.Color(100, 150, 200),
        )
        self.mode_3v3 = _MenuButton(
            pg.Rect(screen_size[0] // 2 - 100, 150, 80, 50),
            "3v3",
            pg.Color(50, 100, 150),
            pg.Color(100, 150, 200),
        )
        self.mode_4v4 = _MenuButton(
            pg.Rect(screen_size[0] // 2, 150, 80, 50), "4v4", pg.Color(50, 100, 150), pg.Color(100, 150, 200)
        )
        self.mode_4ffa = _MenuButton(
            pg.Rect(screen_size[0] // 2 + 100, 150, 80, 50),
            "4FFA",
            pg.Color(50, 100, 150),
            pg.Color(100, 150, 200),
        )

        self.size_tiny = _MenuButton(
            pg.Rect(200, 220, 120, 50), "Tiny", pg.Color(50, 100, 150), pg.Color(100, 150, 200)
        )
        self.size_small = _MenuButton(
            pg.Rect(350, 220, 120, 50), "Small", pg.Color(50, 100, 150), pg.Color(100, 150, 200)
        )
        self.size_medium = _MenuButton(
            pg.Rect(500, 220, 120, 50), "Medium", pg.Color(50, 100, 150), pg.Color(100, 150, 200)
        )
        self.size_large = _MenuButton(
            pg.Rect(650, 220, 120, 50), "Large", pg.Color(50, 100, 150), pg.Color(100, 150, 200)
        )
        self.size_huge = _MenuButton(
            pg.Rect(800, 220, 120, 50), "Huge", pg.Color(50, 100, 150), pg.Color(100, 150, 200)
        )

        map_list = list(MAPS.keys())
        for i, map_name in enumerate(map_list):
            x = 100 + (i % 2) * 300
            y = 350 + (i // 2) * 80
            self.map_buttons[map_name] = _MenuButton(
                pg.Rect(x, y, 200, 60), map_name, pg.Color(100, 100, 100), pg.Color(150, 150, 150)
            )

        self.start_btn = _MenuButton(
            pg.Rect(screen_size[0] // 2 - 80, screen_size[1] - 100, 160, 50),
            "Start Game",
            pg.Color(50, 150, 50),
            pg.Color(100, 200, 100),
        )
        self.spectate_btn = _MenuButton(
            pg.Rect(screen_size[0] // 2 + 100, screen_size[1] - 100, 160, 50),
            "Spectate",
            pg.Color(100, 50, 150),
            pg.Color(150, 100, 200),
        )
        self.back_btn = _MenuButton(
            pg.Rect(20, screen_size[1] - 70, 120, 50), "Back", pg.Color(150, 100, 50), pg.Color(200, 150, 100)
        )

    def handle_event(self, event: pg.Event) -> Any:
        """Handles setup events.

        :param event: Pygame event.
        :return: Transition tuple or None.
        """
        if event.type == pg.MOUSEBUTTONDOWN:
            if self.mode_1v1.is_clicked(event.pos):
                self.game_mode = "1v1"
            elif self.mode_2v2.is_clicked(event.pos):
                self.game_mode = "2v2"
            elif self.mode_3v3.is_clicked(event.pos):
                self.game_mode = "3v3"
            elif self.mode_4v4.is_clicked(event.pos):
                self.game_mode = "4v4"
            elif self.mode_4ffa.is_clicked(event.pos):
                self.game_mode = "4ffa"

            if self.size_tiny.is_clicked(event.pos):
                self.size_choice = "tiny"
            elif self.size_small.is_clicked(event.pos):
                self.size_choice = "small"
            elif self.size_medium.is_clicked(event.pos):
                self.size_choice = "medium"
            elif self.size_large.is_clicked(event.pos):
                self.size_choice = "large"
            elif self.size_huge.is_clicked(event.pos):
                self.size_choice = "huge"

            for map_name, btn in self.map_buttons.items():
                if btn.is_clicked(event.pos):
                    self.map_choice = map_name

            if self.start_btn.is_clicked(event.pos) and self.game_mode and self.size_choice and self.map_choice:
                return "start_game", self.game_mode, self.size_choice, self.map_choice, False

            if self.spectate_btn.is_clicked(event.pos) and self.game_mode and self.size_choice and self.map_choice:
                return "start_game", self.game_mode, self.size_choice, self.map_choice, True

            if self.back_btn.is_clicked(event.pos):
                return "menu"

        return None

    def update(self, mouse_pos: IntPoint) -> None:
        """Updates button hovers.

        :param mouse_pos: Mouse position.
        """
        self.mode_1v1.update(mouse_pos)
        self.mode_2v2.update(mouse_pos)
        self.mode_3v3.update(mouse_pos)
        self.mode_4v4.update(mouse_pos)
        self.mode_4ffa.update(mouse_pos)
        self.size_tiny.update(mouse_pos)
        self.size_small.update(mouse_pos)
        self.size_medium.update(mouse_pos)
        self.size_large.update(mouse_pos)
        self.size_huge.update(mouse_pos)
        for btn in self.map_buttons.values():
            btn.update(mouse_pos)

        self.start_btn.update(mouse_pos)
        self.spectate_btn.update(mouse_pos)
        self.back_btn.update(mouse_pos)

    def draw(self, surface: pg.Surface) -> None:
        """Draws setup menu.

        :param surface: Surface to draw on.
        """
        surface.fill(pg.Color(40, 40, 40))

        title = FONT_LARGE.render("Skirmish Setup", True, pg.Color(0, 255, 200))
        title_rect = title.get_rect(center=(surface.width // 2, 40))
        surface.blit(title, title_rect)

        mode_label = FONT_MEDIUM.render("Select Game Mode:", True, pg.Color(200, 200, 200))
        surface.blit(mode_label, (50, 120))
        self.mode_1v1.draw(surface)
        self.mode_2v2.draw(surface)
        self.mode_3v3.draw(surface)
        self.mode_4v4.draw(surface)
        self.mode_4ffa.draw(surface)

        if self.game_mode:
            mode_text = FONT_MEDIUM.render(f"Selected: {self.game_mode}", True, pg.Color(100, 255, 100))
            surface.blit(mode_text, (surface.width - 250, 160))

        size_label = FONT_MEDIUM.render("Select Size:", True, pg.Color(200, 200, 200))
        surface.blit(size_label, (50, 190))
        self.size_tiny.draw(surface)
        self.size_small.draw(surface)
        self.size_medium.draw(surface)
        self.size_large.draw(surface)
        self.size_huge.draw(surface)

        if self.size_choice:
            size_text = FONT_MEDIUM.render(f"Selected: {self.size_choice}", True, pg.Color(100, 255, 100))
            surface.blit(size_text, (surface.width - 250, 230))

        map_label = FONT_MEDIUM.render("Select Map:", True, pg.Color(200, 200, 200))
        surface.blit(map_label, (50, 320))
        for btn in self.map_buttons.values():
            btn.draw(surface)

        if self.map_choice:
            map_text = FONT_MEDIUM.render(f"Selected: {self.map_choice}", True, pg.Color(100, 255, 100))
            surface.blit(map_text, (surface.width - 250, 390))

        self.start_btn.draw(surface)
        self.spectate_btn.draw(surface)
        self.back_btn.draw(surface)


@dataclass(kw_only=True)
class VictoryScreen:
    """Displays win/loss message with continue button.

    :param is_victory: Victory status (True/False/None).
    :param all_stats: Dict of team stats.
    :param player_team: Player's team.
    """

    screen_size: InitVar[IntPoint]
    is_victory: bool
    # pyrefly: ignore [implicit-any-type-argument]
    all_stats: dict
    player_team: Team | None = None

    def __post_init__(self, screen_size: IntPoint) -> None:
        self.continue_btn = _MenuButton(
            pg.Rect(screen_size[0] // 2 - 100, screen_size[1] // 2 + 300, 200, 60),
            "Continue",
            pg.Color(50, 150, 50),
            pg.Color(100, 200, 100),
        )

        # Table configuration
        self.table_x = 100
        self.table_y = 250
        self.table_width = 800
        self.col_widths = [100] * 8
        # Player, Units Created, Units Killed, Units Lost, Buildings Constructed,
        # Buildings Razed, Buildings Lost, Credits Earned
        self.row_height = 30
        self.num_rows = len(self.all_stats) + 1  # +1 for header
        self.table_height = self.num_rows * self.row_height
        self.line_color = pg.Color(255, 255, 255)
        self.header_color = pg.Color(100, 100, 100)
        self.row_color_even = pg.Color(40, 40, 40)
        self.row_color_odd = pg.Color(60, 60, 60)

    def handle_event(self, event: pg.Event) -> str | None:
        """Handles victory screen events.

        :param event: Pygame event.
        :return: Transition string or None.
        """
        if event.type == pg.MOUSEBUTTONDOWN and self.continue_btn.is_clicked(event.pos):
            return "menu"

        return None

    def update(self, mouse_pos: IntPoint) -> None:
        """Updates button hover.

        :param mouse_pos: Mouse position.
        """
        self.continue_btn.update(mouse_pos)

    def draw(self, surface: pg.Surface) -> None:
        """Draws victory screen with stats table.

        :param surface: Surface to draw on.
        """
        surface.fill(pg.Color(20, 20, 20))

        if self.is_victory is None:
            title_text = "MATCH ENDED"
            title_color = pg.Color(0, 255, 200)
            message_text = "All HQs have been destroyed."
            message_color = pg.Color(200, 200, 200)
        elif self.is_victory:
            title_text = "VICTORY!"
            title_color = pg.Color(0, 255, 100)
            message_text = "All enemies defeated!"
            message_color = pg.Color(100, 255, 150)
        else:
            title_text = "DEFEAT!"
            title_color = pg.Color(255, 50, 50)
            message_text = "Your HQ was destroyed!"
            message_color = pg.Color(255, 100, 100)

        title = FONT_LARGE.render(title_text, True, title_color)
        message = FONT_MEDIUM.render(message_text, True, message_color)

        title_rect = title.get_rect(center=(surface.width // 2, 150))
        msg_rect = message.get_rect(center=(surface.width // 2, 200))

        surface.blit(title, title_rect)
        surface.blit(message, msg_rect)

        if self.all_stats:
            # Draw table
            # Horizontal lines
            for i in range(self.num_rows + 1):
                y = self.table_y + i * self.row_height
                pg.draw.line(
                    surface,
                    self.line_color,
                    (self.table_x, y),
                    (self.table_x + self.table_width, y),
                    2,
                )

            # Vertical lines
            x_pos = self.table_x
            for width in self.col_widths:
                pg.draw.line(
                    surface,
                    self.line_color,
                    (x_pos, self.table_y),
                    (x_pos, self.table_y + self.table_height),
                    2,
                )
                x_pos += width

            # Header row
            headers = [
                "Player",
                "Produced",
                "Killed",
                "Casualties",
                "Built",
                "Raized",
                "Raized by",
                "Economy",
            ]
            x_pos = self.table_x
            for i, header in enumerate(headers):
                text_surf = FONT_MEDIUM.render(header, True, pg.Color("white"))
                text_rect = text_surf.get_rect(
                    center=(x_pos + self.col_widths[i] // 2, self.table_y + self.row_height // 2)
                )
                # Background for header
                pg.draw.rect(
                    surface,
                    self.header_color,
                    (x_pos, self.table_y, self.col_widths[i], self.row_height),
                )
                surface.blit(text_surf, text_rect)
                x_pos += self.col_widths[i]

            # Data rows
            sorted_stats = sorted(self.all_stats.items(), key=lambda item: item[0])  # Sort by team name
            x_pos = self.table_x
            for row_idx, (team_name, stats) in enumerate(sorted_stats):
                row_y = self.table_y + (row_idx + 1) * self.row_height
                row_color = self.row_color_even if row_idx % 2 == 0 else self.row_color_odd
                pg.draw.rect(surface, row_color, (self.table_x, row_y, self.table_width, self.row_height))

                team_enum = _get_team_enum(team_name)
                team_color = team_to_color[team_enum] if team_enum else pg.Color(255, 255, 255)

                values = [
                    team_name,
                    str(stats.get("units_created", 0)),
                    str(stats.get("units_destroyed", 0)),
                    str(stats.get("units_lost", 0)),
                    str(stats.get("buildings_constructed", 0)),
                    str(stats.get("buildings_destroyed", 0)),
                    str(stats.get("buildings_lost", 0)),
                    f"${stats.get('credits_earned', 0):,}",
                ]

                for col_idx, value in enumerate(values):
                    color = team_color if col_idx == 0 else pg.Color(255, 255, 255)
                    text_surf = FONT_MEDIUM.render(value, True, color)
                    text_rect = text_surf.get_rect(
                        center=(x_pos + self.col_widths[col_idx] // 2, row_y + self.row_height // 2)
                    )
                    surface.blit(text_surf, text_rect)
                    x_pos += self.col_widths[col_idx]

                x_pos = self.table_x  # Reset for next row

        self.continue_btn.draw(surface)

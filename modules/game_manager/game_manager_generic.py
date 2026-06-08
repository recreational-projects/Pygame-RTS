"""Implements generic GameManager."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pygame as pg

from modules.data_2d import (
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)
from modules.game_state import GameState
from modules.screens import MainMenu, SkirmishSetup, VictoryScreen


@dataclass(kw_only=True)
class GameManagerGeneric(ABC):
    """Abstract generic GameManager orchestrates state machine, initializes game data, runs loops.

    Handles menu, setup, playing, victory/defeat states.
    """

    screen: pg.Surface = field(init=False)
    clock: pg.time.Clock = field(init=False)
    state: GameState = field(init=False)
    main_menu: MainMenu = field(init=False)
    skirmish_setup: SkirmishSetup = field(init=False)
    victory_screen: VictoryScreen | None = field(init=False)
    running: bool = False

    def __post_init__(self) -> None:
        pg.init()
        self.screen = pg.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pg.display.set_caption("Paper Tigers")
        self.clock = pg.time.Clock()
        self.state = GameState.MENU

        screen_size_ = self.screen.size
        self.main_menu = MainMenu(screen_size_)
        self.skirmish_setup = SkirmishSetup(screen_size_)
        self.victory_screen = None
        self.running = True

    def run(self) -> None:
        """State machine loop: menu -> setup -> playing -> victory/defeat -> menu."""
        while self.running:
            if self.state == GameState.MENU:
                self.main_menu.update(pg.mouse.get_pos())
                self.main_menu.draw(self.screen)
                for event in pg.event.get():
                    if event.type == pg.QUIT:
                        self.running = False

                    result = self.main_menu.handle_event(event)
                    if result == "skirmish_setup":
                        self.state = GameState.SKIRMISH_SETUP
                    elif result == "quit":
                        self.running = False

                pg.display.flip()
                self.clock.tick(60)

            elif self.state == GameState.SKIRMISH_SETUP:
                self.skirmish_setup.update(pg.mouse.get_pos())
                self.skirmish_setup.draw(self.screen)

                for event in pg.event.get():
                    if event.type == pg.QUIT:
                        self.running = False

                    result = self.skirmish_setup.handle_event(event)
                    if result == "menu":
                        self.state = GameState.MENU
                        self.skirmish_setup = SkirmishSetup(
                            screen_size=self.screen.size,
                        )
                    elif result and result[0] == "start_game":
                        _, game_mode, size_choice, map_choice, spectate = result
                        self._initialize_game(
                            game_mode=game_mode, size_name=size_choice, map_name=map_choice, spectator_mode=spectate
                        )
                        self.state = GameState.PLAYING

                pg.display.flip()
                self.clock.tick(60)

            elif self.state == GameState.PLAYING:
                self._run_game()

            elif self.state in (GameState.VICTORY, GameState.DEFEAT):
                if self.victory_screen is None:
                    raise ValueError("No victory screen")

                self.victory_screen.update(pg.mouse.get_pos())
                self.victory_screen.draw(self.screen)

                for event in pg.event.get():
                    if event.type == pg.QUIT:
                        self.running = False
                    result = self.victory_screen.handle_event(event)
                    if result == "menu":
                        self.state = GameState.MENU
                        self.skirmish_setup = SkirmishSetup(
                            screen_size=self.screen.size,
                        )

                pg.display.flip()
                self.clock.tick(60)

        pg.quit()

    @abstractmethod
    def _run_game(self) -> None:
        pass

    @abstractmethod
    def _initialize_game(self, *, game_mode: str, size_name: str, map_name: str, spectator_mode: bool = False) -> None:
        pass

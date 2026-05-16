from enum import Enum


class GameState(Enum):
    """Defining the high-level states of the game, used by the GameManager for state transitions."""

    MENU = 1  # Main menu screen.
    SKIRMISH_SETUP = 2  # Setup screen for skirmish games.
    PLAYING = 3  # Active gameplay.
    VICTORY = 4  # Victory screen.
    DEFEAT = 5  # Defeat screen.

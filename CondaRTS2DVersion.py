"""Runs the 2d version of the game."""

from modules.game_manager import GameManager


def main() -> None:
    """Run the game."""
    manager = GameManager()
    manager.run()


if __name__ == "__main__":
    main()

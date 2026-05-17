import pygame as pg


class GameConsole:
    """Placeholder console for logging messages.

    Not fully implemented.
    """

    def __init__(self) -> None:
        self.messages = []

    def log(self, message: str) -> None:
        """Adds a message to the console log.

        :param message: Log message.
        """
        self.messages.append(message)

    def handle_event(self, event: pg.Event) -> None:
        """Handles console-specific events (placeholder).

        :param event: Pygame event.
        """
        pass

    def draw(self, surface: pg.Surface) -> None:
        """Draws console (placeholder).

        :param surface: Surface to draw on.
        """
        pass

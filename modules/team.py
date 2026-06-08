"""Implements Team."""

from enum import Enum

from pygame import Color


class Team(Enum):
    RED = 1
    BLUE = 2
    GREEN = 3
    CYAN = 4
    MAGENTA = 5
    ORANGE = 6
    YELLOW = 7
    GREY = 8


team_to_color = {
    Team.RED: Color(255, 0, 0),
    Team.BLUE: Color(0, 0, 255),
    Team.GREEN: Color(0, 255, 0),
    Team.CYAN: Color(0, 255, 255),
    Team.MAGENTA: Color(255, 0, 255),
    Team.ORANGE: Color(255, 165, 0),
    Team.YELLOW: Color(255, 255, 0),
    Team.GREY: Color(128, 128, 128),
}

team_to_name = {
    Team.RED: "Red",
    Team.BLUE: "Blue",
    Team.GREEN: "Green",
    Team.CYAN: "Cyan",
    Team.MAGENTA: "Magenta",
    Team.ORANGE: "Orange",
    Team.YELLOW: "Yellow",
    Team.GREY: "Grey",
}

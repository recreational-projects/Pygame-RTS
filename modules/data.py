"""Data not specific to 2d/iso mode."""

UNIT_BUTTON_LABELS = {
    "AttackHelicopter": "Attack Heli",
    "BlackMarket": "Black Market",
    "HeavyTank": "Heavy Tank",
    "MachineGunVehicle": "MG Vehicle",
    "OilDerrick": "Oil Derrick",
    "PowerPlant": "Power Plant",
    "RocketArtillery": "Rocket Artillery",
    "RocketSoldier": "Rocket Soldier",
    "ShaleFracker": "Shale Fracker",
    "TankDestroyer": "Tank Destroyer",
    "WarFactory": "War Factory",
}
"""Unit button labels for the production interface where they should differ from the unit name."""


class Palette:
    _RED = (255, 0, 0)
    _GREEN = (0, 255, 0)
    PLACEMENT_VALID_COLOR = _GREEN
    PLACEMENT_INVALID_COLOR = _GREEN

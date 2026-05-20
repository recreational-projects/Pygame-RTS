"""Data specific to 2d mode."""

"""These constants define the dimensions and behavior of the game screen, map, and related UI elements."""

SCREEN_WIDTH = 1280
"""Overall window size."""
SCREEN_HEIGHT = 720
"""Overall window size."""
CONSOLE_HEIGHT = 100
"""Reserves space at the bottom for a console (though not fully implemented)."""
MAP_WIDTH = 100000
"""Define the playable world size."""
MAP_HEIGHT = 80000
"""Define the playable world size."""
TILE_SIZE = 40
"""Used for grid snapping and procedural map generation."""
MINI_MAP_WIDTH = 200
"""Size the minimap in the corner."""
MINI_MAP_HEIGHT = 150
"""Size the minimap in the corner."""
PAN_EDGE = 30
"""Control edge-scrolling camera panning."""
PAN_SPEED = 10
"""Control edge-scrolling camera panning."""
STARTING_POSITIONS_EDGE_OFFSET = 50

PLASMA_BURN_PARTICLE_COUNT: int = 10
PLASMA_BURN_DURATION: int = 2
PROJECTILE_LIFETIME = 5.0


# Dictionary of maps with dimensions and base colors for procedural terrain generation.
# UNIT_CLASSES defines stats for all unit and building types: cost, health, speed, weapons, etc.

MAPS = {
    "Desert": {"width": 2560, "height": 1440, "color": (139, 120, 80)},
    "Forest": {"width": 3200, "height": 1800, "color": (34, 100, 34)},
    "Ice": {"width": 2560, "height": 1440, "color": (180, 200, 220)},
    "Urban": {"width": 2560, "height": 1440, "color": (100, 100, 100)},
}

UNIT_CLASSES = {
    "Infantry": {
        "cost": 100,
        "hp": 125,
        "speed": 0.5,
        "attack_range": 40,
        "sight_range": 120,
        "weapons": [
            {
                "name": "Rifle",
                "damage": 10,
                "fire_rate": 0.6,
                "projectile_speed": 10,
                "projectile_length": 8,
                "projectile_width": 4,
                "cooldown": 25,
            }
        ],
        "size": (16, 16),
        "air": False,
        "is_building": False,
    },
    "Tank": {
        "cost": 700,
        "hp": 300,
        "speed": 0.6,
        "attack_range": 80,
        "sight_range": 200,
        "weapons": [
            {
                "name": "Cannon",
                "damage": 80,
                "fire_rate": 0.3,
                "projectile_speed": 10,
                "projectile_length": 12,
                "projectile_width": 6,
                "cooldown": 50,
            }
        ],
        "size": (30, 20),
        "air": False,
        "is_building": False,
    },
    "Grenadier": {
        "cost": 300,
        "hp": 100,
        "speed": 0.5,
        "attack_range": 100,
        "sight_range": 120,
        "weapons": [
            {
                "name": "Grenade",
                "damage": 20,
                "fire_rate": 0.75,
                "projectile_speed": 10,
                "projectile_length": 10,
                "projectile_width": 5,
                "cooldown": 20,
            }
        ],
        "size": (16, 16),
        "air": False,
        "is_building": False,
    },
    "MachineGunVehicle": {
        "cost": 600,
        "hp": 200,
        "speed": 0.8,
        "attack_range": 120,
        "sight_range": 200,
        "weapons": [
            {
                "name": "MG",
                "damage": 25,
                "fire_rate": 0.3,
                "projectile_speed": 10,
                "projectile_length": 6,
                "projectile_width": 3,
                "cooldown": 50,
            }
        ],
        "size": (35, 25),
        "air": False,
        "is_building": False,
    },
    "RocketArtillery": {
        "cost": 800,
        "hp": 150,
        "speed": 0.5,
        "attack_range": 150,
        "sight_range": 175,
        "weapons": [
            {
                "name": "Rockets",
                "damage": 200,
                "fire_rate": 0.1,
                "projectile_speed": 10,
                "projectile_length": 15,
                "projectile_width": 8,
                "cooldown": 150,
            }
        ],
        "size": (40, 25),
        "air": False,
        "is_building": False,
    },
    "AttackHelicopter": {
        "cost": 1200,
        "hp": 200,
        "speed": 0.9,
        "attack_range": 100,
        "sight_range": 175,
        "weapons": [
            {
                "name": "Missiles",
                "damage": 30,
                "fire_rate": 0.375,
                "projectile_speed": 10,
                "projectile_length": 10,
                "projectile_width": 4,
                "cooldown": 40,
            }
        ],
        "size": (25, 15),
        "air": True,
        "fly_height": 10,
        "is_building": False,
    },
    "Headquarters": {
        "cost": 1000,
        "starting_credits": 7500,
        "hp": 500,
        "speed": 0,
        "attack_range": 0,
        "sight_range": 200,
        # pyrefly: ignore [implicit-any-empty-container]
        "weapons": [],
        "size": (40, 40),
        "air": False,
        "is_building": True,
    },
    "Barracks": {
        "cost": 300,
        "hp": 200,
        "speed": 0,
        "attack_range": 0,
        "sight_range": 200,
        # pyrefly: ignore [implicit-any-empty-container]
        "weapons": [],
        "producible": ["Infantry", "Grenadier"],
        "production_time": 60,
        "gate_width": 16,
        "half_door_offset": 12,
        "door_color": (60, 60, 60),
        "size": (32, 32),
        "air": False,
        "is_building": True,
    },
    "WarFactory": {
        "cost": 500,
        "hp": 200,
        "speed": 0,
        "attack_range": 0,
        "sight_range": 200,
        # pyrefly: ignore [implicit-any-empty-container]
        "weapons": [],
        "producible": ["Tank", "MachineGunVehicle", "RocketArtillery"],
        "production_time": 60,
        "gate_width": 16,
        "half_door_offset": 12,
        "door_color": (60, 60, 60),
        "size": (40, 32),
        "air": False,
        "is_building": True,
    },
    "Hangar": {
        "cost": 600,
        "hp": 200,
        "speed": 0,
        "attack_range": 0,
        "sight_range": 200,
        # pyrefly: ignore [implicit-any-empty-container]
        "weapons": [],
        "producible": ["AttackHelicopter"],
        "production_time": 90,
        "gate_width": 8,
        "half_door_offset": 8,
        "door_color": (80, 80, 80),
        "size": (36, 28),
        "air": False,
        "is_building": True,
    },
    "PowerPlant": {
        "cost": 300,
        "hp": 200,
        "speed": 0,
        "attack_range": 0,
        "sight_range": 200,
        # pyrefly: ignore [implicit-any-empty-container]
        "weapons": [],
        "size": (32, 32),
        "air": False,
        "is_building": True,
    },
    "OilDerrick": {
        "cost": 300,
        "hp": 200,
        "speed": 0,
        "attack_range": 0,
        "sight_range": 200,
        # pyrefly: ignore [implicit-any-empty-container]
        "weapons": [],
        "income": 100,
        "income_interval": 300,
        "size": (24, 32),
        "air": False,
        "is_building": True,
    },
    "Refinery": {
        "cost": 2000,
        "hp": 200,
        "speed": 0,
        "attack_range": 0,
        "sight_range": 200,
        # pyrefly: ignore [implicit-any-empty-container]
        "weapons": [],
        "income": 125,
        "income_interval": 300,
        "size": (48, 32),
        "air": False,
        "is_building": True,
    },
    "ShaleFracker": {
        "cost": 800,
        "hp": 200,
        "speed": 0,
        "attack_range": 0,
        "sight_range": 200,
        # pyrefly: ignore [implicit-any-empty-container]
        "weapons": [],
        "income": 165,
        "income_interval": 300,
        "size": (28, 28),
        "air": False,
        "is_building": True,
    },
    "BlackMarket": {
        "cost": 1500,
        "hp": 200,
        "speed": 0,
        "attack_range": 0,
        "sight_range": 200,
        # pyrefly: ignore [implicit-any-empty-container]
        "weapons": [],
        "income": 200,
        "income_interval": 300,
        "size": (36, 24),
        "air": False,
        "is_building": True,
    },
    "Turret": {
        "cost": 400,
        "hp": 200,
        "speed": 0,
        "attack_range": 300,
        "sight_range": 200,
        "weapons": [
            {
                "name": "TurretGun",
                "damage": 20,
                "fire_rate": 0.67,
                "projectile_speed": 5,
                "projectile_length": 10,
                "projectile_width": 4,
                "cooldown": 30,
            }
        ],
        "size": (24, 24),
        "air": False,
        "is_building": True,
    },
}

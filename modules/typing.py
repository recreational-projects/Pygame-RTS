from typing import TypeGuard

import pygame as pg


def ensure_rect(val: object) -> None:
    if not is_rect(val):
        raise TypeError(f"{val}: unexpected non-`Rect` type: {type(val)}")


def is_rect(val: object) -> TypeGuard[pg.Rect]:
    return isinstance(val, pg.Rect)

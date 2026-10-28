"""Ramps and stairs the collision data does not have. No game access, so it is tested offline.

The walk grid is built from the zone's collision data, which leaves out some ramps and stairs: a raised terrace
or upper street then reads as a separate walkable piece with no way onto it. The game's own nav graph does link
those levels, but its waypoints can be far apart, and walking one of its long legs straight across a busy area
gets stuck on what lies between. So when the collision data has no route to a destination on another piece and
the nav graph has one, the wizard walks by the collision data to the nav route's last waypoint still on its own
piece, the foot of the ramp; from there by the nav legs, which are short where the ground climbs, only to the
first waypoint on the next piece, the top of the ramp; and plans again, so a long nav leg across the new level
goes by the collision data too.

Seen in the Commons (2026-10-28): the Smith of "Find the Smiths" stands on a terrace at height 253; the collision
data found no route, and the nav route's 5,000-long leg across the middle left the wizard stuck at (-1012, 851).
Walking to the foot of the ramp at (-3877, 1443) first, then up the nav legs, reached it; Olde Town's Smith was
reached the same way.
"""

from __future__ import annotations

import math
from typing import Callable

from .geometry import Point

RAMP_FOOT_MIN_DISTANCE = 500.0


def foot_of_the_ramp(nav_legs: list[Point] | None, piece_of: Callable[[Point], int | None], start: Point,
                     min_distance: float = RAMP_FOOT_MIN_DISTANCE) -> Point | None:
    """The last waypoint of the nav route `nav_legs` that is on the start's walkable piece (`piece_of`), when it is
    at least `min_distance` from the start; else None (no route, a start off the walk grid, or the wizard already
    at the foot, where the nav legs take over)."""
    here = piece_of(start)
    if not nav_legs or here is None:
        return None
    on_this_side = [point for point in nav_legs if piece_of(point) == here]
    if not on_this_side:
        return None
    foot = on_this_side[-1]
    return foot if math.dist(foot, start) >= min_distance else None


def top_of_the_ramp(nav_legs: list[Point] | None, piece_of: Callable[[Point], int | None], start: Point) -> Point | None:
    """At the foot of the ramp: the first waypoint of the nav route on another walkable piece of the grid, so the nav
    walk stops once up the ramp and the next turn plans again from the new level, where a long nav leg across it
    goes by the collision data instead; None when no later waypoint is on the grid (the nav legs finish the walk)."""
    here = piece_of(start)
    if not nav_legs or here is None:
        return None
    return next((point for point in nav_legs if piece_of(point) not in (None, here)), None)

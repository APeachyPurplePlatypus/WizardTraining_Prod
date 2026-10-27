"""Teleport volumes inside a zone, and which one to walk into when the target can't be reached on foot.
No game access, so it is tested offline.

Some zones are split into areas with no walkable path between them. Triton Avenue's lower street and its
upper level differ by about 1,100 units of height; the game joins them with teleport volumes ("Tele Up",
"Tele Down") that move the wizard when it walks in, like a door. Walking in is ordinary play, not the
memory-writing teleport this framework never uses.

The volumes are listed in the zone's volumes.xml, in KingsIsle's binary format. Its layout here was
inferred, not documented: a volume's name is stored with a one-byte prefix holding twice its length, and
after the name, x, y and z are floats 8, 20 and 32 bytes on, then the radius 60 bytes on. It was checked
on WC_Triton, where walking into "Tele Up" at (-16336, 1176) landed the wizard at (-17120, 880) on the
upper level. Values outside plausible ranges are dropped rather than trusted.
"""

from __future__ import annotations

import math
from collections import deque
import struct
from dataclasses import dataclass

from .geometry import Point, xy

VOLUME_NAME_PREFIX = b"TeleportVol_"
ENTER_EVENT_PREFIX = b"Enter_"
X_OFFSET, Y_OFFSET, Z_OFFSET, RADIUS_OFFSET = 8, 20, 32, 60
LEFT_ZONE, NO_EFFECT = "left the zone", "no effect"


@dataclass(frozen=True)
class TeleportVolume:
    name: str
    x: float
    y: float
    z: float
    radius: float

    @property
    def point(self) -> Point:
        return self.x, self.y


def parse_teleport_volumes(data: bytes) -> list[TeleportVolume]:
    volumes, start = [], data.find(VOLUME_NAME_PREFIX)
    while start != -1:
        volume = _volume_at(data, start)
        if volume is not None:
            volumes.append(volume)
        start = data.find(VOLUME_NAME_PREFIX, start + 1)
    return volumes


def _volume_at(data: bytes, start: int) -> TeleportVolume | None:
    if start < 1 or data[max(0, start - len(ENTER_EVENT_PREFIX)):start] == ENTER_EVENT_PREFIX:
        return None
    end = start + data[start - 1] // 2
    if end + RADIUS_OFFSET + 4 > len(data):
        return None
    try:
        name = data[start:end].decode("ascii")
    except UnicodeDecodeError:
        return None
    x, y, z, radius = (struct.unpack_from("<f", data, end + offset)[0]
                       for offset in (X_OFFSET, Y_OFFSET, Z_OFFSET, RADIUS_OFFSET))
    if not name.isprintable() or not all(math.isfinite(value) for value in (x, y, z, radius)):
        return None
    if max(abs(x), abs(y)) > 200_000 or abs(z) > 20_000 or not 10 <= radius <= 3000:
        return None
    return TeleportVolume(name, x, y, z, radius)


def describe_outcome(outcome) -> str:
    if isinstance(outcome, str):
        return outcome
    return "landed outside the known walkable area" if outcome is None else f"landed in walkable piece {outcome}"


def choose_crossing(volumes: list[tuple[TeleportVolume, int | None]], *, start_piece: int, goal_piece: int,
                    outcomes: dict[str, object], goal) -> TeleportVolume | None:
    """The teleport volume to walk into from `start_piece` toward `goal_piece`. `volumes` pairs each volume
    with the walkable piece it stands in; `outcomes` maps volumes already tried to the piece they landed
    in, LEFT_ZONE or NO_EFFECT. In order of preference:
    1. the first volume of the shortest chain known to lead to the goal's piece, such as Triton's High_Ledge
       and then Tele Down out of the TempestNexus area;
    2. the untried volume in the wizard's piece nearest the goal;
    3. the first volume of the shortest known chain to a piece that still has an untried volume.
    Volumes that left the zone or did nothing are not tried again."""
    chain = known_chain(volumes, outcomes, start_piece, lambda piece: piece == goal_piece)
    if chain:
        return chain[0]
    untried_here = [volume for volume, piece in volumes if piece == start_piece and volume.name not in outcomes]
    if untried_here:
        return min(untried_here, key=lambda volume: math.dist(volume.point, xy(goal)))
    has_untried = {piece for volume, piece in volumes if volume.name not in outcomes}
    chain = known_chain(volumes, outcomes, start_piece, lambda piece: piece in has_untried)
    return chain[0] if chain else None


def known_chain(volumes: list[tuple[TeleportVolume, int | None]], outcomes: dict[str, object], start_piece: int,
                arrived) -> list[TeleportVolume]:
    """The shortest chain of volumes known to lead piece to piece from `start_piece` to a piece for which
    `arrived(piece)` holds, or an empty list."""
    came_from = {start_piece: None}
    frontier = deque([start_piece])
    while frontier:
        piece = frontier.popleft()
        if piece != start_piece and arrived(piece):
            chain = []
            while came_from[piece] is not None:
                volume, piece = came_from[piece]
                chain.append(volume)
            return chain[::-1]
        for volume, standing_in in volumes:
            landed = outcomes.get(volume.name)
            if standing_in == piece and isinstance(landed, int) and landed not in came_from:
                came_from[landed] = (volume, piece)
                frontier.append(landed)
    return []

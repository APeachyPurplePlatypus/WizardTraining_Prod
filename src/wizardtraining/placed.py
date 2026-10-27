"""Objects placed in a zone, read from its gamedata.bin, for goals the quest arrow does not point at.
No game access, so it is tested offline.

Some goals have no arrow. In "Clear as Crystal" the arrow read (0, 0, 0): the goal the game tracked had
no quest helper, and the Cog to collect was not among the loaded entities. But the goal names its object
by tag ("WC_TA_Cog"), and the zone's gamedata.bin places six "WC_TA_Cog instance" objects.

gamedata.bin is KingsIsle's binary format, and its layout here was inferred, not documented: an object's
name, "<template> instance" or "<template> instance (n)", is stored after a 2-byte little-endian length,
and its x, y and z are floats 54, 50 and 46 bytes before the name. It was checked against Triton Avenue:
WC_Triton_Telepapad_04 decodes to (-10536.5, -6778.9, 137.5), as the live entity reads, and the other
telepads sit where the zone's teleport volumes are.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass

from .geometry import Point

INSTANCE_NAME = re.compile(rb"[\x20-\x7e]+? instance(?: \(\d+\))?")
INSTANCE_SUFFIX = re.compile(r" instance(?: \(\d+\))?$")
X_BEFORE_NAME, Y_BEFORE_NAME, Z_BEFORE_NAME = 54, 50, 46


@dataclass(frozen=True)
class PlacedObject:
    template: str
    x: float
    y: float
    z: float

    @property
    def point(self) -> Point:
        return self.x, self.y

    @property
    def key(self) -> str:
        return f"{self.template}@{self.x:.0f},{self.y:.0f}"


def parse_placed_objects(data: bytes) -> list[PlacedObject]:
    placed = []
    for match in INSTANCE_NAME.finditer(data):
        start = match.start()
        if start < X_BEFORE_NAME:
            continue
        length = struct.unpack_from("<H", data, start - 2)[0]
        name = data[start:start + length].decode("ascii", errors="replace")
        if not INSTANCE_SUFFIX.search(name):
            continue
        x, y, z = (struct.unpack_from("<f", data, start - offset)[0]
                   for offset in (X_BEFORE_NAME, Y_BEFORE_NAME, Z_BEFORE_NAME))
        if all(math.isfinite(value) for value in (x, y, z)) and max(abs(x), abs(y)) < 200_000 and abs(z) < 20_000:
            placed.append(PlacedObject(INSTANCE_SUFFIX.sub("", name), x, y, z))
    return placed


def objects_for_goal(placed: list[PlacedObject], tags: list[str], *, me, visited=()) -> list[PlacedObject]:
    """Placed objects whose template is one of the goal's tags, nearest first, leaving out visited ones."""
    wanted = set(tags)
    found = [thing for thing in placed if thing.template in wanted and thing.key not in visited]
    return sorted(found, key=lambda thing: math.dist(thing.point, (me[0], me[1])))

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
GATE_NAME = re.compile(rb"[A-Za-z0-9_\-]*Gate[A-Za-z0-9_\-]*")
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
    """Objects named "<template> instance", and gates, which in the Commons are named without the suffix
    ("WC_GateCommons_ToRavenWood", in the same layout)."""
    instances = [(start, INSTANCE_SUFFIX.sub("", name)) for start, name, _ in _named_records(data, INSTANCE_NAME)
                 if INSTANCE_SUFFIX.search(name)]
    gates = [(start, name) for start, name, matched in _named_records(data, GATE_NAME)
             if GATE_WORD in name.lower() and matched.startswith(name)]
    placed = []
    for start, template in sorted(instances + gates):
        x, y, z = (struct.unpack_from("<f", data, start - offset)[0]
                   for offset in (X_BEFORE_NAME, Y_BEFORE_NAME, Z_BEFORE_NAME))
        if all(math.isfinite(value) for value in (x, y, z)) and max(abs(x), abs(y)) < 200_000 and abs(z) < 20_000:
            placed.append(PlacedObject(template, x, y, z))
    return placed


def parse_named_objects(data: bytes, names: list[str]) -> list[PlacedObject]:
    """Objects stored under exactly these names, which are not "<template> instance": "You Can Dig It" names its
    Dirt Mounds by tag ("WC_PetDirtMound-Cyclops2"), and Cyclops Lane's gamedata.bin holds "WC_PetDirtMound-Cyclops1",
    "-Cyclops2" and "-Cyclops3" in the layout of the other objects: the name after a 2-byte length, its x, y and z
    54, 50 and 46 bytes before. At (-8830, 6869), (-7007, 17048) and (-12045, 11574), each within 600 units of the
    zone's walkable ground."""
    placed, seen = [], set()
    for name in names:
        encoded = name.encode("ascii", errors="ignore")
        for match in re.finditer(re.escape(encoded), data):
            start = match.start()
            if not encoded or start < X_BEFORE_NAME or struct.unpack_from("<H", data, start - 2)[0] != len(encoded):
                continue
            x, y, z = (struct.unpack_from("<f", data, start - offset)[0]
                       for offset in (X_BEFORE_NAME, Y_BEFORE_NAME, Z_BEFORE_NAME))
            if (all(math.isfinite(value) for value in (x, y, z)) and max(abs(x), abs(y)) < 200_000 and abs(z) < 20_000
                    and (name, round(x), round(y)) not in seen):
                seen.add((name, round(x), round(y)))
                placed.append(PlacedObject(name, x, y, z))
    return placed


def _named_records(data: bytes, pattern: re.Pattern) -> list[tuple[int, str, str]]:
    """Where each match of `pattern` starts, the name as long as the 2-byte length before it says, and the match.
    A gate's name is the whole of its match or the start of it: "WC_GateCommons_ToRavenWood" is followed by a
    letter that belongs to the next field."""
    records = []
    for match in pattern.finditer(data):
        start = match.start()
        if start < X_BEFORE_NAME:
            continue
        length = struct.unpack_from("<H", data, start - 2)[0]
        name = data[start:start + length].decode("ascii", errors="replace")
        records.append((start, name, match.group().decode("ascii", errors="replace")))
    return records


GATE_WORD = "gate"
MIN_SHARED_WORD = 4


def words(text: str) -> set[str]:
    """Lower-case words of a template or zone name, split at separators and capitals: "WC-GateStreet_TritonLane"
    gives {"wc", "gate", "street", "triton", "lane"}."""
    return {word.lower() for word in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", text)}


def gate_toward(placed: list[PlacedObject], destination_zone: str, *, arrival=None) -> PlacedObject | None:
    """The street gate leading to `destination_zone`: one whose name holds a word of at least MIN_SHARED_WORD
    letters of the zone's name ("TritonLane" and "WC_Triton", "ToRavenWood" and "WC_Ravenwood"), else the gate
    nearest `arrival`, the point where the wizard came in from that zone, if given."""
    gates = [thing for thing in placed if GATE_WORD in thing.template.lower()]
    zone_words = {word for word in words(destination_zone.rsplit("/", 1)[-1]) if len(word) >= MIN_SHARED_WORD}
    named = [gate for gate in gates if any(word in gate.template.lower() for word in zone_words)]
    if named:
        return named[0]
    if arrival is not None and gates:
        return min(gates, key=lambda gate: math.dist(gate.point, (arrival[0], arrival[1])))
    return None


def objects_for_goal(placed: list[PlacedObject], tags: list[str], *, me, visited=()) -> list[PlacedObject]:
    """Placed objects whose template is one of the goal's tags, nearest first, leaving out visited ones."""
    wanted = set(tags)
    found = [thing for thing in placed if thing.template in wanted and thing.key not in visited]
    return sorted(found, key=lambda thing: math.dist(thing.point, (me[0], me[1])))

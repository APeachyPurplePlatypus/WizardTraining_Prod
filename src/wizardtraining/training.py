"""Going back to the wizard's school to learn the spells its level now allows, then back to the quest at hand. No game
access, so it is tested offline.

The operator asked the wizard to go back to its school every so often to learn new spells, and to check first
whether it is in a dungeon quest: "If the answer is no, then you can direct to train and then go back to the quest
at hand." In a dungeon here means inside one: a tower or dungeon instance, which a walk out of gives up. Those are the
zones the wizard entered with X at an interact prompt, and Wizard City's interiors named "_T1", "_T2" and so on
(General Akilles' tower, Sapphyra's tower and Lord Nightshade's dungeon among them; houses are "_H1"). A defeat in
Lord Nightshade's dungeon put the wizard out in the Commons, two doors from its school.

Each school's Wizard City professor teaches the school's spells from the level listed, free of training points
("Free" in the training window). The lists are Wizard404's (wizard404.com, trainable spells by school, retrieved
2026-10-27), checked in the game for Ice up to level 10. They only decide when to go: at the professor, every free
spell the window offers at or below the wizard's level is learned. A visit is made once per level, so a name spelled
differently in the game cannot send the wizard back again and again.

The way there, zone by zone: in the school, to its professor, the only NPC placed there; in Ravenwood, into the
school's volume ("to IceSchool"); in the Commons, through its gate to Ravenwood; anywhere else, back toward the
Commons through the zone's way out: Triton Avenue, Cyclops Lane and Firecat Alley lead to Olde Town, Olde Town to the
Shopping District, and the Shopping District and Unicorn Way to the Commons. The Life, Death and Balance schools'
doors in Ravenwood are not teleport volumes, so their way in is not known yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

COMMONS = "WizardCity/WC_Hub"
RAVENWOOD = "WizardCity/WC_Ravenwood"
TOWER_OR_DUNGEON_NAME = re.compile(r"/Interiors/[^/]*_T\d+$")
HUB_WORD, EXIT_WORD, ENTRANCE_WORD = "hub", "exit", "entrance"
TRAINER, VOLUME, GATE = "trainer", "volume", "gate"


@dataclass(frozen=True)
class School:
    professor: str
    interior: str
    ravenwood_door: str
    spells: tuple[tuple[int, str], ...]


SCHOOLS = {
    "Ice": School("Lydia Greyrose", "WizardCity/Interiors/WC_SchoolFrost", "to IceSchool",
                  ((1, "Frost Beetle"), (5, "Snow Serpent"), (8, "Volcanic Shield"), (10, "Evil Snowman"),
                   (16, "Tower Shield"), (20, "Volcanic Golem"), (22, "Ice Wyvern"), (24, "Frostbite"),
                   (26, "Blizzard"), (28, "Ice Guardian"), (30, "Balefrost"))),
    "Fire": School("Dalia Falmea", "WizardCity/Interiors/WC_SchoolFire", "to FireSchool",
                   ((1, "Fire Cat"), (5, "Fire Elf"), (8, "Glacial Shield"), (10, "Sunbird"), (16, "Fire Trap"),
                    (18, "Heck Hound"), (20, "Glacial Golem"), (22, "Immolate"), (22, "Meteor Strike"),
                    (26, "Wyldfire"), (28, "Fire Elemental"))),
    "Storm": School("Halston Balestrom", "WizardCity/Interiors/WC_SchoolStorm", "to StormSchool",
                    ((1, "Thunder Snake"), (5, "Lightning Bats"), (8, "Thermic Shield"), (10, "Storm Shark"),
                     (16, "Storm Trap"), (18, "Water Elemental"), (20, "Thermic Golem"), (22, "Kraken"),
                     (26, "Windstorm"), (30, "Darkwind"))),
    "Myth": School("Cyrus Drake", "WizardCity/Interiors/WC_SchoolMyth", "to MythSchool",
                   ((1, "Blood Bat"), (3, "Golem Minion"), (5, "Troll"), (7, "Troll Minion"), (8, "Myth Trap"),
                    (10, "Cyclops"), (16, "Ether Shield"), (18, "Cyclops Minion"), (20, "Ether Golem"),
                    (22, "Humongofrog"), (26, "Time of Legend"))),
}


@dataclass(frozen=True)
class Way:
    kind: str
    name: str | None = None


def same_spell(first: str, second: str) -> bool:
    """"Blood Bat" and "Bloodbat" are one spell."""
    return "".join(first.lower().split()) == "".join(second.lower().split())


def spells_to_learn(school: str | None, level: int, known: list[str]) -> list[str]:
    """The spells the school's professor teaches at or below `level` that are not among `known`, by name."""
    if school not in SCHOOLS:
        return []
    return [name for needed, name in SCHOOLS[school].spells
            if needed <= level and not any(same_spell(name, spell) for spell in known)]


def in_dungeon(zone: str | None, entered_with_x: list[str]) -> bool:
    return isinstance(zone, str) and (zone in entered_with_x or TOWER_OR_DUNGEON_NAME.search(zone) is not None)


def way_out_toward_the_commons(volume_names: list[str]) -> str | None:
    """The volume that leads back toward the Commons: one named for the hub ("Street1 Hub Exit", "WC_Shop Hub"),
    else one named as an exit and not an entrance ("Street4 Street2 Exit"), else the zone's only volume ("Cavern to
    Street4" in the Haunted Cave)."""
    lowered = [(name, name.lower()) for name in volume_names]
    for wanted in (lambda name: HUB_WORD in name and ENTRANCE_WORD not in name,
                   lambda name: EXIT_WORD in name and ENTRANCE_WORD not in name):
        if found := [name for name, low in lowered if wanted(low)]:
            return found[0]
    return volume_names[0] if len(volume_names) == 1 else None


def way_to_school(zone: str | None, school: School, volume_names: list[str]) -> Way | None:
    """The next step toward the school's professor from `zone`, or None when no way on is known."""
    if zone == school.interior:
        return Way(TRAINER, school.professor)
    if zone == RAVENWOOD:
        door = next((name for name in volume_names if school.ravenwood_door.lower() in name.lower()), None)
        return Way(VOLUME, door) if door else None
    if zone == COMMONS:
        return Way(GATE, RAVENWOOD)
    out = way_out_toward_the_commons(volume_names)
    return Way(VOLUME, out) if out else None

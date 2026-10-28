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
TOWER_OR_DUNGEON_NAME = re.compile(r"/Interiors/[^/]*_T\d+$|/WC_Golem_Tower/WC_Golem_Tower_\d+$")
INTERIOR_PART = "/Interiors/"
HUB_WORD, EXIT_WORD, ENTRANCE_WORD, TOWER_WORD, COMMONS_WORD = "hub", "exit", "entrance", "tower", "commons"
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


def in_dungeon(zone: str | None, entered_with_x: list[str], dungeons: list[str] = ()) -> bool:
    """A tower floor or dungeon: named as one, an interior entered with X, or a zone behind a dungeon-entry box
    (`dungeons`, `RunRecord.dungeon_zones`) or under one: Sunken City is WizardCity/WC_Streets/WC_Sunken_City, named
    like a street. A street entered with X is not one: Triton Avenue's underwater zone
    (WC_Triton_Underwater/WC_Triton_Underwater) opens with X, and counted as a dungeon, it had no refill trips, so
    after each heavy fight the wizard walked on at under half health into the next pair of guards (18:48 to 19:02)."""
    return isinstance(zone, str) and ((zone in entered_with_x and INTERIOR_PART in zone)
                                      or any(zone == dungeon or zone.startswith(dungeon + "/") for dungeon in dungeons)
                                      or TOWER_OR_DUNGEON_NAME.search(zone) is not None)


def in_tower(zone: str | None, entered_with_x: list[str], dungeons: list[str] = ()) -> bool:
    """A tower floor: a dungeon whose zone is named for a tower. The game's travel buttons do not work there (the
    operator, 2026-10-28: "it works in dungeons but not towers"; Mark Location did nothing on a Golem Tower floor),
    and a walk out gives up its progress ("I don't think you can leave a tower without losing progress")."""
    return in_dungeon(zone, entered_with_x, dungeons) and TOWER_WORD in zone.rsplit("/", 1)[-1].lower()


def travel_buttons_allowed(zone: str | None, entered_with_x: list[str], leaving_resets: list[str], *,
                           use_travel_buttons: bool, leave_dungeons: bool, dungeons: list[str] = ()) -> bool:
    """Whether Mark Location, Recall Location and Go Home may be pressed in `zone`: with the travel buttons on, never
    on a tower floor nor in a dungeon found reset after a trip out, and in any other dungeon only with
    `leave_dungeons`. The first trip out of a dungeon (WC_Cyclops_T1, 01:07 to 01:12) marked the spot and went home,
    but Recall could not bring the wizard back in; until the operator decides, dungeons are refilled in place."""
    if not use_travel_buttons or in_tower(zone, entered_with_x, dungeons) or zone in leaving_resets:
        return False
    return leave_dungeons or not in_dungeon(zone, entered_with_x, dungeons)


def may_leave_to_refill(zone: str | None, entered_with_x: list[str], leaving_resets: list[str], *,
                        use_travel_buttons: bool, dungeons: list[str] = ()) -> bool:
    """A dungeon the wizard may leave by Go Home to refill and come back to by its return button
    (`gametravel.resume_instance`): with the travel buttons on, any dungeon but a tower floor and one found reset
    after a trip out. The operator, 2026-10-28 23:18 UTC: "ResumeInstanceButton can be used without approval to get
    back to where you were in the dungeon faster". Tower floors keep the old rule until a trip out of a dungeon has
    shown the button brings the wizard back with its progress kept."""
    return (use_travel_buttons and in_dungeon(zone, entered_with_x, dungeons)
            and not in_tower(zone, entered_with_x, dungeons) and zone not in leaving_resets)


def way_out_toward_the_commons(volume_names: list[str]) -> str | None:
    """The volume that leads back toward the Commons: one named for the hub ("Street1 Hub Exit", "WC_Shop Hub") or
    the Commons itself (Ravenwood's "Teleport location (to Commons)"), else one named as an exit and not an entrance
    ("Street4 Street2 Exit"), else the zone's only volume ("Cavern to Street4" in the Haunted Cave)."""
    lowered = [(name, name.lower()) for name in volume_names]
    for wanted in (lambda name: (HUB_WORD in name or COMMONS_WORD in name) and ENTRANCE_WORD not in name,
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


OLDE_TOWN, SHOPPING_DISTRICT = "WizardCity/WC_Streets/WC_OldeTown", "WizardCity/WC_Shop_Area"
TRITON, CYCLOPS, FIRECAT = ("WizardCity/WC_Streets/WC_Triton", "WizardCity/WC_Streets/WC_Cyclops",
                            "WizardCity/WC_Streets/WC_Firecat")
UNICORN_WAY, HAUNTED_CAVE, DARK_CAVE = ("WizardCity/WC_Streets/WC_Unicorn", "WizardCity/WC_Streets/WC_HauntedCave",
                                        "WizardCity/WC_Streets/WC_DarkCave")
ZONE_PARENT = {"WizardCity/WC_Ravenwood_Teleporter": RAVENWOOD, "WizardCity/WC_Golem_Tower": COMMONS, RAVENWOOD: COMMONS, SHOPPING_DISTRICT: COMMONS, UNICORN_WAY: COMMONS, "WizardCity/WC_NightSide": COMMONS,
               OLDE_TOWN: SHOPPING_DISTRICT, TRITON: OLDE_TOWN, CYCLOPS: OLDE_TOWN, FIRECAT: OLDE_TOWN,
               HAUNTED_CAVE: TRITON, DARK_CAVE: CYCLOPS, "WizardCity/WC_Streets/WC_Colossus": SHOPPING_DISTRICT,
               "WizardCity/WC_Streets/WC_Triton_Underwater/WC_Triton_Underwater": TRITON}
# Wizard City's zones as a tree around the Commons: each zone and the zone one door nearer to it. From the zone files
# (teleport volumes named for the hub and the "Street" numbers, and the street gates): the Commons leads to Ravenwood,
# the Shopping District, Unicorn Way and Golem Court (its "WC_Golem_Tower Hub Exit"); the Shopping District to Olde Town; Olde Town to Triton Avenue, Cyclops Lane
# and Firecat Alley; Triton Avenue to the Haunted Cave; Cyclops Lane to the Dark Cave. The Shopping District also
# leads to Colossus Boulevard (its gate "BigGenericBlocker_CollossusGate"; the boulevard's way out is "Street6 WC_Shops
# Exit"), which was missing, so a goal there could not be walked to from Triton Avenue (17:38).
DOWN_VOLUMES = {(SHOPPING_DISTRICT, OLDE_TOWN): "Shop Area to Street2",
                (TRITON, "WizardCity/WC_Streets/WC_Triton_Underwater/WC_Triton_Underwater"): "VolumeTritonUnderwater"}
# Triton Avenue's way under the water is the trigger volume "VolumeTritonUnderwater" on the lower street, not a
# TeleportVol: "Trouble Underfoot" sends the wizard to an NPC there, and the run stood at its arrow, unable to get
# close (18:28).
UP_VOLUMES = {DARK_CAVE: "Cavern to Street3"}
# The Dark Cave's two ways out are named for the streets they lead to; Street3 is Cyclops Lane (its own way out is
# "Street3 Street2 Exit"), the one toward the Commons. Its zone file names no hub or exit volume.
AREA_ZONES = {"Cyclops Lane": CYCLOPS, "Firecat Alley": FIRECAT, "Triton Avenue": TRITON, "Unicorn Way": UNICORN_WAY,
              "Olde Town": OLDE_TOWN, "Shopping District": SHOPPING_DISTRICT}
# The area names the spellbook's quest page shows (`txtWorld`), for the zones they are.


def zone_for_area(area: str | None) -> str | None:
    return AREA_ZONES.get(area.strip()) if area else None


def zones_toward_the_commons(zone: str) -> list[str]:
    """`zone`, then each zone one door nearer to the Commons, ending in the Commons; just `zone` if it is not in the
    tree."""
    chain = [zone]
    while chain[-1] in ZONE_PARENT:
        chain.append(ZONE_PARENT[chain[-1]])
    return chain


def next_zone_toward(zone: str | None, target: str) -> str | None:
    """The zone one door from `zone` on the way to `target`, or None when they are the same or one is not in the
    tree."""
    if not zone or zone == target:
        return None
    if zone not in ZONE_PARENT and zone != COMMONS:
        return None
    down = zones_toward_the_commons(target)
    if down[-1] != COMMONS:
        return None
    if zone in down:
        return down[down.index(zone) - 1]
    return ZONE_PARENT.get(zone)


def way_toward_zone(zone: str | None, target: str, volume_names: list[str]) -> Way | None:
    """The next door of the way from `zone` to `target`: back toward the Commons through the zone's way out, or on
    through the gate to the next zone, or the volume `DOWN_VOLUMES` names. None when none is known."""
    following = next_zone_toward(zone, target)
    if following is None:
        return None
    if ZONE_PARENT.get(zone) == following:
        hint = UP_VOLUMES.get(zone)
        out = way_out_toward_the_commons(volume_names) or next(
            (name for name in volume_names if hint and hint.lower() in name.lower()), None)
        return Way(VOLUME, out) if out else None
    if hint := DOWN_VOLUMES.get((zone, following)):
        name = next((name for name in volume_names if hint.lower() in name.lower()), None)
        return Way(VOLUME, name) if name else None
    return Way(GATE, following)

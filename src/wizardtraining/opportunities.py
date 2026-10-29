"""Opportunities: game features, tips and patterns that could speed progress, found while the run plays and kept
across runs (`RunRecord.opportunities`, knowledge.json).

The operator, 2026-10-29: "there is a lot going on in mmorpgs, you are going to need to decide when to add something
to your memory bank. Something like the quest help from ohers could speed up progress for you as you get better at the
game. there will be similar opportunities that arise. See if you can reconize these patterns", and "ensure this
behavior is added to the framework".

Three sources, none needing a click of its own: the game's text (tip boxes closed with OK, NPC dialog pages), numbers
the run measures (XP by activity, what fights cost, how many wisp walks gave nothing), and HUD buttons the framework
has never pressed. Each is merged by key into the store, and counted each time it is seen again. A status gate keeps
what brings in other players, spends gold or crowns, or needs a new kind of click as NEEDS_OPERATOR: it is reported,
never acted on. Pure: no game access.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import asdict, dataclass
from statistics import mean

FEATURE, PATTERN, BUTTON = "feature", "pattern", "button"
USABLE, NEEDS_OPERATOR = "usable", "needs the operator"

TIP_WORDS = re.compile(r"\b(button|click|group|mount|pet|reward|faster|free|bonus|daily|gift|finder|speed)\b",
                       re.IGNORECASE)
DIALOG_WORDS = re.compile(r"\b(button|click|press|mount|crowns?|membership|finder|spellbook|training points?|"
                          r"teleport\w*)\b", re.IGNORECASE)
OPERATOR_WORDS = re.compile(r"\b(players?|friends?|group|crowns?|gold|buy|purchase|membership|trade)\b",
                            re.IGNORECASE)

USED_HUD_BUTTONS = {"MarkButton", "GoHomeButton", "RecallButton", "ResumeInstanceButton", "btnSpellbook",
                    "btnCompass", "PotionButton", "ResumeInstanceGlow"}
BUTTON_WORDS = ("button", "btn")

EVIDENCE_LENGTH = 300
MEASURES_KEPT = 100
QUEST_OVER_FIGHT_RATIO = 5.0
FEW_QUESTS, FEW_FIGHTS, FEW_WISP_WALKS = 3, 5, 10
TAKEN_WISP_SHARE = 0.4
COSTLY_FIGHT_SHARE = 0.35


@dataclass
class Opportunity:
    """`key` names it for merging; `evidence` is what was seen or measured, the latest kept."""
    key: str
    kind: str
    source: str
    evidence: str
    first_seen: str
    times_seen: int = 1
    status: str = USABLE


def now_text() -> str:
    """The local time, as the event log writes it."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def status_for(text: str) -> str:
    """NEEDS_OPERATOR when the text speaks of other players, gold or crowns; else USABLE."""
    return NEEDS_OPERATOR if OPERATOR_WORDS.search(text) else USABLE


def key_of(kind: str, name: str) -> str:
    return f"{kind}:{' '.join(re.sub(r'[^a-z0-9 ]', ' ', name.lower()).split())[:60]}"


def from_tip(title: str, text: str, when: str) -> Opportunity | None:
    """A game box closed with OK whose title or text names a feature (TIP_WORDS): the "Quest Friend Finder" tip told
    of a HUD button that groups friendly players and teleports them to you (20:38)."""
    if not TIP_WORDS.search(f"{title} {text}"):
        return None
    return Opportunity(key_of(FEATURE, title or text[:40]), FEATURE, "a game tip box", text[:EVIDENCE_LENGTH], when,
                       status=status_for(f"{title} {text}"))


def from_dialog(speaker: str | None, pages: list[str], when: str) -> list[Opportunity]:
    """Dialog pages that point at something to use (DIALOG_WORDS: a button, a mount, training points...); story text
    with none of these words is left out, so the store keeps hints, not the plot."""
    found = []
    for page in pages:
        if (match := DIALOG_WORDS.search(page)) is not None:
            found.append(Opportunity(key_of(FEATURE, f"{match.group(0)} {page[:30]}"), FEATURE,
                                     f"dialog{' with ' + speaker if speaker else ''}", page[:EVIDENCE_LENGTH], when,
                                     status=status_for(page)))
    return found


def unused_buttons(names: list[str], used: set[str], when: str) -> list[Opportunity]:
    """HUD buttons the framework has never pressed: a new kind of click, so NEEDS_OPERATOR."""
    return [Opportunity(key_of(BUTTON, name), BUTTON, "the HUD", f"a HUD button never pressed: {name}", when,
                        status=NEEDS_OPERATOR)
            for name in dict.fromkeys(names) if name not in used and is_a_button(name)]


def is_a_button(name: str) -> bool:
    """A HUD window named as one button ("btnFriends", "OpenFishingButton"), not a window holding several
    ("compassAndTeleporterButtons", "windowForBtns", "CrownShopButtonsWindow"), which the first read listed too."""
    lowered = name.lower()
    return (any(word in lowered for word in BUTTON_WORDS) and "window" not in lowered
            and not lowered.endswith(("buttons", "btns")))


def measured_patterns(xp_by_activity: dict[str, list[int]], fight_costs: list[float], wisp_walks: list[bool],
                      when: str) -> list[Opportunity]:
    """Patterns from the run's numbers, once they are clear and steady: quest hand-ins paying QUEST_OVER_FIGHT_RATIO
    times a fight or more (over FEW_QUESTS hand-ins and FEW_FIGHTS fights), fights costing COSTLY_FIGHT_SHARE of the
    wizard's health or more on average, and TAKEN_WISP_SHARE or more of FEW_WISP_WALKS wisp walks giving nothing.
    `fight_costs` are fractions of the health pool; `wisp_walks` whether each gave anything."""
    found = []
    quests, fights = xp_by_activity.get("talk", []), xp_by_activity.get("battle", [])
    if len(quests) >= FEW_QUESTS and len(fights) >= FEW_FIGHTS and mean(fights) > 0 \
            and mean(quests) >= QUEST_OVER_FIGHT_RATIO * mean(fights):
        found.append(Opportunity(key_of(PATTERN, "quests pay more than fights"), PATTERN, "the run's XP",
                                 f"a quest hand-in gave {mean(quests):.0f} XP on average ({len(quests)} of them), a "
                                 f"fight {mean(fights):.0f} ({len(fights)}): avoid optional fights on the way to goals",
                                 when))
    if len(fight_costs) >= FEW_FIGHTS and mean(fight_costs) >= COSTLY_FIGHT_SHARE:
        found.append(Opportunity(key_of(PATTERN, "fights cost much of the health"), PATTERN, "the run's fights",
                                 f"a fight cost {mean(fight_costs):.0%} of the health pool on average "
                                 f"({len(fight_costs)} fights): each is a refill, so keep away from them", when))
    if len(wisp_walks) >= FEW_WISP_WALKS:
        empty = sum(1 for gained in wisp_walks if not gained) / len(wisp_walks)
        if empty >= TAKEN_WISP_SHARE:
            found.append(Opportunity(key_of(PATTERN, "wisps are often taken"), PATTERN, "the run's wisp walks",
                                     f"{empty:.0%} of {len(wisp_walks)} wisp walks gave nothing: wisps near other "
                                     "players are usually taken", when))
    return found


def note(store: dict[str, dict], found: Opportunity) -> bool:
    """Merge `found` into `store` by key: a new one is added, a known one counted again with the latest evidence and
    the stricter status. True when it is new."""
    known = store.get(found.key)
    if known is None:
        store[found.key] = asdict(found)
        return True
    known["times_seen"] = int(known.get("times_seen", 1)) + 1
    known["evidence"] = found.evidence
    if found.status == NEEDS_OPERATOR:
        known["status"] = NEEDS_OPERATOR
    return False


def describe(found: Opportunity) -> str:
    """One line for the event log and the reports."""
    gate = " (needs the operator: reported, not acted on)" if found.status == NEEDS_OPERATOR else ""
    return f"{found.kind} from {found.source}{gate}: {found.evidence}"

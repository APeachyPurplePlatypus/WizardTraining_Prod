"""The decisions a model is most likely to replace: which card to play, and what to do with a quest offer.

Each policy is a plain object with one method and no game access, so it can be tested offline and
swapped without touching the code that reads the game and clicks. `combat.fight` and `dialog.talk`
check what a policy returns before acting on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

ATTACK_TARGETS = {"Damage": "enemy", "Steal": "enemy", "AOE": "all enemies"}
HEAL_SPELL_TYPES = {"Heal"}
LOW_HEALTH_FRACTION = 0.4
SIDE_QUEST_OFFER_PHRASE = "offering you a side quest"
ACCEPT, DECLINE, GO_BACK, STOP = "accept", "decline", "go back", "stop"


@dataclass(frozen=True)
class Card:
    """A card in hand. `spell_type` is the game's own type name ("Damage", "Steal", "AOE", "Heal", ...)."""
    name: str | None
    spell_type: str | None
    castable: bool


@dataclass(frozen=True)
class Combatant:
    name: str | None
    health: int | None


@dataclass(frozen=True)
class RoundView:
    """What the wizard sees in a planning phase. `enemies` holds only the living ones."""
    round_number: int | None
    health: int | None
    max_health: int | None
    pips: int | None
    power_pips: int | None
    cards: tuple[Card, ...]
    enemies: tuple[Combatant, ...]

    def health_fraction(self) -> float | None:
        if isinstance(self.health, int) and isinstance(self.max_health, int) and self.max_health > 0:
            return self.health / self.max_health
        return None


@dataclass(frozen=True)
class Cast:
    """Play `cards[card]` on the wizard ("self"), on `enemies[enemy]` ("enemy"), or on every enemy at once
    ("all enemies", for spells with no single target)."""
    card: int
    target: Literal["self", "enemy", "all enemies"]
    enemy: int = 0


TARGETS = ("self", "enemy", "all enemies")


def problem_with(choice: Cast, view: RoundView) -> str | None:
    """Why the battle code must not act on `choice`, or None if it can."""
    if not 0 <= choice.card < len(view.cards) or not view.cards[choice.card].castable:
        return "the policy chose a card that is not castable"
    if choice.target not in TARGETS:
        return f"the policy chose an unknown target {choice.target!r}"
    if choice.target == "enemy" and not 0 <= choice.enemy < len(view.enemies):
        return "the policy chose an enemy that is not there"
    return None


class CombatPolicy(Protocol):
    def choose(self, view: RoundView) -> Cast | None:
        """The card to play this round, or None to pass."""


class SpellTypePolicy:
    """Below LOW_HEALTH_FRACTION heal, else the first affordable attack on the first living enemy, else pass.
    It won every early Wizard City battle it played with starter cards; it knows nothing of schools,
    shields, blades or pip planning."""

    def choose(self, view: RoundView) -> Cast | None:
        fraction = view.health_fraction()
        if fraction is not None and fraction < LOW_HEALTH_FRACTION:
            heal = first_castable(view.cards, lambda card: card.spell_type in HEAL_SPELL_TYPES)
            if heal is not None:
                return Cast(heal, "self")
        if not view.enemies:
            return None
        attack = first_castable(view.cards, lambda card: card.spell_type in ATTACK_TARGETS)
        if attack is None:
            return None
        return Cast(attack, ATTACK_TARGETS[view.cards[attack].spell_type])


def first_castable(cards: tuple[Card, ...], wanted) -> int | None:
    return next((index for index, card in enumerate(cards) if card.castable and wanted(card)), None)


class OfferPolicy(Protocol):
    def decide(self, pages: list[str], *, can_go_back: bool) -> str:
        """What to do on a dialog page showing ACCEPT and DECLINE: ACCEPT, DECLINE, GO_BACK or STOP.
        `pages` is the text of every page of this conversation so far, the offer page last."""

    def choose_service(self, options: list[str], *, active_quest: str | None) -> int | None:
        """Which option of an NPC's services menu to click, or None to leave the menu to the operator.
        `options` are the option labels (quest titles); `active_quest` is the active quest's title."""


def same_title(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and a.strip().casefold() == b.strip().casefold()


class MainQuestsOnly:
    """The main-quest dialogs seen so far had no DECLINE button, so a page with one is an optional offer.
    Decline offers the dialog calls a side quest. If the offer's wording was shown before reading began,
    go back a page once to read it. Otherwise stop for the operator rather than guess.

    An NPC's services menu lists quests by title, and whether a quest is a main quest can be read only
    once it is accepted. So the menu's option for the active quest is taken, and otherwise only a title
    the operator approved (`approved_titles`, the CLI's --approve-quest). An approved quest's offer page is
    accepted unless it calls itself a side quest; the loop stops if it turns out not to be a main quest."""

    def __init__(self, approved_titles=()):
        self.approved_titles = tuple(approved_titles)
        self._approved_offer_pending = False

    def decide(self, pages: list[str], *, can_go_back: bool) -> str:
        if any(SIDE_QUEST_OFFER_PHRASE in page.lower() for page in pages):
            return DECLINE
        if self._approved_offer_pending:
            self._approved_offer_pending = False
            return ACCEPT
        return GO_BACK if can_go_back else STOP

    def choose_service(self, options: list[str], *, active_quest: str | None) -> int | None:
        for index, option in enumerate(options):
            if same_title(option, active_quest):
                return index
        for title in self.approved_titles:
            for index, option in enumerate(options):
                if same_title(option, title):
                    self._approved_offer_pending = True
                    return index
        return None

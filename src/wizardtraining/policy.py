"""The decisions a model is most likely to replace: which card to play, and what to do with a quest offer.

Each policy is a plain object with one method and no game access, so it can be tested offline and
swapped without touching the code that reads the game and clicks. `combat.fight` and `dialog.talk`
check what a policy returns before acting on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

ATTACK_TARGETS = {"Damage": "enemy", "Steal": "enemy", "AOE": "all enemies"}
HEAL_SPELL_TYPES = {"Heal"}
LOW_HEALTH_FRACTION = 0.4
MOST_PIPS_TO_SAVE_FOR = 7
SIDE_QUEST_OFFER_PHRASE = "offering you a side quest"
ACCEPT, DECLINE, GO_BACK, STOP = "accept", "decline", "go back", "stop"
LEAVE_MENU = "leave menu"
UNIVERSAL = "Universal"


@dataclass(frozen=True)
class Card:
    """A card in hand. `spell_type` is the game's own type name ("Damage", "Steal", "AOE", "Heal", ...) and
    `school` its magic school ("Fire", "Myth", ...) when it could be read."""
    name: str | None
    spell_type: str | None
    castable: bool
    school: str | None = None
    pips: int | None = None
    accuracy: int | None = None

    def hit_chance(self) -> float:
        """The card's accuracy as a fraction; 1 when it could not be read."""
        return self.accuracy / 100 if self.accuracy else 1.0


@dataclass(frozen=True)
class DamageModifier:
    """A shield, ward or trap on a combatant: damage of `school`, or of every school when it is UNIVERSAL,
    changes by `percent` on the next hit. Negative for shields and wards, positive for traps."""
    school: str
    percent: int


@dataclass(frozen=True)
class Combatant:
    """A living combatant. `resistances` are its own stats by school, as fractions: 0.25 resists a quarter of
    that school's damage, -0.15 takes 15% more. A school not listed takes the UNIVERSAL value, if any."""
    name: str | None
    health: int | None
    incoming: tuple[DamageModifier, ...] = ()
    resistances: dict[str, float] = field(default_factory=dict)

    def damage_factor(self, school: str | None) -> float:
        """The share of a hit of `school` that lands after this combatant's shields, wards, traps and
        resistances."""
        factor = 1.0
        for modifier in self.incoming:
            if modifier.school in (school, UNIVERSAL):
                factor *= 1 + modifier.percent / 100
        return factor * (1 - self.resistances.get(school, self.resistances.get(UNIVERSAL, 0.0)))


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
class Pass:
    """Play no card this round, for `reason`."""
    reason: str


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
    def choose(self, view: RoundView) -> Cast | Pass | None:
        """The card to play this round, or a Pass (or None) to play none."""


class SpellTypePolicy:
    """Below LOW_HEALTH_FRACTION, heal; with a heal in hand that needs more pips than the wizard has, pass to
    save pips for it. Otherwise attack the first living enemy, with the affordable attack expected to land best:
    the share its shields, wards, traps and resistances let through, times the card's accuracy. The first in hand
    on a tie. It knows nothing of
    blades or of saving pips for attacks."""

    def choose(self, view: RoundView) -> Cast | Pass | None:
        fraction = view.health_fraction()
        if fraction is not None and fraction < LOW_HEALTH_FRACTION:
            heal = first_castable(view.cards, lambda card: card.spell_type in HEAL_SPELL_TYPES)
            if heal is not None:
                return Cast(heal, "self")
            if (worth_saving_for := heal_worth_saving_for(view)) is not None:
                return Pass(f"saving pips for {worth_saving_for.name} ({worth_saving_for.pips} pips)")
        if not view.enemies:
            return None
        attacks = [index for index, card in enumerate(view.cards) if card.castable and card.spell_type in ATTACK_TARGETS]
        if not attacks:
            return None
        target = view.enemies[0]
        attack = max(attacks, key=lambda index: target.damage_factor(view.cards[index].school)
                     * view.cards[index].hit_chance())
        return Cast(attack, ATTACK_TARGETS[view.cards[attack].spell_type])


def heal_worth_saving_for(view: RoundView) -> Card | None:
    """A heal in hand that is not castable only because the wizard lacks pips, and costs at most
    MOST_PIPS_TO_SAVE_FOR: passing gains a pip each round, so it becomes castable."""
    have = (view.pips or 0) + (view.power_pips or 0)
    return next((card for card in view.cards if card.spell_type in HEAL_SPELL_TYPES and not card.castable
                 and card.pips is not None and have < card.pips <= MOST_PIPS_TO_SAVE_FOR), None)


def first_castable(cards: tuple[Card, ...], wanted) -> int | None:
    return next((index for index, card in enumerate(cards) if card.castable and wanted(card)), None)


class OfferPolicy(Protocol):
    def decide(self, pages: list[str], *, can_go_back: bool) -> str:
        """What to do on a dialog page showing ACCEPT and DECLINE: ACCEPT, DECLINE, GO_BACK or STOP.
        `pages` is the text of every page of this conversation so far, the offer page last."""

    def choose_service(self, options: list[str], *, active_quest: str | None, business_here: bool) -> int | str | None:
        """Which option of an NPC's services menu to click (its index), LEAVE_MENU to close the menu, or None
        to leave it to the operator. `options` are the option labels (quest titles); `active_quest` is the
        active quest's title; `business_here` says whether that quest has something to do with this NPC now."""


def same_title(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and a.strip().casefold() == b.strip().casefold()


def index_of(options: list[str], title: str) -> int | None:
    return next((index for index, option in enumerate(options) if same_title(option, title)), None)


class MainQuestsOnly:
    """The main-quest dialogs seen so far had no DECLINE button, so a page with one is an optional offer.
    Decline offers the dialog calls a side quest. If the offer's wording was shown before reading began,
    go back a page once to read it. Otherwise stop for the operator rather than guess.

    An NPC's services menu lists quests by title, and whether a quest is a main quest can be read only
    once it is accepted. With a quest active, the menu's option for it is taken only when that quest has
    business with this NPC (to talk or to turn in); otherwise the menu is left, because the menu reopens
    after every conversation and choosing the active quest again only replays its dialog. With no quest
    active, the first title the operator approved (`approved_titles`, the CLI's --approve-quest) is taken,
    one main quest at a time. An approved quest's offer page is accepted unless it calls itself a side
    quest; the loop stops if it turns out not to be a main quest."""

    side_quests = False

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

    def choose_service(self, options: list[str], *, active_quest: str | None, business_here: bool) -> int | str | None:
        if active_quest is not None:
            index = index_of(options, active_quest) if business_here else None
            return LEAVE_MENU if index is None else index
        for title in self.approved_titles:
            index = index_of(options, title)
            if index is not None:
                self._approved_offer_pending = True
                return index
        return None


class TakeAllQuests(MainQuestsOnly):
    """Accept every quest offer, side quests included, so the side quests of a world are in the quest book before
    the main quest leaves it. The loop plays whichever quest the game has active. An NPC's services menu still
    gets the active quest only when it has business there; with no quest active, the approved titles come
    first, then the first quest the menu lists."""

    side_quests = True

    def decide(self, pages: list[str], *, can_go_back: bool) -> str:
        return ACCEPT

    def choose_service(self, options: list[str], *, active_quest: str | None, business_here: bool) -> int | str | None:
        choice = super().choose_service(options, active_quest=active_quest, business_here=business_here)
        if choice is None and active_quest is None and options:
            return 0
        return choice

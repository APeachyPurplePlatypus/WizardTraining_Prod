"""The decisions a model is most likely to replace: which card to play, and what to do with a quest offer.

Each policy is a plain object with one method and no game access, so it can be tested offline and
swapped without touching the code that reads the game and clicks. `combat.fight` and `dialog.talk`
check what a policy returns before acting on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal, Protocol

from .sidequests import QUEST_FINDER
from .strategies import COMBAT_STRATEGIES, MOST_DANGEROUS, CombatStrategy, fight_situation

ATTACK_TARGETS = {"Damage": "enemy", "Steal": "enemy", "AOE": "all enemies"}
HEAL_SPELL_TYPES = {"Heal"}
LOW_HEALTH_FRACTION = 0.4
MOST_PIPS_TO_SAVE_FOR = 7
FLEE_BELOW_MANA = 2
SURE_DAMAGE_PER_PIP = 60
STUN = "stun"
EXTRACT_EFFECT = "collect_essence"
SINGLE_TARGET_ATTACKS = ("Damage", "Steal")
ENEMY_DAMAGE_PER_PIP = 125
SIDE_QUEST_OFFER_PHRASE = "offering you a side quest"
ACCEPT, DECLINE, GO_BACK, STOP = "accept", "decline", "go back", "stop"
LEAVE_MENU = "leave menu"
SERVICE_WORDS = ("shop", "trading", "trade", "rematch", "vendor", "bazaar", "sell", "buy", "train")
UNIVERSAL = "Universal"


@dataclass(frozen=True)
class Card:
    """A card in hand. `spell_type` is the game's own type name ("Damage", "Steal", "AOE", "Heal", ...),
    `school` its magic school ("Fire", "Myth", ...) when it could be read, and `effects` the names of its spell
    effects ("damage", "stun", ...): Freeze is a "Manipulation" whose one effect is "stun"."""
    name: str | None
    spell_type: str | None
    castable: bool
    school: str | None = None
    pips: int | None = None
    accuracy: int | None = None
    effects: tuple[str, ...] = ()
    enchanted: bool = False

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
    that school's damage, -0.15 takes 15% more. A school not listed takes the UNIVERSAL value, if any.
    `stunnable` is false while a stun or a stun block is on it, so a stun would be wasted. `pips` counts what it
    can spend next round, a power pip as two, when it could be read."""
    name: str | None
    health: int | None
    incoming: tuple[DamageModifier, ...] = ()
    resistances: dict[str, float] = field(default_factory=dict)
    stunnable: bool = True
    pips: int | None = None

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
    """What the wizard sees in a planning phase. `enemies` holds only the living ones. `can_flee` turns false once
    a flee did not end the battle: some boss fights, such as General Akilles in his tower, cannot be fled."""
    round_number: int | None
    health: int | None
    max_health: int | None
    pips: int | None
    power_pips: int | None
    cards: tuple[Card, ...]
    enemies: tuple[Combatant, ...]
    mana: int | None = None
    can_flee: bool = True

    def health_fraction(self) -> float | None:
        if isinstance(self.health, int) and isinstance(self.max_health, int) and self.max_health > 0:
            return self.health / self.max_health
        return None


@dataclass(frozen=True)
class Pass:
    """Play no card this round, for `reason`."""
    reason: str


@dataclass(frozen=True)
class Flee:
    """Leave the battle with its Flee button, for `reason`."""
    reason: str


@dataclass(frozen=True)
class Cast:
    """Play `cards[card]` on the wizard ("self"), on `enemies[enemy]` ("enemy"), or on every enemy at once
    ("all enemies", for spells with no single target)."""
    card: int
    target: Literal["self", "enemy", "all enemies"]
    enemy: int = 0


@dataclass(frozen=True)
class Enchant:
    """Play `cards[card]`, an enchantment, onto `cards[onto]`, another card in hand; the round's cast comes after,
    chosen again from the hand as it is then."""
    card: int
    onto: int


TARGETS = ("self", "enemy", "all enemies")


def problem_with(choice: Cast | Enchant, view: RoundView) -> str | None:
    """Why the battle code must not act on `choice`, or None if it can."""
    if isinstance(choice, Enchant):
        if not all(0 <= index < len(view.cards) and view.cards[index].castable for index in (choice.card, choice.onto)):
            return "the policy chose an enchantment or a card to enchant that is not castable"
        return None if choice.card != choice.onto else "the policy chose to enchant a card with itself"
    if not 0 <= choice.card < len(view.cards) or not view.cards[choice.card].castable:
        return "the policy chose a card that is not castable"
    if choice.target not in TARGETS:
        return f"the policy chose an unknown target {choice.target!r}"
    if choice.target == "enemy" and not 0 <= choice.enemy < len(view.enemies):
        return "the policy chose an enemy that is not there"
    return None


class CombatPolicy(Protocol):
    def choose(self, view: RoundView) -> Cast | Pass | Flee | None:
        """The card to play this round, a Pass (or None) to play none, or Flee to leave the battle."""


class SpellTypePolicy:
    """With less than FLEE_BELOW_MANA mana, flee, unless this battle cannot be fled. Below LOW_HEALTH_FRACTION,
    heal, and also when the enemies' pips could take what health is left (`within_reach_of_a_big_hit`), or else
    stun the enemy holding the most pips; with a heal in hand that needs more pips than the wizard has, stun an enemy
    or pass to save pips for it.
    Then, when an attack surely finishes an enemy, the cheapest such attack on it, to save mana. When a stronger
    attack in hand needs one pip more than the wizard has, stun an enemy instead (`stun_while_saving_a_pip`).
    Otherwise attack the enemy with the least health with the affordable attack expected to do the most to it: its
    pip cost (damage grows with pips: Frost Beetle, 1 pip, about 85; Snow Serpent, 2 pips, about 175), times the
    share the target's shields, wards, traps and resistances let through, times the card's accuracy; the first in
    hand on a tie. It knows nothing of blades.

    It plays by a `strategies.CombatStrategy`: when to heal, how big an enemy's saved-up hit is counted, which enemy
    is attacked first, and whether pips are saved for a bigger card. With `strategy_for`, the strategy is chosen at
    the first round of each fight (after `new_fight`) from the enemies in it, so a strategy that lost to Flame
    Servants is not played against them again because a later fight against Nirini Sentries changed it.
    Pips are saved for a heal only in danger (below LOW_HEALTH_FRACTION, or within reach of a big hit), whatever the
    strategy's heal line: playing "heal earlier" (below 60%) against two Nirini Sentries, the wizard passed for Pixie
    at 49%, healed, fell below 60% again, and passed again, while the last Sentry stood at 220 for eight rounds."""

    def __init__(self, strategy: CombatStrategy = COMBAT_STRATEGIES[0], strategy_for=None, essence_from=None):
        self.strategy = strategy
        self.strategy_for = strategy_for
        self.essence_from = essence_from
        self._strategy_chosen = False
        self._extracted = False

    def new_fight(self) -> None:
        self._strategy_chosen = False
        self._extracted = False

    def choose(self, view: RoundView) -> Cast | Enchant | Pass | Flee | None:
        if self.strategy_for is not None and not self._strategy_chosen and view.enemies:
            self.strategy = self.strategy_for(fight_situation([enemy.name for enemy in view.enemies]))
            self._strategy_chosen = True
        if out_of_mana(view) and view.can_flee:
            return Flee(f"out of mana ({view.mana} left)")
        fraction = view.health_fraction()
        wanted = self.essence_from() if self.essence_from is not None and not self._extracted else set()
        if wanted and (fraction is None or fraction >= LOW_HEALTH_FRACTION):
            extraction = extract_essence(view, wanted)
            if isinstance(extraction, Cast):
                self._extracted = True
            if extraction is not None:
                return extraction
        attacks = [index for index, card in enumerate(view.cards) if card.castable and card.spell_type in ATTACK_TARGETS]
        finisher = cheapest_finisher(view, attacks) if view.enemies else None
        per_pip = self.strategy.enemy_damage_per_pip
        if finisher is not None and ends_the_danger(view, finisher, per_pip):
            return finisher
        big_hit = within_reach_of_a_big_hit(view, per_pip)
        if (fraction is not None and fraction < self.strategy.heal_below) or big_hit:
            heal = first_castable(view.cards, lambda card: card.spell_type in HEAL_SPELL_TYPES)
            if heal is not None:
                return Cast(heal, "self")
            if big_hit and (stun := stun_on_the_most_dangerous(view)) is not None:
                return stun
            in_danger = big_hit or (fraction is not None and fraction < LOW_HEALTH_FRACTION)
            if in_danger and (worth_saving_for := heal_worth_saving_for(view)) is not None:
                return stun_on_the_most_dangerous(view) or Pass(f"saving pips for {worth_saving_for.name} "
                                                                f"({worth_saving_for.pips} pips)")
        if not view.enemies:
            return None
        if finisher is not None:
            return finisher
        stun = stun_while_saving_a_pip(view, attacks)
        if stun is not None:
            return stun
        if self.strategy.save_pips_for_bigger_cards and (bigger := bigger_card_soon(view, attacks)) is not None:
            return stun_on_the_most_dangerous(view) or Pass(f"saving pips for {bigger.name} ({bigger.pips} pips)")
        if not attacks:
            return None
        enemy = most_dangerous(view.enemies) if self.strategy.target == MOST_DANGEROUS else weakest(view.enemies)
        attack = max(attacks, key=lambda index: expected_damage(view.cards[index], view.enemies[enemy]))
        return Cast(attack, ATTACK_TARGETS[view.cards[attack].spell_type], enemy)


def essence_enemies(view: RoundView, wanted: set[str]) -> list[int]:
    """The enemies whose essence a quest goal needs, by name ("Lost Soul" for "Lost Soul Essence")."""
    names = {name.lower() for name in wanted}
    return [index for index, enemy in enumerate(view.enemies) if (enemy.name or "").lower() in names]


def is_extract(card: Card) -> bool:
    return EXTRACT_EFFECT in card.effects or (card.name or "").lower().startswith("extract ")


def extract_essence(view: RoundView, wanted: set[str]) -> Cast | Enchant | None:
    """With an enemy in the fight whose essence a goal needs: hit it with a castable enchanted attack, else enchant
    the cheapest castable single-target attack with an Extract spell in hand. Gilda Burke ("Know Thine Enemy"):
    Extract spells "enchant damage spells, which can then capture an enemy's very essence"; an enchanted spell that
    deals damage extracts one Animus, a defeating hit one more, and the duel must be won to collect it. None when
    there is no such enemy, or the hand cannot do it this round."""
    victims = essence_enemies(view, wanted)
    if not victims:
        return None
    enchanted = first_castable(view.cards, lambda card: card.enchanted and card.spell_type in SINGLE_TARGET_ATTACKS)
    if enchanted is not None:
        return Cast(enchanted, "enemy", victims[0])
    extract = first_castable(view.cards, is_extract)
    attacks = [index for index, card in enumerate(view.cards)
               if card.castable and not card.enchanted and card.spell_type in SINGLE_TARGET_ATTACKS]
    if extract is None or not attacks:
        return None
    return Enchant(extract, min(attacks, key=lambda index: view.cards[index].pips or 1))


def weakest(enemies: tuple[Combatant, ...]) -> int:
    """The enemy with the least health, the first on a tie. Every enemy down is one hitting the wizard no more:
    General Akilles (470) and his Cyclops Legionnaire (235) took 100 to 200 health a round between them, and every
    attack went to Akilles while the Cyclops kept hitting."""
    return min(range(len(enemies)), key=lambda index: (enemies[index].health is None, enemies[index].health or 0))


def most_dangerous(enemies: tuple[Combatant, ...]) -> int:
    """The enemy holding the most pips, on a tie the one with the most health: its next hit is the biggest. Lord
    Nightshade (690) stayed untouched while the wizard spent eight rounds on his Field Guard (395)."""
    return max(range(len(enemies)), key=lambda index: (enemies[index].pips or 0, enemies[index].health or 0))


def bigger_card_soon(view: RoundView, attacks: list[int]) -> Card | None:
    """An attack in hand that needs one or two pips more than the wizard has, which it can pay for in mana, and that
    is expected to do more than the best attack it can cast now, else None."""
    have = (view.pips or 0) + (view.power_pips or 0)
    target = view.enemies[weakest(view.enemies)]
    best_now = max((expected_damage(view.cards[index], target) for index in attacks), default=0.0)
    soon = [card for card in view.cards if card.spell_type in ATTACK_TARGETS and not card.castable and card.pips
            and have < card.pips <= have + 2 and (view.mana is None or view.mana >= card.pips)
            and expected_damage(card, target) > best_now]
    return max(soon, key=lambda card: expected_damage(card, target), default=None)


def cheapest_finisher(view: RoundView, attacks: list[int]) -> Cast | None:
    """The cheapest attack that surely finishes an enemy, on the first such enemy."""
    sure = [(view.cards[card].pips or 1, enemy, card) for enemy, target in enumerate(view.enemies) for card in attacks
            if surely_finishes(view.cards[card], target)]
    if not sure:
        return None
    _, enemy, card = min(sure)
    return Cast(card, ATTACK_TARGETS[view.cards[card].spell_type], enemy)


def stun_while_saving_a_pip(view: RoundView, attacks: list[int]) -> Cast | None:
    """A stun on the enemy with the most health that can be stunned, when an attack in hand needs exactly one pip
    more than the wizard has (and no more mana than it has) and is expected to do more than the best attack it can
    cast now. Freeze costs no pips, so the next round has the pip for the stronger attack, and the stunned enemy
    loses its turn: over two rounds a stun and a Snow Serpent do about 175 to a wand's two hits of about 140, and
    one enemy hit fewer lands."""
    have = (view.pips or 0) + (view.power_pips or 0)
    target = view.enemies[weakest(view.enemies)]
    best_now = max((expected_damage(view.cards[index], target) for index in attacks), default=0.0)
    one_pip_away = [card for card in view.cards if card.spell_type in ATTACK_TARGETS and not card.castable
                    and card.pips == have + 1 and (view.mana is None or view.mana >= card.pips)]
    if not any(expected_damage(card, target) > best_now for card in one_pip_away):
        return None
    return stun_on_the_most_dangerous(view)


def stun_on_the_most_dangerous(view: RoundView) -> Cast | None:
    """A castable stun on the enemy that can be stunned holding the most pips, on a tie the one with the most
    health, or None. Pips are what its next spell can spend."""
    stun = first_castable(view.cards, lambda card: STUN in card.effects)
    stunnable = [index for index, enemy in enumerate(view.enemies) if enemy.stunnable]
    if stun is None or not stunnable:
        return None
    return Cast(stun, "enemy", max(stunnable, key=lambda index: (view.enemies[index].pips or 0,
                                                                view.enemies[index].health or 0)))


def ends_the_danger(view: RoundView, finisher: Cast, per_pip: int = ENEMY_DAMAGE_PER_PIP) -> bool:
    """Finishing the enemy `finisher` targets leaves no enemy, or none that could take what health is left: then
    the finishing blow comes before any heal. With 288 health and Alicane Swiftarrow at 16, holding 3 pips, the
    wizard passed to save pips for a heal instead of finishing her with a 1-pip attack, and lost the battle."""
    left = tuple(enemy for index, enemy in enumerate(view.enemies) if index != finisher.enemy)
    return not left or not within_reach_of_a_big_hit(replace(view, enemies=left), per_pip)


def within_reach_of_a_big_hit(view: RoundView, per_pip: int = ENEMY_DAMAGE_PER_PIP) -> bool:
    """The wizard's health is no more than what the enemies could deal next round if each spent all its pips, at
    ENEMY_DAMAGE_PER_PIP. General Akilles, stunned in the first round, saved his pips and took 357 health or more in
    one round, where his hits had been 100 to 140; the wizard had a 245 heal in hand at 45% health and attacked,
    since it healed only below LOW_HEALTH_FRACTION. Alicane Swiftarrow then hit for 396 with 4 pips, 99 a pip: at
    100 a pip the wizard, with 487, counted itself out of reach and fell to 91, so the estimate keeps a quarter's
    margin."""
    if not isinstance(view.health, int):
        return False
    reach = sum((enemy.pips or 0) * per_pip for enemy in view.enemies)
    return reach > 0 and view.health <= reach


def out_of_mana(view: RoundView) -> bool:
    """Less than FLEE_BELOW_MANA mana, and no castable attack in hand the wizard can still pay for (a mana a pip). The
    operator's rule: "if no mana you have to flee". With 0 mana and no wand spell in hand, the wizard passed four
    rounds and was defeated by a Cyclops Legionnaire it could not hurt. With 1 mana and a 1-pip Fire Cat that would
    surely finish a Cyclops at 60 health, it clicked Flee instead; the flee did not take, and the hand did not work
    again in that battle, so a spell the wizard can pay for comes first."""
    if not isinstance(view.mana, int) or view.mana >= FLEE_BELOW_MANA:
        return False
    return not any(card.castable and card.spell_type in ATTACK_TARGETS and (card.pips or 1) <= view.mana
                   for card in view.cards)


def surely_finishes(card: Card, target: Combatant) -> bool:
    """The card does at least SURE_DAMAGE_PER_PIP per pip after the target's shields, wards, traps and resistances,
    and that is the target's remaining health or more. Then the cheapest such card is played: a Warhorn with 15
    health left took a 2-pip Snow Serpent where a 1-pip Frost Beetle would do, with mana the scarcest thing."""
    return (isinstance(target.health, int)
            and (card.pips or 1) * SURE_DAMAGE_PER_PIP * target.damage_factor(card.school) >= target.health)


def expected_damage(card: Card, target: Combatant) -> float:
    """How much a card should do, in pips of damage: its pip cost (1 when unknown), times what the target lets
    through of its school, times its accuracy."""
    return (card.pips or 1) * target.damage_factor(card.school) * card.hit_chance()


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


def first_quest_option(options: list[str]) -> int | str:
    """The first option of an NPC's menu that names a quest rather than a service, else LEAVE_MENU. The giver the
    journal's Quest Finder pointed to in Olde Town offered ['Wizards in the Mist', 'Recipe Shop', 'Rematch Trading'],
    and the menu was left, since no option was named for the active quest, the Quest Finder itself."""
    return next((index for index, option in enumerate(options)
                 if not any(word in option.lower() for word in SERVICE_WORDS)), LEAVE_MENU)


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
        if active_quest is not None and same_title(active_quest, QUEST_FINDER):
            return first_quest_option(options)
        choice = super().choose_service(options, active_quest=active_quest, business_here=business_here)
        if choice is None and active_quest is None and options:
            return 0
        return choice

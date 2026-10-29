"""Which cards in hand to discard during the wizard's own planning phase, so the next draw can bring cards it needs.

The operator, 2026-10-29 02:01 UTC: "u can discard cards to find cards you really need to use. like for example,
discard a stun card for the chance to draw a 3 pip attack spell, add this function to the framework as a generic
thing". A discard is a right-click on a card in the wizard's own hand; the hand is filled again from the deck at the
start of the next round, so a discarded card is a slot for a fresh draw, and one card fewer left in the deck.

A card is let go when it will not help over the next round or two, by what the round shows: a stun when no enemy
can be stunned, or when the wizard is safe and short of attacks (the need is damage), but one stun is kept against two
or more enemies that can be stunned, where a stun a round holds back half the hits; an attack every enemy resists
by RESISTED_BY_ALL or more, while another attack is in hand; a second heal while health is safe. Kept always: the
best castable attack, a heal when health could fall below KEEP_A_HEAL_BELOW within two enemy turns, traps, item
cards (a wand comes back each round) and treasure cards (used up once played). At most MAX_DISCARDS_PER_ROUND a
round, and never so many that fewer than DECK_RESERVE cards stay in the deck. Pure: no game access.
"""

from __future__ import annotations

from dataclasses import dataclass

from .policy import (ATTACK_TARGETS, ENEMY_DAMAGE_PER_PIP, HEAL_SPELL_TYPES, STUN, Card, RoundView, enemy_reach,
                     expected_damage, from_an_item, is_trap)

RESISTED_BY_ALL = 0.25
MAX_DISCARDS_PER_ROUND = 2
DECK_RESERVE = 3
KEEP_A_HEAL_BELOW = 0.5
ENEMY_TURNS_AHEAD = 2
FEW_ATTACKS = 2


@dataclass(frozen=True)
class Discard:
    """Discard `cards[card]` for `reason`."""
    card: int
    reason: str


def is_attack(card: Card) -> bool:
    return card.spell_type in ATTACK_TARGETS


def is_heal(card: Card) -> bool:
    return card.spell_type in HEAL_SPELL_TYPES


def is_stun(card: Card) -> bool:
    return STUN in card.effects


def health_at_risk(view: RoundView, hit_seen=None) -> bool:
    """Health could fall below KEEP_A_HEAL_BELOW of the pool within ENEMY_TURNS_AHEAD enemy turns, by what the
    enemies' pips reach (`policy.enemy_reach`, held to the biggest hits seen); unknown health counts as at risk."""
    if not isinstance(view.health, int) or not isinstance(view.max_health, int) or view.max_health <= 0:
        return True
    reach = sum(enemy_reach(enemy, ENEMY_DAMAGE_PER_PIP, hit_seen) for enemy in view.enemies) * ENEMY_TURNS_AHEAD
    return view.health - reach < KEEP_A_HEAL_BELOW * view.max_health


def best_attack(view: RoundView) -> int | None:
    """The castable attack expected to do the most to the weakest enemy."""
    living = [enemy for enemy in view.enemies if isinstance(enemy.health, int)]
    target = min(living, key=lambda enemy: enemy.health, default=view.enemies[0] if view.enemies else None)
    castable = [index for index, card in enumerate(view.cards) if is_attack(card) and card.castable]
    if target is None or not castable:
        return None
    return max(castable, key=lambda index: expected_damage(view.cards[index], target))


def cards_to_discard(view: RoundView, *, deck_left: int | None, treasure: frozenset[int] = frozenset(),
                     hit_seen=None) -> list[Discard]:
    """The cards to discard this round, most useless first, as the module docstring sets out. None while the deck
    count is unknown."""
    if not view.enemies or deck_left is None:
        return []
    budget = min(MAX_DISCARDS_PER_ROUND, deck_left - DECK_RESERVE)
    if budget <= 0:
        return []
    at_risk = health_at_risk(view, hit_seen)
    keep = {best_attack(view)}
    heals = [index for index, card in enumerate(view.cards) if is_heal(card)]
    if at_risk and heals:
        keep.add(heals[0])
    attacks = [index for index, card in enumerate(view.cards) if is_attack(card)]
    deck_attacks = [index for index in attacks if not from_an_item(view.cards[index])]
    stuns = [index for index, card in enumerate(view.cards) if is_stun(card)]
    if sum(1 for enemy in view.enemies if enemy.stunnable) >= 2 and stuns:
        keep.add(stuns[0])
    found = []
    for index, card in enumerate(view.cards):
        if index in keep or index in treasure or from_an_item(card) or is_trap(card):
            continue
        reason = None
        if is_stun(card) and not any(enemy.stunnable for enemy in view.enemies):
            reason = "no enemy can be stunned"
        elif is_stun(card) and not at_risk and len(deck_attacks) < FEW_ATTACKS:
            reason = (f"a stun while health is safe and the hand holds {len(deck_attacks)} attack(s) besides wands: "
                      "the need is damage")
        elif (is_attack(card) and len(attacks) > 1
              and all(enemy.damage_factor(card.school) <= 1 - RESISTED_BY_ALL for enemy in view.enemies)):
            reason = f"every enemy resists {card.school or 'its school'} by {RESISTED_BY_ALL:.0%} or more"
        elif is_heal(card) and not at_risk and len(heals) > 1 and index != heals[0]:
            reason = "a second heal while health is safe"
        if reason is not None:
            found.append(Discard(index, f"{card.name}: {reason}"))
    return found[:budget]


def deck_left(deck_size: int | None, hand: tuple[Card, ...], used_from_the_deck: int) -> int | None:
    """Cards still in the deck: its size, less the deck's cards in hand and those already cast or discarded this
    battle; item cards come from gear, not the deck. None when the deck's size is unknown."""
    if deck_size is None:
        return None
    in_hand = sum(1 for card in hand if not from_an_item(card))
    return max(deck_size - in_hand - used_from_the_deck, 0)

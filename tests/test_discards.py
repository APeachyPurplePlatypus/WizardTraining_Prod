import unittest

from wizardtraining.discards import DECK_RESERVE, cards_to_discard, deck_left
from wizardtraining.policy import Card, Combatant, RoundView

SERPENT = Card("Snow Serpent", "Damage", True, school="Ice", pips=2, effects=("damage",))
SNOWMAN = Card("Evil Snowman", "Damage", False, school="Ice", pips=3, effects=("damage",))
FREEZE = Card("Freeze", "Manipulation", True, school="Ice", pips=0, effects=("stun",))
PIXIE = Card("Pixie", "Heal", True, school="Life", pips=2, effects=("heal",))
HEARTBEAT = Card("Heartbeat", "Heal", True, school="Life", pips=1, effects=("heal",))
TRAP = Card("Ice Trap", "Trap", True, school="Ice", pips=0, effects=("modify_incoming_damage",))
WAND = Card("Frost Beetle - Starter Wand", "Damage", True, school="Ice", pips=1, effects=("damage",), item_card=True)
GUARD = Combatant("Riverclaw Guard", 345, pips=1)


def view(cards, *, health=1100, enemies=(GUARD,), pips=2):
    return RoundView(round_number=2, health=health, max_health=1195, pips=pips, power_pips=0, cards=tuple(cards),
                     enemies=tuple(enemies))


class DiscardTest(unittest.TestCase):
    def test_a_stun_goes_when_health_is_safe_and_attacks_are_short(self):
        found = cards_to_discard(view([SERPENT, FREEZE, PIXIE, TRAP, WAND]), deck_left=7)
        self.assertEqual([discard.card for discard in found], [1])
        self.assertIn("the need is damage", found[0].reason)

    def test_one_stun_stays_against_two_enemies_and_the_spare_goes(self):
        pair = (GUARD, Combatant("Riverclaw Guard", 345, pips=1))
        found = cards_to_discard(view([SNOWMAN, FREEZE, FREEZE, PIXIE, TRAP, WAND], enemies=pair), deck_left=9)
        self.assertEqual([discard.card for discard in found], [2])

    def test_a_stun_stays_when_health_is_at_risk(self):
        strong = Combatant("Royal Guard", 250, pips=5)
        self.assertEqual(cards_to_discard(view([SERPENT, FREEZE, PIXIE], health=500, enemies=(strong,)),
                                          deck_left=7), [])

    def test_a_stun_goes_when_no_enemy_can_be_stunned(self):
        stunned = Combatant("Riverclaw Guard", 345, stunnable=False, pips=1)
        found = cards_to_discard(view([SERPENT, SNOWMAN, FREEZE], health=500, enemies=(stunned,)), deck_left=7)
        self.assertEqual([discard.card for discard in found], [2])

    def test_an_attack_every_enemy_resists_goes_while_another_attack_is_in_hand(self):
        cold_proof = Combatant("Snowman", 400, resistances={"Ice": 0.5}, pips=1)
        fire = Card("Fire Cat", "Damage", True, school="Fire", pips=1, effects=("damage",))
        found = cards_to_discard(view([fire, SERPENT], enemies=(cold_proof,)), deck_left=7)
        self.assertEqual([discard.card for discard in found], [1])

    def test_a_second_heal_goes_while_health_is_safe_and_the_first_stays(self):
        found = cards_to_discard(view([SERPENT, SNOWMAN, PIXIE, HEARTBEAT]), deck_left=7)
        self.assertEqual([discard.card for discard in found], [3])

    def test_the_best_attack_traps_wands_and_treasure_cards_are_kept(self):
        self.assertEqual(cards_to_discard(view([SERPENT, TRAP, WAND]), deck_left=7), [])
        self.assertEqual(cards_to_discard(view([SERPENT, FREEZE]), deck_left=7, treasure=frozenset({1})), [])

    def test_no_discards_when_the_deck_is_nearly_out_or_its_size_unknown(self):
        hand = [SERPENT, FREEZE, PIXIE]
        self.assertEqual(cards_to_discard(view(hand), deck_left=DECK_RESERVE), [])
        self.assertEqual(cards_to_discard(view(hand), deck_left=None), [])

    def test_the_deck_count_leaves_out_item_cards(self):
        self.assertEqual(deck_left(14, (SERPENT, FREEZE, PIXIE, WAND), 3), 8)
        self.assertIsNone(deck_left(None, (SERPENT,), 0))


if __name__ == "__main__":
    unittest.main()

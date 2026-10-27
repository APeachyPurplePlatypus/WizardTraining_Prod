import json
import tempfile
import unittest
from pathlib import Path

from wizardtraining.decks import (ADD, KEEP, REMOVE, DeckCard, DeckChange, DeckLog, change_text, plan_deck_changes)

SNOWMAN = DeckCard("Evil Snowman", 0, 3)
FULL = [DeckCard("Frost Beetle", 3), DeckCard("Snow Serpent", 3), DeckCard("Volcanic Shield", 2),
        DeckCard("Pixie", 3), DeckCard("Freeze", 3)]


class DeckPlanTest(unittest.TestCase):
    def test_a_free_slot_is_used_before_any_card_is_taken_out(self):
        deck = [DeckCard("Frost Beetle", 3), DeckCard("Volcanic Shield", 2)]
        changes = plan_deck_changes(SNOWMAN, deck)
        self.assertEqual([(change.action, change.name) for change in changes], [(ADD, "Evil Snowman")] * 3)

    def test_a_full_deck_gives_up_a_partial_shield_and_says_why(self):
        changes = plan_deck_changes(SNOWMAN, FULL)
        self.assertEqual([(change.action, change.name) for change in changes],
                         [(REMOVE, "Volcanic Shield"), (ADD, "Evil Snowman"), (REMOVE, "Volcanic Shield"),
                          (ADD, "Evil Snowman")] + [(KEEP, "Evil Snowman")])
        self.assertIn("blocks only Fire and Storm", changes[0].reason)
        self.assertIn("1 copy of Evil Snowman stay out", changes[-1].reason)

    def test_with_no_rule_the_deck_is_left_alone_and_the_log_says_so(self):
        deck = [DeckCard("Frost Beetle", 7), DeckCard("Freeze", 7)]
        changes = plan_deck_changes(SNOWMAN, deck)
        self.assertEqual([(change.action, change.copies) for change in changes], [(KEEP, 3)])
        self.assertIn("no rule picks a card", changes[0].reason)

    def test_a_spell_already_at_its_wanted_copies_is_kept(self):
        changes = plan_deck_changes(DeckCard("Evil Snowman", 3, 3), FULL + [DeckCard("Evil Snowman", 3)])
        self.assertEqual([change.action for change in changes], [KEEP])
        self.assertIn("already in the deck x3", changes[0].reason)

    def test_the_copy_limit_caps_the_copies_wanted(self):
        changes = plan_deck_changes(DeckCard("Tower Shield", 0, 1), [])
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].action, ADD)

    def test_spellings_that_differ_in_spacing_are_one_card(self):
        deck = [DeckCard("Evil  Snow man", 3)]
        self.assertEqual([change.action for change in plan_deck_changes(SNOWMAN, deck)], [KEEP])


class DeckLogTest(unittest.TestCase):
    def test_one_line_per_card_with_the_deck_size_as_it_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            log = DeckLog(Path(folder))
            deck = FULL + [DeckCard("Filler", 0)]
            changes = [DeckChange(REMOVE, "Volcanic Shield", 1, "r1"), DeckChange(ADD, "Evil Snowman", 1, "r2"),
                       DeckChange(KEEP, "Evil Snowman", 2, "r3")]
            log.add_plan(changes, deck, level=10, zone="WizardCity/WC_Hub")
            lines = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(line["action"], line["deck_before"], line["deck_after"]) for line in lines],
                         [(REMOVE, 14, 13), (ADD, 13, 14), (KEEP, 14, 14)])
        self.assertEqual((lines[0]["card"], lines[0]["reason"], lines[0]["level"]), ("Volcanic Shield", "r1", 10))
        self.assertIn("time", lines[0])

    def test_the_change_reads_as_a_sentence_with_its_reason(self):
        self.assertEqual(change_text(DeckChange(REMOVE, "Pixie", 1, "weak")), "take out Pixie x1: weak")


if __name__ == "__main__":
    unittest.main()

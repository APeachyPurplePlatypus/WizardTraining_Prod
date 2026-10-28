import json
import tempfile
import unittest
from pathlib import Path

from wizardtraining.spells import (KNOWN_AT_FIRST_CHECK, LEARNED, Spell, SpellLog, learned_text, newly_learned,
                                   spell_entry)

FREEZE = Spell(1887199642, name="Freeze", school="Ice", pips=0, effects=("stun 1",))


class SpellsTest(unittest.TestCase):
    def test_a_spell_reads_as_its_name_school_pips_and_effects(self):
        self.assertEqual(FREEZE.text(), "Freeze (Ice, 0 pips; stun 1)")
        self.assertEqual(Spell(74836240).text(), "spell 74836240")
        self.assertEqual(Spell(1, name="Pixie").text(), "Pixie")

    def test_newly_learned_keeps_the_game_order_and_lists_each_spell_once(self):
        self.assertEqual(newly_learned([5, 7], [7, 9, 5, 3, 9]), [9, 3])
        self.assertEqual(newly_learned([], [2, 1]), [2, 1])
        self.assertEqual(newly_learned([1, 2], [2, 1]), [])

    def test_the_log_says_whether_a_new_spell_is_in_the_deck(self):
        deck = {74836240: 2, 1887199642: 1}
        self.assertEqual(learned_text(FREEZE, deck), "learned Freeze (Ice, 0 pips; stun 1); in the equipped deck x1 "
                                                     "(3 cards)")
        self.assertEqual(learned_text(FREEZE, {74836240: 2}), "learned Freeze (Ice, 0 pips; stun 1); not in the "
                                                              "equipped deck (2 cards)")
        entry = spell_entry(FREEZE, kind=LEARNED, deck={}, level=11, zone="WizardCity/WC_Hub")
        self.assertEqual((entry["kind"], entry["name"], entry["in_deck"], entry["deck_cards"], entry["level"]),
                         (LEARNED, "Freeze", 0, 0, 11))

    def test_the_log_is_one_json_line_per_spell(self):
        with tempfile.TemporaryDirectory() as folder:
            log = SpellLog(Path(folder))
            log.add(spell_entry(FREEZE, kind=KNOWN_AT_FIRST_CHECK, deck={1887199642: 1}, level=10, zone="z"))
            log.add(spell_entry(Spell(5), kind=LEARNED, deck={}, level=11, zone="z"))
            lines = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(line["kind"], line["template_id"], line["in_deck"]) for line in lines],
                         [(KNOWN_AT_FIRST_CHECK, 1887199642, 1), (LEARNED, 5, 0)])
        self.assertIn("time", lines[0])


if __name__ == "__main__":
    unittest.main()

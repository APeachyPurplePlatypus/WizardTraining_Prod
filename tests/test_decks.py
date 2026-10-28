import json
import tempfile
import unittest
from pathlib import Path

from wizardtraining.decks import (ADD, ATTACK, EXTRACT, HEAL, KEEP, OTHER, REMOVE, SHIELD, STUN, DeckChange, DeckLog,
                                  change_text, cell_center, deck_spell, first_missing, plan_changes, role_of,
                                  spell_page_and_cell, wanted_deck)

# The Deck page as read in the game, 2026-10-28 09:49: the Starter Deck, 14 cards.
LIST = [deck_spell("Freeze", 3, 3, ["stun 1"], 0),
        deck_spell("Volcanic Shield", 0, 3, ["modify_incoming_damage -70", "modify_incoming_damage -70"], 0),
        deck_spell("Frost Beetle", 3, 3, ["damage 65-105"], 1),
        deck_spell("Snow Serpent", 3, 3, ["damage 155-195"], 2),
        deck_spell("Evil Snowman", 2, 3, ["damage 240-300"], 3),
        deck_spell("Pixie", 3, 3, ["heal 400"], 2),
        deck_spell("Extract Undead", 0, 3, ["collect_essence 100"], 0)]


def copies(wanted):
    return {want.name: want.copies for want in wanted}


class RoleTest(unittest.TestCase):
    def test_roles_come_from_the_spells_effects(self):
        self.assertEqual([spell.role for spell in LIST], [STUN, SHIELD, ATTACK, ATTACK, ATTACK, HEAL, EXTRACT])
        self.assertEqual(role_of([]), OTHER)
        self.assertEqual(LIST[3].strength, 195)


class WantedDeckTest(unittest.TestCase):
    def test_an_essence_goal_puts_one_extract_in_and_the_strongest_hits_and_heals_come_before_stuns(self):
        wanted = wanted_deck(LIST, 14, essence_needed=True)
        self.assertEqual(copies(wanted), {"Extract Undead": 1, "Pixie": 3, "Evil Snowman": 3, "Snow Serpent": 3,
                                          "Frost Beetle": 3, "Freeze": 1, "Volcanic Shield": 0})
        freeze = next(want for want in wanted if want.name == "Freeze")
        self.assertIn("1 of 3 copies fit in the 14-card deck", freeze.reason)

    def test_without_an_essence_goal_the_extract_stays_out_and_says_why(self):
        wanted = wanted_deck(LIST, 14, essence_needed=False)
        self.assertEqual(copies(wanted)["Extract Undead"], 0)
        self.assertEqual(copies(wanted)["Freeze"], 2)
        extract = next(want for want in wanted if want.name == "Extract Undead")
        self.assertIn("no open quest goal needs an essence", extract.reason)

    def test_a_shield_is_never_wanted(self):
        wanted = wanted_deck(LIST, 100, essence_needed=False)
        self.assertEqual(copies(wanted)["Volcanic Shield"], 0)
        self.assertIn("never casts", next(want for want in wanted if want.name == "Volcanic Shield").reason)


class PlanTest(unittest.TestCase):
    def test_cards_come_out_before_others_go_in_one_copy_at_a_time(self):
        changes = plan_changes(LIST, wanted_deck(LIST, 14, essence_needed=True))
        self.assertEqual([(change.action, change.name) for change in changes if change.action != KEEP],
                         [(REMOVE, "Freeze"), (REMOVE, "Freeze"), (ADD, "Extract Undead"), (ADD, "Evil Snowman")])
        self.assertEqual([change.name for change in changes if change.action == KEEP], ["Volcanic Shield"])

    def test_a_deck_as_wanted_needs_no_change(self):
        done = [deck_spell("Pixie", 3, 3, ["heal 400"], 2), deck_spell("Frost Beetle", 3, 3, ["damage 65-105"], 1)]
        self.assertEqual(plan_changes(done, wanted_deck(done, 6, essence_needed=False)), [])

    def test_the_first_missing_card_is_the_one_to_try_when_the_capacity_is_unknown(self):
        self.assertEqual(first_missing(LIST, wanted_deck(LIST, 10_000, essence_needed=True)), "Extract Undead")
        self.assertEqual(first_missing(LIST, wanted_deck(LIST, 10_000, essence_needed=False)), "Evil Snowman")


class PageTest(unittest.TestCase):
    def test_the_seventh_spell_is_on_the_second_page(self):
        self.assertEqual(spell_page_and_cell(6), (1, 0))
        self.assertEqual(spell_page_and_cell(4), (0, 4))

    def test_cells_are_counted_row_by_row(self):
        self.assertEqual(cell_center((0, 0, 200, 300), 0, 2, 3), (50, 50))
        self.assertEqual(cell_center((0, 0, 200, 300), 3, 2, 3), (150, 150))


class DeckLogTest(unittest.TestCase):
    def test_one_line_per_card_with_the_deck_size(self):
        with tempfile.TemporaryDirectory() as folder:
            log = DeckLog(Path(folder))
            log.add(DeckChange(REMOVE, "Freeze", 1, "r1"), deck_before=14, deck_after=13, level=13, zone="WizardCity/WC_Hub")
            lines = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual((lines[0]["action"], lines[0]["card"], lines[0]["deck_before"], lines[0]["deck_after"]),
                         (REMOVE, "Freeze", 14, 13))
        self.assertIn("time", lines[0])

    def test_the_change_reads_as_a_sentence_with_its_reason(self):
        self.assertEqual(change_text(DeckChange(REMOVE, "Pixie", 1, "weak")), "take out Pixie x1: weak")
        self.assertEqual(change_text(DeckChange(KEEP, "Volcanic Shield", 0, "a shield")),
                         "leave out Volcanic Shield: a shield")


if __name__ == "__main__":
    unittest.main()

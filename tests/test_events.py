import json
import tempfile
import unittest
from pathlib import Path

from wizardtraining.events import (EventLog, change, describe_battle, describe_changes, describe_round, dialog_text,
                                   enemy_names, threat_text)


def round_entry(number, health, action, enemies):
    return {"view": {"round_number": number, "health": health, "max_health": 624, "pips": 3,
                     "enemies": [{"name": name, "health": hp} for name, hp in enemies]}, "action": action}


class EventLogTest(unittest.TestCase):
    def test_writes_one_json_line_per_event(self):
        with tempfile.TemporaryDirectory() as folder:
            events = EventLog.in_folder(Path(folder))
            events.emit("battle", "won", outcome="won")
            events.emit("zone", "A -> B")
            lines = [json.loads(line) for line in events.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([line["kind"] for line in lines], ["battle", "zone"])
        self.assertEqual(lines[0]["outcome"], "won")
        self.assertIn("time", lines[0])

    def test_without_a_file_it_only_logs(self):
        self.assertEqual(EventLog().emit("run", "started")["summary"], "started")


class DescriptionTest(unittest.TestCase):
    def test_enemy_names_are_counted(self):
        self.assertEqual(enemy_names([{"name": "Ghost"}, {"name": "Ghost"}, {"name": "Rat"}]), "Ghost x2, Rat")
        self.assertEqual(enemy_names([]), "none seen")

    def test_change(self):
        self.assertEqual(change(10, 23), "+13")
        self.assertEqual(change(10, 4), "-6")
        self.assertEqual(change(10, 10), "no change")
        self.assertEqual(change(None, 3), "no change")

    def test_dialog_text_drops_markup(self):
        pages = ["<center>Welcome, young Wizard!</center>", "", "Go see <b>Professor Drake</b> in the Myth School."]
        self.assertEqual(dialog_text(pages), "Welcome, young Wizard!\nGo see Professor Drake in the Myth School.")

    def test_describe_round(self):
        text = describe_round(round_entry(2, 450, "cast Frost Beetle on enemy", [("Haunted Minion", 35)]))
        self.assertEqual(text, "round 2: me 450/624 with 3 pips; cast Frost Beetle on enemy; "
                               "enemies left: Haunted Minion 35")

    def test_describe_round_shows_the_pips_an_enemy_holds(self):
        entry = round_entry(8, 357, "cast Frost Beetle (Ice) on enemy General Akilles", [("General Akilles", 145)])
        entry["view"]["enemies"][0]["pips"] = 5
        self.assertTrue(describe_round(entry).endswith("enemies left: General Akilles 145 (5 pips)"))

    def test_describe_round_says_when_the_wizard_returned_to_combat(self):
        entry = round_entry(3, 442, "cast Frost Beetle (Ice) on enemy Fire Elf Hunter", [("Fire Elf Hunter", 55)])
        entry["returned to combat"] = "answered 'Would you like to return to combat?'"
        self.assertIn("442/624 with 3 pips; answered 'Would you like to return to combat?'; cast Frost Beetle",
                      describe_round(entry))

    def test_threat_text_names_the_closest_approaches_before_a_battle(self):
        closest = [{"name": "FireElf-Red-L02", "distance": 301, "seconds_before": 3.2},
                   {"name": "Snowman-Fire-L12", "distance": 954, "seconds_before": 0.1}]
        self.assertEqual(threat_text(closest), "; closest approaches before the battle: FireElf-Red-L02 301 (3.2 s "
                                               "before), Snowman-Fire-L12 954 (0.1 s before)")
        self.assertEqual(threat_text(None), "")
        self.assertEqual(threat_text([]), "")

    def test_describe_round_lists_the_hand(self):
        entry = round_entry(1, 600, "cast Snow Serpent (Ice) on enemy", [("Warhorn", 285)])
        entry["view"]["cards"] = [{"name": "Frost Beetle", "pips": 1}, {"name": "Snow Serpent", "pips": 2},
                                  {"name": "Frost Beetle", "pips": 1}]
        self.assertTrue(describe_round(entry).endswith("; hand: Frost Beetle x2 (1 pips), Snow Serpent (2 pips)"))

    def test_describe_round_shows_mana_when_known(self):
        entry = round_entry(2, 450, "pass: the hand read empty", [("Warhorn", 285)])
        entry["view"]["mana"] = 3
        self.assertTrue(describe_round(entry).startswith("round 2: me 450/624 with 3 pips, 3 mana; pass: the hand read empty"))

    def test_describe_round_shows_wards_and_traps(self):
        entry = round_entry(3, 400, "cast Frost Beetle (Ice) on enemy", [("The Harvest Lord", 335)])
        entry["view"]["enemies"][0]["incoming"] = [{"school": "Myth", "percent": -50}, {"school": "Ice", "percent": 25}]
        self.assertTrue(describe_round(entry).endswith("enemies left: The Harvest Lord 335 (Myth -50%, Ice +25%)"))
        entry["view"]["enemies"][0]["resistances"] = {"Myth": 0.3, "Storm": -0.1}
        self.assertTrue(describe_round(entry).endswith("(Myth -50%, Ice +25%; resists Myth 30%, Storm -10%)"))

    def test_describe_battle_says_what_happened(self):
        battle = {"rounds": [round_entry(1, 624, "cast Imp", [("Haunted Minion", 135)]),
                             round_entry(2, 580, "cast Imp", [("Haunted Minion", 40)])]}
        text = describe_battle(battle, seconds=41.6, outcome="won",
                               before={"health": 624, "max_health": 624, "gold": 100, "level": 5},
                               after={"health": 534, "max_health": 624, "gold": 113, "level": 5})
        self.assertEqual(text, "won after 2 rounds in 42 s against up to 1 at once (Haunted Minion); "
                               "health 624/624 -> 534/624, gold +13, level 5")

    def test_describe_battle_names_rounds_whose_move_the_game_never_logged(self):
        rounds = [round_entry(number, 300, "cast Fire Cat", [("Cyclops Legionnaire", 60)]) for number in (5, 6, 7)]
        rounds[0]["sent"], rounds[1]["sent"], rounds[2]["sent"] = ["Cast Spell"], [], None
        text = describe_battle({"rounds": rounds}, seconds=60, outcome="lost",
                               before={"health": 300, "max_health": 801}, after={"health": 1, "max_health": 801})
        self.assertTrue(text.endswith("; the game logged no move in rounds 6"))

    def test_counts_enemies_that_join_after_the_first_round(self):
        battle = {"rounds": [round_entry(1, 624, "cast", [("Electric Eel", 150)]),
                             round_entry(2, 624, "cast", [("Electric Eel", 55), ("Electric Eel", 150)]),
                             round_entry(3, 454, "cast", [("Electric Eel", 138)])]}
        text = describe_battle(battle, seconds=157, outcome="won", before={"health": 624, "max_health": 624},
                               after={"health": 454, "max_health": 624})
        self.assertIn("against up to 2 at once (Electric Eel x2)", text)

    def test_describe_changes(self):
        before = {"zone": "OldeTown", "level": 5}
        after = {"zone": "Triton", "level": 6}
        quest = {"title": "Trouble on Triton Avenue", "goal": "persona", "goal_id": 2, "goal_zone": "Triton"}
        found = describe_changes(before, after, {"title": "Trouble on Triton Avenue", "goal_id": 1}, quest)
        self.assertEqual([kind for kind, _ in found], ["zone", "level", "quest"])
        self.assertEqual(found[2][1], "Trouble on Triton Avenue: persona goal in Triton")
        self.assertEqual(describe_changes(after, after, quest, quest), [])


if __name__ == "__main__":
    unittest.main()

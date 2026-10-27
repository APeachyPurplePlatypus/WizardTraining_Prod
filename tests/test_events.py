import json
import tempfile
import unittest
from pathlib import Path

from wizardtraining.events import EventLog, change, describe_battle, describe_changes, describe_round, enemy_names


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

    def test_describe_round(self):
        text = describe_round(round_entry(2, 450, "cast Frost Beetle on enemy", [("Haunted Minion", 35)]))
        self.assertEqual(text, "round 2: me 450/624 with 3 pips; cast Frost Beetle on enemy; "
                               "enemies left: Haunted Minion 35")

    def test_describe_battle_says_what_happened(self):
        battle = {"rounds": [round_entry(1, 624, "cast Imp", [("Haunted Minion", 135)]),
                             round_entry(2, 580, "cast Imp", [("Haunted Minion", 40)])]}
        text = describe_battle(battle, seconds=41.6, outcome="won",
                               before={"health": 624, "max_health": 624, "gold": 100, "level": 5},
                               after={"health": 534, "max_health": 624, "gold": 113, "level": 5})
        self.assertEqual(text, "won after 2 rounds in 42 s against up to 1 at once (Haunted Minion); "
                               "health 624/624 -> 534/624, gold +13, level 5")

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

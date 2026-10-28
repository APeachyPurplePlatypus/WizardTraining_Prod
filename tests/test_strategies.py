import unittest

from wizardtraining.strategies import (COMBAT_STRATEGIES, CROWD_STRATEGIES, NO_CLOSER_FIGHTS, NO_CLOSER_SECONDS,
                                       WALK_STRATEGIES, GoalApproach, combat_strategy_named, fight_situation, next_combat_strategy,
                                       next_walk_strategy)


class StrategiesTest(unittest.TestCase):
    def test_each_lost_fight_takes_the_next_strategy_never_one_already_tried(self):
        tried = []
        names = []
        while (strategy := next_combat_strategy(tried)) is not None:
            names.append(strategy.name)
            tried.append(strategy.name)
        self.assertEqual(names, [strategy.name for strategy in COMBAT_STRATEGIES])
        self.assertEqual(len(set(names)), len(names))
        self.assertIsNone(next_combat_strategy(names))

    def test_the_strategies_differ_in_what_they_change(self):
        default, earlier, dangerous, saving = COMBAT_STRATEGIES
        self.assertGreater(earlier.heal_below, default.heal_below)
        self.assertGreater(earlier.enemy_damage_per_pip, default.enemy_damage_per_pip)
        self.assertNotEqual(dangerous.target, default.target)
        self.assertTrue(saving.save_pips_for_bigger_cards)
        self.assertTrue(all(strategy.why for strategy in COMBAT_STRATEGIES))

    def test_a_walk_strategy_is_taken_once_and_only_when_available(self):
        self.assertEqual(next_walk_strategy([])[0], WALK_STRATEGIES[0][0])
        self.assertEqual(next_walk_strategy(["nav graph first"])[0], "collision data first")
        available = {"wait for the way to clear"}
        self.assertEqual(next_walk_strategy([], available)[0], "wait for the way to clear")
        self.assertIsNone(next_walk_strategy(["wait for the way to clear"], available))

    def test_crowd_strategies_come_first_when_asked_for(self):
        self.assertEqual(next_walk_strategy([], first=CROWD_STRATEGIES)[0], "wait for the way to clear")
        self.assertEqual(next_walk_strategy(["wait for the way to clear"], first=CROWD_STRATEGIES)[0],
                         "go to the Commons and walk back")

    def test_a_walk_no_closer_for_three_fights_or_five_minutes_is_a_stall(self):
        approach, key = GoalApproach(), ("Krokotopia/KT_Pyramid/KT_Chamber", "QuestTitle", 1)
        self.assertFalse(approach.note(key, 15000, 0.0, fought=False))
        for fight in range(NO_CLOSER_FIGHTS - 1):
            self.assertFalse(approach.note(key, 15100, 10.0 + fight, fought=True))
        self.assertTrue(approach.note(key, 14900, 20.0, fought=True))
        approach.restart(20.0)
        self.assertFalse(approach.note(key, 15000, 30.0, fought=False))
        self.assertTrue(approach.note(key, 15000, 20.0 + NO_CLOSER_SECONDS, fought=False))

    def test_getting_closer_or_a_new_goal_starts_over(self):
        approach, key = GoalApproach(), ("zone", "quest", 1)
        approach.note(key, 15000, 0.0, fought=False)
        approach.note(key, 15000, 10.0, fought=True)
        approach.note(key, 15000, 11.0, fought=True)
        self.assertFalse(approach.note(key, 10000, 12.0, fought=True))
        self.assertFalse(approach.note(("zone", "quest", 2), 10000, 999.0, fought=True))

    def test_a_strategy_is_found_by_its_name_and_an_unknown_name_is_the_default(self):
        self.assertEqual(combat_strategy_named("heal earlier"), COMBAT_STRATEGIES[1])
        self.assertEqual(combat_strategy_named("gone"), COMBAT_STRATEGIES[0])

    def test_a_fight_is_known_by_its_enemies_in_any_order(self):
        self.assertEqual(fight_situation(["Lord Nightshade", "Field Guard"]), fight_situation(["Field Guard", "Lord Nightshade"]))
        self.assertEqual(fight_situation([]), "unknown enemies")


if __name__ == "__main__":
    unittest.main()

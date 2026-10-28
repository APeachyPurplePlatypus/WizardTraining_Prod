import unittest

from wizardtraining.strategies import (COMBAT_STRATEGIES, WALK_STRATEGIES, fight_situation, next_combat_strategy,
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

    def test_a_fight_is_known_by_its_enemies_in_any_order(self):
        self.assertEqual(fight_situation(["Lord Nightshade", "Field Guard"]), fight_situation(["Field Guard", "Lord Nightshade"]))
        self.assertEqual(fight_situation([]), "unknown enemies")


if __name__ == "__main__":
    unittest.main()

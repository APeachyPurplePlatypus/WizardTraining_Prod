import unittest

from wizardtraining.experience import progress_text, xp_gained, xp_to_next, xp_to_reach

# From the game's MagicXPConfig.xml (read 2026-10-28): the total experience at which the next level begins.
TABLE = {12: 11175, 13: 13755, 14: 16680, 15: 20200}


class ExperienceTest(unittest.TestCase):
    def test_progress_toward_the_next_level(self):
        self.assertEqual(xp_to_next(13, TABLE), 13755)
        self.assertEqual(progress_text(13, 13732, TABLE), "2,557 of 2,580 XP into level 13: 23 to level 14 (99%)")
        self.assertEqual(progress_text(14, 13765, TABLE), "10 of 2,925 XP into level 14: 2,915 to level 15 (0%)")
        self.assertEqual(progress_text(99, 10, TABLE), "10 XP in all at level 99")

    def test_gains_are_the_difference_of_the_totals_across_a_level_up(self):
        self.assertEqual(xp_gained((13, 13732), (14, 13765), TABLE), 33)
        self.assertIsNone(xp_gained((13, 13300), (13, 13104), TABLE))

    def test_what_is_left_to_a_target_level(self):
        self.assertEqual(xp_to_reach(13, 13104, 15, TABLE), 16680 - 13104)
        self.assertEqual(xp_to_reach(14, 13765, 15, TABLE), 2915)
        self.assertEqual(xp_to_reach(15, 0, 15, TABLE), 0)


if __name__ == "__main__":
    unittest.main()

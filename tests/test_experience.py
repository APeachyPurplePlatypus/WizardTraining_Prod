import unittest

from wizardtraining.experience import progress_text, xp_gained, xp_to_next, xp_to_reach

# From the game's MagicXPConfig.xml (read 2026-10-28): what each level takes to reach the next.
TABLE = {12: 11175, 13: 13755, 14: 16680, 15: 20200}


class ExperienceTest(unittest.TestCase):
    def test_progress_toward_the_next_level(self):
        self.assertEqual(xp_to_next(13, TABLE), 13755)
        self.assertEqual(progress_text(13, 13104, TABLE), "13,104 of 13,755 XP into level 13: 651 to level 14 (95%)")
        self.assertEqual(progress_text(99, 10, TABLE), "10 XP into level 99")

    def test_gains_within_a_level_and_across_a_level_up(self):
        self.assertEqual(xp_gained((13, 13104), (13, 13300), TABLE), 196)
        self.assertEqual(xp_gained((13, 13104), (14, 49), TABLE), 651 + 49)
        self.assertIsNone(xp_gained((13, 13300), (13, 13104), TABLE))

    def test_what_is_left_to_a_target_level(self):
        self.assertEqual(xp_to_reach(13, 13104, 15, TABLE), 651 + 16680)
        self.assertEqual(xp_to_reach(15, 0, 15, TABLE), 0)


if __name__ == "__main__":
    unittest.main()

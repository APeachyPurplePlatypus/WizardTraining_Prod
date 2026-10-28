import unittest

from wizardtraining.sidequests import UNSUPPORTED, unsupported_reason


class UnsupportedQuestsTest(unittest.TestCase):
    def test_a_quest_that_needs_a_pet_is_unsupported_with_its_reason(self):
        self.assertIn("pet", unsupported_reason("You Can Dig It"))

    def test_other_quests_and_no_title_are_not(self):
        self.assertIsNone(unsupported_reason("Looking Sharp!"))
        self.assertIsNone(unsupported_reason(None))
        self.assertTrue(all(reason for reason in UNSUPPORTED.values()))


if __name__ == "__main__":
    unittest.main()

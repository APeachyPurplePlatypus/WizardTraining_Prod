import unittest

from wizardtraining.ramps import foot_of_the_ramp, top_of_the_ramp

COMMONS_NAV_ROUTE = [(443, -2225), (914, -2120), (953, -1119), (-3416, 1257), (-3877, 1443), (-4112, 833), (-4376, 297),
                     (-3896, -183), (-4856, -2103), (-5336, -2583), (-5089, -2734)]
PIECES = {(443, -2225): 0, (914, -2120): 0, (953, -1119): 0, (-3416, 1257): 0, (-3877, 1443): 0, (-4376, 297): 1,
          (-3896, -183): 1, (-4856, -2103): 1, (22, -2170): 0, (-3870, 1440): 0}


def piece_of(point):
    return PIECES.get(tuple(round(value) for value in point))


class FootOfTheRampTest(unittest.TestCase):
    """The Commons, 2026-10-28: the Smith's terrace is off the walk grid; its nav route climbs from (-3877, 1443)."""

    def test_the_last_nav_waypoint_on_the_starts_piece(self):
        self.assertEqual(foot_of_the_ramp(COMMONS_NAV_ROUTE, piece_of, (22, -2170)), (-3877, 1443))

    def test_none_at_the_foot_itself_where_the_nav_legs_take_over(self):
        self.assertIsNone(foot_of_the_ramp(COMMONS_NAV_ROUTE, piece_of, (-3870, 1440)))

    def test_none_without_a_nav_route_or_off_the_grid(self):
        self.assertIsNone(foot_of_the_ramp(None, piece_of, (22, -2170)))
        self.assertIsNone(foot_of_the_ramp(COMMONS_NAV_ROUTE, piece_of, (99999, 99999)))


class TopOfTheRampTest(unittest.TestCase):
    """From the foot, the nav walk stops on the next level, so its 2,150-long leg across the terrace is planned again."""

    def test_the_first_nav_waypoint_on_another_piece(self):
        self.assertEqual(top_of_the_ramp(COMMONS_NAV_ROUTE[4:], piece_of, (-3877, 1443)), (-4376, 297))

    def test_on_the_upper_level_the_long_leg_goes_to_its_far_end_by_the_collision_data(self):
        upper = COMMONS_NAV_ROUTE[6:]
        self.assertEqual(foot_of_the_ramp(upper, piece_of, (-4376, 297)), (-4856, -2103))

    def test_none_when_the_rest_is_off_the_grid(self):
        self.assertIsNone(top_of_the_ramp(COMMONS_NAV_ROUTE[8:], piece_of, (-4856, -2103)))


if __name__ == "__main__":
    unittest.main()

import math
import unittest
from types import SimpleNamespace

from wizardtraining.geometry import (angle_between, distance_to_path, distance_to_segment, flat_distance, path_within,
                                     point_toward, xy)


class GeometryTest(unittest.TestCase):
    def test_reads_points_from_objects_and_sequences(self):
        self.assertEqual(xy(SimpleNamespace(x=1.0, y=2.0, z=3.0)), (1.0, 2.0))
        self.assertEqual(xy((4.0, 5.0, 6.0)), (4.0, 5.0))

    def test_flat_distance_ignores_height(self):
        self.assertEqual(flat_distance(SimpleNamespace(x=0.0, y=0.0, z=0.0), (3.0, 4.0, 1000.0)), 5.0)

    def test_angle_between_takes_the_short_way_round(self):
        self.assertAlmostEqual(angle_between(0.1, 2 * math.pi - 0.1), 0.2)
        self.assertAlmostEqual(angle_between(2 * math.pi - 0.1, 0.1), -0.2)
        self.assertTrue(-math.pi <= angle_between(math.pi, 0.0) < math.pi)

    def test_point_toward(self):
        self.assertEqual(point_toward((0, 0), (0, 10), 3), (0.0, 3.0))
        self.assertEqual(point_toward((5, 5), (5, 5), 3), (5.0, 5.0))

    def test_distance_to_segment(self):
        self.assertEqual(distance_to_segment((5, 3), (0, 0), (10, 0)), 3)
        self.assertEqual(distance_to_segment((-3, 4), (0, 0), (10, 0)), 5)
        self.assertEqual(distance_to_segment((3, 4), (0, 0), (0, 0)), 5)

    def test_distance_to_path(self):
        self.assertEqual(distance_to_path((5, 5), [(0, 0), (10, 0), (10, 10)]), 5)
        self.assertEqual(distance_to_path((3, 4), [(0, 0)]), 5)

    def test_path_within_cuts_the_path_at_the_length(self):
        self.assertEqual(path_within([(0, 0), (10, 0), (10, 10)], 15), [(0, 0), (10, 0), (10.0, 5.0)])
        self.assertEqual(path_within([(0, 0), (10, 0)], 50), [(0, 0), (10, 0)])


if __name__ == "__main__":
    unittest.main()

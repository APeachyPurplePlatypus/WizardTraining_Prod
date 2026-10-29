import math
import unittest
from types import SimpleNamespace

from wizardtraining.geometry import (angle_between, bearing, distance_to_path, distance_to_segment, flat_distance,
                                     lookahead_point, path_beyond, path_within, point_toward, project_onto_segment, xy)


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

    def test_bearing_matches_wizwalker_yaw_convention(self):
        self.assertAlmostEqual(bearing((0, 0), (0, -10)), 0.0)
        self.assertAlmostEqual(bearing((0, 0), (-10, 0)), math.pi / 2)
        self.assertAlmostEqual(bearing((0, 0), (0, 10)), math.pi)
        self.assertAlmostEqual(bearing((0, 0), (10, 0)), 3 * math.pi / 2)
        self.assertEqual(bearing((5, 5), (5, 5)), 0.0)

    def test_point_toward(self):
        self.assertEqual(point_toward((0, 0), (0, 10), 3), (0.0, 3.0))
        self.assertEqual(point_toward((5, 5), (5, 5), 3), (5.0, 5.0))

    def test_distance_to_segment(self):
        self.assertEqual(distance_to_segment((5, 3), (0, 0), (10, 0)), 3)
        self.assertEqual(distance_to_segment((-3, 4), (0, 0), (10, 0)), 5)
        self.assertEqual(distance_to_segment((3, 4), (0, 0), (0, 0)), 5)
        foot, along, dist = project_onto_segment((5, 3), (0, 0), (10, 0))
        self.assertEqual(foot, (5.0, 0.0))
        self.assertAlmostEqual(along, 0.5)
        self.assertEqual(dist, 3.0)

    def test_distance_to_path(self):
        self.assertEqual(distance_to_path((5, 5), [(0, 0), (10, 0), (10, 10)]), 5)
        self.assertEqual(distance_to_path((3, 4), [(0, 0)]), 5)

    def test_path_within_cuts_the_path_at_the_length(self):
        self.assertEqual(path_within([(0, 0), (10, 0), (10, 10)], 15), [(0, 0), (10, 0), (10.0, 5.0)])
        self.assertEqual(path_within([(0, 0), (10, 0)], 50), [(0, 0), (10, 0)])


class PathBeyondTest(unittest.TestCase):
    def test_the_rest_of_a_path_after_a_length(self):
        path = [(0, 0), (1000, 0), (1000, 1000)]
        self.assertEqual(path_beyond(path, 500), [(500, 0), (1000, 0), (1000, 1000)])
        self.assertEqual(path_beyond(path, 1500), [(1000, 500), (1000, 1000)])
        self.assertEqual(path_beyond(path, 5000), [(1000, 1000)])


class LookaheadPointTest(unittest.TestCase):
    def test_slides_around_a_corner_before_reaching_the_vertex(self):
        polyline = [(0, 0), (1000, 0), (1000, 1000)]
        carrot, seg = lookahead_point((850, 0), polyline, 250.0)
        self.assertEqual(seg, 0)
        self.assertEqual(carrot, (1000.0, 100.0))

    def test_falls_back_to_the_corner_when_cutting_it_hits_a_wall(self):
        polyline = [(0, 0), (1000, 0), (1000, 1000)]
        carrot, seg = lookahead_point((850, 0), polyline, 250.0, line_walkable=lambda a, b: False)
        self.assertEqual(seg, 0)
        self.assertEqual(carrot, (1000.0, 0.0))

    def test_advances_the_active_segment_once_past_the_corner(self):
        polyline = [(0, 0), (1000, 0), (1000, 1000)]
        carrot, seg = lookahead_point((980, 150), polyline, 250.0)
        self.assertEqual(seg, 1)
        self.assertEqual(carrot, (1000.0, 400.0))


if __name__ == "__main__":
    unittest.main()

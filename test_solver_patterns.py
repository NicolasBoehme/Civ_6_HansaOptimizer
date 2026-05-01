import unittest

from algorithm.solve import solve
from test_board import build_civ_like_test_board


class SolverPatternTests(unittest.TestCase):
    def test_n3_avoids_start_hosted_triangle_fallback(self) -> None:
        board, starting_city = build_civ_like_test_board()

        placement = solve(board, starting_city, 3)

        self.assertGreaterEqual(placement.score, 30)
        self.assertNotEqual(placement.template_name, "triangle_3+fallback")

    def test_n4_prefers_exact_double_split(self) -> None:
        board, starting_city = build_civ_like_test_board()

        placement = solve(board, starting_city, 4)

        self.assertEqual(placement.template_name, "double_2+double_2")
        self.assertEqual(len(placement.cities), 4)
        self.assertGreaterEqual(placement.score, 40)


if __name__ == "__main__":
    unittest.main()

import unittest

from generate import all_jigs


class StandardSquareJigTest(unittest.TestCase):
    def test_four_by_four_uses_freed_space_between_pockets(self):
        jig = next(j for j in all_jigs() if j.key == "std-mag-57x57")
        self.assertEqual(jig.cols_rows, (4, 4))
        self.assertEqual(len(jig.pockets), 16)
        self.assertEqual(jig.plate, (308.0, 308.0))
        self.assertEqual(jig.plate_z, 8.0)
        for p in jig.pockets:
            self.assertEqual((p.w, p.h, p.depth), (57.5, 57.5, 6.0))
        for positions in (
            sorted({p.x for p in jig.pockets}),
            sorted({p.y for p in jig.pockets}),
        ):
            self.assertAlmostEqual(positions[0], 6.25)
            self.assertAlmostEqual(308.0 - positions[-1] - 57.5, 6.25)
            for left, right in zip(positions, positions[1:]):
                self.assertAlmostEqual(right - left - 57.5, 65.5 / 3)


if __name__ == "__main__":
    unittest.main()

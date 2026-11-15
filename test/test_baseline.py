"""The script reader against test/baseline.json (see test/baseline.py)

Today this checks the old reader still gives what the snapshot says.
Step 2 of plans/source-tree.md points the parts at source.statements,
step 3 the cards at the new cards.split; step 7 deletes it.
"""

import unittest

from test import baseline


class Parity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.snapshot = baseline.load()

    def test_same_files(self):
        self.assertEqual(sorted(self.snapshot), baseline.files())

    def test_every_file(self):
        for path, expected in self.snapshot.items():
            with self.subTest(path=path):
                found = baseline.record(path, (baseline.ROOT / path).read_text())
                self.assertEqual(found.get("error"), expected.get("error"))
                self.assertEqual(found.get("parts"), expected.get("parts"))
                self.assertEqual(found["cards"], expected["cards"])


if __name__ == "__main__":
    unittest.main()

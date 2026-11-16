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

    def test_the_files_are_still_there(self):
        self.assertTrue(set(self.snapshot) <= set(baseline.files()))

    def test_every_file_not_edited_since(self):
        edited = [path for path, expected in self.snapshot.items()
                  if baseline.sha(path) != expected["sha"]]
        self.assertLess(len(edited), 10, edited)  # the check still covers nearly all
        for path, expected in self.snapshot.items():
            if path in edited:
                continue
            with self.subTest(path=path):
                found = baseline.record(path, (baseline.ROOT / path).read_text())
                self.assertEqual(found.get("error"), expected.get("error"))
                self.assertEqual(found.get("parts"), expected.get("parts"))
                self.assertEqual(found["cards"], expected["cards"])


if __name__ == "__main__":
    unittest.main()

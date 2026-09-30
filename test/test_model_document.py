import unittest
from pathlib import Path

from automationv3.database import connect, init_db
from automationv3.editor.document import (
    open_document, get_document, all_documents, save_document, save_draft, set_meta
)


class TestDocument(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        init_db(self.conn)

        self.root = Path(__file__).resolve().parent / 'data' / 'rvts'

        self.temp_file = self.root / 'BRA' / 'temp.rvt'
        self.temp_file.write_text((self.root / 'BRA' / 'tc_bra_00001.rvt').read_text())

    def tearDown(self):
        self.conn.close()
        self.temp_file.unlink()

    def test_create(self):
        document = open_document(self.conn, self.root / 'BRA' / 'tc_bra_00001.rvt')

        self.assertIsNotNone(document)
        self.assertEqual(all_documents(self.conn), [document])

    def test_create_many(self):
        open_document(self.conn, self.root / 'BRA' / 'tc_bra_00001.rvt')
        open_document(self.conn, self.root / 'BRA' / 'tc_bra_00002.rvt')

        self.assertEqual(len(all_documents(self.conn)), 2)

    def test_open_twice(self):
        open_document(self.conn, self.root / 'BRA' / 'tc_bra_00001.rvt')
        open_document(self.conn, self.root / 'BRA' / 'tc_bra_00001.rvt')

        self.assertEqual(len(all_documents(self.conn)), 1)

    def test_modified_time(self):
        document = open_document(self.conn, self.temp_file)
        mtime_before = document.st_mtime

        save_document(self.conn, document)

        self.assertGreater(document.st_mtime, mtime_before)
        self.assertEqual(get_document(self.conn, document.id).st_mtime, document.st_mtime)

    def test_mime(self):
        document = open_document(self.conn, self.root / 'BRA' / 'tc_bra_00001.rvt')
        self.assertEqual(document.mime, 'application/rvt+edn')

    def test_draft(self):
        document = open_document(self.conn, self.temp_file)
        draft_text = '(Wait 1)'

        save_draft(self.conn, document, draft_text)

        reloaded = get_document(self.conn, document.id)
        self.assertTrue(reloaded.is_modified())
        self.assertEqual(draft_text, reloaded.content)
        self.assertNotEqual(draft_text, self.temp_file.read_text())

        save_document(self.conn, reloaded)
        self.assertFalse(get_document(self.conn, document.id).is_modified())
        self.assertEqual(draft_text, self.temp_file.read_text())

    def test_meta(self):
        document = open_document(self.conn, self.temp_file)
        set_meta(self.conn, document, 'raw', True)
        self.assertEqual(get_document(self.conn, document.id).meta, {'raw': True})


if __name__ == '__main__':
    unittest.main()

import unittest
from pathlib import Path

from automationv3.database import connect, init_db
from automationv3.editor.editor import (
    create_editor, get_editor, add_document, select_document, close_document
)


class TestEditor(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        init_db(self.conn)

        self.root = Path(__file__).resolve().parent / 'data' / 'rvts'
        self.temp_file = self.root / 'BRA' / 'temp.rvt'
        self.temp_file2 = self.root / 'BRA' / 'temp2.rvt'

        self.temp_file.write_text('TEST FILE')
        self.temp_file2.write_text('TEST FILE 2')

        self.editor_id = create_editor(self.conn).id

    def tearDown(self):
        self.conn.close()
        self.temp_file.unlink()
        self.temp_file2.unlink()

    def editor(self):
        return get_editor(self.conn, self.editor_id)

    def test_create(self):
        self.assertEqual(len(self.editor().documents), 0)

    def test_missing(self):
        self.assertIsNone(get_editor(self.conn, 999))

    def test_open(self):
        document = add_document(self.conn, self.editor_id, self.temp_file)
        self.assertIn(document, self.editor().documents)

    def test_open_single_time(self):
        add_document(self.conn, self.editor_id, self.temp_file)
        add_document(self.conn, self.editor_id, self.temp_file)
        self.assertEqual(len(self.editor().documents), 1)

    def test_close(self):
        document = add_document(self.conn, self.editor_id, self.temp_file)
        close_document(self.conn, self.editor_id, document.id)
        self.assertNotIn(document, self.editor().documents)

    def test_active_document(self):
        document1 = add_document(self.conn, self.editor_id, self.temp_file)
        document2 = add_document(self.conn, self.editor_id, self.temp_file2)

        # no active document
        self.assertIsNone(self.editor().active_document)

        # select document1
        select_document(self.conn, self.editor_id, document1.id)
        self.assertEqual(document1, self.editor().active_document)

        # select document2
        select_document(self.conn, self.editor_id, document2.id)
        self.assertEqual(document2, self.editor().active_document)

        # close active document
        close_document(self.conn, self.editor_id, document2.id)
        self.assertEqual(document1, self.editor().active_document)

    def test_active_document_deleted_from_disk(self):
        document1 = add_document(self.conn, self.editor_id, self.temp_file)
        document2 = add_document(self.conn, self.editor_id, self.temp_file2)
        select_document(self.conn, self.editor_id, document2.id)

        self.temp_file2.unlink()
        self.assertEqual(document1, self.editor().active_document)
        self.temp_file2.write_text('')


if __name__ == '__main__':
    unittest.main()

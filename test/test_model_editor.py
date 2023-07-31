import unittest
import sqlite3
import os
from pathlib import Path

from automationv3.models import Editor

class TestEditor(unittest.TestCase):
    def setUp(self):
        self.db_file = "test_document.db"
        self.conn = sqlite3.connect(self.db_file)
        Editor.ensure_db(self.conn)
        
        self.root = Path(__file__).resolve().parent / 'data' / 'rvts'
        self.temp_file = self.root / 'BRA' / 'temp.rvt'
        self.temp_file2 = self.root / 'BRA' / 'temp2.rvt'

        self.temp_file.write_text('TEST FILE')
        self.temp_file2.write_text('TEST FILE 2')
        

    def tearDown(self):
        self.conn.close()
        os.remove(self.db_file)
        self.temp_file.unlink()


    def test_create(self):
        editor = Editor.create(self.conn)
        self.assertEqual(len(editor.documents()), 0)

    def test_open(self):
        editor = Editor.create(self.conn)
        document = editor.open(self.temp_file)

        self.assertIn(document, editor.documents())
    
    def test_open_single_time(self):
        editor = Editor.create(self.conn)
        document = editor.open(self.temp_file)
        document = editor.open(self.temp_file)

        self.assertEqual(len(editor.documents()), 1)

        
    def test_close(self):
        editor = Editor.create(self.conn)
        document = editor.open(self.temp_file)
        editor.close(document)

        self.assertNotIn(document, editor.documents())

    def test_active_document(self):
        editor = Editor.create(self.conn)
        document1 = editor.open(self.temp_file)
        document2 = editor.open(self.temp_file2)

        # no active document
        self.assertIsNone(editor.active_document)

        # select document1
        editor.select_document(document1)
        self.assertEqual(document1, editor.active_document)
        
        # select document2
        editor.select_document(document2)
        self.assertEqual(document2, editor.active_document)
        
        # close active document
        editor.close(document2)
        self.assertEqual(document1, editor.active_document)



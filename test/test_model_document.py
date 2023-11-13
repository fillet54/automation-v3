
import unittest
import sqlite3
import os
from pathlib import Path

from automationv3.editor.models import Document 

class TestDocument(unittest.TestCase):
    def setUp(self):
        self.db_file = "test_document.db"
        self.conn = sqlite3.connect(self.db_file)
        Document.ensure_db(self.conn)

        self.root = Path(__file__).resolve().parent / 'data' / 'rvts'

        self.temp_file = self.root / 'BRA' / 'temp.rvt'
        self.temp_file.write_text((self.root / 'BRA' / 'tc_bra_00001.rvt').read_text())


    def tearDown(self):
        self.conn.close()
        os.remove(self.db_file)
        self.temp_file.unlink()

    def test_create(self):
        document = Document.open(self.conn, self.root / 'BRA' / 'tc_bra_00001.rvt')

        self.assertIsNotNone(document)
        self.assertGreater(len(Document.all(self.conn)), 0)
    
    def test_create_many(self):
        document1 = Document.open(self.conn, self.root / 'BRA' / 'tc_bra_00001.rvt')
        document2 = Document.open(self.conn, self.root / 'BRA' / 'tc_bra_00002.rvt')

        self.assertEqual(len(Document.all(self.conn)), 2)
    
    def test_open_twice(self):
        document1 = Document.open(self.conn, self.root / 'BRA' / 'tc_bra_00001.rvt')
        document2 = Document.open(self.conn, self.root / 'BRA' / 'tc_bra_00001.rvt')

        self.assertEqual(len(Document.all(self.conn)), 1)

    def test_modified_time(self):
        document1 = Document.open(self.conn, self.root / 'BRA' / 'tc_bra_00001.rvt')
        mtime_before = document1.st_mtime

        document1.save()
        mtime_after = document1.st_mtime

        self.assertGreater(mtime_after, mtime_before)

    def test_mime(self):
        document = Document.open(self.conn, self.root / 'BRA' / 'tc_bra_00001.rvt')
        self.assertEqual(document.mime, 'application/rvt+edn')


    def test_draft(self):
        document = Document.open(self.conn, self.root / 'BRA' / 'temp.rvt')
        original_text = document.content
    
        draft_text = '''{
        :rvt/title "TITLE"
        :rvt/description "DESCRIPTION"
        :rvt/requirements []
        :rvt/setup []
        :rvt/steps []
        '''
        document.save_draft(draft_text)


        self.assertEqual(draft_text, document.content)
        self.assertNotEqual(draft_text, self.temp_file.read_text())







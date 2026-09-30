import unittest
import sqlite3
import os
from pathlib import Path

from automationv3.editor.models import Treeview, FileNode 
from automationv3.database import init_db

class TestTreeview(unittest.TestCase):
    def setUp(self):
        self.db_file = "test_treeview.db"
        self.conn = sqlite3.connect(self.db_file)
        self.root = Path(__file__).resolve().parent / 'data' / 'rvts'
        init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        os.remove(self.db_file)

    def test_create(self):
        treeview = Treeview.create(self.conn, self.root, FileNode)
        self.assertIsNotNone(treeview)
    
    def test_children(self):
        treeview = Treeview.create(self.conn, self.root, FileNode)
        self.assertTrue(self.root / 'BRA' in treeview.root.children())
        self.assertTrue(self.root / 'FUE' in treeview.root.children())
    
    def test_relative_path(self):
        treeview = Treeview.create(self.conn, self.root, FileNode)
        child = list(sorted(treeview.root.children()))[0]
        self.assertEqual(child.relative_path, Path('BRA'))

    def test_is_dir(self):
        treeview = Treeview.create(self.conn, self.root, FileNode)
        node = treeview.node('BRA')
        self.assertTrue(node.is_dir())
        self.assertFalse(node.is_file())
    
    def test_is_file(self):
        treeview = Treeview.create(self.conn, self.root, FileNode)
        node = treeview.node(self.root / 'BRA' / 'tc_bra_00001.rvt')
        self.assertTrue(node.is_file())
        self.assertFalse(node.is_dir())

    def test_outside_root(self):
        treeview = Treeview.create(self.conn, self.root, FileNode)
        with self.assertRaises(ValueError):
            treeview.node('../../')
        with self.assertRaises(ValueError):
            treeview.node('/etc/passwd')

    def test_toggle(self):
        treeview = Treeview.create(self.conn, self.root, FileNode)
        node = treeview.node(self.root / 'BRA')

        self.assertFalse(node in treeview.opened)
        treeview.toggle(node)
        self.assertTrue(node in treeview.opened)
        treeview.toggle(node)
        self.assertFalse(node in treeview.opened)


import unittest
import sqlite3
import os
from pathlib import Path

from automationv3.models import Treeview, FilesystemTreeNode 

class TestTreeview(unittest.TestCase):
    def setUp(self):
        self.db_file = "test_treeview.db"
        self.conn = sqlite3.connect(self.db_file)
        self.root = Path(__file__).resolve().parent / 'data' / 'rvts'
        Treeview.ensure_db(self.conn)

    def tearDown(self):
        self.conn.close()
        os.remove(self.db_file)

    def test_create(self):
        treeview = Treeview.create(self.conn, self.root, FilesystemTreeNode)
        self.assertIsNotNone(treeview)
    
    def test_children(self):
        treeview = Treeview.create(self.conn, self.root, FilesystemTreeNode)
        self.assertTrue('BRA' in treeview.root.children())
        self.assertTrue('FUE' in treeview.root.children())
    
    def test_relative_path(self):
        treeview = Treeview.create(self.conn, self.root, FilesystemTreeNode)
        child = list(sorted(treeview.root.children()))[0]
        self.assertEqual(child.relative_path, Path('BRA'))

    def test_is_dir(self):
        treeview = Treeview.create(self.conn, self.root, FilesystemTreeNode)
        node = treeview.node('BRA')
        self.assertTrue(node.is_dir())
        self.assertFalse(node.is_file())
    
    def test_is_file(self):
        treeview = Treeview.create(self.conn, self.root, FilesystemTreeNode)
        node = treeview.node(self.root / 'BRA' / 'tc_bra_00001.rvt')
        self.assertTrue(node.is_file())
        self.assertFalse(node.is_dir())

    def test_toggle(self):
        treeview = Treeview.create(self.conn, self.root, FilesystemTreeNode)
        node = treeview.node(self.root / 'BRA')

        self.assertFalse(node in treeview.opened)
        treeview.toggle(node)
        self.assertTrue(node in treeview.opened)
        treeview.toggle(node)
        self.assertFalse(node in treeview.opened)


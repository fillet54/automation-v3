import unittest
from pathlib import Path

from automationv3.services.database import connect, init_db
from automationv3.services.workspace import FileNode
from automationv3.web.workspace import expanded_nodes, toggle_expanded


class TestFileNode(unittest.TestCase):
    def setUp(self):
        self.root_path = Path(__file__).resolve().parent / 'data' / 'rvts'
        self.root = FileNode(self.root_path)

    def test_children(self):
        self.assertIn(self.root_path / 'BRA', self.root.children())
        self.assertIn(self.root_path / 'FUE', self.root.children())

    def test_relative_path(self):
        child = sorted(self.root.children())[0]
        self.assertEqual(child.relative_path, Path('BRA'))

    def test_is_root(self):
        self.assertTrue(self.root.is_root)
        self.assertFalse(FileNode('BRA', self.root).is_root)

    def test_is_dir(self):
        node = FileNode('BRA', self.root)
        self.assertTrue(node.is_dir())
        self.assertFalse(node.is_file())

    def test_is_file(self):
        node = FileNode(self.root_path / 'BRA' / 'tc_bra_00001.rst', self.root)
        self.assertTrue(node.is_file())
        self.assertFalse(node.is_dir())

    def test_outside_root(self):
        with self.assertRaises(ValueError):
            FileNode('../../', self.root)
        with self.assertRaises(ValueError):
            FileNode('/etc/passwd', self.root)


class TestExpandedNodes(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        init_db(self.conn)
        self.root = FileNode(Path(__file__).resolve().parent / 'data' / 'rvts')

    def tearDown(self):
        self.conn.close()

    def test_toggle(self):
        node = FileNode('BRA', self.root)

        self.assertNotIn(node, expanded_nodes(self.conn, 'ws', self.root))
        toggle_expanded(self.conn, 'ws', node)
        self.assertIn(node, expanded_nodes(self.conn, 'ws', self.root))
        toggle_expanded(self.conn, 'ws', node)
        self.assertNotIn(node, expanded_nodes(self.conn, 'ws', self.root))

    def test_per_workspace(self):
        toggle_expanded(self.conn, 'ws1', FileNode('BRA', self.root))
        self.assertEqual(expanded_nodes(self.conn, 'ws2', self.root), set())

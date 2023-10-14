import unittest
import os

from automationv3.jobqueue.sqlqueue import *


class TestSqlPriorityQueue(unittest.TestCase):
   
    def setUp(self):
        self.q = SQLPriorityQueue(memory=True)

    def test_empty_at_start(self):
        self.assertTrue(self.q.empty())

    def test_simple_put(self):
        self.q.put('Message 1')

        self.assertEqual(self.q.pop()['message'], 'Message 1')
    
    def test_size(self):
        self.q.put('Message 1')
        self.q.put('Message 2')
        self.q.put('Message 3')
        self.q.put('Message 4')

        self.assertEqual(self.q.qsize(), 4)

    def test_not_empty_after_put(self):
        self.q.put('Message 1')
        self.assertFalse(self.q.empty())

    def test_empty_after_pop(self):
        self.q.put('Message 1')
        self.q.pop()
        self.assertTrue(self.q.empty())
    
    def test_pop_from_empty_is_none(self):
        self.q.put('Message 1')
        self.q.pop()
        self.assertIsNone(self.q.pop())

    def test_peek_leaves_message_in_queue(self):
        self.q.put('Message 1')
        self.assertEqual(self.q.peek()['message'], 'Message 1')
        self.assertFalse(self.q.empty())

    def test_get_returns_messages(self):
        self.q.put('Message 1')
        self.q.put('Message 2')

        msgs = self.q.get()
        self.assertEqual(msgs[0]['message'], 'Message 1')
        self.assertEqual(msgs[1]['message'], 'Message 2')
        self.assertFalse(self.q.empty())

    def test_raising_priority(self):
        id1 = self.q.put('Message 1')['message_id']
        id2 = self.q.put('Message 2')['message_id']

        self.assertEqual(self.q.peek()['message_id'], id1)

        self.q.update_priority(id2, 1)
        self.assertEqual(self.q.peek()['message_id'], id2)

    def test_get_message_by_id(self):
        id1 = self.q.put('Message 1')['message_id']
        id2 = self.q.put('Message 2')['message_id']

        self.assertEqual(self.q.get(message_id=id1)['message'], 'Message 1')


    def test_mark_message_done(self):
        id1 = self.q.put('Message 1')['message_id']
        self.q.done(id1)

        self.assertEqual(self.q.get(message_id=id1)['status'], Status.DONE)



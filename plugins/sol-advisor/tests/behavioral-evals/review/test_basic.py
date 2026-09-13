import unittest
from publisher import publish
class PublishTests(unittest.TestCase):
    def test_valid(self):
        output = []
        self.assertTrue(publish("x", {"expires_at":100}, lambda x:x, lambda:90, output))
        self.assertEqual(output, ["x"])
    def test_expired(self):
        output = []
        self.assertFalse(publish("x", {"expires_at":100}, lambda x:x, lambda:101, output))
        self.assertEqual(output, [])

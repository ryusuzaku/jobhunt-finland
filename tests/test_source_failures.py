"""Adapter errors must be observable; no live HTTP is used."""
import unittest
from src.sources.shine import ShineSource, SourceLayoutError

class Response:
    text = '<html><title>Thousands of jobs</title><body>JavaScript application shell</body></html>'
    def raise_for_status(self): pass
class Client:
    async def get(self, *args, **kwargs): return Response()

class SourceFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_shine_unreadable_layout_is_not_silent_success(self):
        with self.assertRaises(SourceLayoutError):
            await ShineSource().fetch(Client())

if __name__ == '__main__':
    unittest.main()

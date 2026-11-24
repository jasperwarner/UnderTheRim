from __future__ import annotations

import http.client
import unittest
from unittest import mock

from upsets import http as uhttp
from upsets.http import FetchError, get_text


class FakeResp:
    def __init__(self, body=b"", error=None):
        self.body, self.error = body, error

    def read(self):
        if self.error:
            raise self.error
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class GetTextTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(uhttp.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def test_incomplete_read_retries_then_fetch_error(self):
        calls = []

        def opener(req, timeout=None):
            calls.append(req.full_url)
            return FakeResp(error=http.client.IncompleteRead(b"partial"))
        with self.assertRaises(FetchError):
            get_text("https://example.test/x", retries=2, opener=opener)
        self.assertEqual(len(calls), 3)

    def test_http_exception_then_success(self):
        responses = [FakeResp(error=http.client.RemoteDisconnected("gone")),
                     FakeResp(b"hello")]
        self.assertEqual(get_text("https://example.test/x",
                                  opener=lambda req, timeout=None: responses.pop(0)), "hello")


if __name__ == "__main__":
    unittest.main()

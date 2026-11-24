from __future__ import annotations

import datetime
import io
import json
import unittest
import urllib.error

from upsets.http import FetchError
from upsets.notion import NotionClient
from upsets.report import Report

TOKEN = "secret_abc123"


class FakeResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, query_results=None, page_url="https://notion.so/page", raises=None):
        self.query_results = query_results or []
        self.page_url = page_url
        self.raises = raises
        self.calls = []

    def __call__(self, request, timeout=None):
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        self.calls.append((request.get_method(), request.full_url, body, dict(request.header_items())))
        if self.raises:
            raise self.raises
        url = request.full_url
        if url.endswith("/query"):
            return FakeResponse({"results": [{"id": p} for p in self.query_results]})
        if url.endswith("/v1/pages"):
            return FakeResponse({"id": "newpage", "url": self.page_url})
        return FakeResponse({})


def make_report(blocks_flags=None):
    return Report(
        day=datetime.date(2026, 11, 21),
        flags={"men": [], "women": []},
        warnings=[],
        final_counts={"men": 5, "women": 4},
        polls_used="men: 11/17",
    )


class NotionClientTests(unittest.TestCase):
    def test_rerun_archives_old_page(self):
        op = FakeOpener(query_results=["old1"])
        NotionClient(TOKEN, "db1", opener=op).publish(make_report())
        seq = [(m, u.split("/v1")[1]) for m, u, _, _ in op.calls]
        self.assertEqual(seq, [
            ("POST", "/databases/db1/query"),
            ("PATCH", "/pages/old1"),
            ("POST", "/pages"),
        ])
        self.assertEqual(op.calls[0][2]["filter"],
                         {"property": "Date", "date": {"equals": "2026-11-21"}})
        self.assertEqual(op.calls[1][2], {"archived": True})

    def test_first_run_creates(self):
        r = make_report()
        op = FakeOpener()
        url = NotionClient(TOKEN, "db1", opener=op).publish(r)
        self.assertEqual(len(op.calls), 2)
        body = op.calls[1][2]
        self.assertEqual(body["parent"], {"database_id": "db1"})
        props = body["properties"]
        self.assertEqual(props["Status"]["select"]["name"], r.status)
        self.assertEqual(props["Name"]["title"][0]["text"]["content"], "D2 Upsets — Nov 21, 2026")
        self.assertEqual(props["Date"], {"date": {"start": "2026-11-21"}})
        self.assertEqual(props["Flags"], {"number": 0})
        self.assertEqual(props["Polls used"]["rich_text"][0]["text"]["content"], "men: 11/17")
        self.assertEqual(url, "https://notion.so/page")
        headers = {k.lower(): v for k, v in op.calls[1][3].items()}
        self.assertEqual(headers["authorization"], "Bearer " + TOKEN)
        self.assertEqual(headers["notion-version"], "2022-06-28")

    def test_over_100_blocks_are_chunked(self):
        import upsets.notion as notion
        blocks = [{"type": "paragraph", "n": i} for i in range(250)]
        orig = notion.to_notion_blocks
        notion.to_notion_blocks = lambda r: blocks
        try:
            op = FakeOpener()
            NotionClient(TOKEN, "db1", opener=op).publish(make_report())
        finally:
            notion.to_notion_blocks = orig
        self.assertEqual(len(op.calls[1][2]["children"]), 100)
        appends = op.calls[2:]
        self.assertEqual([c[0] for c in appends], ["PATCH", "PATCH"])
        self.assertTrue(all(c[1].endswith("/v1/blocks/newpage/children") for c in appends))
        self.assertEqual([len(c[2]["children"]) for c in appends], [100, 50])

    def test_token_not_in_error(self):
        err = urllib.error.HTTPError(
            "https://api.notion.com/v1/pages", 401, "Unauthorized", {},
            io.BytesIO(json.dumps({"message": "API token is invalid."}).encode()))
        op = FakeOpener(raises=err)
        with self.assertRaises(FetchError) as cm:
            NotionClient(TOKEN, "db1", opener=op).publish(make_report())
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertIn("401", str(cm.exception))
        self.assertIn("API token is invalid.", str(cm.exception))


if __name__ == "__main__":
    unittest.main()

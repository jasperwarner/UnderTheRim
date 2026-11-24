from __future__ import annotations

import datetime
import io
import json
import unittest
import urllib.error

from upsets.http import FetchError
from upsets.notion import NotionClient
from upsets.models import Flag, Game, Team
from upsets.report import Report, to_notion_blocks

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


def http_error(code, message="boom"):
    return urllib.error.HTTPError(
        "https://api.notion.com/v1/x", code, "err", {},
        io.BytesIO(json.dumps({"message": message}).encode()))


class FakeOpener:
    def __init__(self, query_results=None, page_url="https://notion.so/page", raises=None,
                 fail_on=None):
        self.query_results = query_results or []
        self.page_url = page_url
        self.raises = raises
        # fail_on: {(method, path suffix): [exception, ...]} raised in order, then succeed
        self.fail_on = fail_on or {}
        self.calls = []

    def __call__(self, request, timeout=None):
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        self.calls.append((request.get_method(), request.full_url, body, dict(request.header_items())))
        if self.raises:
            raise self.raises
        url = request.full_url
        for (method, suffix), errors in self.fail_on.items():
            if request.get_method() == method and url.endswith(suffix) and errors:
                raise errors.pop(0)
        if url.endswith("/query"):
            return FakeResponse({"results": [{"id": p} for p in self.query_results]})
        if url.endswith("/v1/pages"):
            return FakeResponse({"id": "newpage", "url": self.page_url})
        return FakeResponse({})


def make_report(blocks_flags=None):
    return Report(
        day=datetime.date(2026, 11, 21),
        flags=blocks_flags if blocks_flags is not None else {("d2", "men"): [],
                                                              ("d2", "women"): []},
        warnings=[],
        final_counts={("d2", "men"): 5, ("d2", "women"): 4},
        polls_used="men: 11/17",
    )


class NotionClientTests(unittest.TestCase):
    def test_rerun_archives_old_page(self):
        op = FakeOpener(query_results=["old1"])
        NotionClient(TOKEN, "db1", opener=op).publish(make_report())
        seq = [(m, u.split("/v1")[1]) for m, u, _, _ in op.calls]
        self.assertEqual(seq, [
            ("POST", "/pages"),
            ("POST", "/databases/db1/query"),
            ("PATCH", "/pages/old1"),
        ])
        self.assertEqual(op.calls[1][2]["filter"],
                         {"property": "Date", "date": {"equals": "2026-11-21"}})
        self.assertEqual(op.calls[2][2], {"archived": True})

    def test_new_page_is_not_archived(self):
        op = FakeOpener(query_results=["old1", "newpage"])
        NotionClient(TOKEN, "db1", opener=op).publish(make_report())
        archived = [u for m, u, _, _ in op.calls if m == "PATCH"]
        self.assertEqual(archived, ["https://api.notion.com/v1/pages/old1"])

    def test_failed_create_leaves_old_page(self):
        op = FakeOpener(query_results=["old1"],
                        fail_on={("POST", "/v1/pages"): [http_error(400, "bad block")]})
        with self.assertRaises(FetchError):
            NotionClient(TOKEN, "db1", opener=op, sleep=lambda s: None).publish(make_report())
        self.assertEqual([m for m, _, _, _ in op.calls], ["POST"])
        self.assertFalse(any(u.endswith("/pages/old1") for _, u, _, _ in op.calls))

    def test_retries_once_on_429_and_5xx(self):
        for code in (429, 500, 503):
            sleeps = []
            op = FakeOpener(fail_on={("POST", "/v1/pages"): [http_error(code)]})
            url = NotionClient(TOKEN, "db1", opener=op, sleep=sleeps.append).publish(make_report())
            self.assertEqual(url, "https://notion.so/page")
            self.assertEqual(sleeps, [2.0], code)
            self.assertEqual([u.split("/v1")[1] for _, u, _, _ in op.calls][:2],
                             ["/pages", "/pages"])

    def test_gives_up_after_one_retry(self):
        sleeps = []
        op = FakeOpener(fail_on={("POST", "/v1/pages"): [http_error(502), http_error(502)]})
        with self.assertRaises(FetchError) as cm:
            NotionClient(TOKEN, "db1", opener=op, sleep=sleeps.append).publish(make_report())
        self.assertIn("502", str(cm.exception))
        self.assertNotIn(TOKEN, str(cm.exception))
        self.assertEqual(len(sleeps), 1)
        self.assertEqual(len(op.calls), 2)

    def test_no_retry_on_400(self):
        sleeps = []
        op = FakeOpener(fail_on={("POST", "/v1/pages"): [http_error(400)]})
        with self.assertRaises(FetchError):
            NotionClient(TOKEN, "db1", opener=op, sleep=sleeps.append).publish(make_report())
        self.assertEqual((sleeps, len(op.calls)), ([], 1))

    def test_first_run_creates(self):
        r = make_report()
        op = FakeOpener()
        url = NotionClient(TOKEN, "db1", opener=op).publish(r)
        self.assertEqual(len(op.calls), 2)
        body = op.calls[0][2]
        self.assertEqual(body["parent"], {"database_id": "db1"})
        props = body["properties"]
        self.assertEqual(props["Status"]["select"]["name"], r.status)
        self.assertEqual(props["Name"]["title"][0]["text"]["content"], "Upsets — Nov 21, 2026")
        self.assertEqual(props["Date"], {"date": {"start": "2026-11-21"}})
        self.assertEqual(props["Flags"], {"number": 0})
        self.assertEqual(props["Polls used"]["rich_text"][0]["text"]["content"], "men: 11/17")
        self.assertEqual(url, "https://notion.so/page")
        headers = {k.lower(): v for k, v in op.calls[0][3].items()}
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
        self.assertEqual(len(op.calls[0][2]["children"]), 100)
        appends = op.calls[1:3]
        self.assertEqual([c[0] for c in appends], ["PATCH", "PATCH"])
        self.assertTrue(all(c[1].endswith("/v1/blocks/newpage/children") for c in appends))
        self.assertEqual([len(c[2]["children"]) for c in appends], [100, 50])

    def test_real_two_division_page_is_chunked(self):
        def flag(division, gender, n):
            g = Game(str(n), gender, Team("a", "A", 70, True, "c"), Team("b", "B", 60, False, "c"),
                     "final", "FINAL", f"/game/{n}", division=division)
            return Flag(g, f"Game {n}", ["Upset"], division=division, story="Big story",
                        facts=["fact one", "fact two"])
        flags = {(d, g): [flag(d, g, i * 100 + j) for j in range(15)]
                 for i, (d, g) in enumerate([("d1", "men"), ("d1", "women"),
                                             ("d2", "men"), ("d2", "women")])}
        r = make_report(flags)
        blocks = to_notion_blocks(r)
        self.assertGreater(len(blocks), 100)
        op = FakeOpener()
        NotionClient(TOKEN, "db1", opener=op).publish(r)
        sent = op.calls[0][2]["children"]
        self.assertEqual(len(sent), 100)
        for c in op.calls[1:]:
            if c[0] == "PATCH" and c[1].endswith("/v1/blocks/newpage/children"):
                self.assertLessEqual(len(c[2]["children"]), 100)
                sent = sent + c[2]["children"]
        self.assertEqual(sent, blocks)
        self.assertEqual(op.calls[0][2]["properties"]["Flags"], {"number": 60})

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

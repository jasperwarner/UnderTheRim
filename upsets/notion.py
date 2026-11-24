from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from upsets.http import FetchError
from upsets.report import Report, to_notion_blocks

BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
CHUNK = 100
RETRY_DELAY = 2.0


class NotionError(FetchError):
    """A Notion API call failed. Never carries the token."""


def _rich(content: str) -> list[dict[str, Any]]:
    return [{"text": {"content": content}}]


def _retryable(code: int) -> bool:
    return code == 429 or 500 <= code <= 599


class NotionClient:
    def __init__(self, token: str, database_id: str, opener=urllib.request.urlopen,
                 retry_delay: float = RETRY_DELAY, sleep=time.sleep):
        self._token = token
        self._database_id = database_id
        self._opener = opener
        self._retry_delay = retry_delay
        self._sleep = sleep

    def _call(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """One request, retried once after a short pause on 429 or 5xx."""
        for attempt in (1, 2):
            try:
                return self._call_once(method, path, body)
            except urllib.error.HTTPError as e:
                if attempt == 1 and _retryable(e.code):
                    self._sleep(self._retry_delay)
                    continue
                raise NotionError(f"Notion {e.code}: {_error_message(e)}")
        raise AssertionError("unreachable")

    def _call_once(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            BASE_URL + path,
            data=json.dumps(body).encode("utf-8"),
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise NotionError(f"Notion request failed: {type(e).__name__}")

    def publish(self, r: Report) -> str:
        """Create the day's page first, then archive any older pages for that date.

        If creating fails, the old page is left in place untouched.
        """
        day = r.day.isoformat()
        blocks = to_notion_blocks(r)
        title = f"D2 Upsets — {r.day.strftime('%b')} {r.day.day}, {r.day.year}"
        page = self._call("POST", "/pages", {
            "parent": {"database_id": self._database_id},
            "properties": {
                "Name": {"title": _rich(title)},
                "Date": {"date": {"start": day}},
                "Flags": {"number": r.flag_count},
                "Status": {"select": {"name": r.status}},
                "Polls used": {"rich_text": _rich(r.polls_used)},
            },
            "children": blocks[:CHUNK],
        })
        for i in range(CHUNK, len(blocks), CHUNK):
            self._call("PATCH", f"/blocks/{page['id']}/children",
                       {"children": blocks[i:i + CHUNK]})

        found = self._call("POST", f"/databases/{self._database_id}/query", {
            "filter": {"property": "Date", "date": {"equals": day}},
        })
        for old in found.get("results", []):
            if old.get("id") != page["id"]:
                self._call("PATCH", f"/pages/{old['id']}", {"archived": True})
        return page["url"]


def _error_message(e: urllib.error.HTTPError) -> str:
    try:
        msg: Optional[str] = json.loads(e.read().decode("utf-8")).get("message")
    except Exception:
        msg = None
    return msg or str(e.reason or "error")

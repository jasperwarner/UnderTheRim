from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = "d2-upsets/1.0"
MIN_GAP = 0.5

_last_request = 0.0


class FetchError(Exception):
    pass


def _throttle() -> None:
    global _last_request
    wait = MIN_GAP - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def get_text(url: str, timeout: float = 20, retries: int = 2, opener=None) -> str:
    open_url = opener or urllib.request.urlopen
    last: Exception | None = None
    for attempt in range(retries + 1):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with open_url(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            last = e
            if attempt < retries:
                time.sleep(1.0 * (attempt + 1))
    raise FetchError(f"could not fetch {url}: {last}")


def get_json(url: str) -> Any:
    text = get_text(url)
    try:
        return json.loads(text)
    except ValueError as e:
        raise FetchError(f"bad JSON from {url}: {e}")

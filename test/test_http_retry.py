"""Limiter: Retry-After, reset, backoff. Bez sieci."""
import json
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import http_retry  # noqa: E402


class Resp:
    def __init__(self, payload, headers=None):
        self.headers = headers or {}
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class HttpRetryTests(unittest.TestCase):
    def setUp(self):
        http_retry.reset()
        self.sleeps = []
        self._sleep = http_retry.time.sleep
        self._urlopen = http_retry.urllib.request.urlopen
        http_retry.time.sleep = self._sleep_record

    def tearDown(self):
        http_retry.time.sleep = self._sleep
        http_retry.urllib.request.urlopen = self._urlopen
        http_retry.reset()

    def _patch_urlopen(self, fn):
        http_retry.urllib.request.urlopen = fn

    def _sleep_record(self, seconds):
        self.sleeps.append(seconds)

    def test_retry_after_seconds_and_http_date(self):
        from datetime import datetime, timezone

        self.assertEqual(http_retry.parse_retry_after("5"), 5.0)
        self.assertIsNone(http_retry.parse_retry_after("-1"))
        self.assertIsNone(http_retry.parse_retry_after("not-a-date"))
        target = datetime(2026, 10, 18, 20, 0, 10, tzinfo=timezone.utc).timestamp()
        self.assertAlmostEqual(
            http_retry.parse_retry_after("Sun, 18 Oct 2026 20:00:10 GMT", now=target - 10),
            10.0,
            delta=0.01,
        )

    def test_header_wait_prefers_retry_after_over_reset(self):
        headers = {
            "Retry-After": "5",
            "X-Ratelimit-Limit": "1",
            "X-Ratelimit-Remaining": "0",
            "X-Ratelimit-Reset": "1792353800",
        }
        self.assertEqual(http_retry.header_wait(headers, now=1792350000), 5.0)

    def test_header_wait_remaining_allows_immediate(self):
        self.assertEqual(http_retry.header_wait({"X-Ratelimit-Remaining": "2"}), 0.0)

    def test_header_wait_reset_unix_when_retry_after_missing(self):
        self.assertAlmostEqual(
            http_retry.header_wait({"X-Ratelimit-Reset": "1792353750"}, now=1792353745),
            5.0,
            delta=0.01,
        )

    def test_header_wait_absent(self):
        self.assertIsNone(http_retry.header_wait({}))
        self.assertIsNone(http_retry.header_wait(None))

    def test_delay_caps_and_backoff(self):
        delay, source = http_retry.delay_for(
            {"Retry-After": "10000"}, default=5, attempt=0, limited=True
        )
        self.assertEqual(delay, 60.0)
        self.assertEqual(source, "Retry-After")
        delay, source = http_retry.delay_for(None, default=5, attempt=2, limited=True)
        self.assertEqual((delay, source), (16.0, "backoff"))
        delay, source = http_retry.delay_for({"Retry-After": "0"}, default=5, attempt=1, limited=True)
        self.assertEqual((delay, source), (1.0, "Retry-After"))

    def test_success_paces_next_call_from_retry_after(self):
        headers = {"Retry-After": "5", "X-Ratelimit-Remaining": "0", "X-Ratelimit-Limit": "1"}
        responses = [Resp({"n": 1}, headers), Resp({"n": 2}, headers)]

        def urlopen(req, timeout=60):
            return responses.pop(0)

        self._patch_urlopen(urlopen)
        self.assertEqual(http_retry.get_json("https://api.tibiamarket.top/item_history?item_id=1"), {"n": 1})
        self.assertEqual(self.sleeps, [])
        self.assertEqual(http_retry.get_json("https://api.tibiamarket.top/item_history?item_id=2"), {"n": 2})
        self.assertEqual(len(self.sleeps), 1)
        self.assertAlmostEqual(self.sleeps[0], 5.25, delta=0.15)

    def test_429_retries_using_retry_after_then_returns_body(self):
        headers = {"Retry-After": "5", "X-Ratelimit-Remaining": "0"}
        calls = {"n": 0}

        def urlopen(req, timeout=60):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.HTTPError(
                    req.full_url, 429, "Too Many Requests", headers, None
                )
            return Resp({"ok": True}, headers)

        self._patch_urlopen(urlopen)
        body = http_retry.get_json("https://api.tibiamarket.top/market_board?item_id=284")
        self.assertEqual(body, {"ok": True})
        self.assertEqual(calls["n"], 2)
        self.assertEqual(len(self.sleeps), 1)
        self.assertAlmostEqual(self.sleeps[0], 5.25, delta=0.15)
        self.assertEqual(http_retry._stats["limited"], 1)
        self.assertEqual(http_retry._stats["ok"], 1)

    def test_429_without_headers_uses_backoff(self):
        calls = {"n": 0}

        def urlopen(req, timeout=60):
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)
            return Resp({"ok": 1}, {"X-Ratelimit-Remaining": "1"})

        self._patch_urlopen(urlopen)
        body = http_retry.get_json("https://api.tibiamarket.top/item_history?item_id=9", retries=4)
        self.assertEqual(body, {"ok": 1})
        self.assertAlmostEqual(self.sleeps[0], 4.0, delta=0.15)
        self.assertAlmostEqual(self.sleeps[1], 8.0, delta=0.15)

    def test_exhausted_429_raises(self):
        def urlopen(req, timeout=60):
            raise urllib.error.HTTPError(
                req.full_url, 429, "Too Many Requests", {"Retry-After": "1"}, None
            )

        self._patch_urlopen(urlopen)
        with self.assertRaises(urllib.error.HTTPError):
            http_retry.get_json("https://api.tibiamarket.top/item_history?item_id=3", retries=2)
        self.assertEqual(len(self.sleeps), 1)
        self.assertAlmostEqual(self.sleeps[0], 1.25, delta=0.15)

    def test_http_500_is_not_retried(self):
        calls = {"n": 0}

        def urlopen(req, timeout=60):
            calls["n"] += 1
            raise urllib.error.HTTPError(req.full_url, 500, "nope", {}, None)

        self._patch_urlopen(urlopen)
        with self.assertRaises(urllib.error.HTTPError):
            http_retry.get_json("https://api.tibiamarket.top/world_data")
        self.assertEqual(calls["n"], 1)
        self.assertEqual(self.sleeps, [])

    def test_connection_error_is_retried(self):
        calls = {"n": 0}

        def urlopen(req, timeout=60):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.URLError("reset")
            return Resp({"ok": 1}, {"Retry-After": "5", "X-Ratelimit-Remaining": "0"})

        self._patch_urlopen(urlopen)
        body = http_retry.get_json("https://api.tibiamarket.top/item_metadata")
        self.assertEqual(body, {"ok": 1})
        self.assertAlmostEqual(self.sleeps[0], 2.0, delta=0.15)


if __name__ == "__main__":
    unittest.main()

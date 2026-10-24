"""GET JSON z limitem tempa dla api.tibiamarket.top.

Sondowanie 2026-10-18: /item_history, /market_values, /market_board i /item_metadata
zwracaja na 200 i na 429:
  X-Ratelimit-Limit: 1
  X-Ratelimit-Remaining: 0
  Retry-After: 5
Stary odstep 0.6s/2s wchodzil w okno i prawie kazdy request konczyl sie 429.
Tu czekamy tyle, ile mowi serwer (Retry-After albo X-Ratelimit-Reset), z malym
zapasem, a gdy naglowka nie ma — staly odstep albo wykladniczy backoff.
"""
from __future__ import annotations

import atexit
import datetime as dt
import email.utils
import json
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_INTERVAL = 5.0
CUSHION = 0.25
MAX_WAIT = 60.0
MAX_ATTEMPTS = 6

_not_before = 0.0
_announced = False
_stats = {"ok": 0, "limited": 0, "last_wait": 0.0}


def reset() -> None:
    """Stan limitera (testy)."""
    global _not_before, _announced
    _not_before = 0.0
    _announced = False
    _stats["ok"] = 0
    _stats["limited"] = 0
    _stats["last_wait"] = 0.0


def _summary() -> None:
    if _stats["ok"] or _stats["limited"]:
        print(
            f"http summary: ok={_stats['ok']} limited={_stats['limited']} "
            f"last_wait={_stats['last_wait']:.2f}s",
            flush=True,
        )


atexit.register(_summary)


def _header(headers, name: str) -> str | None:
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    value = getter(name)
    if value is None:
        value = getter(name.lower())
    if value is None:
        return None
    return str(value).strip()


def parse_retry_after(value: str | None, now: float | None = None) -> float | None:
    """Sekundy z Retry-After (delta albo data HTTP). None gdy brak / nieparsowalne."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        seconds = None
    else:
        if seconds < 0:
            return None
        return seconds
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    current = time.time() if now is None else now
    return parsed.timestamp() - current


def header_wait(headers, now: float | None = None) -> float | None:
    """Wymagana przerwa po tej odpowiedzi.

    None = serwer nie podal limitu.
    0 = mozna isc od razu (zostaly tokeny albo Retry-After 0).
    """
    retry_after = _header(headers, "Retry-After")
    remaining = _header(headers, "X-Ratelimit-Remaining")
    reset = _header(headers, "X-Ratelimit-Reset")
    if retry_after is None and remaining is None and reset is None:
        return None
    if remaining is not None:
        try:
            if float(remaining) > 0:
                return 0.0
        except ValueError:
            pass
    current = time.time() if now is None else now
    # Retry-After jest wlasciwym kontraktem. Reset bywa tym samym oknem, ale
    # przy rozjechanym zegarze potrafi wydluzyc kazdy request do capu.
    parsed = parse_retry_after(retry_after, now=current)
    if parsed is not None:
        return min(MAX_WAIT, max(0.0, parsed))
    if reset is not None:
        try:
            reset_val = float(reset)
        except ValueError:
            reset_val = None
        if reset_val is not None:
            if reset_val > 1_000_000_000:
                return min(MAX_WAIT, max(0.0, reset_val - current))
            return min(MAX_WAIT, max(0.0, reset_val))
    return 0.0


def delay_for(headers, *, default: float | None, attempt: int, limited: bool) -> tuple[float, str]:
    """Ile sekundy odczekac przed nastepnym requestem i skad ta liczba."""
    advised = header_wait(headers)
    if advised is None:
        if limited:
            return min(MAX_WAIT, 4.0 * (2 ** attempt)), "backoff"
        return float(DEFAULT_INTERVAL if default is None else default), "default"
    if limited and advised <= 0:
        # Retry-After: 0 — nie krecimy sie w miejscu, ale tez nie czekamy 4s.
        return min(MAX_WAIT, 0.5 * (attempt + 1)), "Retry-After"
    if advised <= 0:
        return 0.0, "Retry-After"
    return min(MAX_WAIT, advised + CUSHION), "Retry-After"


def _where(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    item = urllib.parse.parse_qs(parsed.query).get("item_id", [None])[0]
    if item:
        return f"{parsed.path} item_id={item}"
    return parsed.path or url


def _schedule(delay: float, source: str, url: str) -> None:
    global _not_before, _announced
    delay = max(0.0, delay)
    _stats["last_wait"] = delay
    _not_before = time.monotonic() + delay
    if not _announced and delay > 0 and source == "Retry-After":
        _announced = True
        print(f"rate limit: waiting {delay:.2f}s between requests ({source}) {_where(url)}", flush=True)


def _wait_turn() -> None:
    delay = _not_before - time.monotonic()
    if delay > 0:
        time.sleep(delay)


def get_json(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 60,
    retries: int = MAX_ATTEMPTS,
    default_interval: float = DEFAULT_INTERVAL,
):
    """GET -> JSON. 429/503: Retry-After, potem kolejna proba. Inne HTTP ida wyzej."""
    if retries < 1:
        raise ValueError("retries must be >= 1")
    hdrs = headers or {"User-Agent": "nevia-pipeline/0.1"}
    last_error: Exception | None = None
    for attempt in range(retries):
        _wait_turn()
        req = urllib.request.Request(url, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                delay, source = delay_for(
                    resp.headers, default=default_interval, attempt=attempt, limited=False
                )
                _schedule(delay, source, url)
                _stats["ok"] += 1
                return json.loads(body.decode())
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code in (429, 503) and attempt < retries - 1:
                delay, source = delay_for(e.headers, default=None, attempt=attempt, limited=True)
                _stats["limited"] += 1
                print(
                    f"429 wait {delay:.1f}s ({source}, attempt {attempt + 1}/{retries}): {_where(url)}",
                    flush=True,
                )
                _schedule(delay, source, url)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_error = e
            if attempt < retries - 1:
                delay = min(MAX_WAIT, 2.0 * (2 ** attempt))
                print(
                    f"retry {type(e).__name__} wait {delay:.1f}s "
                    f"(attempt {attempt + 1}/{retries}): {_where(url)}",
                    flush=True,
                )
                _schedule(delay, "backoff", url)
                continue
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"get_json failed without an exception: {url}")

"""Laczenie plikow danych, gdy daily i weekly zjadly ten sam snapshot.

Oba joby pisza data/raw/<dzis>/*.json i potem build_gold nadpisuje data/gold
oraz docs/data. Zwykly rebase rozjezdza jednolinijkowy JSON. Tu scalamy
zawartosc: historia i orderbook to unia kluczy, wiersze marketu po id,
config.yaml zostaje z main (ludzkie edycje).
"""
from __future__ import annotations

import csv
import io
import json
import pathlib

DERIVED_PREFIXES = ("data/gold/", "docs/data/")


def is_derived(path: str) -> bool:
    norm = path.replace("\\", "/")
    return norm.startswith(DERIVED_PREFIXES)


def merge_file(path: str, base: bytes | None, ours: bytes | None, main: bytes | None) -> bytes | None:
    """Wynik merge albo None = skasowac plik.

    ours = commit joba, ktory teraz publikuje. main = aktualny origin/main.
    """
    if ours is None and main is None:
        return None
    if ours is None:
        # Job skasowal plik, main go zmienil — zostawiamy dane z main.
        return main
    if main is None:
        return ours
    if ours == main:
        return main
    norm = path.replace("\\", "/")
    if norm == "config.yaml" or norm.endswith((".yaml", ".yml")):
        return main
    if norm.endswith(".json"):
        return _merge_json_bytes(norm, ours, main)
    if norm.endswith(".csv"):
        return _merge_csv_bytes(ours, main)
    if norm.endswith(".txt"):
        return _merge_txt_bytes(ours, main)
    if norm.startswith("data/raw/"):
        return ours
    return main


def _merge_json_bytes(path: str, ours: bytes, main: bytes) -> bytes:
    try:
        ours_obj = json.loads(ours.decode("utf-8"))
        main_obj = json.loads(main.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ours if path.startswith("data/") else main
    merged = merge_parsed(path, ours_obj, main_obj)
    if merged == main_obj:
        return main
    if merged == ours_obj:
        return ours
    sample = ours if path.startswith("data/raw/") else main
    return _encode_json(merged, sample)


def merge_parsed(path: str, ours, main):
    name = pathlib.PurePosixPath(path.replace("\\", "/")).name
    if name == "market_history_top.json":
        return _merge_history(ours, main)
    if name == "orderbook_nevia.json":
        return _merge_orderbook(ours, main)
    if name == "market_values_nevia.json":
        return _merge_id_rows(ours, main, use_time=True)
    if name == "market_metadata_all.json":
        return _merge_id_rows(ours, main, use_time=False)
    if name == "market_world_data.json":
        return _merge_keyed_rows(ours, main, "name", "last_update")
    if name == "events.json":
        return _merge_events(ours, main)
    if name == "creatures.json":
        return _merge_creatures(ours, main)
    if name == "creatures_failed.json":
        return _merge_date_map(ours, main)
    if name.startswith("tibiadata_"):
        return ours
    return _merge_generic(ours, main)


def _merge_history(ours, main):
    if not isinstance(ours, dict) or not isinstance(main, dict):
        return ours if isinstance(ours, dict) else main
    out = dict(main)
    for key, series in ours.items():
        if key not in out:
            out[key] = series
        else:
            out[key] = _merge_snaps(series, out[key])
    return out


def _snap_key(snap, index: int):
    if isinstance(snap, dict) and snap.get("time") is not None:
        stamped = _as_float(snap.get("time"))
        if stamped is not None:
            return ("t", stamped)
        return ("t", str(snap.get("time")))
    try:
        blob = json.dumps(snap, sort_keys=True, default=str)
    except TypeError:
        blob = str(index)
    return ("i", index, blob)


def _merge_snaps(ours, main):
    if not isinstance(ours, list):
        return ours if ours else main
    if not isinstance(main, list):
        return ours
    merged: dict = {}
    for source in (main, ours):
        for index, snap in enumerate(source):
            key = _snap_key(snap, index)
            merged[key] = snap  # ours nadpisuje ten sam timestamp

    def sort_key(key):
        if key[0] == "t":
            try:
                return (0, float(key[1]))
            except (TypeError, ValueError):
                return (1, 0.0)
        index = key[1] if len(key) > 1 and isinstance(key[1], int) else 0
        return (2, index)

    return [merged[key] for key in sorted(merged, key=sort_key)]


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _book_time(book):
    if not isinstance(book, dict):
        return None
    stamped = _as_float(book.get("update_time"))
    if stamped is not None:
        return stamped
    best = None
    for side in ("sellers", "buyers"):
        for row in book.get(side) or []:
            if isinstance(row, dict):
                row_time = _as_float(row.get("time"))
                if row_time is not None:
                    best = row_time if best is None else max(best, row_time)
    return best


def _offer_count(book) -> int:
    if not isinstance(book, dict):
        return 0
    return len(book.get("sellers") or []) + len(book.get("buyers") or [])


def _prefer_book(ours, main):
    ours_time, main_time = _book_time(ours), _book_time(main)
    if ours_time is not None and main_time is not None and ours_time != main_time:
        return ours if ours_time > main_time else main
    if ours_time is not None and main_time is None:
        return ours
    if main_time is not None and ours_time is None:
        return main
    if _offer_count(ours) != _offer_count(main):
        return ours if _offer_count(ours) > _offer_count(main) else main
    return ours


def _merge_orderbook(ours, main):
    if not isinstance(ours, dict) or not isinstance(main, dict):
        return ours if isinstance(ours, dict) else main
    out = dict(main)
    for key, book in ours.items():
        if key not in out:
            out[key] = book
        else:
            out[key] = _prefer_book(book, out[key])
    return out


def _richness(row) -> int:
    if not isinstance(row, dict):
        return 0
    return sum(1 for value in row.values() if value not in (None, "", [], {}))


def _prefer_timed_row(existing, new, use_time: bool):
    if not isinstance(existing, dict):
        return new
    if not isinstance(new, dict):
        return existing
    if use_time:
        existing_time = _as_float(existing.get("time"))
        new_time = _as_float(new.get("time"))
        if existing_time is not None and new_time is not None and existing_time != new_time:
            return new if new_time > existing_time else existing
    if _richness(new) != _richness(existing):
        return new if _richness(new) > _richness(existing) else existing
    return new


def _merge_id_rows(ours, main, use_time: bool):
    if not isinstance(ours, list) or not isinstance(main, list):
        return ours if isinstance(ours, list) else main
    return _merge_rows(ours, main, lambda row: row.get("id") if isinstance(row, dict) else None,
                       lambda existing, new: _prefer_timed_row(existing, new, use_time))


def _merge_keyed_rows(ours, main, key: str, time_field: str):
    if not isinstance(ours, list) or not isinstance(main, list):
        return ours if isinstance(ours, list) else main

    def prefer(existing, new):
        if not isinstance(existing, dict) or not isinstance(new, dict):
            return new if isinstance(new, dict) else existing
        existing_stamp = str(existing.get(time_field) or "")
        new_stamp = str(new.get(time_field) or "")
        if existing_stamp != new_stamp:
            return new if new_stamp > existing_stamp else existing
        return new

    return _merge_rows(ours, main, lambda row: row.get(key) if isinstance(row, dict) else None, prefer)


def _merge_rows(ours, main, key_fn, prefer):
    out = []
    index: dict = {}
    for row in main:
        key = key_fn(row)
        if key is None:
            out.append(row)
            continue
        if key not in index:
            index[key] = len(out)
            out.append(row)
        else:
            out[index[key]] = prefer(out[index[key]], row)
    for row in ours:
        key = key_fn(row)
        if key is None:
            out.append(row)
            continue
        if key not in index:
            index[key] = len(out)
            out.append(row)
        else:
            out[index[key]] = prefer(out[index[key]], row)
    return out


def _merge_events(ours, main):
    if not isinstance(ours, list) or not isinstance(main, list):
        return ours if isinstance(ours, list) else main
    seen = set()
    out = []
    for row in list(main) + list(ours):
        if isinstance(row, dict):
            key = (str(row.get("date")), str(row.get("name")))
        else:
            key = ("raw", json.dumps(row, sort_keys=True, default=str))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    out.sort(key=lambda row: (
        str(row.get("date")) if isinstance(row, dict) else "",
        str(row.get("name")) if isinstance(row, dict) else "",
    ))
    return out


def _merge_creatures(ours, main):
    if not isinstance(ours, dict) or not isinstance(main, dict):
        return ours if isinstance(ours, dict) else main
    out = dict(main)
    for key, value in ours.items():
        current = out.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merged = dict(current)
            for field, field_value in value.items():
                if field_value not in (None, "", [], {}):
                    merged[field] = field_value
                elif field not in merged:
                    merged[field] = field_value
            out[key] = merged
        elif value not in (None, "", [], {}):
            out[key] = value
        elif key not in out:
            out[key] = value
    return out


def _merge_date_map(ours, main):
    if not isinstance(ours, dict) or not isinstance(main, dict):
        return ours if isinstance(ours, dict) else main
    out = dict(main)
    for key, value in ours.items():
        if key not in out or str(value) > str(out[key]):
            out[key] = value
    return out


def _merge_generic(ours, main):
    if isinstance(ours, dict) and isinstance(main, dict):
        out = dict(main)
        for key, value in ours.items():
            if key not in out:
                out[key] = value
            else:
                out[key] = _merge_generic(value, out[key])
        return out
    if isinstance(ours, list) and isinstance(main, list):
        if ours and isinstance(ours[0], dict) and "id" in ours[0]:
            return _merge_id_rows(ours, main, use_time="time" in ours[0])
        seen = set()
        out = []
        for value in list(main) + list(ours):
            try:
                marker = json.dumps(value, sort_keys=True, default=str)
            except TypeError:
                marker = str(value)
            if marker in seen:
                continue
            seen.add(marker)
            out.append(value)
        return out
    if ours in (None, "", [], {}):
        return main
    return ours


def _encode_json(obj, sample: bytes) -> bytes:
    text = sample.decode("utf-8", "replace") if sample else ""
    indent = None
    newline = text.find("\n")
    if 0 <= newline < 80:
        spaces = 0
        for char in text[newline + 1:]:
            if char == " ":
                spaces += 1
            else:
                break
        if spaces:
            indent = spaces
    non_ascii = any(byte > 127 for byte in sample[:8000]) if sample else False
    encoded = json.dumps(obj, indent=indent, ensure_ascii=not non_ascii)
    if text.endswith("\n"):
        encoded += "\n"
    return encoded.encode("utf-8")


def _parse_csv(blob: bytes):
    text = blob.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = list(reader.fieldnames or [])
    rows = list(reader)
    return header, rows


def _row_key(row: dict, header: list[str]):
    if "id" in header and row.get("id"):
        return ("id", row.get("id"))
    if "hunt_id" in header and "slot" in header:
        return ("member", row.get("hunt_id"), row.get("slot"))
    if "hunt_id" in header and "creature" in header:
        return ("kill", row.get("hunt_id"), row.get("creature"))
    return ("row", tuple(row.get(column, "") for column in header))


def _filled(row: dict) -> int:
    return sum(1 for value in row.values() if value not in (None, ""))


def _merge_csv_bytes(ours: bytes, main: bytes) -> bytes:
    ours_header, ours_rows = _parse_csv(ours)
    main_header, main_rows = _parse_csv(main)
    header = list(main_header or ours_header)
    for column in ours_header:
        if column not in header:
            header.append(column)
    if not header:
        return main or ours
    out_rows: list[dict] = []
    index: dict = {}
    for row in list(main_rows) + list(ours_rows):
        key = _row_key(row, header)
        if key not in index:
            index[key] = len(out_rows)
            out_rows.append(row)
            continue
        current = out_rows[index[key]]
        # ours idzie drugi: przy remisie zostaje swiezszy wiersz joba.
        if _filled(row) >= _filled(current):
            out_rows[index[key]] = row
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=header, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in out_rows:
        writer.writerow({column: row.get(column, "") for column in header})
    text = buf.getvalue()
    sample = (main or ours).decode("utf-8", "replace")
    if sample.endswith("\n") and not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _merge_txt_bytes(ours: bytes, main: bytes) -> bytes:
    seen = set()
    lines = []
    for blob in (main, ours):
        for line in blob.decode("utf-8", "replace").splitlines():
            if line not in seen:
                seen.add(line)
                lines.append(line)
    text = "\n".join(lines)
    if text:
        text += "\n"
    return text.encode("utf-8")

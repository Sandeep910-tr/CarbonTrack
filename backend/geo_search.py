"""
Local place-name autocomplete for the pickup/destination fields on the
driver's New Trip form.

This is deliberately NOT a call to Google Places Autocomplete - the app
already avoids that (see PlaceAutocomplete.jsx) to keep the typing
experience free of per-keystroke billed API calls. Instead we ship a
census-style India state/district/village directory
(backend/data/village_places.csv, ~605k rows) and search it in-process.

Index shape: a single list of tuples, sorted by lowercase name, so a
prefix search is a binary search (bisect) instead of a linear scan over
600k+ rows on every keystroke:

    (name_lower, name, level, district, state)

`level` is one of "state" / "district" / "village". The list is built
once (on first request) and cached for the life of the process - the
dataset is static, so there's nothing to invalidate.
"""
import os
import csv
import bisect
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLACES_CSV_PATH = os.path.join(BASE_DIR, "data", "village_places.csv")

_lock = threading.Lock()
_index = None  # None until first load; then a sorted list of tuples


def _build_index():
    rows = []
    if os.path.exists(PLACES_CSV_PATH):
        with open(PLACES_CSV_PATH, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("name") or "").strip()
                if not name:
                    continue
                rows.append((
                    name.lower(),
                    name,
                    row.get("level") or "village",
                    (row.get("district") or "").strip(),
                    (row.get("state") or "").strip(),
                ))
    rows.sort(key=lambda r: r[0])
    return rows


def _get_index():
    global _index
    if _index is None:
        with _lock:
            if _index is None:  # re-check: another thread may have built it first
                _index = _build_index()
    return _index


# Villages far outnumber states/districts, so a very short, very common
# prefix ("ka", "ma"...) can match tens of thousands of rows before we ever
# get to rank them. Cap how many candidates we scan past the first match so
# one keystroke can't trigger an unbounded walk through the list.
_SCAN_CAP = 3000

_LEVEL_RANK = {"state": 0, "district": 1, "village": 2}


def _display(name, level, district, state):
    if level == "state":
        return name
    if level == "district":
        return f"{name}, {state}"
    return f"{name}, {district}, {state}"


def search_places(query, limit=8):
    """Prefix-search the place index. Returns a list of dicts:
    {name, level, district, state, display}, ranked so shorter / more
    important (state > district > village) matches surface first."""
    query = (query or "").strip().lower()
    if len(query) < 2:
        return []

    index = _get_index()
    if not index:
        return []

    start = bisect.bisect_left(index, (query,))
    matches = []
    seen_display = set()
    scanned = 0
    i = start
    while i < len(index) and scanned < _SCAN_CAP:
        name_lower, name, level, district, state = index[i]
        if not name_lower.startswith(query):
            break
        display = _display(name, level, district, state)
        if display not in seen_display:
            seen_display.add(display)
            matches.append({
                "name": name,
                "level": level,
                "district": district,
                "state": state,
                "display": display,
                "exact": name_lower == query,
            })
        i += 1
        scanned += 1

    matches.sort(key=lambda m: (not m["exact"], _LEVEL_RANK.get(m["level"], 9), len(m["name"]), m["name"]))
    return matches[:limit]

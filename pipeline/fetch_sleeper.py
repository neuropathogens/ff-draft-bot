"""Pull live player pool, ADP, injuries, depth-chart order from Sleeper public API.

Sleeper endpoints used (no auth required):
  GET https://api.sleeper.app/v1/players/nfl        -> full player master (big, cache it)
  GET https://api.sleeper.app/v1/players/nfl/trending/add?limit=200  -> hot adds

ADP is NOT in the players endpoint. We derive draft value from Sleeper's
per-player `search_rank` (their overall ranking) plus the trending signal, and
you can overlay real ADP by dropping a CSV in pipeline/adp.csv (columns:
full_name,position,team,adp). If present it overrides search_rank ordering.
"""
from __future__ import annotations
import csv
import json
import os
import time
import requests

PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
TRENDING_URL = "https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours=168&limit=300"
CACHE = os.path.join(os.path.dirname(__file__), ".cache_players.json")
ADP_CSV = os.path.join(os.path.dirname(__file__), "adp.csv")

SKILL_POS = {"QB", "RB", "WR", "TE", "K", "DEF"}


def _get(url: str) -> dict | list:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()


def load_players(max_age_hours: float = 12.0) -> dict:
    """Return Sleeper player master, cached to disk to avoid re-downloading ~5MB."""
    if os.path.exists(CACHE):
        age_h = (time.time() - os.path.getmtime(CACHE)) / 3600.0
        if age_h < max_age_hours:
            with open(CACHE) as f:
                return json.load(f)
    data = _get(PLAYERS_URL)
    with open(CACHE, "w") as f:
        json.dump(data, f)
    return data


def load_trending() -> dict[str, int]:
    """player_id -> add count over last week. Signal for rising opportunity."""
    try:
        rows = _get(TRENDING_URL)
    except Exception:
        return {}
    return {r["player_id"]: r.get("count", 0) for r in rows}


def load_adp_overrides() -> dict[tuple[str, str], float]:
    """Optional real ADP from pipeline/adp.csv keyed by (lower full_name, position)."""
    if not os.path.exists(ADP_CSV):
        return {}
    out: dict[tuple[str, str], float] = {}
    with open(ADP_CSV, newline="") as f:
        for row in csv.DictReader(f):
            try:
                key = (row["full_name"].strip().lower(), row["position"].strip().upper())
                out[key] = float(row["adp"])
            except (KeyError, ValueError):
                continue
    return out


def normalized_pool() -> list[dict]:
    """Flatten Sleeper master into draftable skill-position rows with the raw
    fields our scoring layer needs: depth-chart order, injury status, age, team."""
    players = load_players()
    trending = load_trending()
    adp = load_adp_overrides()
    out: list[dict] = []
    for pid, p in players.items():
        pos = p.get("position")
        if pos not in SKILL_POS:
            continue
        if p.get("active") is False and pos not in {"DEF"}:
            continue
        name = p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip()
        if not name:
            continue
        row = {
            "player_id": pid,
            "name": name,
            "position": pos,
            "team": p.get("team"),
            "age": p.get("age"),
            "years_exp": p.get("years_exp"),
            "search_rank": p.get("search_rank") or 99999,
            "depth_chart_order": p.get("depth_chart_order"),
            "depth_chart_position": p.get("depth_chart_position"),
            "injury_status": p.get("injury_status"),
            "trending_adds": trending.get(pid, 0),
            "adp": adp.get((name.lower(), pos)),
        }
        out.append(row)
    return out


if __name__ == "__main__":
    pool = normalized_pool()
    print(f"{len(pool)} draftable players")
    for r in sorted(pool, key=lambda x: x["search_rank"])[:15]:
        print(r["search_rank"], r["name"], r["position"], r["team"],
              "depth", r["depth_chart_order"], "inj", r["injury_status"])

"""Value model. Turns raw Sleeper + nflverse signals into a single draft value.

Pipeline of layers (all documented inline):

  1. base_points   projected PPR points. Uses real ADP/search_rank to place a
                   player on a positional points curve calibrated to typical PPR
                   finishes, then adjusts by usage. This is a *model*, not a
                   scrape of someone's projection, so it stays transparent.
  2. opportunity   target/rush/air-yards share + depth-chart order. Volume is
                   the #1 predictor of fantasy points, so this moves value most.
  3. efficiency    YPRR proxy + YPC, lightly weighted (efficiency is noisier /
                   less sticky than volume).
  4. situation     coaching.json team multiplier + pass/run lean by position.
  5. availability  P(plays) from injury status, age cliff, depth competition.
                   Multiplies expected value -> a stud who misses games is worth
                   less than his per-game rate.
  6. VOR           value over replacement at position = the draftable number.

Everything is bounded so one noisy input can't blow up a ranking.
"""
from __future__ import annotations
import json
import math
import os

COACHING = os.path.join(os.path.dirname(__file__), "coaching.json")

# Standard PPR roster: QB, 2RB, 2WR, TE, FLEX, K, DEF. 12-team assumed for
# replacement level. Starters drafted per position across the league:
STARTERS_12 = {"QB": 12, "RB": 30, "WR": 36, "TE": 12, "K": 12, "DEF": 12}

# Rough top-finish PPR point anchors (season totals) to shape the value curve.
# rank 1 at a position ~ HIGH, replacement ~ LOW. Model interpolates between.
POS_CURVE = {
    "QB":  (400, 210),  # (elite, replacement-ish)
    "RB":  (330, 90),
    "WR":  (330, 95),
    "TE":  (230, 70),
    "K":   (150, 110),
    "DEF": (170, 100),
}


def _load_coaching() -> dict:
    with open(COACHING) as f:
        return json.load(f)


def _pos_rank_points(pos: str, pos_rank: int) -> float:
    """Interpolate a season point projection from positional rank using an
    exponential-ish decay between elite and replacement anchors."""
    hi, lo = POS_CURVE.get(pos, (200, 80))
    starters = STARTERS_12.get(pos, 24)
    # decay so that ~replacement rank lands near lo, elite near hi
    x = min(max(pos_rank, 1), starters * 3)
    k = 3.0 / (starters * 3)  # decay rate
    frac = math.exp(-k * (x - 1))
    return lo + (hi - lo) * frac


def _team_adj(coaching: dict, team: str | None, pos: str) -> float:
    t = coaching["default"].copy()
    if team and team in coaching.get("teams", {}):
        t.update(coaching["teams"][team])
    mult = t.get("off_mult", 1.0)
    if pos in ("WR", "TE"):
        mult *= t.get("pass_lean", 1.0)
    elif pos == "RB":
        # RB benefits from both run lean and (in PPR) pass lean, weighted
        mult *= 0.7 * t.get("run_lean", 1.0) + 0.3 * t.get("pass_lean", 1.0)
    elif pos == "QB":
        mult *= 0.6 * t.get("pass_lean", 1.0) + 0.4 * t.get("run_lean", 1.0)
    mult *= t.get("pace", 1.0) ** 0.5  # pace helps but sub-linearly
    return mult


def _opportunity_mult(row: dict, prof: dict | None) -> float:
    """Volume signal. Depth-chart order is the live starter signal from Sleeper;
    prior-season shares confirm/adjust it."""
    pos = row["position"]
    mult = 1.0
    dco = row.get("depth_chart_order")
    if dco is not None:
        # WR3+ / RB2 / etc. get discounted; starters get a small bump
        if pos in ("RB",):
            mult *= {1: 1.10, 2: 0.80, 3: 0.55}.get(dco, 0.40)
        elif pos in ("WR",):
            mult *= {1: 1.08, 2: 0.98, 3: 0.82, 4: 0.65}.get(dco, 0.5)
        elif pos in ("TE",):
            mult *= {1: 1.06, 2: 0.7}.get(dco, 0.5)
    if prof:
        # blend prior usage: high WOPR / rush_share pushes value up
        if pos in ("WR", "TE"):
            mult *= 0.85 + min(prof.get("wopr", 0) * 1.6, 0.45)
        elif pos == "RB":
            rs = prof.get("rush_share", 0)
            ts = prof.get("target_share", 0)
            mult *= 0.85 + min(rs * 0.9 + ts * 1.2, 0.5)
        snap = prof.get("snap_pct")
        if snap:
            mult *= 0.9 + min(snap / 100.0 * 0.2, 0.2)
    return max(mult, 0.25)


def _efficiency_mult(row: dict, prof: dict | None) -> float:
    if not prof:
        return 1.0
    pos = row["position"]
    m = 1.0
    if pos in ("WR", "TE"):
        yprr = prof.get("yprr_proxy", 0)  # rec yds per target proxy
        m *= 0.96 + max(min((yprr - 8.0) * 0.01, 0.06), -0.04)
    elif pos == "RB":
        ypc = prof.get("ypc", 0)
        m *= 0.96 + max(min((ypc - 4.2) * 0.02, 0.06), -0.04)
    return m


def _availability(row: dict) -> tuple[float, list[str]]:
    """P(player is on the field / stays a starter). Multiplies value.
    Returns (prob, flags)."""
    p = 1.0
    flags: list[str] = []
    inj = (row.get("injury_status") or "").lower()
    if inj in ("questionable",):
        p *= 0.92
    elif inj in ("doubtful",):
        p *= 0.6; flags.append("doubtful")
    elif inj in ("out", "ir", "pup", "sus"):
        p *= 0.35; flags.append(inj.upper())
    age = row.get("age")
    pos = row["position"]
    if age:
        # RB age cliff ~28, WR ~30, TE/QB later
        cliff = {"RB": 28, "WR": 30, "TE": 31, "QB": 36}.get(pos, 30)
        if age >= cliff:
            pen = min((age - cliff + 1) * 0.03, 0.18)
            p *= (1 - pen)
            flags.append(f"age {age}")
    # depth competition: not clear starter
    dco = row.get("depth_chart_order")
    if dco and dco >= 3 and pos in ("RB", "WR"):
        flags.append("buried on depth chart")
    return max(p, 0.2), flags


def score_pool(pool: list[dict], usage: dict[tuple[str, str], dict]) -> list[dict]:
    coaching = _load_coaching()

    # establish positional rank from best available ordering signal:
    # real ADP if present, else Sleeper search_rank.
    def order_key(r):
        return (r["adp"] if r.get("adp") else r["search_rank"] + 0.0)

    by_pos: dict[str, list[dict]] = {}
    for r in pool:
        by_pos.setdefault(r["position"], []).append(r)
    for pos, rows in by_pos.items():
        rows.sort(key=order_key)
        for i, r in enumerate(rows, 1):
            r["_pos_rank"] = i

    scored: list[dict] = []
    for r in pool:
        pos = r["position"]
        prof = usage.get((r["name"].lower(), pos))
        base = _pos_rank_points(pos, r["_pos_rank"])
        opp = _opportunity_mult(r, prof)
        eff = _efficiency_mult(r, prof)
        sit = _team_adj(coaching, r.get("team"), pos)
        avail, flags = _availability(r)

        proj = base * opp * eff * sit
        exp_value = proj * avail  # games-adjusted expected points

        # trending adds = market catching onto rising opportunity
        if r.get("trending_adds", 0) > 5000:
            exp_value *= 1.04
            flags.append("trending up")

        r.update({
            "proj_points": round(proj, 1),
            "exp_value": round(exp_value, 1),
            "opp_mult": round(opp, 3),
            "eff_mult": round(eff, 3),
            "situation_mult": round(sit, 3),
            "availability": round(avail, 3),
            "flags": flags,
            "usage": prof or {},
        })
        scored.append(r)

    # VOR: subtract positional replacement expected value
    repl: dict[str, float] = {}
    for pos, n in STARTERS_12.items():
        vals = sorted((r["exp_value"] for r in scored if r["position"] == pos), reverse=True)
        repl[pos] = vals[n] if len(vals) > n else (vals[-1] if vals else 0)
    for r in scored:
        r["vor"] = round(r["exp_value"] - repl.get(r["position"], 0), 1)

    scored.sort(key=lambda r: r["vor"], reverse=True)
    for i, r in enumerate(scored, 1):
        r["overall_rank"] = i
    return scored

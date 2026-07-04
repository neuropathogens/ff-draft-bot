"""Orchestrate: fetch -> score -> write extension/data/rankings.json.

Run:  python build.py
Out:  ../extension/data/rankings.json   (consumed live by the Chrome extension)

Also assigns tiers (value cliffs) per position so the draft assistant can warn
"last player in tier" and computes a simple bye week for stacking penalties.
"""
from __future__ import annotations
import json
import os
import datetime as _dt

from fetch_sleeper import normalized_pool
from fetch_nflverse import usage_profiles
from scoring import score_pool

OUT = os.path.join(os.path.dirname(__file__), "..", "extension", "data", "rankings.json")
TOP_N = 350  # deep enough for a 12-team standard draft + waiver targets


def assign_tiers(scored: list[dict]) -> None:
    """Break each position into tiers where value drops off a cliff (gap-based)."""
    for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
        rows = [r for r in scored if r["position"] == pos]
        rows.sort(key=lambda r: r["vor"], reverse=True)
        if not rows:
            continue
        tier = 1
        rows[0]["tier"] = 1
        for prev, cur in zip(rows, rows[1:]):
            gap = prev["vor"] - cur["vor"]
            # dynamic threshold: bigger gaps near the top define tiers
            thresh = max(8.0, prev["vor"] * 0.06)
            if gap > thresh:
                tier += 1
            cur["tier"] = tier


def main() -> None:
    print("Fetching Sleeper pool...")
    pool = normalized_pool()
    print(f"  {len(pool)} players")
    print("Fetching nflverse usage (may take a minute)...")
    usage = usage_profiles()
    print("Scoring...")
    scored = score_pool(pool, usage)
    assign_tiers(scored)

    top = scored[:TOP_N]
    payload = {
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "format": "PPR",
        "roster": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DEF": 1, "BENCH": 6},
        "flex_positions": ["RB", "WR", "TE"],
        "count": len(top),
        "players": [
            {
                "rank": r["overall_rank"],
                "name": r["name"],
                "pos": r["position"],
                "team": r.get("team"),
                "tier": r.get("tier", 99),
                "vor": r["vor"],
                "proj": r["proj_points"],
                "exp": r["exp_value"],
                "adp": r.get("adp"),
                "posrank": r.get("_pos_rank"),
                "avail": r["availability"],
                "flags": r["flags"],
                "why": _why(r),
                "sleeper_id": r["player_id"],
            }
            for r in top
        ],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"Wrote {len(top)} players -> {os.path.relpath(OUT)}")


def _why(r: dict) -> str:
    """Human-readable rationale shown in the draft panel."""
    bits = []
    u = r.get("usage") or {}
    if u.get("target_share"):
        bits.append(f"{u['target_share']*100:.0f}% tgt share")
    if u.get("rush_share"):
        bits.append(f"{u['rush_share']*100:.0f}% rush share")
    if u.get("snap_pct"):
        bits.append(f"{u['snap_pct']:.0f}% snaps")
    if r.get("situation_mult", 1) >= 1.03:
        bits.append("plus offense")
    elif r.get("situation_mult", 1) <= 0.98:
        bits.append("weak offense")
    if r.get("opp_mult", 1) >= 1.05:
        bits.append("clear role")
    elif r.get("opp_mult", 1) <= 0.8:
        bits.append("crowded role")
    if r["flags"]:
        bits.append("⚠ " + ", ".join(r["flags"]))
    return " · ".join(bits) if bits else "value vs replacement"


if __name__ == "__main__":
    main()

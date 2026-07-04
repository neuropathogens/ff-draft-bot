"""Pull prior-season usage + efficiency from nflverse (nfl_data_py).

These are the real "advanced analytics" inputs behind opportunity and efficiency
scores. We aggregate the most recent completed season to a per-player profile:

  target_share      - share of team targets (WR/TE/RB receiving role)
  rush_share        - share of team carries (RB/QB)
  air_yards_share   - share of team air yards (downfield role)
  wopr              - weighted opportunity rating (0.7*tgt_share + 0.3*ay_share)
  snap_pct          - offensive snap share (availability of role)
  yprr_proxy        - receiving yards / routes proxy (efficiency)
  ypc               - yards per carry (efficiency)
  games             - games played (durability signal)

If nfl_data_py or the network is unavailable the pipeline still runs; these
fields just come back empty and scoring falls back to Sleeper-only signals.
"""
from __future__ import annotations
import datetime as _dt

# NOTE: season is inferred, not hardcoded, so this stays correct year over year.
def _target_season() -> int:
    now = _dt.date.today()
    # Before September, the most recent *completed* season is last year.
    return now.year - 1 if now.month < 9 else now.year


def usage_profiles(season: int | None = None) -> dict[tuple[str, str], dict]:
    """Return {(lower name, position): profile dict}. Empty on any failure."""
    season = season or _target_season()
    try:
        import nfl_data_py as nfl
        import pandas as pd
    except Exception as e:  # library missing
        print(f"[nflverse] skipped ({e}); usage metrics empty")
        return {}

    try:
        wk = nfl.import_weekly_data([season])
        snaps = _load_snaps(nfl, season)
    except Exception as e:
        print(f"[nflverse] load failed for {season} ({e}); trying {season-1}")
        try:
            wk = nfl.import_weekly_data([season - 1])
            snaps = _load_snaps(nfl, season - 1)
        except Exception as e2:
            print(f"[nflverse] no data ({e2}); usage metrics empty")
            return {}

    import pandas as pd  # noqa
    g = wk.groupby(["player_display_name", "position", "recent_team"], dropna=False)
    agg = g.agg(
        targets=("targets", "sum"),
        receptions=("receptions", "sum"),
        rec_yards=("receiving_yards", "sum"),
        air_yards=("receiving_air_yards", "sum"),
        carries=("carries", "sum"),
        rush_yards=("rushing_yards", "sum"),
        games=("week", "nunique"),
    ).reset_index()

    # team totals for share computation
    team_tgt = wk.groupby("recent_team")["targets"].sum()
    team_car = wk.groupby("recent_team")["carries"].sum()
    team_ay = wk.groupby("recent_team")["receiving_air_yards"].sum()

    out: dict[tuple[str, str], dict] = {}
    for _, r in agg.iterrows():
        team = r["recent_team"]
        name = str(r["player_display_name"])
        pos = str(r["position"])
        tt = team_tgt.get(team, 0) or 1
        tc = team_car.get(team, 0) or 1
        ta = team_ay.get(team, 0) or 1
        tgt_share = float(r["targets"]) / tt
        ay_share = float(r["air_yards"]) / ta
        profile = {
            "target_share": round(tgt_share, 4),
            "rush_share": round(float(r["carries"]) / tc, 4),
            "air_yards_share": round(ay_share, 4),
            "wopr": round(0.7 * tgt_share + 0.3 * ay_share, 4),
            "yprr_proxy": round(float(r["rec_yards"]) / max(r["targets"], 1), 3),
            "ypc": round(float(r["rush_yards"]) / max(r["carries"], 1), 3),
            "games": int(r["games"]),
            "snap_pct": snaps.get((name.lower(), pos), None),
        }
        out[(name.lower(), pos)] = profile
    print(f"[nflverse] built {len(out)} usage profiles for season {season}")
    return out


def _load_snaps(nfl, season: int) -> dict[tuple[str, str], float]:
    try:
        s = nfl.import_snap_counts([season])
        s = s.groupby(["player", "position"])["offense_pct"].mean().reset_index()
        return {(str(r["player"]).lower(), str(r["position"])): round(float(r["offense_pct"]), 3)
                for _, r in s.iterrows()}
    except Exception:
        return {}


if __name__ == "__main__":
    prof = usage_profiles()
    for k in list(prof)[:10]:
        print(k, prof[k])

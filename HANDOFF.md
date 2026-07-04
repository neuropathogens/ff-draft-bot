# Session Handoff — FF Draft Bot

State snapshot so work can resume after a context clear. Project-only; no personal data.

## What this is
PPR live fantasy-football draft assistant. Two parts:
- **`extension/`** — Chrome MV3 overlay. Live best-pick recommender on the draft page for **Sleeper** (public draft API) and **ESPN** (DOM scrape + manual fallback).
- **`pipeline/`** — Python. Rebuilds `extension/data/rankings.json` from live Sleeper API + nflverse usage data via the value model.

Standard roster (QB/2RB/2WR/TE/FLEX/K/DEF + 6 bench), PPR.

## Status: shipped & pushed
- Repo: `neuropathogens/ff-draft-bot` (public, `main`).
- All files validated: JSON parses, JS `node --check` clean, Python compiles, engine sim passes.
- Extension loads and runs off a bundled **seed** board (48 players).

## Architecture
```
pipeline/
  fetch_sleeper.py   live pool, ADP override (adp.csv), injuries, depth-chart order
  fetch_nflverse.py  prior-season target/rush/air-yards share, snaps, YPRR, YPC
  coaching.json      per-team scheme/pace/pass-lean multipliers (edit each offseason)
  scoring.py         VALUE MODEL — VOR blended from opportunity·efficiency·situation·availability
  build.py           orchestrate -> extension/data/rankings.json (top ~350)
extension/
  manifest.json      MV3, Sleeper + ESPN hosts
  engine.js          PICK LOGIC (pure): pickScore = 0.55·VOR_norm + 0.30·need + tierScarcity + byePenalty, ·(0.6+0.4·avail)
  panel.js / .css    overlay UI + state (taken set, my roster, recommendations)
  content-sleeper.js live driver: reads draft id from URL, polls api.sleeper.app/v1/draft/<id>/picks, filters by your draft_slot
  content-espn.js    best-effort name-match DOM scraper; manual ✕/＋ is the reliable fallback
  data/rankings.json the board (seed now; regenerate with build.py)
```

## Value model (the "advanced analytics")
6 layers into one VOR number, in `scoring.py`:
1. base points — positional-rank curve off live ADP/search_rank
2. opportunity — target/rush/air-yards share + WOPR + snap% (nflverse) + live depth-chart order (Sleeper). Weighted most (volume predicts points).
3. efficiency — YPRR proxy, YPC (light weight, noisy)
4. situation — `coaching.json` team mult + pass/run lean by position
5. availability — injury status, age cliff by position, depth competition → P(plays)
6. VOR — value over positional replacement (12-team starter baseline)
Then tiers assigned by value-cliff gaps.

## How to run
- Extension: `chrome://extensions` → Developer mode → Load unpacked → `extension/`.
  - Sleeper: open draft room, set draft slot in panel header (stored). Auto-syncs.
  - ESPN: open draft, auto-detect + correct with ✕ taken / ＋ my team buttons.
- Live board: `cd pipeline && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python build.py`. Reload extension.
- Optional real ADP: `pipeline/adp.csv` (`full_name,position,team,adp`) overrides ordering.

## Open TODOs (offered, not done)
- Seed rows for K + DEF + kickers (seed currently has none; pipeline adds them live).
- Test `adp.csv` override wiring end-to-end.
- Extension icons (manifest has no icon set).
- ESPN scraper hardening (obfuscated class names; name-match is the workaround).

## Known limits
- Sleeper live sync is solid (public API). ESPN has no open draft API — auto-detect is best-effort; confirm with ✕/＋.
- Seed board is a hand-baked 2026 PPR outlook. Run the pipeline for current ADP/depth/injury numbers.

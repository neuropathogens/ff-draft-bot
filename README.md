# FF Draft Bot — PPR Live Assistant

Live in-draft best-pick recommender for **Sleeper** and **ESPN**. Standard roster
(QB / 2RB / 2WR / TE / FLEX / K / DEF + bench), **PPR** scoring. Built to draft the
best possible team by leaning on real usage analytics, not just name value.

Two parts:

- **`extension/`** — a Chrome (MV3) extension. Overlays a panel on your live draft
  room, tracks who's been picked and what's on your team, and tells you the best
  pick *this turn*. Works out of the box with a bundled seed board.
- **`pipeline/`** — a Python job that rebuilds the ranking board from **live data**
  (Sleeper API + nflverse) with the advanced-analytics value model. Run it before
  your draft to get a fresh, real board.

---

## The value model (what "advanced analytics" means here)

`pipeline/scoring.py` blends these layers into one draftable number (VOR):

| Layer | Source | Why it matters |
|---|---|---|
| **Base points** | positional rank curve off live ADP / Sleeper search_rank | anchor to reality |
| **Opportunity** | target share, rush share, air-yards share, WOPR, snap % (nflverse) + **live depth-chart order** (Sleeper) | volume is the #1 predictor of fantasy points |
| **Efficiency** | YPRR proxy, YPC (nflverse) | separate real from lucky, lightly weighted (noisy) |
| **Situation** | `pipeline/coaching.json` — per-team scheme/pace/pass-lean/OL, editable | coaching + offense shape opportunity |
| **Availability** | injury status, age cliff by position, depth competition | a stud who misses games is worth less |
| **VOR** | value over positional replacement | the actual draft-day number |

The live board also carries **tiers** (value cliffs) so the assistant can warn
"last player in this tier — grab now."

The in-draft pick logic (`extension/engine.js`) then weighs board value against
**your roster needs**, **tier scarcity**, and **bye-week spread**.

---

## Setup

### 1. Load the extension (works immediately with seed data)

1. Chrome → `chrome://extensions`
2. Toggle **Developer mode** (top right)
3. **Load unpacked** → select the `extension/` folder
4. Open your draft room:
   - **Sleeper:** `sleeper.com/draft/...` — panel auto-polls the public draft API.
     Set your **draft slot** in the panel header once so it knows your team.
   - **ESPN:** `fantasy.espn.com/football/draft?...` — panel auto-detects picks from
     the page (best-effort). Use the **✕ taken** / **＋ my team** buttons to correct
     anything it misses. Those buttons are the always-works fallback on any platform.

The panel shows: recommended pick (top 3 with reasons), your roster + needs, and
the best-available board with a position filter.

### 2. Rebuild the board with live data (recommended before a real draft)

```bash
cd pipeline
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python build.py          # writes ../extension/data/rankings.json
```

Then reload the extension (or just the draft page). The bundled `rankings.json` is
only a **seed** (~48 players) so the UI works before you run the pipeline; `build.py`
replaces it with a full ~350-player live board.

**Optional real ADP:** drop `pipeline/adp.csv` (`full_name,position,team,adp`) and it
overrides Sleeper's ordering. **Tune situations:** edit `pipeline/coaching.json` each
offseason (bump teams that upgraded OC/QB/OL, fade expected regression).

---

## How it decides a pick

`recommend()` scores every available player as:

```
pickScore = (0.55·VOR_norm + 0.30·rosterNeed + tierScarcity + byePenalty)
            · (0.6 + 0.4·availability)
```

- **VOR_norm** — talent/value vs replacement, normalized across the board
- **rosterNeed** — unfilled starters weighted highest; FLEX and bench depth next; K/DEF suppressed until late
- **tierScarcity** — urgency spikes when a position tier is about to empty
- **byePenalty** — small ding for stacking same-bye starters at a position
- **availability** — injury/age/depth risk discounts the whole score

---

## Files

```
pipeline/
  fetch_sleeper.py   live pool, ADP override, injuries, depth-chart order
  fetch_nflverse.py  prior-season usage + efficiency (target/rush/air-yards share, snaps)
  coaching.json      per-team scheme adjustments (edit each offseason)
  scoring.py         the value model (VOR + all layers)
  build.py           orchestrate -> extension/data/rankings.json
extension/
  manifest.json      MV3, Sleeper + ESPN hosts
  engine.js          pick recommendation logic (pure, no DOM)
  panel.js / .css    overlay UI + state
  content-sleeper.js live driver via Sleeper public draft API
  content-espn.js    best-effort DOM scraper + manual fallback
  data/rankings.json the board (seed now; regenerate with build.py)
```

## Notes / limits

- Sleeper live sync is solid (public API). ESPN has no open draft API, so ESPN
  auto-detect is best-effort DOM scraping — always confirm with the ✕/＋ buttons.
- The seed board reflects a 2026 PPR outlook baked in by hand; **run the pipeline**
  for numbers that reflect current ADP, depth charts, and injuries.
- Not affiliated with Sleeper or ESPN. For personal draft use.

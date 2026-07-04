// Recommendation engine — pure logic, no DOM. Shared by all platforms.
// Given the ranked pool, who's already taken, and my current roster, decide the
// best pick THIS turn. Weighs: value-over-replacement, positional need, tier
// cliffs (scarcity urgency), roster construction, and bye-week spread.

const ROSTER_SLOTS = { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, K: 1, DEF: 1 };
const FLEX_POS = ["RB", "WR", "TE"];
const BENCH_TARGET = { RB: 2, WR: 2, QB: 1, TE: 1 }; // desired depth beyond starters

function normName(s) {
  return (s || "")
    .toLowerCase()
    .replace(/[.'`]/g, "")
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, "")
    .replace(/[^a-z ]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

// what positions does my roster still need, and how urgently (0..1)
function rosterNeeds(myPlayers) {
  const have = { QB: 0, RB: 0, WR: 0, TE: 0, K: 0, DEF: 0 };
  for (const p of myPlayers) if (have[p.pos] != null) have[p.pos]++;

  // fill required starters first
  const need = {};
  for (const pos of Object.keys(ROSTER_SLOTS)) {
    const req = ROSTER_SLOTS[pos];
    const deficit = Math.max(req - have[pos], 0);
    need[pos] = deficit;
  }
  // flex: if RB+WR+TE starters filled, flex still wants a startable body
  const flexFilled = FLEX_POS.reduce((a, pos) => a + Math.min(have[pos], ROSTER_SLOTS[pos]), 0);
  const flexReq = FLEX_POS.reduce((a, pos) => a + ROSTER_SLOTS[pos], 0);
  const flexOpen = flexFilled >= flexReq ? 1 : 0;

  // urgency weight per position
  const weight = {};
  for (const pos of Object.keys(have)) {
    let w = 0;
    if (need[pos] > 0) w = 1.0 + need[pos] * 0.25; // unfilled starter = high
    else {
      // depth want
      const depthWant = BENCH_TARGET[pos] || 0;
      const extra = have[pos] - ROSTER_SLOTS[pos];
      w = extra < depthWant ? 0.45 : 0.15;
    }
    // FLEX pulls RB/WR/TE up a bit when a flex slot is open
    if (flexOpen && FLEX_POS.includes(pos)) w += 0.35;
    // never chase K/DEF early
    if (pos === "K" || pos === "DEF") w = myPlayers.length >= 13 ? 0.8 : 0.02;
    weight[pos] = w;
  }
  return { have, weight, flexOpen };
}

// tier scarcity: how urgent to grab this player before the tier empties
function tierUrgency(player, available) {
  const sameTier = available.filter(p => p.pos === player.pos && p.tier === player.tier);
  const n = sameTier.length;
  if (n <= 1) return 0.30;      // last of tier — grab now
  if (n === 2) return 0.18;
  if (n <= 4) return 0.08;
  return 0.0;
}

// bye-week clustering penalty (avoid too many starters same bye)
function byePenalty(player, myPlayers) {
  if (!player.bye) return 0;
  const clash = myPlayers.filter(p => p.bye && p.bye === player.bye && p.pos === player.pos).length;
  return clash >= 1 ? -0.05 * clash : 0;
}

// MAIN: return ranked recommendations for the current pick
function recommend(pool, takenSet, myPlayers, opts = {}) {
  const topN = opts.topN || 5;
  const available = pool.filter(p => !takenSet.has(normName(p.name)));
  const { weight } = rosterNeeds(myPlayers);

  // normalize VOR to 0..1 across the available board for blending
  const maxVor = Math.max(1, ...available.map(p => p.vor || 0));

  const scored = available.map(p => {
    const vorN = (p.vor || 0) / maxVor;                 // base talent/value
    const need = weight[p.pos] || 0.2;                  // roster fit
    const scarce = tierUrgency(p, available);           // grab-now urgency
    const bye = byePenalty(p, myPlayers);
    const availAdj = (p.avail != null ? p.avail : 1);   // injury/durability
    // blended pick score
    const score = (0.55 * vorN + 0.30 * need + scarce + bye) * (0.6 + 0.4 * availAdj);
    return { ...p, pickScore: score, _need: need, _scarce: scarce };
  });

  scored.sort((a, b) => b.pickScore - a.pickScore);

  const best = scored.slice(0, topN).map(p => ({
    ...p,
    reason: buildReason(p, weight),
  }));
  return { best, available: scored };
}

function buildReason(p, weight) {
  const bits = [];
  if ((weight[p.pos] || 0) >= 1.0) bits.push(`fills ${p.pos} starter`);
  else if ((weight[p.pos] || 0) >= 0.6) bits.push(`${p.pos} flex/depth need`);
  if (p._scarce >= 0.18) bits.push(`last of tier ${p.tier}`);
  else if (p._scarce >= 0.08) bits.push(`tier ${p.tier} thinning`);
  if (p.vor != null) bits.push(`VOR ${p.vor}`);
  if (p.avail != null && p.avail < 0.85) bits.push(`avail ${(p.avail * 100) | 0}%`);
  if (p.why) bits.push(p.why);
  return bits.join(" · ");
}

// expose for content scripts (no modules in MV3 content scripts by default)
window.FFEngine = { recommend, normName, rosterNeeds, ROSTER_SLOTS, FLEX_POS };

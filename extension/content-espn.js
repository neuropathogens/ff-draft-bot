// ESPN live driver. ESPN has no open draft API (auth-gated), so this best-effort
// scrapes the draft DOM for names that match our ranked pool and marks them
// taken. ESPN ships obfuscated, frequently-changing class names, so this uses a
// NAME-MATCH strategy (match any pool player rendered in the pick feed) rather
// than brittle exact selectors. The panel's manual ✕/＋ buttons are the always-
// works fallback if ESPN changes its markup.

(function () {
  let poolNames = [];        // normalized names from rankings
  let ready = false;

  function buildPoolIndex() {
    const S = FFPanel.getState();
    poolNames = (S.pool || []).map(p => ({ raw: p.name, n: FFEngine.normName(p.name), pos: p.pos, team: p.team }));
    ready = poolNames.length > 0;
  }

  // Heuristic: the draft "pick feed" / history. We look at containers likely to
  // hold completed picks; fall back to whole-doc scan throttled.
  const PICK_CONTAINERS = [
    ".draft-columns", ".draftHistory", ".pick-history", "[class*='draftHistory']",
    "[class*='pickHistory']", "[class*='DraftHistory']", ".players-table--drafted",
  ];
  // where MY roster shows (right rail / my-team panel)
  const MY_CONTAINERS = [
    "[class*='myTeam']", "[class*='MyTeam']", ".draft-roster", "[class*='rosterSlot']",
  ];

  function scanContainer(selectors) {
    const found = new Set();
    const nodes = [];
    for (const sel of selectors) document.querySelectorAll(sel).forEach(n => nodes.push(n));
    const scope = nodes.length ? nodes : [document.body];
    const text = scope.map(n => n.innerText || "").join("\n").toLowerCase();
    for (const p of poolNames) {
      // require both name tokens present to avoid false positives
      const parts = p.n.split(" ").filter(Boolean);
      const last = parts[parts.length - 1];
      const first = parts[0];
      if (last && first && text.includes(last) && text.includes(first)) found.add(p.raw);
    }
    return [...found];
  }

  function tick() {
    if (!ready) { buildPoolIndex(); if (!ready) return; }
    const taken = scanContainer(PICK_CONTAINERS);
    if (taken.length) FFPanel.setTaken(taken);

    const mine = scanContainer(MY_CONTAINERS)
      .map(raw => {
        const meta = poolNames.find(p => p.raw === raw);
        return { name: raw, pos: meta?.pos, team: meta?.team };
      });
    if (mine.length) FFPanel.setMyRoster(mine);

    FFPanel.setInfo(
      taken.length
        ? `ESPN · auto-detected ${taken.length} picks · verify with ✕/＋ if a name is missed`
        : "ESPN · open the draft room. Auto-detect best-effort; use ✕ taken / ＋ my team to be exact."
    );
  }

  function start() {
    FFPanel.init("ESPN");
    buildPoolIndex();
    setInterval(tick, 2500);
    // also react to DOM churn for faster updates
    const obs = new MutationObserver(() => { /* throttled by interval */ });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  const boot = setInterval(() => {
    if (window.FFPanel && window.FFEngine) { clearInterval(boot); start(); }
  }, 300);
})();

// Sleeper live driver. Reads the draft id from the URL, polls Sleeper's PUBLIC
// draft API for picks (no auth), feeds taken players + my roster to the panel.
// You set your draft slot once (stored); we filter picks by draft_slot to know
// which players are on YOUR team.

(function () {
  const DRAFT_RE = /\/draft\/[^/]+\/(\d+)/;

  function draftId() {
    const m = location.pathname.match(DRAFT_RE) || location.href.match(DRAFT_RE);
    return m ? m[1] : null;
  }

  let mySlot = null;
  let timer = null;
  let lastCount = -1;

  async function api(path) {
    const r = await fetch(`https://api.sleeper.app/v1/${path}`);
    if (!r.ok) throw new Error(`sleeper ${path} ${r.status}`);
    return r.json();
  }

  async function poll() {
    const id = draftId();
    if (!id) { FFPanel.setInfo("Open a Sleeper draft room to activate."); return; }
    try {
      const picks = await api(`draft/${id}/picks`);
      if (picks.length === lastCount) return; // no change, skip re-render churn
      lastCount = picks.length;

      const takenNames = [];
      const mine = [];
      for (const p of picks) {
        const md = p.metadata || {};
        const name = `${md.first_name || ""} ${md.last_name || ""}`.trim();
        if (!name) continue;
        takenNames.push(name);
        if (mySlot && Number(p.draft_slot) === Number(mySlot)) {
          mine.push({ name, pos: md.position, team: md.team });
        }
      }
      FFPanel.setTaken(takenNames);
      if (mySlot) FFPanel.setMyRoster(mine);
      FFPanel.setInfo(`Live · ${picks.length} picks made` + (mySlot ? ` · you = slot ${mySlot}` : " · set your slot ▶"));
    } catch (e) {
      FFPanel.setInfo("Sleeper API blip, retrying… " + e.message);
    }
  }

  function slotBar() {
    const head = document.getElementById("ffb-head");
    if (!head || document.getElementById("ffb-slot")) return;
    const wrap = document.createElement("span");
    wrap.id = "ffb-slot";
    wrap.innerHTML = `slot <input id="ffb-slot-in" type="number" min="1" max="16" style="width:34px"/>`;
    head.insertBefore(wrap, document.getElementById("ffb-min"));
    const inp = wrap.querySelector("#ffb-slot-in");
    chrome.storage.local.get(["sleeperSlot"], (v) => {
      if (v.sleeperSlot) { mySlot = v.sleeperSlot; inp.value = v.sleeperSlot; }
    });
    inp.onchange = () => {
      mySlot = Number(inp.value) || null;
      chrome.storage.local.set({ sleeperSlot: mySlot });
      lastCount = -1; poll();
    };
  }

  function start() {
    FFPanel.init("Sleeper");
    setTimeout(slotBar, 400);
    poll();
    timer = setInterval(poll, 3000);
  }

  // wait for panel + engine to be ready
  const boot = setInterval(() => {
    if (window.FFPanel && window.FFEngine) { clearInterval(boot); start(); }
  }, 300);

  // Sleeper is an SPA; re-check draft id on navigation
  let lastPath = location.pathname;
  setInterval(() => {
    if (location.pathname !== lastPath) { lastPath = location.pathname; lastCount = -1; }
  }, 1000);
})();

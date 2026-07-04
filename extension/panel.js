// Overlay panel UI + state. Platform content scripts feed it taken players and
// my roster; it renders live recommendations from FFEngine.

(function () {
  const S = {
    pool: [],
    taken: new Set(),      // normalized names
    myPlayers: [],         // [{name,pos,team,bye}]
    platform: "?",
    myInfo: "",
  };

  const norm = (s) => window.FFEngine.normName(s);

  async function loadPool() {
    const url = chrome.runtime.getURL("data/rankings.json");
    const res = await fetch(url);
    const json = await res.json();
    S.pool = json.players || [];
    render();
  }

  // ---- public API used by content scripts ----
  window.FFPanel = {
    init(platform) {
      S.platform = platform;
      mount();
      loadPool();
    },
    // full replace of taken set from platform names
    setTaken(names) {
      S.taken = new Set(names.map(norm));
      render();
    },
    // add single taken name (incremental)
    addTaken(name) {
      S.taken.add(norm(name));
      render();
    },
    setMyRoster(players) {
      S.myPlayers = players;
      render();
    },
    setInfo(txt) {
      S.myInfo = txt;
      const el = document.getElementById("ffb-info");
      if (el) el.textContent = txt;
    },
    getState: () => S,
  };

  // ---- UI ----
  function mount() {
    if (document.getElementById("ffb-root")) return;
    const root = document.createElement("div");
    root.id = "ffb-root";
    root.innerHTML = `
      <div id="ffb-head">
        <span id="ffb-title">FF Draft Bot · PPR</span>
        <span id="ffb-plat"></span>
        <button id="ffb-min" title="minimize">–</button>
      </div>
      <div id="ffb-body">
        <div id="ffb-info" class="ffb-muted"></div>
        <div id="ffb-roster"></div>
        <div id="ffb-rec-h" class="ffb-h">Recommended pick</div>
        <div id="ffb-rec"></div>
        <div class="ffb-h">Best available
          <input id="ffb-filter" placeholder="pos filter: RB/WR/…" />
        </div>
        <div id="ffb-board"></div>
      </div>`;
    document.body.appendChild(root);
    document.getElementById("ffb-plat").textContent = S.platform;
    document.getElementById("ffb-min").onclick = () => root.classList.toggle("ffb-collapsed");
    document.getElementById("ffb-filter").oninput = render;
  }

  function render() {
    if (!document.getElementById("ffb-root")) return;
    if (!S.pool.length) return;
    const { best } = window.FFEngine.recommend(S.pool, S.taken, S.myPlayers, { topN: 6 });

    // recommendation cards
    const rec = document.getElementById("ffb-rec");
    rec.innerHTML = best.slice(0, 3).map((p, i) => `
      <div class="ffb-card ffb-t${p.tier}">
        <div class="ffb-c-top">
          <span class="ffb-badge">#${i + 1}</span>
          <b>${esc(p.name)}</b>
          <span class="ffb-pos ffb-${p.pos}">${p.pos}</span>
          <span class="ffb-team">${esc(p.team || "")}</span>
          <span class="ffb-vor">VOR ${p.vor}</span>
        </div>
        <div class="ffb-reason">${esc(p.reason || "")}</div>
        <div class="ffb-actions">
          <button data-mine="${esc(p.name)}" data-pos="${p.pos}" data-team="${esc(p.team||'')}">＋ my team</button>
          <button data-taken="${esc(p.name)}">✕ taken</button>
        </div>
      </div>`).join("");

    // roster summary
    const { have, weight } = window.FFEngine.rosterNeeds(S.myPlayers);
    document.getElementById("ffb-roster").innerHTML =
      `<span class="ffb-h2">My team (${S.myPlayers.length})</span> ` +
      ["QB", "RB", "WR", "TE", "K", "DEF"].map(pos =>
        `<span class="ffb-rcount ${weight[pos] >= 1 ? "ffb-need" : ""}">${pos} ${have[pos]}</span>`
      ).join("");

    // best available board
    const filt = (document.getElementById("ffb-filter").value || "").trim().toUpperCase();
    const avail = S.pool.filter(p => !S.taken.has(norm(p.name)))
      .filter(p => !filt || p.pos === filt)
      .slice(0, 40);
    document.getElementById("ffb-board").innerHTML = avail.map(p => `
      <div class="ffb-row ffb-t${p.tier}">
        <span class="ffb-rk">${p.rank}</span>
        <span class="ffb-nm">${esc(p.name)}</span>
        <span class="ffb-pos ffb-${p.pos}">${p.pos}${p.posrank || ""}</span>
        <span class="ffb-tier">T${p.tier}</span>
        <span class="ffb-vor">${p.vor}</span>
        <button class="ffb-mini" data-mine="${esc(p.name)}" data-pos="${p.pos}" data-team="${esc(p.team||'')}">＋</button>
        <button class="ffb-mini" data-taken="${esc(p.name)}">✕</button>
      </div>`).join("");

    // wire buttons
    document.querySelectorAll("#ffb-root [data-mine]").forEach(b => {
      b.onclick = () => {
        S.myPlayers.push({ name: b.dataset.mine, pos: b.dataset.pos, team: b.dataset.team });
        S.taken.add(norm(b.dataset.mine));
        render();
      };
    });
    document.querySelectorAll("#ffb-root [data-taken]").forEach(b => {
      b.onclick = () => { S.taken.add(norm(b.dataset.taken)); render(); };
    });
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, c =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();

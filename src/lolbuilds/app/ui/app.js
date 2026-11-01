/* lolbuilds — interface : rendu de l'état poussé par le serveur local (/ws) et actions. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
let S = null;            // données statiques (noms fr, descriptions) : /api/static
let state = null;        // état courant poussé par le serveur
let view = "live";
let library = [];
let libRole = "";
let lastKey = "";
let lastToast = null;
let lastHtml = "";
let timerEnds = null;  // hors du HTML : sinon chaque event changerait le rendu
let lastTurn = null;  // id de l'action LCU pour laquelle on a déjà alerté
let turnTotal = null;  // durée de l'action en cours (ms), si le client ne la donne pas

const ROLE_LABEL = { top: "Top", jungle: "Jungle", middle: "Mid", bottom: "ADC", utility: "Support" };
const ROLE_ORDER = ["top", "jungle", "middle", "bottom", "utility"];
const ROLE_SVG = {
  top: '<path d="M2 2h9.5L8.5 5H5v3.5l-3 3z" fill="currentColor"/><path d="M9 9h5v5H9z" fill="currentColor" opacity=".35"/>',
  jungle: '<path d="M8 1.5c.6 3.4 4.5 5 4.5 8.5A4.5 4.5 0 0 1 8 14.5 4.5 4.5 0 0 1 3.5 10C3.5 6.5 7.4 4.9 8 1.5z" fill="currentColor"/>',
  middle: '<path d="M2 11.2 11.2 2H14v2.8L4.8 14H2z" fill="currentColor"/><path d="M2 2h5L2 7zM14 14H9l5-5z" fill="currentColor" opacity=".35"/>',
  bottom: '<path d="M14 14H4.5l3-3H11V7.5l3-3z" fill="currentColor"/><path d="M2 2h5v5H2z" fill="currentColor" opacity=".35"/>',
  utility: '<path d="M8 2.2 10.6 5H5.4zM2.5 6h11l-2.2 3H9.2v5H6.8V9H4.7z" fill="currentColor"/>',
};
const SHARD_ABBR = { adaptive: "FA", attackspeed: "VA", haste: "AC", movespeed: "VD", healthscaling: "PV+", health: "PV", tenacity: "TÉN", armor: "AR", magicres: "RM" };
const FLASH = 4;

/* ------------------------------------------------------------------ formats */
const pct = (x, d = 1) => (x * 100).toFixed(d).replace(".", ",") + " %";
const int = (n) => new Intl.NumberFormat("fr-FR").format(n);
const day = (iso) => (iso ? new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) : "—");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const wrClass = (wr) => (wr >= 0.52 ? "good" : wr < 0.48 ? "bad" : "");
const roleIcon = (r) => `<svg viewBox="0 0 16 16" aria-hidden="true">${ROLE_SVG[r] || ""}</svg>`;

/* ------------------------------------------------------------------ données statiques */
const champ = (key) => S?.champions?.[String(key)];
const perk = (id) => S?.perks?.[String(id)];
const style = (id) => S?.styles?.[String(id)];
const item = (id) => S?.items?.[String(id)];
const spell = (id) => S?.spells?.[String(id)];
const asset = (kind, id) => `/assets/${kind}/${id}.${kind === "splash" ? "jpg" : "png"}`;

const img = (kind, id, cls = "icon", tip = "") =>
  `<img class="${cls}" src="${asset(kind, id)}" alt="" ${tip} onerror="this.style.visibility='hidden'">`;
const tipAttr = (kind, id) => `data-tip="${kind}" data-id="${id}"`;

function orient(spells, key) {
  const [a, b] = spells;
  if (![a, b].includes(FLASH) || !key) return [a, b];
  const other = a === FLASH ? b : a;
  return key === "D" ? [FLASH, other] : [other, FLASH];
}

/* ------------------------------------------------------------------ API */
async function post(path, body) {
  try {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return await r.json();
  } catch {
    toast("warn", "Le serveur local ne répond pas.");
    return { ok: false };
  }
}

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "state") {
      const prevPrefetch = state?.lastPrefetch;
      state = msg.state;
      if (state.notice === "reload") { loadStatic().then(() => { lastHtml = ""; render(); loadLibrary(); }); return; }
      render();
      checkTurn();
      if (view === "library" && prevPrefetch !== state.lastPrefetch) loadLibrary();
    }
  };
  ws.onclose = () => {
    state = state ? { ...state, connection: "offline" } : null;
    renderTop();
    setTimeout(connect, 1500);
  };
}

/* ------------------------------------------------------------------ mon tour : alerte */
let lastStage = null;
let wasInChampSelect = null;  // null : premier état reçu, on n'alerte pas pour une session déjà en cours

/** Sons du champ select : début, phases de bans / picks, mon tour (+ fenêtre au premier plan). */
function checkTurn() {
  const cs = state.champSelect;
  const turn = cs?.turn;
  const id = turn ? `${turn.type}:${turn.id}` : null;
  const events = [];
  if (id !== lastTurn) {
    lastTurn = id;
    const ends = cs?.timer?.endsAt;
    turnTotal = ends ? Math.max(1000, ends - Date.now()) : null;
    if (turn) events.push(turn.type === "ban" ? "myBan" : "myPick");
  }
  const stage = cs?.stage || null;
  if (stage !== lastStage) {
    if (stage === "ban") events.push("banPhase");
    if (stage === "pick" && lastStage) events.push("pickPhase");
    lastStage = stage;
  }
  const first = wasInChampSelect === null;
  if (cs && wasInChampSelect === false) events.push("start");
  wasInChampSelect = Boolean(cs);
  const set = state.settings;
  if (first || !events.length || !set?.turnAlert) return;
  if (turn && events.includes(turn.type === "ban" ? "myBan" : "myPick") && set.alertFocus) api()?.focus();
  // Un seul son à la fois : mon tour d'abord, puis la phase, puis le début du champ select.
  const sound = ["myBan", "myPick", "banPhase", "pickPhase", "start"].filter((e) => events.includes(e))
    .map((e) => set.sounds?.[e]).find((s) => s && s !== "none");
  if (sound) playSound(sound, set.volume);
}

/* ------------------------------------------------------------------ sons (générés, aucun fichier) */
const SOUND_LABEL = { none: "Aucun", cloche: "Cloche", hextech: "Hextech", gong: "Gong", bip: "Bip" };
const SOUND_EVENTS = [
  ["myBan", "Ton tour de bannir"], ["myPick", "Ton tour de choisir"],
  ["banPhase", "Début des bans"], ["pickPhase", "Début des picks"], ["start", "Début du champ select"],
];
// [fréquence Hz, départ s, durée s, forme, harmoniques]
const SOUND_PRESETS = {
  cloche: [[880, 0, 1.2, "sine", [1, 2.76, 5.4]], [1318, 0.18, 1.0, "sine", [1, 2.76]]],
  hextech: [[523, 0, 0.35, "triangle", [1, 2]], [784, 0.11, 0.35, "triangle", [1, 2]], [1047, 0.22, 0.6, "triangle", [1, 2, 3]]],
  gong: [[110, 0, 2.2, "sine", [1, 1.48, 2.1, 2.9]], [165, 0.02, 1.6, "sine", [1, 2.4]]],
  bip: [[660, 0, 0.12, "sine", [1]], [520, 0.13, 0.12, "sine", [1]]],
};

let audio;
function playSound(name, volume = 0.6) {
  const notes = SOUND_PRESETS[name];
  if (!notes || volume <= 0) return;
  try {
    audio = audio || new AudioContext();
    if (audio.state === "suspended") audio.resume();
    const out = audio.createGain();
    out.gain.value = 0.25 * volume;
    out.connect(audio.destination);
    for (const [freq, start, dur, type, partials] of notes) {
      partials.forEach((ratio, k) => {
        const t = audio.currentTime + start;
        const osc = audio.createOscillator();
        const gain = audio.createGain();
        osc.type = type;
        osc.frequency.value = freq * ratio;
        gain.gain.setValueAtTime(0.0001, t);
        gain.gain.exponentialRampToValueAtTime(1 / (k + 1), t + 0.015);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + dur / (1 + k * 0.6));
        osc.connect(gain).connect(out);
        osc.start(t);
        osc.stop(t + dur);
      });
    }
  } catch { /* pas de son : l'alerte visuelle suffit */ }
}

/* ------------------------------------------------------------------ réglages + thèmes */
const THEMES = [
  { id: "hextech", name: "Hextech", tag: "Le client d'origine : or, cristal et hexagones", sw: ["#0a0d13", "#151b26", "#c9a45f", "#43cfc1"] },
  { id: "noxus", name: "Noxus", tag: "L'empire : acier noirci, cramoisi, capitales romaines", sw: ["#0b0708", "#1c1112", "#d2463a", "#c9ced8"] },
  { id: "piltover", name: "Piltover", tag: "La cité du progrès : ivoire, laiton, art nouveau", sw: ["#f3ece0", "#fbf7f0", "#a8711f", "#1f8fbf"] },
  { id: "ionia", name: "Ionia", tag: "Les Terres premières : crépuscule, fleurs d'esprit", sw: ["#0e0a13", "#1c1522", "#e58fb4", "#6fd3a6"] },
];

function applyTheme(theme) {
  const t = THEMES.some((x) => x.id === theme) ? theme : "hextech";
  document.documentElement.dataset.realm = t;
  try { localStorage.setItem("lolbuilds-theme", t); } catch { /* sans stockage : thème appliqué au prochain état */ }
}
try { applyTheme(localStorage.getItem("lolbuilds-theme")); } catch { applyTheme("hextech"); }

function renderSettings() {
  const set = state?.settings;
  if (!set) return;
  const keep = (el) => el === document.activeElement;  // ne pas écraser un réglage en cours de modification
  $("#set-alert").checked = set.turnAlert;
  $("#set-focus").checked = set.alertFocus;
  $("#set-auto").checked = set.autoApply;
  if (!keep($("#set-volume"))) $("#set-volume").value = set.volume;
  $("#set-volume-val").textContent = `${Math.round(set.volume * 100)} %`;
  document.querySelectorAll("[data-setflash]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.setflash === set.flashKey)));
  const box = $("#set-sounds");
  if (!box.childElementCount) {
    box.innerHTML = SOUND_EVENTS.map(([ev, label]) => `
      <div class="set-row"><span class="set-txt"><b>${label}</b></span>
        <span class="set-sound"><select data-sound="${ev}" aria-label="Son : ${label}">${Object.entries(SOUND_LABEL).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
        <button type="button" class="btn ghost" data-testsound="${ev}" aria-label="Écouter">▶</button></span></div>`).join("");
  }
  box.querySelectorAll("select[data-sound]").forEach((sel) => { if (!keep(sel)) sel.value = set.sounds?.[sel.dataset.sound] || "none"; });
  $("#set-themes").innerHTML = THEMES.map((t) => `
    <button type="button" class="theme-card${set.theme === t.id ? " selected" : ""}" data-theme="${t.id}" aria-pressed="${set.theme === t.id}">
      <span class="theme-art${t.id === "hextech" ? " hex" : ""}" ${t.id === "hextech" ? "" : `style="background-image:url('/assets/realms/${t.id}/bg.jpg')"`}>
        ${t.id === "hextech" ? "" : `<i style="--m:url('/assets/realms/${t.id}/crest.png'); --c:${t.sw[2]}"></i>`}</span>
      <span class="theme-sw">${t.sw.map((c) => `<i style="background:${c}"></i>`).join("")}</span>
      <span class="theme-name">${t.name}</span><span class="theme-tag">${t.tag}</span></button>`).join("");
  applyTheme(set.theme);
  renderUpdate();
}

/** Section « Mise à jour » : version installée, dernière release GitHub, bouton d'installation. */
function renderUpdate() {
  const u = state?.update;
  if (!u) return;
  const latest = u.latest ? `version ${esc(u.latest)}` : "";
  const sub = {
    idle: `Version ${esc(u.current)}`,
    checking: `Version ${esc(u.current)} · recherche d'une nouvelle version…`,
    uptodate: `Version ${esc(u.current)} · c'est la dernière`,
    available: `Version ${esc(u.current)} installée · ${latest} disponible`,
    downloading: `Téléchargement de la ${latest} et vérification…`,
    installing: "Installation en cours : lolbuilds va se fermer puis se rouvrir tout seul.",
    error: `Version ${esc(u.current)} · ${esc(u.error || "vérification impossible")}`,
  }[u.status] || `Version ${esc(u.current)}`;
  $("#upd-title").textContent = u.status === "available" ? "Nouvelle version disponible" : "Version installée";
  $("#upd-sub").innerHTML = sub;
  const busy = ["checking", "downloading", "installing"].includes(u.status);
  const page = u.url ? `<a class="btn ghost" href="${esc(u.url)}" target="_blank" rel="noopener">Voir la release</a>` : "";
  let actions = `<button type="button" class="btn ghost" data-update="check"${busy ? " disabled" : ""}>Vérifier</button>`;
  if (u.status === "available") {
    actions = u.installable
      ? `${page}<button type="button" class="btn" data-update="install">Mettre à jour</button>`
      : `<a class="btn" href="${esc(u.url)}" target="_blank" rel="noopener">Télécharger la ${latest}</a>`;
  }
  $("#upd-actions").innerHTML = actions;
  const notes = $("#upd-notes");
  notes.hidden = u.status !== "available" || !u.notes;
  if (!notes.hidden) notes.textContent = u.notes;
}

/* ------------------------------------------------------------------ rendu global */
function render() {
  if (!state) return;
  renderTop();
  if (state.settings) applyTheme(state.settings.theme);
  if (view === "settings") renderSettings();
  if (view === "live") renderLive();
  if (state.toast && state.toast.id !== lastToast) {
    lastToast = state.toast.id;
    toast(state.toast.kind, state.toast.text);
  }
}

function renderTop() {
  const conn = $("#conn");
  const label = $("#conn-label");
  let s = state?.connection || "offline";
  let text = { waiting: "En attente du client", connected: "Client connecté", demo: "Démo", offline: "Serveur local arrêté" }[s];
  if (s === "connected" && state.champSelect) { s = "live"; text = "Champ select en direct"; }
  if (s === "connected" && state.phase === "InProgress") text = "Partie en cours";
  conn.dataset.state = s;
  label.textContent = text;
  if (!state?.settings) return;
  $("#opt-auto").checked = state.settings.autoApply;
  $("#opt-alert").checked = state.settings.turnAlert;
  for (const k of ["D", "F"]) $(`#flash-${k.toLowerCase()}`).setAttribute("aria-pressed", String(state.settings.flashKey === k));
  $("#rail-foot").innerHTML = `<b>${esc(S?.version?.split(".").slice(0, 2).join(".") || "—")}</b>patch<br><br><b>${day(state.lastPrefetch)}</b>builds`;
  const upd = state.update?.status === "available";
  $("#nav-settings").classList.toggle("has-update", upd);
  $("#nav-settings").title = upd ? `Nouvelle version ${state.update.latest} disponible` : "";
}

/* ------------------------------------------------------------------ vue champ select */
function renderLive() {
  const root = $("#view-live");
  const cur = state.current;
  const cs = state.champSelect;
  let html;
  timerEnds = cs?.timer?.endsAt || null;
  if (!cur) {
    html = cs ? turnHtml(cs) + draftHtml(cs, null) + banHtml(state.banSuggestions) + counterHtml(state.counterPicks, null) + emptyHtml("pick")
      : emptyHtml(state.connection);
  } else {
    const b = cur.build;
    const key = `${cur.championId}:${b?.role}:${b?.fetched_at}:${b?.variants?.length}`;
    const enter = key !== lastKey;
    lastKey = key;
    html = (cs ? turnHtml(cs) : "") + heroHtml(cur, cs) + (cs ? draftHtml(cs, cur) + banHtml(state.banSuggestions) : "")
      + (cs && !cur.locked ? counterHtml(state.counterPicks, cur) : "")
      + (b ? buildHtml(cur, b, cs, enter) : noBuildHtml(cur));
  }
  // Le client envoie des events en rafale : on ne touche au DOM que si le rendu change.
  if (html.replace(" enter", "") === lastHtml.replace(" enter", "")) return;
  lastHtml = html;
  root.innerHTML = html;
  tickTimer();
}

function emptyHtml(kind) {
  const hex = `<svg class="hexwait" viewBox="0 0 80 80" aria-hidden="true">
      <g class="spin"><path d="M40 4 71 22v36L40 76 9 58V22z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="6 8"/></g>
      <path d="M40 22 56 31v18L40 58 24 49V31z" fill="currentColor" opacity=".18"/><path d="M40 30 48 34.6v9.2L40 48.5 32 43.8v-9.2z" fill="currentColor"/></svg>`;
  const facts = `<div class="facts"><div><b>${int(state.libraryCount ?? libraryCountGuess())}</b>builds en cache</div><div><b>${day(state.lastPrefetch)}</b>dernière mise à jour</div></div>`;
  const content = {
    waiting: [`En attente du client League`, `Lance League of Legends : l'application se connecte toute seule et suit ta sélection de champion.`],
    offline: [`Serveur local arrêté`, `Relance lolbuilds pour retrouver tes builds.`],
    connected: [`Prêt pour la prochaine partie`, `Dès que la sélection des champions commence, tes builds s'affichent ici. ${state.settings.autoApply ? "Le build préféré sera appliqué automatiquement." : "Clique sur un build pour l'appliquer."}`],
    demo: [`Démo`, esc(state.notice || "Préparation du faux champ select…")],
    pick: [`Choisis ton champion`, `Survole ou verrouille un champion : ses builds apparaissent ici avec leur winrate.`],
  }[kind] || [`Prêt`, ``];
  const pad = kind === "pick" ? ' style="min-height: 320px"' : "";
  return `<div class="empty"${pad}><div class="empty-inner">${hex}<h2>${content[0]}</h2><p>${content[1]}</p>
    ${kind === "pick" ? "" : facts}
    ${kind === "pick" ? "" : `<button type="button" class="btn" data-goto="library">Parcourir les builds</button>`}</div></div>`;
}

function libraryCountGuess() { return library.length || 0; }

function heroHtml(cur, cs) {
  const c = champ(cur.championId);
  const b = cur.build;
  timerEnds = cs?.timer?.endsAt || null;
  const timer = timerEnds ? `<span class="timer num js-timer"></span>` : "";
  const phase = cs ? (cur.locked ? "Champion verrouillé" : cur.preview ? "Aperçu · bon pick" : "Champion survolé") : "Aperçu";
  const roles = (cur.roles.length ? cur.roles : [cur.role]).filter(Boolean);
  const tabs = roles.map((r) => `<button type="button" class="role-tab" data-role="${r}" aria-pressed="${r === cur.role}">
      ${roleIcon(r)}${ROLE_LABEL[r] || r}${r === cur.assigned ? '<span class="assigned" title="Rôle assigné"></span>' : ""}</button>`).join("");
  const meta = b ? `<div class="meta num">
      <span>Winrate <b class="${wrClass(b.winrate)}">${pct(b.winrate)}</b></span>
      <span><b>${int(b.sample_size)}</b> parties${b.source === "opgg" ? " · OP.GG" : ""}</span>
      <span>Patch <b>${esc(b.patch)}</b></span>
      <span>Données du <b>${day(b.fetched_at)}</b></span></div>` : "";
  const fetching = cur.fetching ? `<div class="meta"><span class="loading">Récupération du build sur OP.GG…</span></div>` : "";
  return `<header class="hero">
    <div class="hero-splash" style="background-image:url('${asset("splash", cur.championId)}')"></div>
    <div class="hero-top"><span class="eyebrow">${phase}</span>${timer}</div>
    <div><h1 class="hero-name">${esc(c?.name || cur.champion || "Champion")}</h1>
    <p class="hero-title">${esc(c?.title || "")}</p></div>
    <div class="hero-row"><div class="roles">${tabs}</div>${fetching || meta}</div>
  </header>`;
}

function draftHtml(cs, cur) {
  const cp = state.counterPicks;
  const opp = cur?.opponent || (cp ? { championId: cp.enemyId } : null);
  const slot = (p, enemy) => {
    const id = p.championId || p.intent;
    const isOpp = enemy && opp && id === opp.championId;
    const cls = ["slot", p.isMe ? "me" : "", !p.championId && p.intent ? "intent" : "", isOpp ? "opp" : ""].join(" ");
    const pos = !enemy && p.position ? `<span class="pos">${roleIcon(p.position)}</span>` : "";
    const pick = enemy && id ? ` data-opponent="${id}" role="button" aria-label="Adversaire : ${esc(champ(id)?.name || "")}"` : "";
    return `<div class="${cls}" ${id ? tipAttr("champion", id) : ""}${pick}>${id ? img("champion", id, "") : ""}${pos}</div>`;
  };
  const sorted = [...cs.allies].sort((a, b) => ROLE_ORDER.indexOf(a.position) - ROLE_ORDER.indexOf(b.position));
  const bans = cs.bans.length ? `<div class="bans"><span>Bans</span>${cs.bans.map((b) => `<div class="slot" ${tipAttr("champion", b.championId)}>${img("champion", b.championId, "")}</div>`).join("")}</div>` : "<div></div>";
  return `<div class="draft"><div class="team">${sorted.map((p) => slot(p, false)).join("")}</div>
    <span class="vs">VS</span><div class="team enemy">${cs.enemies.map((p) => slot(p, true)).join("")}</div>${bans}</div>
    ${cur ? matchupHtml(cs, opp) : ""}`;
}

function turnHtml(cs) {
  const t = cs.turn;
  if (!t) return "";
  const what = t.type === "ban" ? "bannir" : "choisir ton champion";
  return `<div class="turn ${t.type}" role="status"><span class="turn-fill js-turn-fill" aria-hidden="true"></span><span class="turn-dot"></span><b>À toi de ${what}</b>
    ${timerEnds ? '<span class="timer num js-timer"></span>' : ""}</div>`;
}

function banHtml(bs) {
  if (!bs) return "";
  const role = ROLE_LABEL[bs.role] || "";
  const title = bs.mode === "threats" ? `Bans suggérés · menaces pour ${esc(champ(bs.championId)?.name || "")}` : `Bans suggérés · les plus forts en ${role}`;
  const note = bs.mode === "threats" ? "winrate de ces champions contre le tien (OP.GG)" : "tier list OP.GG du moment";
  const body = !bs.picks.length ? '<p class="cp-msg dim">Rien à suggérer : tous les candidats sont déjà bannis ou pris.</p>'
    : `<div class="cp-list">${bs.picks.map((p) => `
      <div class="cp ban" ${tipAttr("champion", p.championId)}>
        ${img("champion", p.championId, "")}
        <span class="cp-txt"><span class="cp-name">${esc(champ(p.championId)?.name || "")}</span>
          <span class="cp-games num">${bs.mode === "threats" ? `${int(p.games)} parties` : `Tier ${p.tier} · ${Math.round(p.banRate * 100)} % ban`}</span></span>
        <span class="cp-wr num ${wrClass(p.winrate)}">${pct(p.winrate)}</span>
      </div>`).join("")}</div>`;
  return `<section class="section counters bans-sugg"><div class="section-head"><h2 class="section-title">${title}</h2>
    <span class="section-note">${role} · ${note}</span></div>${body}</section>`;
}

function counterHtml(cp, cur) {
  if (!cp) return "";
  const enemy = esc(champ(cp.enemyId)?.name || "");
  const how = cp.guessed ? "adversaire deviné" : "adversaire choisi à la main";
  let body;
  if (cp.status === "loading") {
    body = '<p class="cp-msg"><span class="loading">Recherche des meilleurs picks sur OP.GG…</span></p>';
  } else if (!cp.picks.length) {
    body = '<p class="cp-msg dim">Aucun champion jouable n\'a assez de parties gagnantes contre lui.</p>';
  } else {
    body = `<div class="cp-list">${cp.picks.map((p) => `
      <button type="button" class="cp${cur?.preview && cur.championId === p.championId ? " selected" : ""}" data-preview="${p.championId}" aria-pressed="${Boolean(cur?.preview && cur.championId === p.championId)}">
        ${img("champion", p.championId, "")}
        <span class="cp-txt"><span class="cp-name">${esc(champ(p.championId)?.name || "")}</span>
          <span class="cp-games num">${int(p.games)} parties${p.main ? ' · <b>ton champion</b>' : ""}</span></span>
        <span class="cp-wr num ${wrClass(p.winrate)}">${pct(p.winrate)}</span>
      </button>`).join("")}</div>`;
  }
  return `<section class="section counters"><div class="section-head"><h2 class="section-title">Bons picks contre ${enemy}</h2>
    <span class="section-note">${ROLE_LABEL[cp.role] || ""} · ${how} · winrate dans ce duel · clique pour voir le build</span></div>${body}</section>`;
}

function matchupHtml(cs, opp) {
  const anyEnemy = cs.enemies.some((e) => e.championId);
  if (!opp) {
    return `<div class="matchup"><span class="dim">${anyEnemy ? "Adversaire de lane non détecté : clique sur un ennemi pour voir les builds contre lui." : "Les builds contre ton adversaire de lane apparaîtront dès qu'il sera choisi."}</span></div>`;
  }
  const name = esc(champ(opp.championId)?.name || "");
  const status = { loading: '<span class="loading">Récupération sur OP.GG…</span>', empty: '<span class="dim">pas assez de parties pour ce duel</span>' }[opp.status] || "";
  const how = opp.guessed ? "deviné d'après les rôles OP.GG · clique sur un autre ennemi pour changer" : "choisi à la main · reclique dessus pour revenir à la détection";
  return `<div class="matchup">${img("champion", opp.championId, "")}<span>Contre <b>${name}</b></span>${status}<span class="dim">${how}</span></div>`;
}

function noBuildHtml(cur) {
  const c = champ(cur.championId);
  const others = cur.roles.length ? ` Builds disponibles pour : ${cur.roles.map((r) => ROLE_LABEL[r]).join(", ")}.` : "";
  const title = `${esc(c?.name || cur.champion)}${cur.role ? " " + (ROLE_LABEL[cur.role] || "") : ""}`;
  if (cur.fetching) {
    return `<div class="empty" style="min-height: 280px"><div class="empty-inner"><h2>Récupération du build ${title}…</h2>
      <p>OP.GG répond en une ou deux secondes. Le build est ensuite gardé pour la journée.</p></div></div>`;
  }
  return `<div class="empty" style="min-height: 280px"><div class="empty-inner">
    <h2>Pas de build pour ${title}</h2>
    <p>OP.GG n'a pas assez de parties pour ce champion dans ce rôle, ou il n'a pas répondu.${others}</p></div></div>`;
}

function variantsOf(b) {
  if (b.variants?.length) return b.variants;
  return [{ primaryStyle: b.primaryStyle, subStyle: b.subStyle, perks: b.perks, spells: b.spells, blocks: b.itemSet.blocks,
            games: b.sample_size, winrate: b.winrate, pick_rate: 1, tags: [], details: b.details }];
}

function buildHtml(cur, b, cs, enter) {
  const variants = variantsOf(b);
  const sel = Math.min(state.selection.variant || 0, variants.length - 1);
  const applied = state.applied;
  const flashKey = state.settings.flashKey;

  const cards = variants.map((v, i) => {
    const ks = perk(v.perks[0]);
    const core = (v.blocks.find((x) => x.key === "core") || v.blocks.find((x) => /^Core/.test(x.type)))?.items || [];
    const boots = (v.blocks.find((x) => x.key === "boots") || v.blocks.find((x) => /^Bottes/.test(x.type)))?.items?.[0];
    const sp = orient(v.spells, flashKey);
    const tags = [...(v.tags || []).map((t) => `<span class="tag${t === "Le plus joué" ? " alt" : t.startsWith("Contre ") ? " vs" : ""}">${esc(t)}</span>`),
      v.details?.runes?.fallback ? '<span class="tag warn">Échantillon faible</span>' : ""].join("");
    const isApplied = applied && applied.variant === i;
    const action = !cs ? "Voir" : isApplied ? "Appliqué" : state.busy && i === sel ? "Application…" : "Appliquer";
    const items = core.map((it, k) => (k ? '<svg class="arrow" viewBox="0 0 10 10"><path d="m3 2 3 3-3 3" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>' : "") +
      img("item", it.id, "icon", tipAttr("item", it.id))).join("");
    return `<button type="button" class="vcard${i === sel ? " selected" : ""}${isApplied ? " applied" : ""}" data-variant="${i}" aria-pressed="${i === sel}">
      <div class="vin">
        <div class="vhead">
          ${img("perk", v.perks[0], "keystone", tipAttr("perk", v.perks[0]))}
          <div><div class="vname">${esc(ks?.name || "Runes")}</div>
            <div class="vtrees">${img("perk", v.primaryStyle, "")}${esc(style(v.primaryStyle)?.name || "")}<span>·</span>${img("perk", v.subStyle, "")}${esc(style(v.subStyle)?.name || "")}</div></div>
          <div class="vwr num"><strong class="${wrClass(v.winrate)}">${pct(v.winrate)}</strong><span>winrate</span></div>
        </div>
        <div class="tags">${tags}</div>
        <div class="pickbar"><div class="pickbar-track"><div class="pickbar-fill" style="width:${Math.max(2, v.pick_rate * 100)}%"></div></div>
          <div class="pickbar-legend num"><span>Pick ${pct(v.pick_rate, 0)}</span><span>${int(v.games)} parties</span></div></div>
        <div class="vitems">${items}<span class="gap"></span>${boots ? img("item", boots.id, "icon", tipAttr("item", boots.id)) : ""}</div>
        <div class="vfoot"><div class="spells">${sp.map((s) => img("spell", s, "icon", tipAttr("spell", s))).join("")}</div>
          <span class="vaction">${action}<span class="num"> · ${i + 1}</span></span></div>
      </div></button>`;
  }).join("");

  const v = variants[sel];
  const note = cs ? appliedBarHtml(applied, variants) : `<div class="preview-note">Aperçu : ce build s'appliquera pendant la sélection des champions${state.settings.autoApply ? " (automatiquement)" : ""}.</div>`;
  return `${note}
    <section class="section"><div class="section-head"><h2 class="section-title">Propositions de build</h2>
      <span class="section-note">Triées par winrate · touches 1 à ${variants.length} pour choisir</span></div>
      <div class="variants${enter ? " enter" : ""}">${cards}</div></section>
    <div class="detail">
      <div class="panel">${runesHtml(v)}</div>
      <div class="panel" style="display:grid; gap:22px; align-content:start">${itemsHtml(v)}${spellsHtml(b, v, cs)}</div>
    </div>`;
}

function appliedBarHtml(applied, variants) {
  if (!applied) {
    return `<div class="applied-bar"><span>${state.settings.autoApply ? "Le build préféré sera appliqué dès que ton champion sera verrouillé." : "Clique sur un build pour l'envoyer au client."}</span></div>`;
  }
  // Étapes désactivées dans config.toml ([champselect] apply_*) : absentes de `steps`, pas affichées.
  const step = (ok, label) => ok === undefined ? "" : `<span class="step ${ok ? "ok" : "ko"}">${ok ? "✓" : "✕"} <span>${label}</span></span>`;
  const ks = perk(variants[applied.variant]?.perks?.[0]);
  return `<div class="applied-bar">${step(applied.steps.runes, "Page de runes")}${step(applied.steps.spells, "Sorts d'invocateur")}${step(applied.steps.items, "Item set")}
    <span class="spacer"></span><span>${applied.auto ? "Appliqué automatiquement" : "Appliqué"} · ${esc(ks?.name || "")}</span></div>`;
}

function runesHtml(v) {
  const p = v.perks;
  const rune = (id, key) => `<div class="rune${key ? " key" : ""}" ${tipAttr("perk", id)}>${img("perk", id, "")}<span class="rune-name">${esc(perk(id)?.name || id)}</span></div>`;
  const shards = p.slice(6, 9).map((id) => {
    const s = perk(id);
    return `<span class="shard" ${tipAttr("perk", id)}><i>${SHARD_ABBR[s?.shard] || "+"}</i>${esc(s?.name || id)}</span>`;
  }).join("");
  return `<h3>Runes</h3><div class="runes">
    <div><div class="tree-head">${img("perk", v.primaryStyle, "")}${esc(style(v.primaryStyle)?.name || "")}</div>
      <div class="rune-list">${rune(p[0], true)}${p.slice(1, 4).map((id) => rune(id)).join("")}</div></div>
    <div><div class="tree-head">${img("perk", v.subStyle, "")}${esc(style(v.subStyle)?.name || "")}</div>
      <div class="rune-list">${p.slice(4, 6).map((id) => rune(id)).join("")}</div>
      <div class="shards">${shards}</div></div>
  </div>`;
}

function itemsHtml(v) {
  const titles = { starter: "Départ", core: "Core", boots: "Bottes", situational: "Situationnel", consumables: "Consommables" };
  const blocks = v.blocks.map((bl) => {
    const key = bl.key || "";
    const stat = (bl.type.match(/\((.*)\)/) || [])[1] || "";
    const items = bl.items.map((it, k) => `<span class="item" ${tipAttr("item", it.id)}>${img("item", it.id)}
        ${key === "core" ? `<span class="step">${k + 1}</span>` : ""}${it.count > 1 ? `<span class="count">${it.count}</span>` : ""}</span>`).join("");
    return `<div><div class="block-head"><b>${esc(titles[key] || bl.type.replace(/\s*\(.*\)/, ""))}</b><span class="num">${esc(stat)}</span></div>
      <div class="block-items">${items}</div></div>`;
  }).join("");
  return `<div><h3>Items</h3><div class="blocks">${blocks}</div></div>`;
}

function spellsHtml(b, v, cs) {
  const flashKey = state.settings.flashKey;
  const opts = b.spell_options?.length ? b.spell_options : [{ spells: v.spells, games: v.games, winrate: v.winrate, pick_rate: v.pick_rate }];
  const same = (a, c) => a.length === c.length && a.every((x) => c.includes(x));
  const active = state.selection.spells ?? opts.findIndex((o) => same(o.spells, v.spells));
  const rows = opts.map((o, i) => {
    const sp = orient(o.spells, flashKey);
    return `<button type="button" class="spell-opt${i === active ? " active" : ""}" data-spells="${i}" ${cs ? "" : "disabled"}>
      <span class="pair">${sp.map((s) => img("spell", s, "icon", tipAttr("spell", s))).join("")}</span>
      <span class="label">${sp.map((s) => esc(spell(s)?.name || s)).join(" + ")}<small class="num">${int(o.games)} parties · pick ${pct(o.pick_rate, 0)}</small></span>
      <span class="wr num ${wrClass(o.winrate)}">${pct(o.winrate)}<small>winrate</small></span></button>`;
  }).join("");
  const hint = flashKey ? `<div class="keyhint">Flash placé sur <kbd>${flashKey}</kbd></div>` : "";
  return `<div><h3>Sorts d'invocateur</h3><div class="spell-opts">${rows}</div>${hint}</div>`;
}

/* ------------------------------------------------------------------ bibliothèque */
async function loadLibrary() {
  try {
    library = await (await fetch("/api/library")).json();
  } catch { library = []; }
  renderLibrary();
  render();  // le compteur « builds en cache » de l'écran d'attente en dépend
}

function renderLibrary() {
  const q = $("#lib-search").value.trim().toLowerCase();
  const rows = library
    .filter((r) => !libRole || r.role === libRole)
    .filter((r) => !q || (champ(r.championId)?.name || r.champion).toLowerCase().includes(q))
    .sort((a, b) => (champ(a.championId)?.name || a.champion).localeCompare(champ(b.championId)?.name || b.champion, "fr"));
  const today = new Date().toISOString().slice(0, 10);
  $("#lib-sub").textContent = library.length
    ? `${library.length} builds · patch ${library[0].patch} · clique sur une ligne pour voir les propositions`
    : "Aucun build pour l'instant : lance le prefetch.";
  $("#lib-roles").innerHTML = ROLE_ORDER.map((r) => `<button type="button" class="chip" data-librole="${r}" aria-pressed="${libRole === r}" title="${ROLE_LABEL[r]}" aria-label="${ROLE_LABEL[r]}">${roleIcon(r)}</button>`).join("");
  const header = `<div class="lib-row header"><span></span><span>Champion</span><span>Rôle</span><span>Winrate</span><span>Parties</span><span>Builds</span><span>Mis à jour</span></div>`;
  $("#lib-table").innerHTML = header + rows.map((r) => `
    <button type="button" class="lib-row" data-open="${r.championId}" data-role="${r.role}">
      ${img("champion", r.championId)}
      <span class="lib-name">${esc(champ(r.championId)?.name || r.champion)}</span>
      <span class="lib-role">${roleIcon(r.role)}${r.roleLabel}</span>
      <span class="lib-wr num ${wrClass(r.winrate)}">${pct(r.winrate)}</span>
      <span class="lib-dim num">${int(r.games)}</span>
      <span class="lib-key">${img("perk", r.keystone, "", tipAttr("perk", r.keystone))}<span class="lib-dim num">×${r.variants}</span></span>
      <span class="lib-dim ${r.fetchedAt !== today ? "stale" : ""}">${day(r.fetchedAt)}</span>
    </button>`).join("");
}

function setView(v) {
  view = v;
  $("#view-live").hidden = v !== "live";
  $("#view-library").hidden = v !== "library";
  $("#view-settings").hidden = v !== "settings";
  document.querySelectorAll(".rail-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  if (v === "library") loadLibrary();
  else render();
}

/* ------------------------------------------------------------------ interactions */
document.addEventListener("click", async (e) => {
  const t = e.target.closest("[data-variant],[data-spells],[data-role],[data-goto],[data-open],[data-view],[data-librole],[data-key],[data-opponent],[data-preview]");
  if (!t) return;
  if (t.dataset.preview) {
    post("/api/preview", { championId: Number(t.dataset.preview) });
  } else if (t.dataset.opponent) {
    post("/api/opponent", { championId: Number(t.dataset.opponent) });
  } else if (t.dataset.open) {
    await post("/api/open", { championId: Number(t.dataset.open), role: t.dataset.role });
    lastKey = "";
    setView("live");
  } else if (t.dataset.variant !== undefined) {
    choose(Number(t.dataset.variant));
  } else if (t.dataset.spells !== undefined) {
    post("/api/spells", { option: Number(t.dataset.spells) });
  } else if (t.dataset.role && t.classList.contains("role-tab")) {
    if (t.getAttribute("aria-pressed") !== "true") post("/api/open", { championId: state.current.championId, role: t.dataset.role });
  } else if (t.dataset.goto) {
    setView(t.dataset.goto);
  } else if (t.dataset.view) {
    setView(t.dataset.view);
  } else if (t.dataset.librole) {
    libRole = libRole === t.dataset.librole ? "" : t.dataset.librole;
    renderLibrary();
  } else if (t.dataset.key) {
    post("/api/settings", { flashKey: state.settings.flashKey === t.dataset.key ? "" : t.dataset.key });
  }
});

function choose(i) {
  if (!state?.current?.build) return;
  const n = variantsOf(state.current.build).length;
  if (i < 0 || i >= n) return;
  post("/api/select", { variant: i, apply: Boolean(state.champSelect) });
}

document.addEventListener("keydown", (e) => {
  if (e.target.matches("input") || view !== "live") return;
  if (/^[1-9]$/.test(e.key)) choose(Number(e.key) - 1);
});

$("#opt-auto").addEventListener("change", (e) => post("/api/settings", { autoApply: e.target.checked }));
$("#opt-alert").addEventListener("change", (e) => post("/api/settings", { turnAlert: e.target.checked }));
$("#set-alert").addEventListener("change", (e) => post("/api/settings", { turnAlert: e.target.checked }));
$("#set-focus").addEventListener("change", (e) => post("/api/settings", { alertFocus: e.target.checked }));
$("#set-auto").addEventListener("change", (e) => post("/api/settings", { autoApply: e.target.checked }));
$("#set-volume").addEventListener("input", (e) => { $("#set-volume-val").textContent = `${Math.round(e.target.value * 100)} %`; });
$("#set-volume").addEventListener("change", (e) => {
  post("/api/settings", { volume: Number(e.target.value) });
  playSound("cloche", Number(e.target.value));
});
$("#set-sounds").addEventListener("change", (e) => {
  const sel = e.target.closest("select[data-sound]");
  if (!sel) return;
  post("/api/settings", { sounds: { [sel.dataset.sound]: sel.value } });
  playSound(sel.value, state?.settings?.volume);
});
$("#view-settings").addEventListener("click", (e) => {
  const test = e.target.closest("[data-testsound]");
  if (test) playSound($(`select[data-sound="${test.dataset.testsound}"]`).value, state?.settings?.volume);
  const theme = e.target.closest("[data-theme]");
  if (theme) { applyTheme(theme.dataset.theme); post("/api/settings", { theme: theme.dataset.theme }); }
  const flash = e.target.closest("[data-setflash]");
  if (flash) post("/api/settings", { flashKey: flash.dataset.setflash });
  const upd = e.target.closest("[data-update]");
  if (upd) post(`/api/update/${upd.dataset.update}`, {});
});
$("#lib-search").addEventListener("input", renderLibrary);

/* ------------------------------------------------------------------ minuteur */
function tickTimer() {
  if (!timerEnds) return;
  const left = Math.max(0, Math.round((timerEnds - Date.now()) / 1000));
  for (const el of document.querySelectorAll(".js-timer")) {
    el.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
    el.classList.toggle("low", left <= 10);
  }
  // Barre du tour : se remplit de gauche à droite à mesure que le temps s'écoule.
  const lcuTotal = state?.champSelect?.timer?.total;
  const total = lcuTotal && lcuTotal >= timerEnds - Date.now() - 1000 ? lcuTotal : turnTotal;
  for (const el of document.querySelectorAll(".js-turn-fill")) {
    const done = total ? Math.min(1, Math.max(0, 1 - (timerEnds - Date.now()) / total)) : 0;
    el.style.transform = `scaleX(${done})`;
    el.classList.toggle("low", left <= 10);
  }
}
setInterval(tickTimer, 250);

/* ------------------------------------------------------------------ infobulles */
const tip = $("#tooltip");
document.addEventListener("mouseover", (e) => {
  const t = e.target.closest("[data-tip]");
  if (!t) { tip.hidden = true; return; }
  const id = t.dataset.id;
  let html = "";
  if (t.dataset.tip === "item") {
    const it = item(id);
    html = it ? `<b>${esc(it.name)}</b><em class="num">${int(it.gold)} or</em>${esc(it.text)}` : "";
  } else if (t.dataset.tip === "perk") {
    const p = perk(id);
    html = p ? `<b>${esc(p.name)}</b>${p.shard ? "Fragment de stats" : esc(p.text)}` : "";
  } else if (t.dataset.tip === "spell") {
    const s = spell(id);
    html = s ? `<b>${esc(s.name)}</b>${esc(s.text)}` : "";
  } else if (t.dataset.tip === "champion") {
    const c = champ(id);
    html = c ? `<b>${esc(c.name)}</b>${esc(c.title)}` : "";
  }
  tip.innerHTML = html;
  tip.hidden = !html;
});
document.addEventListener("mousemove", (e) => {
  if (tip.hidden) return;
  const r = tip.getBoundingClientRect();
  const x = Math.min(e.clientX + 14, innerWidth - r.width - 8);
  const y = e.clientY + 18 + r.height > innerHeight ? e.clientY - r.height - 12 : e.clientY + 18;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
});

/* ------------------------------------------------------------------ toasts */
function toast(kind, text) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  $("#toasts").append(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 350); }, 2600);
}

/* ------------------------------------------------------------------ fenêtre de bureau */
if (new URLSearchParams(location.search).has("desktop")) {
  $("#winctl").hidden = false;
  const api = () => window.pywebview?.api;
  $("#win-min").onclick = () => api()?.minimize();
  $("#win-close").onclick = () => api()?.close();
  $("#win-pin").onclick = async () => {
    const on = await api()?.toggle_on_top();
    $("#win-pin").setAttribute("aria-pressed", String(Boolean(on)));
  };
}

/* ------------------------------------------------------------------ démarrage */
async function loadStatic() {
  try {
    const r = await fetch("/api/static");
    if (r.ok) S = await r.json();
  } catch { /* noms affichés en ids si les données manquent */ }
}

(async () => {
  await loadStatic();
  connect();
  loadLibrary();
})();

// ============================================================================
// Studio Podcast — interface
// ============================================================================
const state = {
  me: null, folders: [], intros: [], current: null, view: "home",
  jobs: [], hist: { items: [], total: 0 }, home: { sig: "", q: null }, detail: null, users: [],
  expanded: new Set(), lastActive: 0, timers: {},
};
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const can = (p) => !!state.me && (state.me.is_admin || state.me.permissions.includes(p));
const fmtSize = (b) => (b ? (b / 1e6).toFixed(1) + " Mo" : "");
const fmtDate = (iso) => iso ? new Date(/Z|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z")
  .toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" }) : "—";
const LABELS = { pending: "En attente", running: "En cours", done: "Terminé", error: "Erreur" };

try { JSON.parse(localStorage.getItem("expanded") || "[]").forEach((id) => state.expanded.add(id)); } catch {}
const saveExpanded = () => { try { localStorage.setItem("expanded", JSON.stringify([...state.expanded])); } catch {} };

// ---------- Icônes (SVG en ligne, style trait) ----------
const ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  history: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.8c1.8.7 3 2.4 3.5 5.2"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  music: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
  play: '<path d="M7 4.5v15l13-7.5z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  download: '<path d="M12 3v12m0 0-4.5-4.5M12 15l4.5-4.5M4 20h16"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  retry: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M16 7l3 3"/>',
  logout: '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  up: '<path d="M12 19V5M5.5 11.5 12 5l6.5 6.5"/>',
  grid: '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
  move: '<path d="M5 12h14M14 7l5 5-5 5"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.7L20 8.5"/><path d="M20 4v4.5h-4.5"/>',
  open: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  edit: '<path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3zM13.5 6.5l3 3"/>',
  scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
  upload: '<path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M4 20h16"/>',
};
const ic = (n) => `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ""}</svg>`;
const hydrateIcons = (root = document) => root.querySelectorAll("[data-ic]").forEach((el) => { el.innerHTML = ic(el.dataset.ic); });

// ---------- Thème clair / sombre (sans choix : celui du système) ----------
const systemDark = matchMedia("(prefers-color-scheme: dark)");
const currentTheme = () => document.documentElement.dataset.theme || (systemDark.matches ? "dark" : "light");
function paintThemeButtons() {
  const dark = currentTheme() === "dark";
  document.querySelectorAll("[data-theme-toggle]").forEach((b) => {
    b.innerHTML = ic(dark ? "sun" : "moon");
    b.title = dark ? "Passer au thème clair" : "Passer au thème sombre";
  });
}
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-theme-toggle]")) return;
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch {}
  paintThemeButtons();
});
systemDark.addEventListener("change", paintThemeButtons);
paintThemeButtons();

// ---------- Réseau ----------
async function api(path, opts = {}) {
  const isForm = opts.body instanceof FormData;
  const res = await fetch(path, {
    ...opts,
    headers: opts.body && !isForm ? { "content-type": "application/json" } : {},
    body: opts.body && !isForm ? JSON.stringify(opts.body) : opts.body,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && !path.startsWith("/api/auth/login")) {
    if (state.me) showLogin("Votre session a expiré, veuillez vous reconnecter.");
    throw new Error(data.detail || "Non connecté");
  }
  if (!res.ok) throw new Error(data.detail || `Erreur ${res.status}`);
  return data;
}

// ---------- Notifications, chargement ----------
function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + (kind === true ? "error" : kind);
  t.textContent = msg;
  $("toasts").appendChild(t);
  setTimeout(() => t.remove(), kind === true || kind === "error" ? 6000 : 3200);
}

async function busy(btn, fn) {  // spinner + bouton bloqué pendant l'action
  if (!btn) return fn();
  btn.classList.add("loading");
  btn.disabled = true;
  try { return await fn(); } finally { btn.classList.remove("loading"); btn.disabled = false; }
}

// ---------- Fenêtres modales (remplacent prompt / confirm / alert) ----------
// buttons : [{label, kind, value, primary}] ; `primary` lance submit(dlg) avec loader, les erreurs s'affichent dans la fenêtre.
function modal({ title, icon, iconKind = "", body = "", buttons, submit, wide = false, onMount }) {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    if (wide) dlg.className = "wide";
    dlg.innerHTML = `
      ${icon ? `<div class="modal-icon ${iconKind}">${icon}</div>` : ""}
      <div class="dialog-head"><h3>${esc(title)}</h3><button class="icon-btn" data-close aria-label="Fermer">✕</button></div>
      <form class="modal-body" novalidate>${body}<div class="form-error" hidden></div></form>
      <div class="dialog-foot">${buttons.map((b, i) => `<button type="button" class="btn ${b.kind || ""}" data-i="${i}">${esc(b.label)}</button>`).join("")}</div>`;
    document.body.appendChild(dlg);
    let done = false;
    const close = (v) => { if (done) return; done = true; dlg.close(); dlg.remove(); resolve(v); };
    const errBox = dlg.querySelector(".form-error");
    const click = async (i) => {
      const b = buttons[i];
      if (!b.primary) return close(b.value ?? null);
      if (!submit) return close(b.value ?? true);
      errBox.hidden = true;
      try { close((await busy(dlg.querySelector(`[data-i="${i}"]`), () => submit(dlg))) ?? true); }
      catch (e) { errBox.textContent = e.message; errBox.hidden = false; }
    };
    dlg.querySelectorAll("[data-i]").forEach((btn) => (btn.onclick = () => click(+btn.dataset.i)));
    dlg.querySelector("form").onsubmit = (e) => { e.preventDefault(); const i = buttons.findIndex((b) => b.primary); if (i >= 0) click(i); };
    dlg.querySelector("[data-close]").onclick = () => close(null);
    dlg.addEventListener("cancel", (e) => { e.preventDefault(); close(null); });
    onMount?.(dlg);
    dlg.showModal();
    dlg.querySelector("input:not([disabled]):not([type=checkbox]), select")?.focus();
  });
}

const confirmBox = async ({ title, message, confirmLabel = "Confirmer", danger = false }) =>
  (await modal({
    title, icon: danger ? "🗑️" : "❓", iconKind: danger ? "danger" : "",
    body: `<p>${message}</p>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: false },
      { label: confirmLabel, kind: danger ? "danger-fill" : "", primary: true, value: true }],
  })) === true;

const alertBox = ({ title, message, kind = "info" }) =>
  modal({ title, icon: kind === "danger" ? "⚠️" : kind === "success" ? "✅" : "ℹ️", iconKind: kind,
    body: `<p>${message}</p>`, buttons: [{ label: "OK", primary: true }] });

const R2_HINT = "Sur R2, les fichiers sont déplacés pour suivre : les anciens liens de partage vers ces fichiers cesseront de fonctionner.";
const r2Hint = () => (state.status?.r2 ? `<p class="hint">${R2_HINT}</p>` : "");

const promptBox = ({ title, label, value = "", placeholder = "", confirmLabel = "Enregistrer", submit, hint = "" }) =>
  modal({
    title, body: `<label>${esc(label)}<input name="v" value="${esc(value)}" placeholder="${esc(placeholder)}" autocomplete="off"></label>${hint}`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: confirmLabel, primary: true }],
    submit: async (dlg) => {
      const v = dlg.querySelector("[name=v]").value.trim();
      if (!v) throw new Error("Ce champ est obligatoire");
      return submit ? ((await submit(v)) ?? v) : v;
    },
  });

// ---------- Connexion ----------
function showLogin(message = "") {
  state.me = null;
  Object.values(state.timers).forEach(clearTimeout);
  $("boot").hidden = true;
  $("app").hidden = true;
  document.querySelectorAll("dialog[open]").forEach((d) => d.close());
  $("loginScreen").hidden = false;
  $("loginError").hidden = !message;
  $("loginError").textContent = message;
  $("loginForm").password.value = "";
  $("loginForm").username.focus();
}

$("loginForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  $("loginError").hidden = true;
  try {
    await busy(f.querySelector("button"), async () => {
      state.me = await api("/api/auth/login", { method: "POST", body: { username: f.username.value, password: f.password.value } });
      state.me = await api("/api/auth/me");
      await startApp();
    });
  } catch (err) { state.me = null; $("loginError").textContent = err.message; $("loginError").hidden = false; }
};

$("userBtn").onclick = (e) => { e.stopPropagation(); $("userMenu").hidden = !$("userMenu").hidden; };
document.addEventListener("click", () => ($("userMenu").hidden = true));
$("userMenu").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-user]");
  if (!b) return;
  if (b.dataset.user === "logout") {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    showLogin();
  } else {
    await modal({
      title: "Changer mon mot de passe",
      body: `<label>Mot de passe actuel<input type="password" name="current" autocomplete="current-password"></label>
             <label>Nouveau mot de passe (8 caractères minimum)<input type="password" name="new" autocomplete="new-password"></label>
             <label>Confirmer<input type="password" name="confirm" autocomplete="new-password"></label>`,
      buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Enregistrer", primary: true }],
      submit: async (dlg) => {
        const v = (n) => dlg.querySelector(`[name=${n}]`).value;
        if (v("new") !== v("confirm")) throw new Error("La confirmation ne correspond pas");
        await api("/api/auth/password", { method: "POST", body: { current: v("current"), new: v("new") } });
        toast("Mot de passe modifié", "ok");
      },
    });
  }
});

// ---------- Démarrage et navigation ----------
async function startApp() {
  $("loginScreen").hidden = true;
  $("app").hidden = false;
  $("boot").hidden = true;
  const name = state.me.display_name || state.me.username;
  $("userName").textContent = name;
  $("userAvatar").textContent = name.slice(0, 1).toUpperCase();
  $("navUsers").hidden = !state.me.is_admin;
  $("emptyNewBtn").hidden = !can("folders.manage");
  $("parallelBox").hidden = !can("settings.manage");
  $("introForm").hidden = !can("intros.manage");
  await Promise.all([loadFolders(), loadIntros()]);
  loadStatus();
  await route();
  tick();
}

function route() {
  const h = location.hash.slice(1);
  if (/^\d+$/.test(h) && byId(+h)) return go("folders", +h);
  if (h === "folders") return go("folders");
  if (h === "history" || h === "intros" || (h === "users" && state.me.is_admin)) return go(h);
  return go("home");
}

async function go(view, id = null) {
  state.view = view;
  state.current = view === "folders" ? id : null;
  const hash = view === "folders" ? (id ? String(id) : "folders") : view;
  if (location.hash.slice(1) !== hash) history.replaceState(null, "", "#" + hash);
  for (const v of ["home", "folders", "history", "intros", "users"]) $(v + "View").hidden = v !== view;
  document.querySelectorAll(".nav-link").forEach((b) => b.classList.toggle("active", b.dataset.nav === view));
  $("sidebar").classList.remove("open");
  if (view === "home") await loadHome();
  else if (view === "history") await loadHistory();
  else if (view === "intros") { renderIntroList(); await loadIntros(); }
  else if (view === "users") await loadUsers();
  else if (view === "folders") { state.jobs = []; state.sel = null; $("newJobPanel").hidden = true; $("foldSearch").value = ""; renderExplorer(); await loadJobs(); }
}
window.addEventListener("hashchange", () => { if (state.me) route(); });
document.addEventListener("click", (e) => {
  const n = e.target.closest("[data-nav]");
  if (n) go(n.dataset.nav);
});
document.addEventListener("click", (e) => {
  const l = e.target.closest("[data-go]");
  if (l) { e.preventDefault(); go(l.dataset.go); }
});
$("menuBtn").onclick = () => $("sidebar").classList.toggle("open");

// Rafraîchissement : la progression vient de la base, elle est donc toujours là après un rechargement de la page
async function tick() {
  clearTimeout(state.timers.tick);
  if (!state.me) return;
  if (document.visibilityState === "visible") {
    const s = await loadStatus();
    const active = s ? s.running + s.pending : 0;
    if (active > 0 || state.lastActive > 0) {
      refreshView();
      if (state.view !== "folders") loadFolders();
    }
    state.lastActive = active;
  }
  state.timers.tick = setTimeout(tick, 3000);
}
function refreshView() {
  if (state.view === "home") loadHome(true);
  else if (state.view === "history") loadHistory(false, true);
  else if (state.view === "folders") { loadJobs(); loadFolders(); }
  if (state.detail && $("detailDialog").open) openDetail(state.detail.id, true);
}

// ---------- Utilitaires de rendu ----------
function keepPlayers(box, html) {  // remplace le HTML sans couper un lecteur audio en cours
  const players = {};
  box.querySelectorAll("audio[data-job]").forEach((a) => (players[a.dataset.job] = a));
  box.innerHTML = html;
  box.querySelectorAll("[data-player]").forEach((slot) => {
    const a = players[slot.dataset.player];
    if (a) slot.replaceWith(a);
    else if (slot.dataset.auto !== undefined) slot.replaceWith(makePlayer(slot.dataset.player, false));
  });
}
function makePlayer(id, autoplay) {
  const a = document.createElement("audio");
  a.controls = true; a.preload = autoplay ? "auto" : "none"; a.dataset.job = id;
  a.src = `/api/jobs/${id}/file/mp3`;
  if (autoplay) a.autoplay = true;
  return a;
}
// Un seul son à la fois : quand un lecteur démarre (détails, rognage, intros, listes), tous les autres se mettent en pause.
// L'événement « play » ne remonte pas dans le DOM : on l'écoute en phase de capture.
document.addEventListener("play", (e) => {
  document.querySelectorAll("audio").forEach((a) => { if (a !== e.target) a.pause(); });
}, true);
const loadingLine = (box) => (box.innerHTML = '<div class="loading-line"><span class="spinner"></span> Chargement…</div>');

const STEP_ICON = { done: "✓", active: "●", pending: "○", skipped: "–", error: "!" };
function renderSteps(j, open = false) {
  const rows = j.steps.map((s, i) => `
    <li class="st ${s.state}">
      <span class="st-icon">${STEP_ICON[s.state]}</span>
      <span class="st-name">${i + 1}. ${esc(s.label)}</span>
      <span class="st-bar"><i style="width:${s.pct}%"></i></span>
      <span class="st-pct">${s.state === "skipped" ? "ignorée" : s.pct + "%"}</span>
    </li>`).join("");
  return j.status === "done" && !open
    ? `<details class="steps"><summary>Détail des étapes</summary><ul>${rows}</ul></details>`
    : `<ul class="steps">${rows}</ul>`;
}

function liveBlock(j) {  // rang dans la file, ou barre globale s'il tourne
  if (j.status === "pending") {
    const note = j.step && j.step !== "En attente" ? ` · ${esc(j.step)}` : "";
    return `<div class="queued">${ic("clock")} En file d'attente — <b>n° ${j.queue_position}</b>${note}</div>`;
  }
  if (j.status !== "running") return "";
  const pct = Math.round(j.progress * 100);
  return `<div class="progress"><div style="width:${pct}%"></div></div>
    <div class="step"><b>Global ${pct}%</b> — ${esc(j.step)}</div>`;
}

const isLive = (j) => j.status === "pending" || j.status === "running";

const editable = (j) => j.can_edit !== false;  // le serveur refuse de toute façon : on ne propose pas ce qui échouerait
function jobActions(j, { detail = true, play = false } = {}) {
  return `<div class="actions">
    ${play && j.has_mp3 ? `<button class="btn small ghost" data-act="play" data-id="${j.id}">${ic("play")} Écouter</button>` : ""}
    ${j.has_mp3 ? `<a class="btn small" href="/api/jobs/${j.id}/file/mp3?download=true">${ic("download")} Télécharger MP3</a>` : ""}
    ${j.on_r2 ? `<button class="btn small ghost" data-act="link" data-id="${j.id}">${ic("link")} Copier le lien</button>` : ""}
    ${detail ? `<button class="btn small ghost" data-act="detail" data-id="${j.id}">${ic("info")} Détails</button>` : ""}
    ${j.status === "done" && j.has_mp3 && can("jobs.trim") && editable(j) ? `<button class="btn small ghost" data-act="trim" data-id="${j.id}">${ic("scissors")} Rogner</button>` : ""}
    ${(j.status === "done" || j.status === "error") && can("jobs.create") && editable(j) ? `<button class="btn small ghost" data-act="retry" data-id="${j.id}">${ic("retry")} Relancer</button>` : ""}
    ${j.status !== "running" && can("jobs.delete") && editable(j) ? `<button class="btn small ghost danger" data-act="delete" data-id="${j.id}">${ic("trash")} Supprimer</button>` : ""}
  </div>`;
}

// Carte « en cours / en file » de l'accueil : anneau de progression, étape courante, une pastille par étape
function activeCard(j) {
  const vis = j.steps.filter((x) => x.state !== "skipped");
  const idx = vis.findIndex((x) => x.state === "active");
  const sub = `${j.folder_path ? ic("folder") + " " + esc(j.folder_path) : ""}${j.created_by ? ` · par ${esc(j.created_by)}` : ""}`;
  const head = `<div class="ac-main">
      <div class="ac-title">${esc(j.title)} <span class="muted">· ${esc(j.date)}</span></div>
      <div class="ac-sub">${sub}</div>`;
  const actions = `<div class="ac-actions"><span class="by">${j.from_upload ? ic("upload") + " Fichier envoyé" : ""}</span>
      <button class="btn small ghost" data-act="detail" data-id="${j.id}">${ic("info")} Détails</button></div>`;
  if (j.status === "pending") {
    return `<div class="active-card pending" data-id="${j.id}">
      <div class="ring queue"><b>n°<i>${j.queue_position}</i></b></div>
      ${head}<div class="ac-step">${ic("clock")} En file d'attente${j.step && j.step !== "En attente" ? ` <small>· ${esc(j.step)}</small>` : ""}</div></div>
      ${actions}</div>`;
  }
  const pct = Math.round(j.progress * 100);
  return `<div class="active-card running" data-id="${j.id}">
    <div class="ring" style="--p:${pct}"><b>${pct}<small>%</small></b></div>
    ${head}
      <div class="ac-step"><span class="live"></span><b>${esc(j.step)}</b>${idx >= 0 ? `<small>· étape ${idx + 1}/${vis.length}</small>` : ""}</div>
      <div class="pips">${vis.map((x) => `<i class="${x.state}" style="--w:${x.pct}%" title="${esc(x.label)} — ${x.pct}%"></i>`).join("")}</div>
    </div>
    ${actions}</div>`;
}

// Ligne compacte (historique, liste des podcasts)
function jobRow(j) {
  const meta = [fmtDate(j.created_at), j.duration_output && `Podcast ${j.duration_output}`,
    j.size_mp3 && fmtSize(j.size_mp3), j.created_by && `par ${j.created_by}`].filter(Boolean);
  return `<div class="hrow" data-id="${j.id}">
    <div>
      <div class="job-title">${esc(j.title)} <span class="muted">· ${esc(j.date)}</span></div>
      <div class="job-sub">${ic("folder")} ${esc(j.folder_path || "")}${j.video_title ? " · " + esc(j.video_title) : ""}</div>
    </div>
    <span class="badge ${j.status}">${LABELS[j.status]}</span>
    ${isLive(j) ? `<div class="wide-col">${liveBlock(j)}</div>`
      : `<div class="h-meta">${meta.map((m) => `<span>${esc(m)}</span>`).join("")}</div>`}
    ${j.error ? `<div class="err-box wide-col">${esc(j.error)}</div>` : ""}
    <div class="wide-col">${jobActions(j, { play: true })}</div>
    <div class="wide-col" data-player="${j.id}"></div>
  </div>`;
}

// ---------- Actions communes ----------
const findJob = (id) => state.jobs.find((j) => j.id === id) || state.hist.items.find((j) => j.id === id)
  || state.home.items?.find((j) => j.id === id) || (state.detail?.id === id ? state.detail : null);

async function copyLink(url, label = "Lien copié") {
  try { await navigator.clipboard.writeText(url); toast(label, "ok"); }
  catch { await modal({ title: "Lien de téléchargement", body: `<input readonly value="${esc(url)}" onfocus="this.select()">`, buttons: [{ label: "Fermer", primary: true }] }); }
}

function introOptions(first, withNone = false, selected = "") {
  const opts = [...first, ...state.intros.map((i) => [String(i.id), i.name + (i.is_default ? " ★ par défaut" : "")])];
  if (withNone) opts.push(["0", "Aucune intro"]);
  return opts.map(([v, l]) => `<option value="${esc(v)}" ${String(selected) === v ? "selected" : ""}>${esc(l)}</option>`).join("");
}

async function handleAction(act, id, btn) {
  const job = findJob(id);
  try {
    if (act === "detail") await openDetail(id);
    else if (act === "play") {
      const row = btn.closest(".hrow");
      const existing = row.querySelector("audio");
      if (existing) { const s = document.createElement("div"); s.className = "wide-col"; s.dataset.player = id; existing.replaceWith(s); return; }
      row.querySelector("[data-player]").replaceWith(makePlayer(id, true));
    } else if (act === "link") {
      const { url, public: pub } = await api(`/api/jobs/${id}/link/mp3`);
      await copyLink(url, pub ? "Lien public copié" : "Lien copié (valable 7 jours)");
    } else if (act === "retry") await retryDialog(job);
    else if (act === "trim") await trimDialog(job);
    else if (act === "rename") await renameJob(job);
    else if (act === "delete") {
      const ok = await confirmBox({ title: "Supprimer ce traitement ?",
        message: `« <b>${esc(job.title)}</b> » sera supprimé, ainsi que ses fichiers (y compris sur R2). Cette action est définitive.`,
        confirmLabel: "Supprimer", danger: true });
      if (!ok) return;
      await api(`/api/jobs/${id}`, { method: "DELETE" });
      if (state.detail?.id === id) $("detailDialog").close();
      toast("Traitement supprimé", "ok");
      refreshView();
    }
  } catch (err) { toast(err.message, true); }
}
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-act]");
  if (btn) busy(btn, () => handleAction(btn.dataset.act, +btn.dataset.id, btn));
});

async function retryDialog(job) {
  const done = await modal({
    title: "Relancer le traitement",
    body: `<p>Corrigez les bornes si la prédication détectée n'était pas la bonne. Vide = détection automatique.</p>
      <div class="row"><label>Début<input name="start" placeholder="1:05:30" value="${esc(job.start_override || job.sermon_start || "")}"></label>
      <label>Fin<input name="end" placeholder="2:10:00" value="${esc(job.end_override || job.sermon_end || "")}"></label></div>
      <label>Intro<select name="intro_id">${introOptions([["keep", "Ne pas changer"], ["", "Automatique (dossier, sinon par défaut)"]], true, "keep")}</select></label>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Relancer", primary: true }],
    submit: async (dlg) => {
      const v = (n) => dlg.querySelector(`[name=${n}]`).value;
      const body = { start: v("start"), end: v("end") };
      if (v("intro_id") !== "keep") body.intro_id = v("intro_id") === "" ? null : +v("intro_id");
      await api(`/api/jobs/${job.id}/retry`, { method: "POST", body });
    },
  });
  if (done) { toast("Traitement relancé", "ok"); refreshView(); loadStatus(); }
}

// ---------- Rognage du podcast terminé ----------
const clock = (s) => { s = Math.max(0, s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return `${h}:${String(m).padStart(2, "0")}:${x.toFixed(1).padStart(4, "0")}`; };
const parseClock = (v) => { const p = String(v).trim().split(":"); if (!v.trim() || p.length > 3 || p.some((x) => !/^\d+(\.\d+)?$/.test(x))) return NaN;
  return p.reduce((a, x) => a * 60 + parseFloat(x), 0); };

async function trimDialog(job) {
  const dur = job.duration_output_s || 0;
  const res = await modal({
    title: "Rogner le podcast", wide: true,
    body: `<p>Retirez le début et/ou la fin du podcast terminé (par exemple un silence, un chant ou une annonce en trop). Écoutez, placez le curseur au bon endroit, puis cliquez « Marquer ici ».</p>
      <div class="trim-player"><audio controls preload="metadata" src="/api/jobs/${job.id}/file/mp3?v=${Date.now()}"></audio></div>
      <div class="trim-marks">
        <div class="mark"><b>Début conservé</b><input name="start" value="0:00:00.0" autocomplete="off">
          <div class="actions"><button class="btn small ghost" type="button" data-mark="start">Marquer ici</button>
          <button class="btn small ghost" type="button" data-prev="start">${ic("play")} Écouter le début</button></div></div>
        <div class="mark"><b>Fin conservée</b><input name="end" value="${clock(dur)}" autocomplete="off">
          <div class="actions"><button class="btn small ghost" type="button" data-mark="end">Marquer ici</button>
          <button class="btn small ghost" type="button" data-prev="end">${ic("play")} Écouter la fin</button></div></div>
      </div>
      <div class="trim-summary" data-summary></div>
      <p class="hint">Format <b>h:mm:ss</b> (secondes décimales possibles). Le rognage ne réencode pas : aucune perte de qualité. L'original est gardé, vous pourrez le restaurer.${job.on_r2 ? " Le fichier R2 est remplacé : <b>le lien de partage change</b>." : ""}</p>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null },
      ...(job.can_restore ? [{ label: "Restaurer l'original", kind: "ghost", value: "restore" }] : []),
      { label: "Rogner", primary: true }],
    onMount: (dlg) => {
      const audio = dlg.querySelector("audio"), start = dlg.querySelector("[name=start]"), end = dlg.querySelector("[name=end]");
      const summary = dlg.querySelector("[data-summary]");
      const refresh = () => {
        const s = parseClock(start.value), e = parseClock(end.value);
        summary.textContent = isNaN(s) || isNaN(e) ? "Format d'heure invalide"
          : e <= s ? "La fin doit être après le début"
          : `Durée après rognage : ${clock(e - s).slice(0, -2)} (retire ${clock(Math.max(dur - (e - s), 0)).slice(0, -2)})`;
      };
      start.oninput = end.oninput = refresh;
      refresh();
      dlg.querySelectorAll("[data-mark]").forEach((b) => (b.onclick = () => {
        (b.dataset.mark === "start" ? start : end).value = clock(audio.currentTime); refresh(); }));
      dlg.querySelectorAll("[data-prev]").forEach((b) => (b.onclick = () => {
        const e = parseClock(end.value), s = parseClock(start.value);
        audio.onended = null;
        if (b.dataset.prev === "start") audio.currentTime = isNaN(s) ? 0 : s;
        else {  // les 8 dernières secondes conservées, puis arrêt à la fin choisie
          audio.currentTime = Math.max(0, (isNaN(e) ? dur : e) - 8);
          audio.ontimeupdate = () => { if (audio.currentTime >= e) { audio.pause(); audio.ontimeupdate = null; } };
        }
        audio.play();
      }));
    },
    submit: async (dlg) => {
      const s = parseClock(dlg.querySelector("[name=start]").value), e = parseClock(dlg.querySelector("[name=end]").value);
      if (isNaN(s) || isNaN(e)) throw new Error("Format d'heure invalide (h:mm:ss)");
      if (e <= s) throw new Error("La fin doit être après le début");
      if (s < 0.05 && e > dur - 0.05) throw new Error("Rien à rogner : début et fin sont ceux du podcast");
      await api(`/api/jobs/${job.id}/trim`, { method: "POST", body: { start: s < 0.05 ? "" : String(s), end: e > dur - 0.05 ? "" : String(e) } });
      return "trimmed";
    },
  });
  if (res === "trimmed") toast("Podcast rogné", "ok");
  else if (res === "restore") {
    if (!(await confirmBox({ title: "Restaurer l'original ?", message: "Le podcast reviendra à sa version d'avant le rognage." + (job.on_r2 ? " Le lien R2 changera." : ""), confirmLabel: "Restaurer" }))) return;
    await api(`/api/jobs/${job.id}/trim/reset`, { method: "POST" });
    toast("Original restauré", "ok");
  } else return;
  refreshView();
}

// ---------- Statut, parallélisme ----------
function r2Pill(s) {
  if (!s.r2) return '<span class="pill">R2 non configuré</span>';
  const sy = s.r2_sync || {};
  if (sy.running) return '<span class="pill busy link" data-r2>R2 · synchronisation…</span>';
  const failed = sy.last?.failed?.length || 0;
  if (failed) return `<span class="pill err link" data-r2>R2 · ${failed} erreur${failed > 1 ? "s" : ""}</span>`;
  return '<span class="pill on link" data-r2>R2 connecté</span>';
}

async function r2Dialog() {
  const sy = (await api("/api/r2/sync").catch(() => null)) || {};
  const l = sy.last;
  const rows = l ? `<dl class="kv"><dt>Dernière synchronisation</dt><dd>${fmtDate(l.at)}</dd>
      <dt>Fichiers déplacés</dt><dd>${l.moved}</dd><dt>Fichiers envoyés</dt><dd>${l.uploaded}</dd><dt>Dossiers créés</dt><dd>${l.markers}</dd></dl>
      ${l.failed.length ? `<div class="err-box">${l.failed.map((f) => `${esc(f.title)} : ${esc(f.error)}`).join("<br>")}</div>` : '<p class="hint">Tout est à jour.</p>'}`
    : '<p class="hint">Aucune synchronisation depuis le démarrage.</p>';
  const go = await modal({
    title: "Synchronisation R2", icon: "☁️",
    body: `<p>L'arborescence de R2 reproduit celle de la plateforme : <b>dossier / sous-dossier / Nom du podcast_date.mp3</b>. Renommer ou déplacer ici le fait aussi là-bas, automatiquement. Cette synchronisation rattrape ce qui aurait échoué et envoie les podcasts jamais envoyés.</p>${rows}`,
    buttons: [{ label: "Fermer", kind: "ghost", value: null }, ...(can("folders.manage") ? [{ label: "Resynchroniser maintenant", primary: true }] : [])],
    submit: async () => { await api("/api/r2/sync", { method: "POST" }); return true; },
  });
  if (go) { toast("Synchronisation R2 lancée", "ok"); loadStatus(); }
}
$("statusBar").addEventListener("click", (e) => { if (e.target.closest("[data-r2]")) r2Dialog(); });

async function loadStatus() {
  const s = await api("/api/status").catch(() => null);
  if (!s) return null;
  $("statusBar").innerHTML = `
    ${r2Pill(s)}
    <span class="pill ${s.llm ? "on" : ""}">Détection ${s.llm ? "IA (" + s.llm + ")" : "heuristique"}</span>
    <span class="pill link ${s.running ? "busy" : ""}" data-status="active">▶ ${s.running}/${s.max_parallel} en cours</span>
    <span class="pill link ${s.pending ? "waiting" : ""}" data-status="active">⏳ ${s.pending} en file</span>`;
  const mb = s.max_upload_mb;
  $("maxUpload").textContent = mb >= 1024 ? `${(mb / 1024).toFixed(1).replace(".0", "")} Go` : `${mb} Mo`;
  const wasSyncing = state.status?.r2_sync?.running;
  state.status = s;
  if (wasSyncing && !s.r2_sync?.running) {
    const f = s.r2_sync?.last?.failed?.length;
    toast(f ? `Synchronisation R2 terminée avec ${f} erreur(s)` : "R2 est à jour", f ? true : "ok");
    refreshView();
  }
  if (state.view === "home") renderHomeStats();
  const sel = $("parallelSelect");
  if (!sel.options.length) for (let n = 1; n <= s.max_parallel_limit; n++) sel.add(new Option(n, n));
  if (document.activeElement !== sel) sel.value = s.max_parallel;
  return s;
}
$("statusBar").addEventListener("click", (e) => {
  if (!e.target.closest("[data-status]")) return;
  $("histStatus").value = "active";
  go("history");
});
$("parallelSelect").onchange = async (e) => {
  try {
    await api("/api/settings", { method: "PUT", body: { max_parallel: +e.target.value } });
    toast(`${e.target.value} traitement(s) en parallèle`, "ok");
    loadStatus();
  } catch (err) { toast(err.message, true); }
};

// ---------- Accueil ----------
function renderHomeStats() {
  const s = state.status;
  if (!s) return;
  const tile = (icon, value, label, kind = "") => `<div class="stat ${kind}"><span class="stat-ic">${ic(icon)}</span><div><b>${value}</b><span>${label}</span></div></div>`;
  $("homeStats").innerHTML = tile("music", state.home.doneTotal ?? "–", "Podcasts prêts", "ok")
    + tile("play", `${s.running}<small>/${s.max_parallel}</small>`, "En cours", s.running ? "busy" : "")
    + tile("clock", s.pending, "En file d'attente", s.pending ? "wait" : "");
}

let homeSearchTimer;
$("homeSearch").oninput = () => { clearTimeout(homeSearchTimer); homeSearchTimer = setTimeout(() => loadHome(), 300); };

async function loadHome(silent = false) {
  if (!silent && !state.home.items) { loadingLine($("homeActive")); loadingLine($("homeDone")); }
  const q = $("homeSearch").value;
  try {
    const act = await api("/api/jobs?status=active&limit=100");
    const sig = act.items.map((j) => j.id + j.status).join(",");
    if (state.view !== "home") return;
    $("homeActiveBox").hidden = !act.total;
    $("homeActiveCount").textContent = act.total || "";
    $("homeActive").innerHTML = act.items.map(activeCard).join("");
    if (silent && sig === state.home.sig && q === state.home.q) { state.home.items = [...act.items, ...(state.home.done || [])]; return; }
    const done = await api(`/api/jobs?status=done&limit=12&q=${encodeURIComponent(q)}`);
    state.home = { sig, q, done: done.items, doneTotal: q ? state.home.doneTotal : done.total, items: [...act.items, ...done.items] };
    renderHomeStats();
    $("homeDoneCount").textContent = done.total || "";
    const empty = !state.folders.length && !act.total && !done.total && !q;
    $("emptyState").hidden = !empty;
    $("homeContent").hidden = empty;
    keepPlayers($("homeDone"), done.items.length ? done.items.map(jobRow).join("")
      : `<p class="muted">${q ? "Aucun podcast ne correspond." : "Aucun podcast terminé pour l'instant."}</p>`);
  } catch (err) { if (!silent) toast(err.message, true); }
}

// ---------- Historique ----------
let histTimer;
$("histSearch").oninput = () => { clearTimeout(histTimer); histTimer = setTimeout(() => loadHistory(), 300); };
$("histStatus").onchange = () => loadHistory();
$("histMore").onclick = (e) => busy(e.currentTarget, () => loadHistory(true));

async function loadHistory(more = false, silent = false) {
  const h = state.hist;
  if (!silent && !more) loadingLine($("histList"));
  const q = new URLSearchParams({ q: $("histSearch").value, status: $("histStatus").value,
    limit: more ? 50 : Math.max(h.items.length, 50), offset: more ? h.items.length : 0 });
  try {
    const res = await api(`/api/jobs?${q}`);
    if (state.view !== "history") return;
    h.items = more ? h.items.concat(res.items) : res.items;
    h.total = res.total;
    $("histCount").textContent = h.total ? `${h.items.length} sur ${h.total} traitement(s)` : "";
    $("histMore").hidden = h.items.length >= h.total;
    keepPlayers($("histList"), h.items.length ? h.items.map(jobRow).join("") : '<p class="muted">Aucun traitement.</p>');
  } catch (err) { if (!silent) toast(err.message, true); }
}

// ---------- Dossiers : explorateur de fichiers ----------
const children = (pid) => state.folders.filter((f) => (f.parent_id ?? null) === pid).sort((a, b) => a.name.localeCompare(b.name, "fr"));
const byId = (id) => state.folders.find((f) => f.id === id);
function pathOf(folder) {
  const out = [];
  for (let cur = folder; cur; cur = cur.parent_id ? byId(cur.parent_id) : null) out.unshift(cur);
  return out;
}
const isInside = (id, ancestorId) => pathOf(byId(id)).some((f) => f.id === ancestorId);  // id est-il dans ancestorId (ou égal) ?

async function loadFolders() {
  state.folders = await api("/api/folders");
  paintFoldersBadge();
  if (state.view === "folders") renderExplorer();
}
function paintFoldersBadge() {  // pastille permanente sur le menu « Dossiers » tant qu'un traitement est actif
  const running = state.folders.reduce((n, f) => n + (f.running || 0), 0), pending = state.folders.reduce((n, f) => n + (f.pending || 0), 0);
  const b = $("navFoldersBadge");
  b.hidden = !running && !pending;
  b.classList.toggle("queue", !running);
  b.textContent = running || pending || "";
  b.title = [running && `${running} en cours`, pending && `${pending} en file`].filter(Boolean).join(" · ");
}
function activity(f) {  // traitements en cours / en file dans ce dossier et tous ses sous-dossiers
  let running = f.running || 0, pending = f.pending || 0;
  for (const c of children(f.id)) { const a = activity(c); running += a.running; pending += a.pending; }
  return { running, pending };
}
function actBadge(a) {
  if (!a.running && !a.pending) return "";
  const txt = a.running ? `${a.running} en cours${a.pending ? ` +${a.pending}` : ""}` : `${a.pending} en file`;
  const tip = [a.running && `${a.running} en cours`, a.pending && `${a.pending} en file`].filter(Boolean).join(" · ");
  return `<span class="act-badge ${a.running ? "running" : ""}" title="${tip}">${txt}</span>`;
}

const FOLDER_SVG = '<svg class="big" viewBox="0 0 64 64" aria-hidden="true"><path class="f-back" d="M5 15a4 4 0 0 1 4-4h14l6 6h26a4 4 0 0 1 4 4v6H5z"/><path class="f-front" d="M5 24h54v25a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4z"/></svg>';
const FILE_SVG = '<svg class="big" viewBox="0 0 64 64" aria-hidden="true"><path class="p-body" d="M14 5h26l11 11v37a4 4 0 0 1-4 4H14a4 4 0 0 1-4-4V9a4 4 0 0 1 4-4z"/><path class="p-fold" d="M40 5v11h11z"/><path class="p-note" d="M28 42V28l11-2v14"/><circle class="p-dot" cx="25" cy="42" r="3.5"/><circle class="p-dot" cx="36" cy="40" r="3.5"/></svg>';

let foldView = "grid";
try { foldView = localStorage.getItem("foldView") === "list" ? "list" : "grid"; } catch {}

const plural = (n, one, many) => `${n} ${n > 1 ? many : one}`;

function jobMeta(j) {
  if (j.status === "running") return `${Math.round(j.progress * 100)} % — ${esc(j.step)}`;
  if (j.status === "pending") return `En file n° ${j.queue_position}`;
  if (j.status === "error") return "Erreur";
  return [j.duration_output, fmtSize(j.size_mp3)].filter(Boolean).join(" · ");
}

function itemFolder(f) {
  const subs = children(f.id).length;
  const meta = [subs && plural(subs, "dossier", "dossiers"), f.job_count && plural(f.job_count, "podcast", "podcasts")].filter(Boolean).join(" · ") || "Vide";
  const tag = !f.can_edit ? `<span class="tag" title="Dossier de l'administration : vous pouvez y travailler, pas le modifier ni le supprimer">${ic("lock")}</span>`
    : state.me.is_admin && f.shared_with?.length ? `<span class="tag shared" title="Attribué à ${plural(f.shared_with.length, "utilisateur", "utilisateurs")}">${ic("users")}</span>` : "";
  const drag = f.can_edit && can("folders.manage");
  return `<div class="item folder ${state.sel?.kind === "folder" && state.sel.id === f.id ? "sel" : ""}" data-kind="folder" data-id="${f.id}" draggable="${drag}" title="${esc(f.name)}">
    ${tag}${actBadge(activity(f))}
    <div class="thumb">${FOLDER_SVG}</div><div class="name">${esc(f.name)}</div>
    <div class="meta">${meta}</div><div class="c-type">Dossier</div><div class="c-date"></div></div>`;
}

function itemJob(j) {
  const pct = Math.round(j.progress * 100);
  return `<div class="item file st-${j.status} ${state.sel?.kind === "job" && state.sel.id === j.id ? "sel" : ""}" data-kind="job" data-id="${j.id}" draggable="${editable(j) && can("folders.manage")}" title="${esc(j.title)}">
    <div class="thumb">${FILE_SVG}${j.status !== "done" ? `<span class="dot ${j.status}"></span>` : ""}</div>
    <div class="name">${esc(j.title)}</div>
    <div class="meta">${jobMeta(j)}</div>
    <div class="c-type">${LABELS[j.status]}</div><div class="c-date">${esc(j.date)}</div>
    ${j.status === "running" ? `<div class="mini"><i style="width:${pct}%"></i></div>` : ""}</div>`;
}

function renderExplorer() {
  const cur = state.current ? byId(state.current) : null;
  if (state.current && !cur) return go("folders");
  // barre de chemin : chaque segment est cliquable et accepte un dépôt
  $("pathbar").innerHTML = [`<button data-crumb="" data-drop="">${ic("home")} Dossiers</button>`,
    ...pathOf(cur).map((p) => `<span class="sep">›</span><button data-crumb="${p.id}" data-drop="${p.id}">${esc(p.name)}</button>`)].join("");
  $("foldUp").disabled = !cur;
  const q = $("foldSearch").value.trim().toLowerCase();
  const folders = children(state.current ?? null).filter((f) => !q || f.name.toLowerCase().includes(q));
  const jobs = cur ? state.jobs.filter((j) => !q || j.title.toLowerCase().includes(q)) : [];
  $("newFolderBtn").hidden = !can("folders.manage");
  $("newJobBtn").hidden = !cur || !can("jobs.create");
  $("foldActions").hidden = $("newFolderBtn").hidden && $("newJobBtn").hidden;
  const box = $("explorer");
  box.className = "explorer " + foldView;
  document.querySelectorAll("[data-fview]").forEach((b) => b.classList.toggle("active", b.dataset.fview === foldView));
  if (!folders.length && !jobs.length) {
    box.innerHTML = `<div class="explorer-empty"><div class="empty-icon">${ic("folder")}</div>
      <b>${q ? "Aucun résultat" : cur ? "Ce dossier est vide" : "Aucun dossier"}</b>
      <span>${q ? "Essayez une autre recherche." : cur ? "Ajoutez un sous-dossier ou lancez un traitement."
        : can("folders.manage") ? "Créez votre premier dossier (par exemple CULTE ROYAL)." : "Aucun dossier ne vous est attribué. Demandez à un administrateur de vous en attribuer un."}</span></div>`;
  } else {
    box.innerHTML = (foldView === "list" ? '<div class="list-head"><span></span><span>Nom</span><span>Détails</span><span>Type</span><span>Date</span></div>' : "")
      + folders.map(itemFolder).join("") + jobs.map(itemJob).join("");
  }
  const eff = cur ? effectiveIntro(cur) : null;
  const introTxt = cur ? (eff ? `Intro : ${esc(eff.name)}${cur.intro_id ? "" : eff.from ? ` (héritée de « ${esc(eff.from.name)} »)` : " (par défaut)"}` : "Aucune intro") : "";
  $("foldStatus").innerHTML = `<span>${plural(folders.length, "dossier", "dossiers")}${cur ? ` · ${plural(jobs.length, "podcast", "podcasts")}` : ""}${cur && !cur.can_edit ? ` · ${ic("lock")} Dossier de l'administration` : ""}</span>`
    + (cur ? (can("folders.manage") && cur.can_edit ? `<button data-intro-dialog class="link-btn">${ic("music")} ${introTxt}</button>` : `<span>${introTxt}</span>`) : "");
}

function openItem(kind, id) {
  if (kind === "folder") openFolder(id);
  else openDetail(id);
}
function openFolder(id) { go("folders", id); }

// ----- sélection, ouverture, navigation
$("explorer").addEventListener("click", (e) => {
  const it = e.target.closest(".item");
  state.sel = it ? { kind: it.dataset.kind, id: +it.dataset.id } : null;
  document.querySelectorAll("#explorer .item").forEach((x) => x.classList.toggle("sel", x === it));
});
$("explorer").addEventListener("dblclick", (e) => {
  const it = e.target.closest(".item");
  if (it) openItem(it.dataset.kind, +it.dataset.id);
});
$("pathbar").addEventListener("click", (e) => {
  const b = e.target.closest("[data-crumb]");
  if (b) go("folders", b.dataset.crumb ? +b.dataset.crumb : null);
});
$("foldUp").onclick = () => { const cur = byId(state.current); if (cur) go("folders", cur.parent_id ?? null); };
$("foldSearch").oninput = () => renderExplorer();
document.querySelectorAll("[data-fview]").forEach((b) => (b.onclick = () => {
  foldView = b.dataset.fview;
  try { localStorage.setItem("foldView", foldView); } catch {}
  renderExplorer();
}));
$("foldStatus").addEventListener("click", (e) => { if (e.target.closest("[data-intro-dialog]")) folderIntroDialog(byId(state.current)); });

// ----- actions sur les dossiers
async function createFolder(parentId) {
  const f = await promptBox({
    title: parentId ? "Nouveau sous-dossier" : "Nouveau dossier",
    label: "Nom", placeholder: parentId ? "Octobre 2026" : "CULTE ROYAL", confirmLabel: "Créer",
    submit: (name) => api("/api/folders", { method: "POST", body: { name, parent_id: parentId } }),
  });
  if (!f || !f.id) return;
  await loadFolders();
  toast("Dossier créé", "ok");
  if (state.view !== "folders") go("folders", f.id);
}
async function renameFolder(f) {
  const r = await promptBox({ title: "Renommer le dossier", label: "Nouveau nom", value: f.name, hint: r2Hint(),
    submit: (name) => api(`/api/folders/${f.id}`, { method: "PATCH", body: { name } }) });
  if (r) { await loadFolders(); toast("Dossier renommé" + (state.status?.r2 ? " — R2 se met à jour" : ""), "ok"); }
}
async function accessDialog(f) {
  const users = (await api("/api/users")).filter((u) => !u.is_admin && u.is_active);
  if (!users.length) return alertBox({ title: "Aucun utilisateur à choisir", kind: "danger",
    message: "Créez d'abord un compte utilisateur (menu Utilisateurs). Les administrateurs voient déjà tous les dossiers." });
  const cur = new Set(f.shared_with || []);
  const r = await modal({
    title: `Attribuer « ${f.name} »`, wide: true,
    body: `<p>Les utilisateurs cochés travaillent dans ce dossier et ses sous-dossiers : lancer des traitements, écouter, télécharger.
      Ils ne peuvent <b>ni le renommer, ni le déplacer, ni le supprimer</b>, ni modifier ce que vous y avez créé. Sans attribution, ils ne le voient pas.</p>
      <div class="perm-list">${users.map((u) => `<label><input type="checkbox" name="u" value="${u.id}" ${cur.has(u.id) ? "checked" : ""}> ${esc(u.display_name || u.username)} <span class="muted">@${esc(u.username)}</span></label>`).join("")}</div>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Enregistrer", primary: true }],
    submit: (dlg) => api(`/api/folders/${f.id}/access`, { method: "PUT", body: { user_ids: [...dlg.querySelectorAll("[name=u]:checked")].map((c) => +c.value) } }),
  });
  if (r) { toast("Attribution enregistrée", "ok"); await loadFolders(); }
}
async function renameJob(j) {
  const r = await promptBox({ title: "Renommer le podcast", label: "Nouveau nom", value: j.title, hint: r2Hint(),
    submit: (title) => api(`/api/jobs/${j.id}`, { method: "PATCH", body: { title } }) });
  if (r) { refreshView(); loadStatus(); toast("Podcast renommé" + (state.status?.r2 ? " — R2 se met à jour" : ""), "ok"); }
}
async function deleteFolder(f) {
  const ok = await confirmBox({ title: "Supprimer le dossier ?", danger: true, confirmLabel: "Supprimer",
    message: `Le dossier « <b>${esc(f.name)}</b> » sera supprimé. Il doit être vide (ni sous-dossier ni traitement).` });
  if (!ok) return;
  try {
    await api(`/api/folders/${f.id}`, { method: "DELETE" });
    state.sel = null;
    await loadFolders();
    toast("Dossier supprimé", "ok");
  } catch (err) { alertBox({ title: "Suppression impossible", message: esc(err.message), kind: "danger" }); }
}

async function folderIntroDialog(f) {
  const r = await modal({
    title: `Intro du dossier « ${f.name} »`,
    body: `<label>Intro utilisée pour les podcasts de ce dossier<select name="intro">${introOptions([["", "Hériter (parent, sinon intro par défaut)"]], false, f.intro_id ?? "")}</select></label>
      <div data-note class="hint"></div><div data-preview></div>
      <a class="page-link" data-go="intros" href="#intros">Gérer la bibliothèque d'intros →</a>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Enregistrer", primary: true }],
    onMount: (dlg) => {
      const sel = dlg.querySelector("[name=intro]");
      const refresh = () => {
        const chosen = sel.value ? { id: +sel.value, name: introName(+sel.value) } : effectiveIntro(byId(f.parent_id));
        dlg.querySelector("[data-note]").textContent = sel.value ? "" : chosen ? `Hérité : ${chosen.name}` : "Aucune intro à hériter : ajoutez un MP3 dans la bibliothèque d'intros.";
        dlg.querySelector("[data-preview]").innerHTML = chosen ? `<audio controls preload="none" src="/api/intros/${chosen.id}/audio" style="width:100%"></audio>` : "";
      };
      sel.onchange = refresh; refresh();
      dlg.querySelector("[data-go]").onclick = (ev) => { ev.preventDefault(); dlg.querySelector("[data-close]").click(); go("intros"); };
    },
    submit: async (dlg) => {
      const v = dlg.querySelector("[name=intro]").value;
      await api(`/api/folders/${f.id}/intro`, { method: "PUT", body: { intro_id: v ? +v : null } });
      return true;
    },
  });
  if (r) { await loadFolders(); toast("Intro du dossier enregistrée", "ok"); }
}

// ----- déplacement (fenêtre « Déplacer vers… » et glisser-déposer)
async function moveItem(kind, id, folderId) {
  try {
    if (kind === "folder") await api(`/api/folders/${id}`, { method: "PATCH", body: { parent_id: folderId } });
    else await api(`/api/jobs/${id}/move`, { method: "POST", body: { folder_id: folderId } });
    state.sel = null;
    await Promise.all([loadFolders(), loadJobs()]);
    toast("Élément déplacé" + (state.status?.r2 ? " — R2 se met à jour" : ""), "ok");
  } catch (err) { toast(err.message, true); }
}
function folderChoices(excludeId) {
  const out = [];
  const walk = (pid, depth) => children(pid).forEach((f) => {
    if (f.id === excludeId) return;  // on ne propose ni le dossier déplacé ni ses sous-dossiers
    out.push({ id: f.id, depth, name: f.name });
    walk(f.id, depth + 1);
  });
  walk(null, 0);
  return out;
}
async function moveDialog(kind, item) {
  const isFolder = kind === "folder";
  const here = isFolder ? (item.parent_id ?? null) : item.folder_id;
  const choices = folderChoices(isFolder ? item.id : null);
  const dest = await modal({
    title: `Déplacer « ${isFolder ? item.name : item.title} »`,
    body: `<div class="move-list">${isFolder ? `<label><input type="radio" name="dest" value="" ${here === null ? "checked" : ""}> ${ic("home")} Dossiers (racine)</label>` : ""}
      ${choices.map((c) => `<label style="padding-left:${10 + c.depth * 20}px"><input type="radio" name="dest" value="${c.id}" ${here === c.id ? "checked" : ""}> ${ic("folder")} ${esc(c.name)}</label>`).join("")}</div>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Déplacer ici", primary: true }],
    submit: async (dlg) => {
      const r = dlg.querySelector("[name=dest]:checked");
      if (!r) throw new Error("Choisissez un dossier de destination");
      return r.value === "" ? "root" : +r.value;
    },
    onMount: (dlg) => { if (state.status?.r2) dlg.querySelector(".move-list").insertAdjacentHTML("afterend", `<p class="hint">${R2_HINT}</p>`); },
  });
  if (dest === null || dest === undefined || dest === true) return;
  const target = dest === "root" ? null : dest;
  if (target === here) return;
  await moveItem(kind, item.id, target);
}

let dragging = null;
$("explorer").addEventListener("dragstart", (e) => {
  const it = e.target.closest(".item");
  if (!it || !can("folders.manage") || it.getAttribute("draggable") !== "true") return e.preventDefault();
  dragging = { kind: it.dataset.kind, id: +it.dataset.id };
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", `${dragging.kind}:${dragging.id}`);
  it.classList.add("dragging");
});
document.addEventListener("dragend", () => { dragging = null; document.querySelectorAll(".dragging,.drop").forEach((x) => x.classList.remove("dragging", "drop")); });
function dropTarget(e) {  // dossier ou segment du chemin sous la souris, s'il peut recevoir l'élément glissé
  const el = e.target.closest(".item.folder, [data-drop]");
  if (!el || !dragging) return null;
  const id = el.dataset.drop !== undefined ? (el.dataset.drop === "" ? null : +el.dataset.drop) : +el.dataset.id;
  if (dragging.kind === "job") {
    const j = state.jobs.find((x) => x.id === dragging.id);
    return id === null || (j && j.folder_id === id) ? null : { el, id };
  }
  const f = byId(dragging.id);
  if (!f || id === dragging.id || (f.parent_id ?? null) === id || (id !== null && isInside(id, dragging.id))) return null;
  return { el, id };
}
document.addEventListener("dragover", (e) => {
  document.querySelectorAll(".drop").forEach((x) => x.classList.remove("drop"));
  const t = dropTarget(e);
  if (t) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; t.el.classList.add("drop"); }
});
document.addEventListener("drop", (e) => {
  const t = dropTarget(e);
  if (!t) return;
  e.preventDefault();
  moveItem(dragging.kind, dragging.id, t.id);
});

// ----- menu contextuel (clic droit)
const ctx = $("ctxMenu");
function hideCtx() { ctx.hidden = true; }
function showCtx(x, y, entries) {
  ctx.innerHTML = entries.map((en, i) => en === "-" ? '<div class="ctx-sep"></div>'
    : `<button data-i="${i}" class="${en.danger ? "danger" : ""}">${ic(en.icon)} ${esc(en.label)}</button>`).join("");
  ctx.hidden = false;
  ctx.style.left = Math.min(x, innerWidth - ctx.offsetWidth - 8) + "px";
  ctx.style.top = Math.min(y, innerHeight - ctx.offsetHeight - 8) + "px";
  ctx.onclick = (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    hideCtx();
    entries[+b.dataset.i].run();
  };
}
document.addEventListener("click", hideCtx);
document.addEventListener("scroll", hideCtx, true);
window.addEventListener("resize", hideCtx);

function ctxEntries(kind, id) {
  const e = [];
  const manage = can("folders.manage");
  if (kind === "folder") {
    const f = byId(id);
    e.push({ label: "Ouvrir", icon: "open", run: () => openFolder(id) });
    if (manage) e.push("-", { label: "Nouveau sous-dossier", icon: "plus", run: () => createFolder(id) });
    if (state.me.is_admin) e.push({ label: "Attribuer à des utilisateurs…", icon: "users", run: () => accessDialog(f) });
    if (manage && f.can_edit) e.push("-",
      { label: "Renommer", icon: "edit", run: () => renameFolder(f) },
      { label: "Déplacer vers…", icon: "move", run: () => moveDialog("folder", f) },
      { label: "Intro du dossier…", icon: "music", run: () => folderIntroDialog(f) },
      "-", { label: "Supprimer", icon: "trash", danger: true, run: () => deleteFolder(f) });
  } else if (kind === "job") {
    const j = state.jobs.find((x) => x.id === id);
    const act = (a) => () => busy(null, () => handleAction(a, id));
    e.push({ label: j.has_mp3 ? "Détails et écoute" : "Détails", icon: "info", run: act("detail") });
    if (j.has_mp3) e.push({ label: "Télécharger le MP3", icon: "download", run: () => { location.href = `/api/jobs/${id}/file/mp3?download=true`; } });
    if (j.on_r2) e.push({ label: "Copier le lien", icon: "link", run: act("link") });
    if (j.status === "done" && j.has_mp3 && can("jobs.trim") && editable(j)) e.push({ label: "Rogner…", icon: "scissors", run: act("trim") });
    if ((j.status === "done" || j.status === "error") && can("jobs.create") && editable(j)) e.push({ label: "Relancer…", icon: "retry", run: act("retry") });
    if (manage && editable(j)) e.push({ label: "Renommer…", icon: "edit", run: () => renameJob(j) },
      { label: "Déplacer vers…", icon: "move", run: () => moveDialog("job", j) });
    if (j.status !== "running" && can("jobs.delete") && editable(j)) e.push("-", { label: "Supprimer", icon: "trash", danger: true, run: act("delete") });
  } else {
    if (manage) e.push({ label: "Nouveau dossier", icon: "plus", run: () => createFolder(state.current) });
    if (state.current && can("jobs.create")) e.push({ label: "Nouveau traitement", icon: "plus", run: openNewJob });
    if (state.current && manage && byId(state.current).can_edit) e.push({ label: "Intro de ce dossier…", icon: "music", run: () => folderIntroDialog(byId(state.current)) });
    e.push({ label: "Actualiser", icon: "refresh", run: () => { loadFolders(); loadJobs(); } });
  }
  return e;
}
$("explorer").addEventListener("contextmenu", (e) => {
  e.preventDefault();
  const it = e.target.closest(".item");
  state.sel = it ? { kind: it.dataset.kind, id: +it.dataset.id } : null;
  document.querySelectorAll("#explorer .item").forEach((x) => x.classList.toggle("sel", x === it));
  const entries = ctxEntries(it?.dataset.kind, it && +it.dataset.id);
  if (entries.length) showCtx(e.clientX, e.clientY, entries);
});

// ----- raccourcis clavier, comme un explorateur
document.addEventListener("keydown", (e) => {
  if (state.view !== "folders" || document.querySelector("dialog[open]") || /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  const s = state.sel;
  if (e.key === "Escape") { hideCtx(); state.sel = null; renderExplorer(); }
  else if (e.key === "Backspace") { e.preventDefault(); $("foldUp").click(); }
  else if (s && e.key === "Enter") openItem(s.kind, s.id);
  else if (s && s.kind === "folder" && e.key === "F2" && can("folders.manage") && byId(s.id).can_edit) { e.preventDefault(); renameFolder(byId(s.id)); }
  else if (s && e.key === "Delete") {
    if (s.kind === "folder" && can("folders.manage") && byId(s.id).can_edit) deleteFolder(byId(s.id));
    else if (s.kind === "job" && can("jobs.delete") && editable(state.jobs.find((x) => x.id === s.id) || {})) handleAction("delete", s.id);
  }
});

// ----- boutons de la barre d'actions
$("newFolderBtn").onclick = () => createFolder(state.current);
$("emptyNewBtn").onclick = () => createFolder(null);
function openNewJob() {
  const f = byId(state.current);
  if (!f) return;
  $("newJobWhere").textContent = `« ${f.name} »`;
  $("newJobPanel").hidden = false;
  updateFilenamePreview();
  $("newJobPanel").scrollIntoView({ behavior: "smooth", block: "nearest" });
  (mode === "batch" ? $("batchUrl") : source === "url" ? form.youtube_url : form.title).focus();
}
$("newJobBtn").onclick = openNewJob;
$("newJobClose").onclick = () => ($("newJobPanel").hidden = true);

async function loadJobs() {
  if (state.view !== "folders" || !state.current) return;
  const folderId = state.current;
  const jobs = await api(`/api/folders/${folderId}/jobs`).catch(() => null);
  if (!jobs || folderId !== state.current || state.view !== "folders") return;
  state.jobs = jobs;
  renderExplorer();
}


// ---------- Intros (bibliothèque MP3) ----------
const introName = (id) => state.intros.find((i) => i.id === id)?.name;
const defaultIntro = () => state.intros.find((i) => i.is_default);

function effectiveIntro(folder) {  // intro du dossier, sinon du parent le plus proche, sinon par défaut
  for (let f = folder; f; f = f.parent_id ? byId(f.parent_id) : null) {
    if (f.intro_id && introName(f.intro_id)) return { name: introName(f.intro_id), id: f.intro_id, from: f };
  }
  const d = defaultIntro();
  return d ? { name: d.name, id: d.id, from: null } : null;
}

function renderIntroSelects() {  // un sélecteur par mode : l'intro d'un traitement individuel et celle d'un lot sont indépendantes
  for (const id of ["jobIntroSelect", "batchIntroSelect"]) {
    const keep = $(id).value;
    $(id).innerHTML = introOptions([["", "Automatique (intro du dossier, sinon par défaut)"]], true, keep);
  }
}

async function loadIntros() {
  state.intros = await api("/api/intros").catch(() => state.intros);
  renderIntroSelects();
  if (state.view === "intros") renderIntroList();
  if (state.view === "folders") renderExplorer();
}

function renderIntroList() {
  const manage = can("intros.manage");
  $("introList").innerHTML = state.intros.length ? state.intros.map((i) => `
    <div class="job intro-item">
      <div class="top">
        <div><b>${esc(i.name)}</b> <span class="muted">${esc(i.duration)}</span>
          ${i.is_default ? '<span class="badge default">Par défaut</span>' : ""}</div>
        ${manage ? `<div class="actions">
          ${i.is_default ? "" : `<button class="btn small ghost" data-intro="default" data-id="${i.id}">★ Par défaut</button>`}
          <button class="btn small ghost" data-intro="rename" data-id="${i.id}">Renommer</button>
          <button class="btn small ghost danger" data-intro="delete" data-id="${i.id}">Supprimer</button>
        </div>` : ""}
      </div>
      <audio controls preload="none" src="/api/intros/${i.id}/audio"></audio>
    </div>`).join("") : '<p class="muted">Aucune intro. Ajoutez un fichier MP3 ci-dessous : la première devient l\'intro par défaut.</p>';
}


$("introList").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-intro]");
  if (!b) return;
  const id = +b.dataset.id, intro = state.intros.find((i) => i.id === id);
  await busy(b, async () => {
    try {
      if (b.dataset.intro === "default") {
        await api(`/api/intros/${id}`, { method: "PATCH", body: { is_default: true } });
        toast("Intro par défaut mise à jour", "ok");
      } else if (b.dataset.intro === "rename") {
        const r = await promptBox({ title: "Renommer l'intro", label: "Nouveau nom", value: intro.name,
          submit: (name) => api(`/api/intros/${id}`, { method: "PATCH", body: { name } }) });
        if (!r) return;
      } else if (b.dataset.intro === "delete") {
        const ok = await confirmBox({ title: "Supprimer cette intro ?", danger: true, confirmLabel: "Supprimer",
          message: `« <b>${esc(intro.name)}</b> » sera supprimée. Les dossiers et traitements qui l'utilisaient repasseront en automatique.` });
        if (!ok) return;
        const r = await api(`/api/intros/${id}`, { method: "DELETE" });
        await loadFolders();
        if (r.was_default) alertBox({ title: "Plus d'intro par défaut", kind: "danger",
          message: "Vous avez supprimé l'intro par défaut. Les prochains podcasts n'auront pas d'intro tant que vous n'en choisissez pas une autre." });
      }
      await loadIntros();
    } catch (err) { toast(err.message, true); }
  });
});

$("introForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target, fd = new FormData();
  fd.append("file", f.file.files[0]);
  fd.append("name", f.name.value);
  fd.append("is_default", f.is_default.checked);
  await busy(f.querySelector("button[type=submit]"), async () => {
    try {
      await api("/api/intros", { method: "POST", body: fd });
      f.reset();
      await loadIntros();
      toast("Intro ajoutée", "ok");
    } catch (err) { toast(err.message, true); }
  });
};

// ---------- Traitements d'un dossier ----------
const form = $("jobForm");
form.date.value = new Date().toISOString().slice(0, 10);
const slugify = (s) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "") || "sans-nom";
function updateFilenamePreview() {
  const t = form.title.value.trim();
  $("filenamePreview").textContent = t ? `Fichier : ${slugify(t)}_${form.date.value}.mp3` : "";
}
form.title.oninput = updateFilenamePreview;
form.date.oninput = updateFilenamePreview;

// Deux modes séparés : traitement individuel (formulaire) ou par lot (liste)
let mode = "single";
function setMode(next) {
  mode = next;
  document.querySelectorAll(".mode-switch [data-mode]").forEach((b) => b.classList.toggle("active", b.dataset.mode === next));
  $("jobForm").hidden = next !== "single";
  $("batchPanel").hidden = next !== "batch";
}
document.querySelector(".mode-switch").addEventListener("click", (e) => {
  const b = e.target.closest("[data-mode]");
  if (!b) return;
  setMode(b.dataset.mode);
  (mode === "single" ? (source === "url" ? form.youtube_url : form.title) : $("batchUrl")).focus();
});

// Source du podcast : lien YouTube ou fichier audio / vidéo envoyé
let source = "url";
function setSource(next) {
  source = next;
  form.querySelectorAll("[data-source]").forEach((b) => b.classList.toggle("active", b.dataset.source === next));
  form.querySelectorAll("[data-src]").forEach((el) => (el.hidden = el.dataset.src !== next));
  form.youtube_url.required = next === "url";
}
form.querySelector(".source-switch").addEventListener("click", (e) => { const b = e.target.closest("[data-source]"); if (b) setSource(b.dataset.source); });
const jobFile = $("jobFile"), dropzone = $("dropzone");
const DROP_TEXT = "Glissez un fichier ici ou cliquez pour le choisir";
function showPicked(file) {
  $("dropName").textContent = file ? `${file.name} — ${fmtSize(file.size)}` : DROP_TEXT;
  if (file && !form.title.value.trim()) { form.title.value = file.name.replace(/\.[^.]+$/, "").replace(/_+/g, " "); updateFilenamePreview(); }
}
jobFile.onchange = () => showPicked(jobFile.files[0]);
["dragenter", "dragover"].forEach((t) => dropzone.addEventListener(t, () => dropzone.classList.add("over")));
["dragleave", "drop"].forEach((t) => dropzone.addEventListener(t, () => dropzone.classList.remove("over")));

function uploadJob(fd, onProgress) {  // XHR : fetch ne donne pas la progression d'un envoi
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", "/api/jobs/upload");
    x.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded, e.total);
    x.onload = () => {
      let data = {};
      try { data = JSON.parse(x.responseText); } catch {}
      if (x.status === 401) { showLogin("Votre session a expiré, veuillez vous reconnecter."); return reject(new Error("Non connecté")); }
      x.status >= 200 && x.status < 300 ? resolve(data) : reject(new Error(data.detail || `Erreur ${x.status}`));
    };
    x.onerror = () => reject(new Error("Envoi interrompu : vérifiez votre connexion"));
    x.send(fd);
  });
}

async function submitFile() {
  const file = jobFile.files[0];
  if (!file) throw new Error("Choisissez un fichier audio ou vidéo");
  const max = (state.status?.max_upload_mb || 4096) * 1024 * 1024;
  if (file.size > max) throw new Error(`Fichier trop volumineux (maximum ${fmtSize(max)})`);
  const fd = new FormData();
  fd.append("folder_id", state.current);
  for (const k of ["title", "date", "start", "end", "intro_id"]) fd.append(k, form[k].value);
  fd.append("file", file);
  $("uploadProgress").hidden = false;
  try {
    await uploadJob(fd, (done, total) => {
      const pct = Math.round((100 * done) / total);
      $("uploadBar").style.width = pct + "%";
      $("uploadText").textContent = pct < 100 ? `Envoi du fichier… ${pct} % (${fmtSize(done)} sur ${fmtSize(total)})` : "Fichier reçu, vérification en cours…";
    });
  } finally { $("uploadProgress").hidden = true; $("uploadBar").style.width = "0"; }
  jobFile.value = ""; showPicked(null);
}

form.onsubmit = async (e) => {
  e.preventDefault();
  await busy(form.querySelector("button[type=submit]"), async () => {
    try {
      if (source === "file") await submitFile();
      else {
        const body = Object.fromEntries(new FormData(form));
        delete body.file;
        body.folder_id = state.current;
        body.intro_id = body.intro_id === "" ? null : +body.intro_id;
        await api("/api/jobs", { method: "POST", body });
        form.youtube_url.value = "";
      }
      form.title.value = ""; form.start.value = ""; form.end.value = "";
      updateFilenamePreview();
      toast("Traitement ajouté à la file d'attente", "ok");
      $("newJobPanel").hidden = true;
      loadJobs(); loadFolders(); loadStatus();
    } catch (err) { toast(err.message, true); }
  });
};
setSource("url");

// ---------- Liste de liens à préparer (ajout groupé) ----------
let batch = [];
try { batch = JSON.parse(localStorage.getItem("batch") || "[]"); } catch {}
const saveBatch = () => { try { localStorage.setItem("batch", JSON.stringify(batch)); } catch {} };
const newId = () => Math.random().toString(36).slice(2, 9);
const fmtBounds = (r) => r.start || r.end ? `${r.start || "début"} → ${r.end || "fin"}` : "";

function renderBatch() {
  $("batchCount").textContent = batch.length || "";
  $("batchList").innerHTML = batch.length ? batch.map((r, i) => `
    <div class="batch-row ${r.error ? "err" : ""}" data-id="${r.id}">
      <span class="n">${i + 1}</span>
      <div style="min-width:0"><div class="t">${esc(r.title)} <span class="muted">· ${esc(r.date)}</span>
        ${fmtBounds(r) ? `<span class="chip accent">${esc(fmtBounds(r))}</span>` : ""}</div>
        <div class="u">${esc(r.url)}</div></div>
      <div class="actions">
        <button class="icon-btn" type="button" data-batch="edit" title="Modifier">${ic("edit")}</button>
        <button class="icon-btn danger" type="button" data-batch="delete" title="Retirer de la liste">${ic("trash")}</button>
      </div>
      ${r.error ? `<div class="e">${esc(r.error)}</div>` : ""}
    </div>`).join("") : '<div class="batch-empty">La liste est vide. Ajoutez un lien ci-dessus.</div>';
  $("batchRunLabel").textContent = batch.length ? `Lancer ${batch.length} traitement${batch.length > 1 ? "s" : ""}` : "Lancer";
  $("batchRunBtn").disabled = !batch.length;
  $("batchClearBtn").disabled = !batch.length;
}

function checkRow(r) {
  if (!/^https?:\/\//i.test(r.url)) return "Le lien doit commencer par http:// ou https://";
  if (!r.title.trim()) return "Le nom est obligatoire";
  for (const [k, label] of [["start", "Début"], ["end", "Fin"]]) if (r[k] && isNaN(parseClock(r[k]))) return `${label} : format h:mm:ss attendu (ex. 1:05:30)`;
  if (r.start && r.end && parseClock(r.end) <= parseClock(r.start)) return "La fin doit être après le début";
  return "";
}

function addBatchRow() {
  const r = { id: newId(), url: $("batchUrl").value.trim(), title: $("batchTitle").value.trim(),
    date: $("batchDate").value || form.date.value, start: $("batchStart").value.trim(), end: $("batchEnd").value.trim() };
  const err = checkRow(r);
  if (err) return toast(err, true);
  batch.push(r);
  saveBatch();
  $("batchUrl").value = ""; $("batchTitle").value = ""; $("batchStart").value = ""; $("batchEnd").value = "";
  renderBatch();
  $("batchUrl").focus();
}
$("batchAddBtn").onclick = addBatchRow;
[$("batchUrl"), $("batchTitle"), $("batchDate"), $("batchStart"), $("batchEnd")].forEach((el) => el.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addBatchRow(); } }));

async function editBatchRow(r) {
  const saved = await modal({
    title: "Modifier ce traitement", wide: true,
    body: `<label>Lien YouTube<input name="url" value="${esc(r.url)}"></label>
      <div class="row"><label>Nom<input name="title" value="${esc(r.title)}"></label>
      <label>Date<input name="date" type="date" value="${esc(r.date)}"></label></div>
      <div class="row"><label>Début de la prédication (facultatif)<input name="start" placeholder="1:05:30" value="${esc(r.start)}"></label>
      <label>Fin (facultatif)<input name="end" placeholder="2:10:00" value="${esc(r.end)}"></label></div>
      <p class="hint">Début et fin vides = détection automatique.</p>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Enregistrer", primary: true }],
    submit: async (dlg) => {
      const v = (n) => dlg.querySelector(`[name=${n}]`).value.trim();
      const next = { ...r, url: v("url"), title: v("title"), date: v("date") || r.date, start: v("start"), end: v("end"), error: "" };
      const err = checkRow(next);
      if (err) throw new Error(err);
      Object.assign(r, next);
    },
  });
  if (saved) { saveBatch(); renderBatch(); }
}

$("batchList").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-batch]");
  if (!b) return;
  const r = batch.find((x) => x.id === b.closest(".batch-row").dataset.id);
  if (b.dataset.batch === "edit") await editBatchRow(r);
  else { batch = batch.filter((x) => x !== r); saveBatch(); renderBatch(); }
});

$("batchClearBtn").onclick = async () => {
  if (await confirmBox({ title: "Vider la liste ?", message: `Les ${batch.length} lien(s) préparés seront retirés de la liste (rien n'est supprimé ailleurs).`, confirmLabel: "Vider", danger: true })) {
    batch = []; saveBatch(); renderBatch();
  }
};

$("batchPasteBtn").onclick = async () => {
  const added = await modal({
    title: "Coller une liste de liens", wide: true,
    body: `<p>Une ligne par traitement : <b>lien | nom | date | début | fin</b> (date, début et fin sont facultatifs ; début et fin valent pour cette ligne seulement).</p>
      <textarea name="text" rows="7" placeholder="https://youtube.com/watch?v=… | La foi qui déplace les montagnes | 2026-10-11 | 1:05:30 | 2:10:00"></textarea>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Ajouter à la liste", primary: true }],
    submit: async (dlg) => {
      const rows = dlg.querySelector("[name=text]").value.split("\n").map((l) => l.trim()).filter(Boolean).map((line) => {
        const [url, title, date, start, end] = line.split("|").map((p) => p.trim());
        return { id: newId(), url: url || "", title: title || "", date: date || form.date.value, start: start || "", end: end || "", error: "" };
      });
      if (!rows.length) throw new Error("Aucune ligne à ajouter");
      const bad = rows.map((r, i) => [i + 1, checkRow(r)]).filter(([, e]) => e);
      if (bad.length) throw new Error(bad.map(([i, e]) => `Ligne ${i} : ${e}`).join(" — "));
      batch.push(...rows);
      return rows.length;
    },
  });
  if (added) { saveBatch(); renderBatch(); toast(`${added} lien(s) ajouté(s) à la liste`, "ok"); }
};

$("batchRunBtn").onclick = (e) => busy(e.currentTarget, async () => {
  if (!batch.length) return;
  const intro = $("batchIntroSelect").value;
  let ok = 0;
  for (const r of [...batch]) {
    try {
      await api("/api/jobs", { method: "POST", body: { folder_id: state.current, youtube_url: r.url, title: r.title,
        date: r.date, start: r.start || null, end: r.end || null, intro_id: intro === "" ? null : +intro } });
      batch = batch.filter((x) => x !== r);
      ok++;
    } catch (err) { r.error = err.message; }
    renderBatch();
  }
  saveBatch();
  if (ok) toast(`${ok} traitement(s) ajouté(s) à la file`, "ok");
  const failed = batch.filter((r) => r.error);
  if (failed.length) alertBox({ title: `${failed.length} ligne(s) non lancée(s)`, kind: "danger",
    message: "Elles restent dans la liste avec leur erreur : modifiez-les puis relancez." });
  loadJobs(); loadStatus();
});
$("batchDate").value = form.date.value;
renderBatch();

// ---------- Détails d'un traitement ----------
async function openDetail(id, silent = false) {
  const j = await api(`/api/jobs/${id}`).catch((err) => { if (!silent) toast(err.message, true); return null; });
  if (!j || (silent && !$("detailDialog").open)) return;  // rafraîchissement tardif : la fenêtre a été fermée entre-temps
  state.detail = j;
  const dlg = $("detailDialog");
  const logOpen = dlg.querySelector("details.log")?.open;
  const keepAudio = dlg.querySelector("audio");
  $("detailTitle").textContent = j.title;
  const admin = state.me.is_admin;  // les autres comptes ne voient ni les étapes, ni le repérage, ni le journal
  const row = (k, v) => v ? `<dt>${k}</dt><dd>${v}</dd>` : "";
  const link = j.links.mp3 ? `<div class="linkrow"><b>MP3</b>
      <input readonly value="${esc(j.links.mp3)}" onfocus="this.select()">
      <button class="btn small" data-copy="mp3">Copier</button>
      <a class="btn small ghost" href="${esc(j.links.mp3)}" target="_blank" rel="noopener">Ouvrir</a></div>` : "";
  $("detailBody").innerHTML = `
    <div class="job-top"><div class="job-sub">${ic("folder")} ${esc(j.folder_path)}</div>
      ${can("folders.manage") && editable(j) ? `<button class="btn small ghost" data-act="rename" data-id="${j.id}">${ic("edit")} Renommer</button>` : ""}
      <span class="badge ${j.status}">${LABELS[j.status]}</span></div>
    ${liveBlock(j)}
    ${j.error ? `<div class="err-box">${esc(j.error)}</div>` : ""}
    ${j.has_mp3 || link ? `<div class="d-title">Écouter et télécharger</div>
      ${j.has_mp3 ? `<div data-player="${j.id}" data-auto></div>` : ""}
      <div class="actions">${j.has_mp3 ? `<a class="btn small" href="/api/jobs/${j.id}/file/mp3?download=true">⬇ Télécharger MP3</a>` : ""}</div>` : ""}
    ${link ? `<div class="d-title">Lien direct de partage (R2)</div>${link}
      <p class="hint">${j.links_public ? "Lien public permanent."
        : `Lien signé valable ${j.links_days} jours, regénéré à chaque ouverture de cette fenêtre. Pour des liens permanents, configurez R2_PUBLIC_BASE_URL.`}</p>` : ""}
    <div class="d-title">Informations</div>
    <dl class="kv">
      ${row("Fichier", esc(j.display_filename))}
      ${admin ? `${row("Intro", esc(j.intro_name))}
      ${row("Source", j.from_upload ? `Fichier envoyé : ${esc(j.video_title || "")}` : "")}
      ${row("Vidéo", j.youtube_url && !j.from_upload ? `<a href="${esc(j.youtube_url)}" target="_blank" rel="noopener">${esc(j.video_title || j.youtube_url)}</a>` : "")}
      ${row("Prédication", j.sermon_start ? `${j.sermon_start} → ${j.sermon_end}` : "")}
      ${row("Repérage", esc(j.detection_note || ""))}
      ${row("Montage", esc(j.edit_note || ""))}
      ${row("Bornes forcées", j.start_override || j.end_override ? `${j.start_override || "début"} → ${j.end_override || "fin"}` : "")}
      ${row("Durée de la vidéo", j.duration_source)}` : ""}
      ${row("Durée du podcast", j.duration_output)}
      ${row("Taille", j.size_mp3 ? fmtSize(j.size_mp3) : "")}
      ${row("Créé par", esc(j.created_by || ""))}
      ${row("Créé le", fmtDate(j.created_at))}
      ${row("Terminé le", j.finished_at ? fmtDate(j.finished_at) : "")}
    </dl>
    ${admin ? `<div class="d-title">Étapes</div>
    ${renderSteps(j, true)}
    <details class="log" ${logOpen ? "open" : ""}><summary>Journal complet</summary>
      <pre class="detail-log">${esc(j.log || "(vide)")}</pre></details>` : ""}
    <div class="dialog-foot">
      ${j.status === "done" && j.has_mp3 && can("jobs.trim") && editable(j) ? `<button class="btn ghost" data-act="trim" data-id="${j.id}">${ic("scissors")} Rogner</button>` : ""}
      ${(j.status === "done" || j.status === "error") && can("jobs.create") && editable(j) ? `<button class="btn ghost" data-act="retry" data-id="${j.id}">Relancer</button>` : ""}
      ${j.status !== "running" && can("jobs.delete") && editable(j) ? `<button class="btn ghost danger" data-act="delete" data-id="${j.id}">Supprimer</button>` : ""}
    </div>`;
  const slot = $("detailBody").querySelector("[data-player]");
  if (slot) slot.replaceWith(keepAudio && keepAudio.dataset.job == j.id ? keepAudio : makePlayer(j.id, false));
  if (!dlg.open) dlg.showModal();
}
$("detailBody").addEventListener("click", (e) => {
  const b = e.target.closest("[data-copy]");
  if (b) copyLink(state.detail.links[b.dataset.copy]);
});
$("detailClose").onclick = () => $("detailDialog").close();
$("detailDialog").addEventListener("close", () => { state.detail = null; });

// ---------- Utilisateurs (administrateur) ----------
async function loadUsers() {
  loadingLine($("usersList"));
  try {
    const users = await api("/api/users");
    state.users = users;
    $("usersList").innerHTML = users.map((u) => {
      const name = u.display_name || u.username;
      const perms = u.is_admin ? ["Tous les droits"] : u.permissions.map((p) => state.me.catalog[p] || p);
      return `<div class="user-row">
        <div class="who"><span class="avatar">${esc(name.slice(0, 1).toUpperCase())}</span>
          <div><div class="job-title">${esc(name)} <span class="muted">@${esc(u.username)}</span>
            ${u.is_system ? '<span class="badge admin">Système</span>' : u.is_admin ? '<span class="badge admin">Admin</span>' : ""}
            <span class="badge ${u.is_active ? "active" : "inactive"}">${u.is_active ? "Actif" : "Désactivé"}</span>
            <span class="badge" title="Traitements simultanés">${u.max_parallel} en parallèle</span></div>
            <div class="job-sub">${u.last_login ? "Dernière connexion : " + fmtDate(u.last_login) : "Jamais connecté"}</div></div></div>
        ${u.is_system ? `<div class="locked" title="${esc("Compte créé au démarrage de l'application")}">${ic("lock")} Compte système protégé</div>` : `<div class="actions">
          <button class="btn small ghost" data-user-act="edit" data-id="${u.id}">${ic("edit")} Modifier</button>
          <button class="btn small ghost" data-user-act="toggle" data-id="${u.id}">${u.is_active ? "Désactiver" : "Activer"}</button>
          <button class="btn small ghost danger" data-user-act="delete" data-id="${u.id}">Supprimer</button>
        </div>`}
        <div class="chips">${perms.length ? perms.map((p) => `<span class="chip">${esc(p)}</span>`).join("") : '<span class="chip">Aucune permission</span>'}</div>
      </div>`;
    }).join("");
  } catch (err) { toast(err.message, true); }
}

async function userForm(user = null) {
  const cat = Object.entries(state.me.catalog);
  const r = await modal({
    title: user ? `Modifier ${user.username}` : "Nouvel utilisateur", wide: true,
    body: `<div class="row"><label>Identifiant<input name="username" value="${esc(user?.username || "")}" ${user ? "disabled" : ""} autocomplete="off" placeholder="prenom.nom"></label>
      <label>Nom affiché<input name="display_name" value="${esc(user?.display_name || "")}" autocomplete="off"></label></div>
      <label>Mot de passe ${user ? "(laisser vide pour ne pas le changer)" : "(8 caractères minimum)"}<input name="password" type="password" autocomplete="new-password"></label>
      <label class="check"><input type="checkbox" name="is_admin" ${user?.is_admin ? "checked" : ""}> Administrateur — tous les droits, gère les comptes</label>
      <label>Traitements simultanés (les suivants restent en file)<input name="max_parallel" type="number" min="1" max="${state.status?.max_parallel_limit || 20}" value="${user?.max_parallel ?? 5}" required></label>
      <div class="d-title">Permissions</div>
      <div class="perm-list">${cat.map(([k, l]) => `<label><input type="checkbox" name="perm" value="${k}" ${user?.permissions.includes(k) ? "checked" : ""}> ${esc(l)}</label>`).join("")}</div>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: user ? "Enregistrer" : "Créer l'utilisateur", primary: true }],
    onMount: (dlg) => {
      const admin = dlg.querySelector("[name=is_admin]");
      const sync = () => dlg.querySelectorAll("[name=perm]").forEach((c) => { if (admin.checked) c.checked = true; c.disabled = admin.checked; });
      admin.onchange = sync; sync();
    },
    submit: async (dlg) => {
      const v = (n) => dlg.querySelector(`[name=${n}]`);
      const body = { display_name: v("display_name").value, is_admin: v("is_admin").checked, max_parallel: +v("max_parallel").value,
        permissions: [...dlg.querySelectorAll("[name=perm]:checked")].map((c) => c.value) };
      if (v("password").value) body.password = v("password").value;
      if (user) return api(`/api/users/${user.id}`, { method: "PATCH", body });
      return api("/api/users", { method: "POST", body: { ...body, username: v("username").value, password: v("password").value } });
    },
  });
  if (r) { toast(user ? "Utilisateur mis à jour" : "Utilisateur créé", "ok"); loadUsers(); }
}

$("newUserBtn").onclick = () => userForm();
$("usersList").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-user-act]");
  if (!b) return;
  const u = state.users.find((x) => x.id === +b.dataset.id);
  await busy(b, async () => {
    try {
      if (b.dataset.userAct === "edit") await userForm(u);
      else if (b.dataset.userAct === "toggle") {
        const ok = u.is_active ? await confirmBox({ title: "Désactiver ce compte ?", confirmLabel: "Désactiver",
          message: `<b>${esc(u.username)}</b> ne pourra plus se connecter et sera déconnecté immédiatement.` }) : true;
        if (!ok) return;
        await api(`/api/users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } });
        toast(u.is_active ? "Compte désactivé" : "Compte activé", "ok");
        loadUsers();
      } else if (b.dataset.userAct === "delete") {
        const ok = await confirmBox({ title: "Supprimer cet utilisateur ?", danger: true, confirmLabel: "Supprimer",
          message: `Le compte <b>${esc(u.username)}</b> sera supprimé définitivement. Ses traitements restent dans l'historique.` });
        if (!ok) return;
        await api(`/api/users/${u.id}`, { method: "DELETE" });
        toast("Utilisateur supprimé", "ok");
        loadUsers();
      }
    } catch (err) { alertBox({ title: "Action impossible", message: esc(err.message), kind: "danger" }); }
  });
});

// ---------- Démarrage ----------
hydrateIcons();
(async function boot() {
  try {
    state.me = await api("/api/auth/me");
    await startApp();
  } catch { showLogin(); }
})();

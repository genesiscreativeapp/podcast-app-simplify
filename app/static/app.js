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
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
};
const ic = (n) => `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ""}</svg>`;
const hydrateIcons = (root = document) => root.querySelectorAll("[data-ic]").forEach((el) => { el.innerHTML = ic(el.dataset.ic); });

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

const promptBox = ({ title, label, value = "", placeholder = "", confirmLabel = "Enregistrer", submit }) =>
  modal({
    title, body: `<label>${esc(label)}<input name="v" value="${esc(value)}" placeholder="${esc(placeholder)}" autocomplete="off"></label>`,
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
  $("newRootBtn").hidden = !can("folders.manage");
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
  if (/^\d+$/.test(h) && byId(+h)) return go("folder", +h);
  if (h === "history" || (h === "users" && state.me.is_admin)) return go(h);
  return go("home");
}

async function go(view, id = null) {
  state.view = view;
  state.current = view === "folder" ? id : null;
  const hash = view === "folder" ? String(id) : view;
  if (location.hash.slice(1) !== hash) history.replaceState(null, "", "#" + hash);
  for (const v of ["home", "history", "users", "folder"]) $(v + "View").hidden = v !== view;
  document.querySelectorAll(".nav-link").forEach((b) => b.classList.toggle("active", b.dataset.nav === view));
  $("sidebar").classList.remove("open");
  renderTree();
  if (view === "home") await loadHome();
  else if (view === "history") await loadHistory();
  else if (view === "users") await loadUsers();
  else if (view === "folder") { state.jobs = []; renderFolder(); await loadJobs(); }
}
window.addEventListener("hashchange", () => { if (state.me) route(); });
document.addEventListener("click", (e) => {
  const n = e.target.closest("[data-nav]");
  if (n) go(n.dataset.nav);
});
$("menuBtn").onclick = () => $("sidebar").classList.toggle("open");

// Rafraîchissement : la progression vient de la base, elle est donc toujours là après un rechargement de la page
async function tick() {
  clearTimeout(state.timers.tick);
  if (!state.me) return;
  if (document.visibilityState === "visible") {
    const s = await loadStatus();
    const active = s ? s.running + s.pending : 0;
    if (active > 0 || state.lastActive > 0) refreshView();
    state.lastActive = active;
  }
  state.timers.tick = setTimeout(tick, 3000);
}
function refreshView() {
  if (state.view === "home") loadHome(true);
  else if (state.view === "history") loadHistory(false, true);
  else if (state.view === "folder") loadJobs();
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

function jobActions(j, { detail = true, play = false } = {}) {
  return `<div class="actions">
    ${play && j.has_mp3 ? `<button class="btn small ghost" data-act="play" data-id="${j.id}">${ic("play")} Écouter</button>` : ""}
    ${j.has_mp3 ? `<a class="btn small" href="/api/jobs/${j.id}/file/mp3?download=true">${ic("download")} Télécharger MP3</a>` : ""}
    ${j.on_r2 ? `<button class="btn small ghost" data-act="link" data-id="${j.id}">${ic("link")} Copier le lien</button>` : ""}
    ${detail ? `<button class="btn small ghost" data-act="detail" data-id="${j.id}">${ic("info")} Détails</button>` : ""}
    ${(j.status === "done" || j.status === "error") && can("jobs.create") ? `<button class="btn small ghost" data-act="retry" data-id="${j.id}">${ic("retry")} Relancer</button>` : ""}
    ${j.status !== "running" && can("jobs.delete") ? `<button class="btn small ghost danger" data-act="delete" data-id="${j.id}">${ic("trash")} Supprimer</button>` : ""}
  </div>`;
}

// Carte complète (dossier, accueil « en cours »)
function jobCard(j, withFolder = false) {
  const stats = [];
  if (j.sermon_start) stats.push(`Prédication <b>${j.sermon_start} → ${j.sermon_end}</b>`);
  if (j.duration_source) stats.push(`Vidéo <b>${j.duration_source}</b>`);
  if (j.duration_output) stats.push(`Podcast <b>${j.duration_output}</b>`);
  if (j.size_mp3) stats.push(`MP3 <b>${fmtSize(j.size_mp3)}</b>`);
  if (j.on_r2) stats.push("☁️ <b>R2</b>");
  return `<div class="job" data-id="${j.id}">
    <div class="job-top">
      <div>
        <div class="job-title">${esc(j.title)} <span class="muted">· ${esc(j.date)}</span></div>
        <div class="job-sub">${withFolder && j.folder_path ? ic("folder") + " " + esc(j.folder_path) + " · " : ""}${esc(j.video_title || j.youtube_url)}</div>
      </div>
      <span class="badge ${j.status}">${LABELS[j.status]}</span>
    </div>
    ${liveBlock(j)}
    ${renderSteps(j)}
    ${stats.length ? `<div class="stats">${stats.map((s) => `<span>${s}</span>`).join("")}</div>` : ""}
    ${j.detection_note && j.status === "done" ? `<div class="hint">${esc(j.detection_note)}</div>` : ""}
    ${j.edit_note && j.status === "done" ? `<div class="hint-box">${esc(j.edit_note)}</div>` : ""}
    ${j.error ? `<div class="err-box">${esc(j.error)}</div>` : ""}
    ${j.has_mp3 ? `<div data-player="${j.id}" data-auto></div>` : ""}
    ${jobActions(j)}
  </div>`;
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

// ---------- Statut, parallélisme ----------
async function loadStatus() {
  const s = await api("/api/status").catch(() => null);
  if (!s) return null;
  $("statusBar").innerHTML = `
    <span class="pill ${s.r2 ? "on" : ""}">R2 ${s.r2 ? "connecté" : "non configuré"}</span>
    <span class="pill ${s.llm ? "on" : ""}">Détection ${s.llm ? "IA (" + s.llm + ")" : "heuristique"}</span>
    <span class="pill link ${s.running ? "busy" : ""}" data-status="active">▶ ${s.running}/${s.max_parallel} en cours</span>
    <span class="pill link ${s.pending ? "waiting" : ""}" data-status="active">⏳ ${s.pending} en file</span>`;
  state.status = s;
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
    keepPlayers($("homeActive"), act.items.map((j) => jobCard(j, true)).join(""));
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

// ---------- Dossiers ----------
const children = (pid) => state.folders.filter((f) => f.parent_id === pid).sort((a, b) => a.name.localeCompare(b.name, "fr"));
const byId = (id) => state.folders.find((f) => f.id === id);
function pathOf(folder) {
  const out = [];
  for (let cur = folder; cur; cur = cur.parent_id ? byId(cur.parent_id) : null) out.unshift(cur);
  return out;
}

async function loadFolders() {
  state.folders = await api("/api/folders");
  renderTree();
}

function renderTree() {
  const build = (pid) => {
    const kids = children(pid);
    if (!kids.length) return "";
    return "<ul>" + kids.map((f) => {
      const hasKids = children(f.id).length > 0;
      const open = state.expanded.has(f.id);
      return `<li>
        <div class="node ${state.view === "folder" && state.current === f.id ? "active" : ""}" data-id="${f.id}">
          <span class="twisty" data-toggle="${f.id}">${hasKids ? (open ? "▾" : "▸") : ""}</span>
          <span class="ficon">${ic("folder")}</span><span>${esc(f.name)}</span>
        </div>
        ${hasKids && open ? build(f.id) : ""}
      </li>`;
    }).join("") + "</ul>";
  };
  $("tree").innerHTML = build(null) || '<p class="hint" style="padding:0 8px">Aucun dossier</p>';
}

$("tree").addEventListener("click", (e) => {
  const tog = e.target.closest("[data-toggle]");
  if (tog && tog.textContent) {
    const id = +tog.dataset.toggle;
    state.expanded.has(id) ? state.expanded.delete(id) : state.expanded.add(id);
    saveExpanded();
    renderTree();
    return;
  }
  const node = e.target.closest(".node");
  if (node) openFolder(+node.dataset.id);
});

function openFolder(id) {
  pathOf(byId(id)).slice(0, -1).forEach((f) => state.expanded.add(f.id));
  saveExpanded();
  go("folder", id);
}

async function createFolder(parentId) {
  const f = await promptBox({
    title: parentId ? "Nouveau sous-dossier" : "Nouveau dossier",
    label: "Nom", placeholder: parentId ? "Octobre 2026" : "CULTE ROYAL", confirmLabel: "Créer",
    submit: (name) => api("/api/folders", { method: "POST", body: { name, parent_id: parentId } }),
  });
  if (!f || !f.id) return;
  if (parentId) state.expanded.add(parentId);
  saveExpanded();
  await loadFolders();
  toast("Dossier créé", "ok");
  openFolder(f.id);
}

function renderFolder() {
  const f = byId(state.current);
  if (!f) return;
  const path = pathOf(f);
  $("crumbs").innerHTML = path.map((p, i) => i < path.length - 1 ? `<a data-id="${p.id}">${esc(p.name)}</a> / ` : "").join("");
  $("folderTitle").textContent = f.name;
  $("subfolders").innerHTML = children(f.id).map((c) => `<div class="subfolder" data-id="${c.id}">${ic("folder")} ${esc(c.name)}</div>`).join("");
  $("folderActions").hidden = !can("folders.manage");
  $("jobFormCard").hidden = !can("jobs.create");
  $("folderIntroSelect").disabled = !can("folders.manage");
  renderFolderIntro();
  updateFilenamePreview();
}

$("crumbs").addEventListener("click", (e) => { const a = e.target.closest("a"); if (a) openFolder(+a.dataset.id); });
$("subfolders").addEventListener("click", (e) => { const d = e.target.closest(".subfolder"); if (d) openFolder(+d.dataset.id); });
$("newRootBtn").onclick = () => createFolder(null);
$("emptyNewBtn").onclick = () => createFolder(null);
$("subfolderBtn").onclick = () => createFolder(state.current);
$("renameBtn").onclick = async () => {
  const f = byId(state.current);
  const r = await promptBox({ title: "Renommer le dossier", label: "Nouveau nom", value: f.name,
    submit: (name) => api(`/api/folders/${f.id}`, { method: "PATCH", body: { name } }) });
  if (r) { await loadFolders(); renderFolder(); toast("Dossier renommé", "ok"); }
};
$("deleteFolderBtn").onclick = async () => {
  const f = byId(state.current);
  const ok = await confirmBox({ title: "Supprimer le dossier ?", danger: true, confirmLabel: "Supprimer",
    message: `Le dossier « <b>${esc(f.name)}</b> » sera supprimé. Il doit être vide (ni sous-dossier ni traitement).` });
  if (!ok) return;
  try {
    await api(`/api/folders/${f.id}`, { method: "DELETE" });
    await loadFolders();
    toast("Dossier supprimé", "ok");
    f.parent_id ? openFolder(f.parent_id) : go("home");
  } catch (err) { alertBox({ title: "Suppression impossible", message: esc(err.message), kind: "danger" }); }
};

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

function renderFolderIntro() {
  const f = byId(state.current);
  if (!f) return;
  $("folderIntroSelect").innerHTML = introOptions([["", "Hériter (parent, sinon intro par défaut)"]], false, f.intro_id ?? "");
  const eff = effectiveIntro(f);
  $("folderIntroNote").textContent = eff
    ? `Intro appliquée : ${eff.name}${f.intro_id ? "" : eff.from ? ` (héritée de « ${eff.from.name} »)` : " (par défaut)"}`
    : "Aucune intro : ajoutez un MP3 dans la bibliothèque.";
  $("folderIntroPlayer").innerHTML = eff ? `<audio controls preload="none" src="/api/intros/${eff.id}/audio"></audio>` : "";
}

function renderIntroSelects() {
  const keep = $("jobIntroSelect").value;
  $("jobIntroSelect").innerHTML = introOptions([["", "Automatique (intro du dossier, sinon par défaut)"]], true, keep);
  const d = defaultIntro();
  $("defaultIntro").textContent = d ? `★ ${d.name}` : "Aucune intro par défaut";
  renderFolderIntro();
}

async function loadIntros() {
  state.intros = await api("/api/intros").catch(() => state.intros);
  renderIntroSelects();
  if ($("introDialog").open) renderIntroList();
}

$("folderIntroSelect").onchange = async (e) => {
  try {
    await api(`/api/folders/${state.current}/intro`, { method: "PUT", body: { intro_id: e.target.value ? +e.target.value : null } });
    await loadFolders();
    renderFolderIntro();
    toast("Intro du dossier enregistrée", "ok");
  } catch (err) { toast(err.message, true); }
};

function renderIntroList() {
  const manage = can("intros.manage");
  $("introList").innerHTML = state.intros.length ? state.intros.map((i) => `
    <div class="intro-item">
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

$("introsBtn").onclick = () => { $("sidebar").classList.remove("open"); renderIntroList(); $("introDialog").showModal(); };
$("introClose").onclick = () => $("introDialog").close();

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

form.onsubmit = async (e) => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(form));
  body.folder_id = state.current;
  body.intro_id = body.intro_id === "" ? null : +body.intro_id;
  await busy(form.querySelector("button[type=submit]"), async () => {
    try {
      await api("/api/jobs", { method: "POST", body });
      form.youtube_url.value = ""; form.title.value = ""; form.start.value = ""; form.end.value = "";
      updateFilenamePreview();
      toast("Traitement ajouté à la file d'attente", "ok");
      loadJobs(); loadStatus();
    } catch (err) { toast(err.message, true); }
  });
};

// Une ligne par traitement : lien | nom | date (facultative)
$("batchBtn").onclick = (e) => busy(e.currentTarget, async () => {
  const lines = $("batchText").value.split("\n").map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return toast("Aucune ligne à ajouter", true);
  const intro = form.intro_id.value;
  let ok = 0;
  const failed = [];
  for (const [i, line] of lines.entries()) {
    const [url, title, date] = line.split("|").map((p) => p.trim());
    try {
      await api("/api/jobs", { method: "POST", body: { folder_id: state.current, youtube_url: url, title: title || "",
        date: date || form.date.value, intro_id: intro === "" ? null : +intro } });
      ok++;
    } catch (err) { failed.push({ line, why: `ligne ${i + 1} : ${err.message}` }); }
  }
  $("batchText").value = failed.map((f) => f.line).join("\n");
  if (ok) toast(`${ok} traitement(s) ajouté(s) à la file`, "ok");
  if (failed.length) alertBox({ title: `${failed.length} ligne(s) non ajoutée(s)`, kind: "danger",
    message: failed.map((f) => esc(f.why)).join("<br>") });
  loadJobs(); loadStatus();
});

async function loadJobs() {
  if (state.view !== "folder" || !state.current) return;
  const folderId = state.current;
  if (!state.jobs.length) loadingLine($("jobs"));
  const jobs = await api(`/api/folders/${folderId}/jobs`).catch(() => null);
  if (!jobs || folderId !== state.current || state.view !== "folder") return;
  state.jobs = jobs;
  keepPlayers($("jobs"), jobs.length ? jobs.map((j) => jobCard(j)).join("") : '<p class="muted">Aucun traitement dans ce dossier.</p>');
}

// ---------- Détails d'un traitement ----------
async function openDetail(id, silent = false) {
  const j = await api(`/api/jobs/${id}`).catch((err) => { if (!silent) toast(err.message, true); return null; });
  if (!j) return;
  state.detail = j;
  const dlg = $("detailDialog");
  const logOpen = dlg.querySelector("details.log")?.open;
  const keepAudio = dlg.querySelector("audio");
  $("detailTitle").textContent = j.title;
  const row = (k, v) => v ? `<dt>${k}</dt><dd>${v}</dd>` : "";
  const link = j.links.mp3 ? `<div class="linkrow"><b>MP3</b>
      <input readonly value="${esc(j.links.mp3)}" onfocus="this.select()">
      <button class="btn small" data-copy="mp3">Copier</button>
      <a class="btn small ghost" href="${esc(j.links.mp3)}" target="_blank" rel="noopener">Ouvrir</a></div>` : "";
  $("detailBody").innerHTML = `
    <div class="job-top"><div class="job-sub">${ic("folder")} ${esc(j.folder_path)}</div><span class="badge ${j.status}">${LABELS[j.status]}</span></div>
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
      ${row("Fichier", esc(j.filename))}
      ${row("Intro", esc(j.intro_name))}
      ${row("Vidéo", j.youtube_url ? `<a href="${esc(j.youtube_url)}" target="_blank" rel="noopener">${esc(j.video_title || j.youtube_url)}</a>` : "")}
      ${row("Prédication", j.sermon_start ? `${j.sermon_start} → ${j.sermon_end}` : "")}
      ${row("Repérage", esc(j.detection_note || ""))}
      ${row("Montage", esc(j.edit_note || ""))}
      ${row("Bornes forcées", j.start_override || j.end_override ? `${j.start_override || "début"} → ${j.end_override || "fin"}` : "")}
      ${row("Durée de la vidéo", j.duration_source)}
      ${row("Durée du podcast", j.duration_output)}
      ${row("Taille", j.size_mp3 ? fmtSize(j.size_mp3) : "")}
      ${row("Créé par", esc(j.created_by || ""))}
      ${row("Créé le", fmtDate(j.created_at))}
      ${row("Terminé le", j.finished_at ? fmtDate(j.finished_at) : "")}
    </dl>
    <div class="d-title">Étapes</div>
    ${renderSteps(j, true)}
    <details class="log" ${logOpen ? "open" : ""}><summary>Journal complet</summary>
      <pre class="detail-log">${esc(j.log || "(vide)")}</pre></details>
    <div class="dialog-foot">
      ${(j.status === "done" || j.status === "error") && can("jobs.create") ? `<button class="btn ghost" data-act="retry" data-id="${j.id}">Relancer</button>` : ""}
      ${j.status !== "running" && can("jobs.delete") ? `<button class="btn ghost danger" data-act="delete" data-id="${j.id}">Supprimer</button>` : ""}
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
            ${u.is_admin ? '<span class="badge admin">Admin</span>' : ""}
            <span class="badge ${u.is_active ? "active" : "inactive"}">${u.is_active ? "Actif" : "Désactivé"}</span></div>
            <div class="job-sub">${u.last_login ? "Dernière connexion : " + fmtDate(u.last_login) : "Jamais connecté"}</div></div></div>
        <div class="actions">
          <button class="btn small ghost" data-user-act="edit" data-id="${u.id}">Modifier</button>
          <button class="btn small ghost" data-user-act="toggle" data-id="${u.id}">${u.is_active ? "Désactiver" : "Activer"}</button>
          <button class="btn small ghost danger" data-user-act="delete" data-id="${u.id}">Supprimer</button>
        </div>
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
      const body = { display_name: v("display_name").value, is_admin: v("is_admin").checked,
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

// ============================================================================
// Studio Podcast — interface
// ============================================================================
const state = {
  detailTab: "podcast", me: null, folders: [], intros: [], current: null, view: "home",
  jobs: [], hist: { items: [], total: 0 }, home: { sig: "", q: null }, detail: null, users: [],
  expanded: new Set(), lastActive: 0, timers: {}, aiUsers: [],
};
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const can = (p) => !!state.me && (state.me.is_admin || state.me.permissions.includes(p));
const fmtSize = (b) => (b ? (b / 1e6).toFixed(1) + " Mo" : "");
const fmtDate = (iso) => iso ? new Date(/Z|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z")
  .toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" }) : "—";
const LABELS = { pending: "En attente", running: "En cours", paused: "En pause", review: "À valider", done: "Terminé", error: "Erreur" };

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
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01"/>',
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
  } else if (b.dataset.user === "ai") {
    await myAiDialog();
  } else {
    await profileDialog();
  }
});

async function profileDialog() {  // nom affiché et mot de passe : tout utilisateur gère son propre compte
  const r = await modal({
    title: "Mon profil",
    body: `<label>Identifiant<input value="${esc(state.me.username)}" disabled></label>
      <label>Nom affiché<input name="display_name" value="${esc(state.me.display_name || "")}" maxlength="120" autocomplete="name" placeholder="${esc(state.me.username)}"></label>
      <div class="d-title">Changer le mot de passe <span class="hint">(facultatif)</span></div>
      <label>Mot de passe actuel<input type="password" name="current" autocomplete="current-password"></label>
      <label>Nouveau mot de passe (8 caractères minimum)<input type="password" name="new" autocomplete="new-password"></label>
      <label>Confirmer<input type="password" name="confirm" autocomplete="new-password"></label>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Enregistrer", primary: true }],
    submit: async (dlg) => {
      const v = (n) => dlg.querySelector(`[name=${n}]`).value;
      const pwd = v("current") || v("new") || v("confirm");
      if (pwd) {  // d'abord le mot de passe : s'il est refusé, rien d'autre n'est enregistré
        if (v("new") !== v("confirm")) throw new Error("La confirmation ne correspond pas");
        await api("/api/auth/password", { method: "POST", body: { current: v("current"), new: v("new") } });
      }
      if (v("display_name").trim() !== (state.me.display_name || "")) {
        state.me = { ...state.me, ...(await api("/api/auth/me", { method: "PATCH", body: { display_name: v("display_name") } })) };
        paintUser();
      }
      return { pwd: !!pwd };
    },
  });
  if (r) toast(r.pwd ? "Profil et mot de passe enregistrés" : "Profil enregistré", "ok");
}

// ---------- Démarrage et navigation ----------
function paintUser() {
  const name = state.me.display_name || state.me.username;
  $("userName").textContent = name;
  $("userAvatar").textContent = name.slice(0, 1).toUpperCase();
}

async function startApp() {
  $("loginScreen").hidden = true;
  $("app").hidden = false;
  $("boot").hidden = true;
  paintUser();
  $("navUsers").hidden = $("navPerms").hidden = $("navVoice").hidden = !state.me.is_admin;
  $("menuAi").hidden = !(can("ai.key") || can("ai.toggle"));
  $("emptyNewBtn").hidden = !can("folders.manage");
  $("parallelBox").hidden = !can("settings.manage");
  $("introForm").hidden = !can("intros.manage");
  $("jobEnBox").hidden = $("batchEnBox").hidden = !can("english.create");
  await Promise.all([loadFolders(), loadIntros(), loadAiUsers()]);
  await syncBatchUploads();
  loadStatus();
  await route();
  tick();
  if (!tourSeen()) setTimeout(startTour, 500);  // première connexion de ce compte sur ce navigateur
}

function route() {
  const h = location.hash.slice(1);
  if (/^\d+$/.test(h) && byId(+h)) return go("folders", +h);
  if (h === "folders") return go("folders");
  if (h === "history" || h === "intros" || h === "trash" || ((h === "users" || h === "perms" || h === "voice") && state.me.is_admin)) return go(h);
  return go("home");
}

async function go(view, id = null) {
  miniAdopt();  // un son en cours continue dans le mini-lecteur
  state.view = view;
  state.current = view === "folders" ? id : null;
  const hash = view === "folders" ? (id ? String(id) : "folders") : view;
  if (location.hash.slice(1) !== hash) history.replaceState(null, "", "#" + hash);
  for (const v of ["home", "folders", "history", "intros", "users", "perms", "trash", "voice"]) $(v + "View").hidden = v !== view;
  document.querySelectorAll(".nav-link").forEach((b) => b.classList.toggle("active", b.dataset.nav === view));
  $("sidebar").classList.remove("open");
  if (view === "home") await loadHome();
  else if (view === "history") await loadHistory();
  else if (view === "intros") { renderIntroList(); await loadIntros(); }
  else if (view === "users") await loadUsers();
  else if (view === "perms") await loadPerms();
  else if (view === "voice") await loadVoice();
  else if (view === "trash") await loadTrash();
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
    const active = s ? s.running + s.pending + (s.english || 0) : 0;
    if (active > 0 || state.lastActive > 0) {
      refreshView(true);
      if (state.view !== "folders") loadFolders();
    }
    state.lastActive = active;
  }
  state.timers.tick = setTimeout(tick, 3000);
}
// `poll` : rafraîchissement automatique (toutes les 3 s), qui évite de tout recharger si rien n'a bougé ;
// sinon (après une action : suppression, renommage, relance…), la page est toujours relue en entier.
function refreshView(poll = false) {
  if (state.view === "home") loadHome(true, !poll);
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
function makePlayer(id, autoplay, lang = "fr") {
  const a = document.createElement("audio");
  a.controls = true; a.preload = autoplay ? "auto" : "none"; a.dataset.job = id; a.dataset.lang = lang;
  a.src = lang === "en" ? `/api/jobs/${id}/english/file` : `/api/jobs/${id}/file/mp3`;
  if (autoplay) a.autoplay = true;
  return a;
}
// Un seul son à la fois : quand un lecteur démarre (détails, rognage, intros, listes), tous les autres se mettent en pause.
// L'événement « play » ne remonte pas dans le DOM : on l'écoute en phase de capture.
document.addEventListener("play", (e) => {
  document.querySelectorAll("audio").forEach((a) => { if (a !== e.target) a.pause(); });
  if (mini.audio && e.target !== mini.audio) miniClose();  // un autre son démarre : le mini-lecteur s'efface
}, true);

// ---------- Mini-lecteur : un son en cours ne s'arrête pas quand on quitte la page ou la fenêtre ----------
// Il apparaît en haut à droite de la page (dans son conteneur, pas dans l'en-tête) tant que le son n'est pas en pause,
// sauf dans l'éditeur de rognage, qui a son propre lecteur.
const mini = { audio: null, ac: null };
const mmss2 = (s) => (isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "0:00");
function miniTitle(a) {
  const lang = a.dataset.lang === "en" ? " (anglais)" : "";
  if (a.closest("#detailDialog")) return $("detailTitle").textContent + lang;
  const row = a.closest(".hrow");
  if (row) return (row.querySelector(".job-title")?.childNodes[0]?.textContent.trim() || "Podcast") + lang;
  return a.closest(".card, .item")?.querySelector("b")?.textContent.trim() || "Lecture en cours";
}
function miniClose() {
  mini.ac?.abort();
  if (mini.audio) { mini.audio.pause(); mini.audio.remove(); }
  mini.audio = mini.ac = null;
  $("miniPlayer").hidden = true;
  $("miniPlayer").innerHTML = "";
}
function miniAdopt() {  // appelé quand on quitte : fermeture des détails, changement de page
  if (document.body.classList.contains("trimming")) return;
  const a = [...document.querySelectorAll("audio")].find((x) => x.isConnected && !x.paused && !x.ended && !x.dataset.editor && !x.closest("#miniPlayer"));
  if (!a) return;
  miniClose();
  const box = $("miniPlayer"), id = a.dataset.job;
  box.innerHTML = `<div class="mp-top"><b class="mp-title" title="${esc(miniTitle(a))}">${esc(miniTitle(a))}</b>
      ${id ? `<button type="button" class="icon-btn" data-mp="open" title="Ouvrir les détails" aria-label="Ouvrir les détails">↗</button>` : ""}
      <button type="button" class="icon-btn" data-mp="close" title="Fermer" aria-label="Fermer">✕</button></div>
    <div class="mp-bar"><button type="button" class="icon-btn mp-play" data-mp="toggle" aria-label="Pause">⏸</button>
      <input type="range" class="mp-seek" min="0" max="1000" value="0" aria-label="Position"><span class="mp-time">0:00 / 0:00</span></div>`;
  const was = !a.paused;
  a.controls = false;
  box.appendChild(a);  // déplacé sans être recréé : la lecture continue
  box.hidden = false;
  if (was && a.paused) a.play().catch(() => {});  // filet : certains navigateurs mettent en pause un média déplacé
  mini.audio = a;
  mini.ac = new AbortController();
  const sig = { signal: mini.ac.signal }, seek = box.querySelector(".mp-seek"), time = box.querySelector(".mp-time"), btn = box.querySelector(".mp-play");
  const paint = () => {
    if (!seek.matches(":active")) seek.value = a.duration ? Math.round((1000 * a.currentTime) / a.duration) : 0;
    time.textContent = `${mmss2(a.currentTime)} / ${mmss2(a.duration)}`;
    btn.textContent = a.paused ? "▶" : "⏸";
    btn.setAttribute("aria-label", a.paused ? "Lecture" : "Pause");
  };
  ["timeupdate", "play", "pause", "loadedmetadata", "durationchange"].forEach((ev) => a.addEventListener(ev, paint, sig));
  a.addEventListener("ended", miniClose, sig);
  seek.oninput = () => { if (a.duration) a.currentTime = (seek.value / 1000) * a.duration; };
  paint();
}
$("miniPlayer").addEventListener("click", (e) => {
  const b = e.target.closest("[data-mp]");
  if (!b || !mini.audio) return;
  if (b.dataset.mp === "toggle") mini.audio.paused ? mini.audio.play() : mini.audio.pause();
  else if (b.dataset.mp === "close") miniClose();
  else if (b.dataset.mp === "open") openDetail(+mini.audio.dataset.job);
});
const loadingLine = (box) => (box.innerHTML = '<div class="loading-line"><span class="spinner"></span> Chargement…</div>');

const STEP_ICON = { done: "✓", active: "●", paused: "⏸", pending: "○", skipped: "–", error: "!" };
function renderSteps(j, open = false, key = "steps") {
  const rows = j.steps.map((s, i) => `
    <li class="st ${s.state}">
      <span class="st-icon">${STEP_ICON[s.state]}</span>
      <span class="st-name">${i + 1}. ${esc(s.label)}</span>
      <span class="st-bar"><i style="width:${s.pct}%"></i></span>
      <span class="st-pct">${s.state === "skipped" ? "ignorée" : s.pct + "%"}</span>
    </li>`).join("");
  return j.status === "done" && !open
    ? `<details class="steps" data-keep="${key}"><summary>Détail des étapes</summary><ul>${rows}</ul></details>`
    : `<ul class="steps">${rows}</ul>`;
}

const fmtTok = (n) => n.toLocaleString("fr-FR");
// Consommation de l'IA, mise à jour après chaque appel (toutes les quelques secondes pendant un traitement)
const tokensLine = (j) => (j.tokens_in || j.tokens_out)
  ? `<div class="tokens" title="Tokens échangés avec l'IA pour ce traitement">${ic("sparkle")} IA : <b>${fmtTok(j.tokens_in + j.tokens_out)}</b> tokens <small>(${fmtTok(j.tokens_in)} envoyés · ${fmtTok(j.tokens_out)} reçus)</small></div>` : "";

// « étape 3/6 » et une pastille par étape : traitement du podcast et version anglaise
const stepNo = (steps) => { const vis = steps.filter((x) => x.state !== "skipped"), i = vis.findIndex((x) => x.state === "active"); return i >= 0 ? `<small>· étape ${i + 1}/${vis.length}</small>` : ""; };
const pips = (steps) => `<div class="pips">${steps.filter((x) => x.state !== "skipped").map((x) => `<i class="${x.state}" style="--w:${x.pct}%" title="${esc(x.label)} — ${x.pct}%"></i>`).join("")}</div>`;

function liveBlock(j) {  // rang dans la file, ou barre globale s'il tourne
  if (j.status === "pending") {
    const note = j.step && j.step !== "En attente" ? ` · ${esc(j.step)}` : "";
    return `<div class="queued">${ic("clock")} En file d'attente — <b>n° ${j.queue_position}</b>${note}</div>`;
  }
  if (j.status === "paused") {
    const pct = Math.round(j.progress * 100);
    return `<div class="progress paused"><div style="width:${pct}%"></div></div>
      <div class="step"><b>⏸ En pause à ${pct} %</b> — le travail déjà fait est gardé ; « Reprendre » continue là où le traitement s'est arrêté</div>${tokensLine(j)}`;
  }
  if (j.status !== "running") return "";
  const pct = Math.round(j.progress * 100);
  return `<div class="progress"><div style="width:${pct}%"></div></div>
    <div class="step"><b>Global ${pct}%</b> — ${esc(j.step)}</div>${tokensLine(j)}`;
}

const isLive = (j) => j.status === "pending" || j.status === "running" || j.status === "paused";
// Arrêter une opération en attente, à valider ou en cours (traitement : act "stop" ; version anglaise : "enstop", `id` = le podcast)
const stopBtn = (x, id, act = "stop") => x.stopping
  ? '<button class="btn small ghost" disabled>Arrêt en cours…</button>'
  : `<button class="btn small ghost danger" data-act="${act}" data-id="${id}">■ Arrêter</button>`;
const canStop = (j) => ["pending", "running", "review", "paused"].includes(j.status) && can("jobs.create") && editable(j);
// Pause (le travail déjà fait est gardé) et reprise : traitement = actions "pause" / "resume", version anglaise = "enpause" / "enresume" (id = le podcast)
const pauseBtn = (x, id, act = "pause") => x.pausing
  ? '<button class="btn small ghost" disabled>Pause en cours…</button>'
  : `<button class="btn small ghost" data-act="${act}" data-id="${id}">⏸ Pause</button>`;
const resumeBtn = (id, act = "resume") => `<button class="btn small" data-act="${act}" data-id="${id}">▶ Reprendre</button>`;
const pauseCtl = (x, id, prefix = "", allowed = true) => !allowed || x.stopping ? ""
  : x.status === "paused" ? resumeBtn(id, prefix + "resume")
  : ["pending", "running"].includes(x.status) ? pauseBtn(x, id, prefix + "pause") : "";
const jobPauseCtl = (j) => pauseCtl(j, j.id, "", can("jobs.create") && editable(j));

// Version anglaise : état à côté du podcast, et les actions utiles directement dans la liste
const EN_LABEL = { pending: "en attente", running: "en cours", paused: "en pause", review: "à valider", done: "prête", error: "erreur" };
const enBadge = (j) => j.english ? `<span class="badge ${j.english.status}" title="Version anglaise : ${EN_LABEL[j.english.status]}">EN · ${EN_LABEL[j.english.status]}${j.english.status === "running" ? ` ${Math.round(j.english.progress * 100)} %` : ""}</span>` : "";
const canEnglish = (j) => j.status === "done" && j.has_mp3 && can("english.create") && editable(j);
const enActions = (j) => {
  const e = j.english;
  return [
    e?.status === "review" && canEnglish(j) ? `<button class="btn small" data-act="enreview" data-id="${j.id}">${ic("edit")} Relire l'anglais</button>` : "",
    e?.has_mp3 ? `<button class="btn small ghost" data-act="enplay" data-id="${j.id}">${ic("play")} Écouter EN</button>
      <a class="btn small ghost" href="/api/jobs/${j.id}/english/file?download=true">${ic("download")} MP3 EN</a>` : "",
    canEnglish(j) && (!e || e.status === "error") ? `<button class="btn small ghost" data-act="english" data-id="${j.id}">${ic("sparkle")} Version anglaise…</button>` : "",
  ].join("");
};

const editable = (j) => j.can_edit !== false;  // le serveur refuse de toute façon : on ne propose pas ce qui échouerait
function jobActions(j, { detail = true, play = false } = {}) {
  return `<div class="actions">
    ${play && j.has_mp3 ? `<button class="btn small ghost" data-act="play" data-id="${j.id}">${ic("play")} Écouter</button>` : ""}
    ${j.status === "review" && can("jobs.create") && editable(j) ? `<button class="btn small" data-act="review" data-id="${j.id}">${ic("scissors")} Relire le texte</button>` : ""}
    ${enActions(j)}
    ${j.has_mp3 ? `<a class="btn small" href="/api/jobs/${j.id}/file/mp3?download=true">${ic("download")} Télécharger MP3</a>` : ""}
    ${j.on_r2 ? `<button class="btn small ghost" data-act="link" data-id="${j.id}">${ic("link")} Copier le lien</button>` : ""}
    ${jobPauseCtl(j)}${canStop(j) ? stopBtn(j, j.id) : ""}
    ${detail ? `<button class="btn small ghost" data-act="detail" data-id="${j.id}">${ic("info")} Détails</button>` : ""}
    ${j.status === "done" && j.has_mp3 && can("jobs.trim") && editable(j) ? `<button class="btn small ghost" data-act="trim" data-id="${j.id}">${ic("scissors")} Rogner</button>` : ""}
    ${(j.status === "done" || j.status === "error") && can("jobs.create") && editable(j) ? `<button class="btn small ghost" data-act="retry" data-id="${j.id}">${ic("retry")} Relancer</button>` : ""}
    ${j.status !== "running" && can("jobs.delete") && editable(j) ? `<button class="btn small ghost danger" data-act="delete" data-id="${j.id}">${ic("trash")} Supprimer</button>` : ""}
  </div>`;
}

// Carte « en cours / en file » de l'accueil : anneau de progression, étape courante, une pastille par étape
function activeCard(j) {
  const sub = `${j.folder_path ? ic("folder") + " " + esc(j.folder_path) : ""}${j.created_by ? ` · par ${esc(j.created_by)}` : ""}`;
  const head = `<div class="ac-main">
      <div class="ac-title">${esc(j.title)} <span class="muted">· ${esc(j.date)}</span></div>
      <div class="ac-sub">${sub}</div>`;
  const actions = `<div class="ac-actions"><span class="by">${j.from_upload ? ic("upload") + " Fichier envoyé" : ""}</span>
      ${jobPauseCtl(j)}${canStop(j) ? stopBtn(j, j.id) : ""}
      <button class="btn small ghost" data-act="detail" data-id="${j.id}">${ic("info")} Détails</button></div>`;
  if (j.status === "review") {
    const mine = can("jobs.create") && editable(j);
    return `<div class="active-card review" data-id="${j.id}">
      <div class="ring review"><b>✋</b></div>
      ${head}<div class="ac-step"><b>À valider</b> <small>· ${j.condense_pct ? `${j.condense_pct} % de réduction visés : ` : ""}relisez le texte et les coupes</small></div></div>
      <div class="ac-actions"><span class="by"></span>${mine ? `<button class="btn small" data-act="review" data-id="${j.id}">${ic("scissors")} Relire le texte</button>` : ""}
        ${canStop(j) ? stopBtn(j, j.id) : ""}
        <button class="btn small ghost" data-act="detail" data-id="${j.id}">${ic("info")} Détails</button></div></div>`;
  }
  if (j.status === "pending") {
    return `<div class="active-card pending" data-id="${j.id}">
      <div class="ring queue"><b>n°<i>${j.queue_position}</i></b></div>
      ${head}<div class="ac-step">${ic("clock")} En file d'attente${j.step && j.step !== "En attente" ? ` <small>· ${esc(j.step)}</small>` : ""}</div></div>
      ${actions}</div>`;
  }
  const pct = Math.round(j.progress * 100);
  const paused = j.status === "paused";
  return `<div class="active-card ${paused ? "paused" : "running"}" data-id="${j.id}">
    <div class="ring" style="--p:${pct}"><b>${pct}<small>%</small></b></div>
    ${head}
      <div class="ac-step">${paused ? "⏸" : '<span class="live"></span>'}<b>${esc(j.step)}</b>${paused ? "" : stepNo(j.steps)}</div>
      ${pips(j.steps)}
      ${tokensLine(j)}
    </div>
    ${actions}</div>`;
}

// Carte d'une version anglaise en cours, en attente ou à valider (accueil)
function enCard(e) {
  const head = `<div class="ac-main"><div class="ac-title">🇬🇧 ${esc(e.title)} <span class="muted">· ${esc(e.date)} · version anglaise</span></div>
      <div class="ac-sub">${e.folder_path ? ic("folder") + " " + esc(e.folder_path) : ""}${e.created_by ? ` · par ${esc(e.created_by)}` : ""}</div>`;
  const detail = `${pauseCtl(e, e.job_id, "en", e.can_edit && can("english.create"))}${e.can_edit && can("english.create") ? stopBtn(e, e.job_id, "enstop") : ""}<button class="btn small ghost" data-act="detail" data-id="${e.job_id}">${ic("info")} Détails</button>`;
  if (e.status === "review") {
    return `<div class="active-card review" data-en="${e.id}"><div class="ring review"><b>✋</b></div>${head}
      <div class="ac-step"><b>Texte anglais à valider</b> <small>· la voix du prédicateur le dira tel quel</small></div></div>
      <div class="ac-actions"><span class="by"></span>${e.can_edit && can("english.create") ? `<button class="btn small" data-act="enreview" data-id="${e.job_id}">${ic("edit")} Relire le texte</button>` : ""}${detail}</div></div>`;
  }
  if (e.status === "pending") {
    return `<div class="active-card pending" data-en="${e.id}"><div class="ring queue"><b>EN</b></div>${head}
      <div class="ac-step">${ic("clock")} En attente du service de voix${state.enAlive ? "" : " <small>· il n'est pas démarré</small>"}</div></div><div class="ac-actions"><span class="by"></span>${detail}</div></div>`;
  }
  const pct = Math.round(e.progress * 100);
  const paused = e.status === "paused";
  return `<div class="active-card ${paused ? "paused" : "running"}" data-en="${e.id}"><div class="ring" style="--p:${pct}"><b>${pct}<small>%</small></b></div>${head}
    <div class="ac-step">${paused ? "⏸" : '<span class="live"></span>'}<b>${esc(e.step)}</b>${paused ? "" : stepNo(e.steps)}</div>
    ${pips(e.steps)}</div><div class="ac-actions"><span class="by"></span>${detail}</div></div>`;
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
    <span class="badge ${j.status}">${LABELS[j.status]}</span> ${enBadge(j)}
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

function introOptions(first, withNone = false, selected = "", lang = "fr") {
  const opts = [...first, ...state.intros.filter((i) => i.lang === lang).map((i) => [String(i.id), i.name + (i.is_default ? " ★ par défaut" : "")])];
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
    } else if (act === "review") await reviewDialog(job);
    else if (act === "english") await englishDialog(job);
    else if (act === "enreview") await enReviewDialog(job);
    else if (act === "enplay") {
      const row = btn.closest(".hrow");
      const existing = row.querySelector('audio[data-lang="en"]');
      if (existing) { const s = document.createElement("div"); s.className = "wide-col"; s.dataset.player = id; existing.replaceWith(s); return; }
      row.querySelector("[data-player]").replaceWith(makePlayer(id, true, "en"));
    } else if (act === "enlink") {
      const { url, public: pub } = await api(`/api/jobs/${id}/english/link`);
      await copyLink(url, pub ? "Lien public (anglais) copié" : "Lien (anglais) copié (valable 7 jours)");
    } else if (act === "endelete") {
      if (!(await confirmBox({ title: "Supprimer la version anglaise ?", danger: true, confirmLabel: "Supprimer définitivement",
        message: `La version anglaise de « <b>${esc(job.title)}</b> » (texte, fichier, et sur R2) sera supprimée <b>pour toujours</b>. Vous pourrez la régénérer.` }))) return;
      await api(`/api/jobs/${id}/english`, { method: "DELETE" });
      toast("Version anglaise supprimée", "ok");
      refreshView();
    } else if (act === "stop" || act === "enstop") {
      const en = act === "enstop";
      if (!(await confirmBox({ title: en ? "Arrêter la version anglaise ?" : "Arrêter ce traitement ?", danger: true, confirmLabel: "Arrêter",
        message: `« <b>${esc(job?.title || "Ce podcast")}</b> » : ce qui a été calculé jusqu'ici est perdu${en ? " (le texte anglais aussi)" : ""} ; « Relancer » repart de zéro.`
          + (en ? " L'arrêt est pris en compte entre deux morceaux de voix ; si le calcul ne répond pas, le service de voix redémarre." : " L'arrêt est pris en compte en quelques secondes.") }))) return;
      await api(`/api/jobs/${id}/${en ? "english/stop" : "stop"}`, { method: "POST" });
      toast("Arrêt demandé", "ok");
      refreshView(); loadStatus();
    } else if (act === "pause" || act === "enpause") {
      await api(`/api/jobs/${id}/${act === "enpause" ? "english/pause" : "pause"}`, { method: "POST" });
      toast("Pause demandée : elle prend effet en quelques secondes", "ok");
      refreshView(); loadStatus();
    } else if (act === "resume" || act === "enresume") {
      await api(`/api/jobs/${id}/${act === "enresume" ? "english/resume" : "resume"}`, { method: "POST" });
      toast("Reprise demandée", "ok");
      refreshView(); loadStatus();
    } else if (act === "retry") await retryDialog(job);
    else if (act === "trim") await trimDialog(job);
    else if (act === "rename") await renameJob(job);
    else if (act === "delete") {
      const ok = await confirmBox({ title: "Supprimer ce traitement ?",
        message: `« <b>${esc(job.title)}</b> » sera déplacé dans la <b>corbeille</b> : vous pourrez le restaurer. Seul un administrateur peut le supprimer définitivement.`,
        confirmLabel: "Mettre à la corbeille" });
      if (!ok) return;
      await api(`/api/jobs/${id}`, { method: "DELETE" });
      if (state.detail?.id === id) $("detailDialog").close();
      toast("Traitement mis à la corbeille", "ok");
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
      <label>Intro<select name="intro_id">${introOptions([["keep", "Ne pas changer"], ["", "Automatique (dossier, sinon par défaut)"]], true, "keep")}</select></label>
      ${state.me.is_admin ? `<label>IA utilisée<select name="ai_user">${aiOptions([["keep", "Ne pas changer"]], "keep")}</select></label>` : ""}
      <div class="row"><label>Durée du podcast<select name="condense_pct">
          ${[["keep", "Ne pas changer"], ["0", "Durée d'origine"], ["10", "Raccourcir d'environ 10 %"], ["20", "Raccourcir d'environ 20 %"], ["30", "Raccourcir d'environ 30 %"], ["40", "Raccourcir d'environ 40 %"], ["45", "Raccourcir d'environ 45 % (maximum)"]]
            .map(([v, l]) => `<option value="${v}" ${v === "keep" ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <label>Relecture du texte<select name="condense_mode"><option value="keep" selected>Ne pas changer</option>
          <option value="auto">Publier directement</option><option value="review">Me montrer le texte avant de publier</option></select></label></div>
      ${can("english.create") ? `<label>Version anglaise<select name="english"><option value="keep" selected>Ne pas changer</option><option value="">Non</option>
        <option value="review">Oui — je valide le texte avant la voix</option><option value="auto">Oui — publier automatiquement</option></select></label>
      <label>Traduction de la version anglaise<select name="english_translator">${trOptions(true)}</select></label>` : ""}`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Relancer", primary: true }],
    submit: async (dlg) => {
      const v = (n) => dlg.querySelector(`[name=${n}]`).value;
      const body = { start: v("start"), end: v("end") };
      if (v("intro_id") !== "keep") body.intro_id = v("intro_id") === "" ? null : +v("intro_id");
      if (state.me.is_admin && v("ai_user") !== "keep") body.ai_user = v("ai_user");
      if (v("condense_pct") !== "keep") body.condense_pct = +v("condense_pct");
      if (v("condense_mode") !== "keep") body.condense_mode = v("condense_mode");
      if (can("english.create") && v("english") !== "keep") body.english = v("english");
      if (can("english.create") && v("english_translator") !== "keep") body.english_translator = v("english_translator");
      await api(`/api/jobs/${job.id}/retry`, { method: "POST", body });
    },
  });
  if (done) { toast("Traitement relancé", "ok"); refreshView(); loadStatus(); }
}

// ---------- Version anglaise : demande et relecture du texte ----------
async function englishDialog(job) {
  const info = await api("/api/english"), e = job.english, d = info.defaults;
  const opts = (map, sel, off = {}) => Object.entries(map).map(([k, l]) => `<option value="${esc(k)}" ${k === sel ? "selected" : ""} ${off[k] ? "disabled" : ""}>${esc(l)}${off[k] ? " (indisponible)" : ""}</option>`).join("");
  const r = await modal({
    title: `Version anglaise · ${job.title}`, icon: "🇬🇧",
    body: `<p>Le texte du podcast final est traduit en anglais, puis lu avec <b>la voix du prédicateur</b> par le service de voix, sur le CPU du serveur : <b>cela peut prendre plusieurs heures</b> (le banc d'essai de l'administrateur mesure le temps).</p>
      ${e?.status === "done" ? '<p class="err-box">Cette demande <b>remplacera</b> la version anglaise existante.</p>' : ""}
      ${info.alive ? "" : '<p class="hint">Le service de voix n\'est pas démarré : la demande attendra qu\'un administrateur l\'active.</p>'}
      <label>Texte anglais<select name="mode"><option value="review">Je le relis et le valide avant que la voix ne le dise (recommandé)</option><option value="auto">Publier automatiquement</option></select></label>
      <label>Traduction<select name="translator">${opts(info.translators, d.translator, { claude: !info.claude_available })}</select></label>
      <label>Moteur de voix<select name="engine">${opts(info.engines, d.engine)}</select></label>
      <label>Voix de référence<select name="refmode"><option value="auto">Choisie automatiquement (le passage le plus régulier)</option><option value="manual">À partir d'un instant précis…</option></select></label>
      <label hidden id="enRefBox">Début de la voix de référence (secondes dans le podcast)<input name="ref_start" type="number" min="0" step="1" value="60"></label>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Lancer", primary: true }],
    onMount: (dlg) => { dlg.querySelector("[name=refmode]").onchange = (ev) => (dlg.querySelector("#enRefBox").hidden = ev.target.value !== "manual"); },
    submit: (dlg) => {
      const v = (n) => dlg.querySelector(`[name=${n}]`).value;
      return api(`/api/jobs/${job.id}/english`, { method: "POST", body: { mode: v("mode"), translator: v("translator"), engine: v("engine"),
        ref_start: v("refmode") === "manual" ? +v("ref_start") : null } });
    },
  });
  if (r) { toast("Version anglaise mise en file d'attente", "ok"); refreshView(); loadStatus(); }
}

async function enReviewDialog(job) {
  const rv = await api(`/api/jobs/${job.id}/english/review`);
  const useOf = (t) => !t.off && !!t.en.trim();
  const row = (t) => `<div class="en-row ${useOf(t) ? "" : "off"}" data-id="${t.id}">
      <label class="en-use" title="Cochée : la voix du prédicateur dira cette phrase"><input type="checkbox" data-use="${t.id}" ${useOf(t) ? "checked" : ""}></label>
      <div class="en-fr">${esc(t.fr)}</div>
      <textarea data-en="${t.id}" rows="${Math.max(2, Math.ceil(t.en.length / 70))}">${esc(t.en)}</textarea></div>`;
  const state_ = (dlg) => {
    const texts = {}, off = [];
    dlg.querySelectorAll("[data-en]").forEach((x) => (texts[x.dataset.en] = x.value));
    dlg.querySelectorAll("[data-use]").forEach((x) => { if (!x.checked) off.push(+x.dataset.use); });
    return { texts, off };
  };
  const r = await modal({
    title: `Relire le texte anglais · ${job.title}`, wide: true,
    body: `<p class="hint">Traduit par : <b>${esc(rv.method || "?")}</b>. <b>La voix du prédicateur dira exactement ce texte</b> : relisez surtout les versets, les noms propres et les termes spirituels. Modifiez le texte de chaque phrase, et <b>décochez</b> celles que la voix ne doit pas dire (leur texte est gardé, vous pouvez les recocher). <b>Enregistrez</b> pour continuer plus tard sans rien perdre.</p>
      <div class="rv-bar"><b id="enSum"></b><span><span id="enDirty" class="rv-dirty" hidden>● modifications non enregistrées</span>
        <button type="button" class="btn small ghost" id="enSave">💾 Enregistrer</button></span></div>
      <div class="en-list" id="enList">${rv.sentences.map(row).join("")}</div>`,
    buttons: [{ label: "Fermer", kind: "ghost", value: null }, { label: "Valider et générer la voix", primary: true }],
    onMount: (dlg) => {
      const dirty = (on) => (dlg.querySelector("#enDirty").hidden = !on);
      const sum = () => {
        const { off } = state_(dlg), used = [...dlg.querySelectorAll("[data-en]")].filter((x) => x.value.trim() && !off.includes(+x.dataset.en)).length;
        dlg.querySelector("#enSum").textContent = `${used} phrase(s) lue(s) par la voix sur ${rv.sentences.length}`;
      };
      sum();
      dlg.querySelector("#enList").addEventListener("change", (e) => {
        if (!e.target.matches("[data-use]")) return;
        e.target.closest(".en-row").classList.toggle("off", !e.target.checked);
        dirty(true); sum();
      });
      dlg.querySelector("#enList").addEventListener("input", (e) => { if (e.target.matches("[data-en]")) { dirty(true); sum(); } });
      dlg.querySelector("#enSave").onclick = (ev) => busy(ev.currentTarget, async () => {
        try {
          await api(`/api/jobs/${job.id}/english/review`, { method: "POST", body: { ...state_(dlg), validate: false } });
          dirty(false); toast("Brouillon enregistré", "ok");
        } catch (err) { toast(err.message, true); }
      });
    },
    submit: (dlg) => api(`/api/jobs/${job.id}/english/review`, { method: "POST", body: state_(dlg) }),
  });
  if (r) { toast("Texte validé : la voix va être générée", "ok"); refreshView(); loadStatus(); }
}

// ---------- Relecture des coupes de condensation ----------
let rvAudio = null;
const mmss = (s) => `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")} s`;
async function reviewDialog(job) {
  const rv = await api(`/api/jobs/${job.id}/review`);
  const byId = new Map(rv.sentences.map((s) => [s.id, s])), why = new Map(rv.removed.map((r) => [r.id, r])), chosen = new Set(rv.chosen);  // chosen = phrases retirées
  const edits = new Map(rv.sentences.filter((s) => s.edited).map((s) => [s.id, s.edited]));                                              // corrections du texte
  const cur = (s) => edits.get(s.id) ?? s.text;
  const cut = (id) => byId.get(id).cut[1] - byId.get(id).cut[0];
  const saved = () => [...chosen].reduce((t, id) => t + cut(id), 0);
  const payload = (removed, validate) => ({ removed, texts: Object.fromEntries(rv.sentences.map((s) => [s.id, cur(s)])), validate });
  const row = (s) => `<li class="rv-row ${why.has(s.id) ? "proposed" : ""} ${chosen.has(s.id) ? "off" : ""} ${edits.has(s.id) ? "edited" : ""}" data-id="${s.id}">
      <label class="rv-use" title="Cochée : la phrase est gardée dans le podcast"><input type="checkbox" data-rv="${s.id}" ${chosen.has(s.id) ? "" : "checked"}>
        <span class="rv-time">${fmtClockShort(s.start)}</span></label>
      <textarea class="rv-edit" data-rv-text="${s.id}" rows="${Math.max(1, Math.ceil(cur(s).length / 85))}">${esc(cur(s))}</textarea>
      <div class="rv-side">${why.has(s.id) ? `<small class="rv-why">${esc(why.get(s.id).reason)}${why.get(s.id).by === "IA" ? " · IA" : ""}</small>` : ""}
        <button type="button" class="icon-btn" data-rv-play="${s.id}" title="Écouter cette phrase (avec 1,5 s de contexte)" aria-label="Écouter">▶</button></div></li>`;
  const proposals = rv.removed.length > 0;
  const r = await modal({
    title: `Relire le texte · ${job.title}`, wide: true,
    body: `<p class="hint">${!proposals ? "Aucune coupe proposée." : rv.method === "heuristique"
      ? "Sans IA : seules les redites évidentes et les formules de remplissage sont proposées ; l'objectif peut ne pas être atteint, par prudence."
      : `Coupes proposées par l'IA${rv.method === "IA + heuristique" ? " (complétées par les redites évidentes)" : ""}.`}
      <b>Décochez</b> une phrase pour la retirer du podcast, cochez-la pour la garder. Vous pouvez aussi <b>corriger le texte</b> d'une phrase : l'audio ne change pas (c'est la voix du prédicateur), mais le texte enregistré et la version anglaise partiront du texte corrigé. Le début, la fin, les lectures bibliques et les « Amen » sont protégés par défaut. <b>Enregistrez</b> pour continuer plus tard sans rien perdre.</p>
      ${rv.key_points?.length ? `<details class="rv-points"><summary>Idées principales repérées (vérifiez qu'elles restent toutes)</summary><ul>${rv.key_points.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></details>` : ""}
      <div class="rv-bar"><label class="check"><input type="checkbox" id="rvOnly" ${proposals ? "checked" : ""}> Seulement les phrases retirées ou corrigées</label>
        <span><span id="rvDirty" class="rv-dirty" hidden>● modifications non enregistrées</span> <button type="button" class="btn small ghost" id="rvSave">💾 Enregistrer</button></span></div>
      <div class="rv-bar"><b id="rvSum"></b></div>
      <ul class="rv-list ${proposals ? "only" : ""}" id="rvList">${rv.sentences.map(row).join("")}</ul>`,
    buttons: [{ label: "Fermer", kind: "ghost", value: null }, { label: "Tout garder (aucune coupe)", kind: "ghost", value: "keep" },
      { label: "Valider le texte", primary: true }],
    onMount: (dlg) => {
      const list = dlg.querySelector("#rvList"), dirty = (on) => (dlg.querySelector("#rvDirty").hidden = !on), sum = () => {
        const s = saved();
        dlg.querySelector("#rvSum").textContent = `${rv.sentences.length - chosen.size} phrase(s) gardée(s) sur ${rv.sentences.length} · ${chosen.size} retirée(s)${chosen.size ? ` : −${mmss(s)} (−${(100 * s / Math.max(rv.total_s, 1)).toFixed(0)} %${rv.pct ? `, objectif −${rv.pct} %` : ""})` : ""} · ${edits.size} corrigée(s)${rv.coverage != null ? ` · idées conservées : ${Math.round(100 * rv.coverage)} % (avant vos changements)` : ""}`;
      };
      sum();
      dlg.querySelector("#rvOnly").onchange = (e) => list.classList.toggle("only", e.target.checked);
      list.addEventListener("change", (e) => {
        if (!e.target.matches("[data-rv]")) return;
        const id = +e.target.dataset.rv;
        e.target.checked ? chosen.delete(id) : chosen.add(id);
        e.target.closest(".rv-row").classList.toggle("off", !e.target.checked);
        dirty(true); sum();
      });
      list.addEventListener("input", (e) => {
        if (!e.target.matches("[data-rv-text]")) return;
        const id = +e.target.dataset.rvText, v = e.target.value.trim();
        v && v !== byId.get(id).text ? edits.set(id, v) : edits.delete(id);
        e.target.closest(".rv-row").classList.toggle("edited", edits.has(id));
        dirty(true); sum();
      });
      list.addEventListener("click", (e) => {
        const b = e.target.closest("[data-rv-play]");
        if (!b) return;
        const s = byId.get(+b.dataset.rvPlay);
        rvAudio?.pause();
        rvAudio = new Audio(`/api/jobs/${job.id}/review/clip?start=${Math.max(s.start - 1.5, 0)}&end=${s.end + 1.5}`);
        rvAudio.play().catch(() => toast("Audio indisponible", true));
      });
      dlg.querySelector("#rvSave").onclick = (ev) => busy(ev.currentTarget, async () => {
        try {
          await api(`/api/jobs/${job.id}/review`, { method: "POST", body: payload([...chosen], false) });
          dirty(false); toast("Brouillon enregistré", "ok");
        } catch (err) { toast(err.message, true); }
      });
    },
    submit: (dlg) => api(`/api/jobs/${job.id}/review`, { method: "POST", body: payload([...chosen], true) }),
  });
  rvAudio?.pause();
  if (r === "keep") await api(`/api/jobs/${job.id}/review`, { method: "POST", body: payload([], true) });
  if (r) { toast("Texte validé : le traitement reprend", "ok"); refreshView(); loadStatus(); }
}
const fmtClockShort = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// ---------- Rognage du podcast terminé ----------
const clock = (s) => { s = Math.max(0, s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return `${h}:${String(m).padStart(2, "0")}:${x.toFixed(1).padStart(4, "0")}`; };
const parseClock = (v) => { const p = String(v).trim().split(":"); if (!v.trim() || p.length > 3 || p.some((x) => !/^\d+(\.\d+)?$/.test(x))) return NaN;
  return p.reduce((a, x) => a * 60 + parseFloat(x), 0); };

async function trimDialog(job) {
  const dur = job.duration_output_s || 0;
  miniClose();  // l'éditeur a son propre lecteur : pas de mini-lecteur pendant le rognage
  document.body.classList.add("trimming");
  const res = await modal({
    title: "Rogner le podcast", wide: true,
    body: `<p>Retirez le début et/ou la fin du podcast terminé (par exemple un silence, un chant ou une annonce en trop). Écoutez, placez le curseur au bon endroit, puis cliquez « Marquer ici ».</p>
      <div class="trim-player"><audio controls preload="metadata" data-editor src="/api/jobs/${job.id}/file/mp3?v=${Date.now()}"></audio></div>
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
  document.body.classList.remove("trimming");
  if (res === "trimmed") toast("Podcast rogné", "ok");
  else if (res === "restore") {
    if (!(await confirmBox({ title: "Restaurer l'original ?", message: "Le podcast reviendra à sa version d'avant le rognage." + (job.on_r2 ? " Le lien R2 changera." : ""), confirmLabel: "Restaurer" }))) return;
    await api(`/api/jobs/${job.id}/trim/reset`, { method: "POST" });
    toast("Original restauré", "ok");
  } else return;
  refreshView();
}

// ---------- Statut, parallélisme ----------
function aiPill(s) {  // cliquable : l'administrateur règle l'IA du serveur, les autres leur IA personnelle (selon leurs droits)
  const open = state.me.is_admin || can("ai.key") || can("ai.toggle");
  if (!s.ai_available) return open
    ? `<button type="button" class="pill link" data-ai title="${state.me.is_admin ? "Configurer l'IA du serveur" : "Ajouter ma clé Anthropic pour utiliser l'IA"}">${state.me.is_admin ? "IA non configurée" : "Détection heuristique · ajouter ma clé"}</button>`
    : '<span class="pill" title="Aucune IA n\'est configurée par l\'administrateur">Détection heuristique</span>';
  const label = s.ai_enabled ? `IA activée${s.ai_personal ? " (ma clé)" : ""}` : "IA désactivée";
  return open ? `<button type="button" class="pill link ${s.ai_enabled ? "on" : "off"}" data-ai title="Régler l'IA">${label}</button>`
    : `<span class="pill ${s.ai_enabled ? "on" : ""}">${label}</span>`;
}
// Compteur de tokens : mis à jour après chaque appel à l'IA (le statut est relu toutes les quelques secondes)
const usagePill = (s) => (s.ai_available || s.ai_usage?.total)
  ? `<button type="button" class="pill link" data-usage title="Consommation de l'IA ce mois-ci (clic : détail)">${ic("sparkle")} ${fmtTok(s.ai_usage?.month || 0)} tokens</button>` : "";
async function usageDialog() {
  const u = await api("/api/ai/usage"), t = (x) => fmtTok(x.in + x.out);
  const line = (label, x) => `<dt>${label}</dt><dd><b>${t(x)}</b> tokens <small>(${fmtTok(x.in)} envoyés · ${fmtTok(x.out)} reçus${x.calls != null ? ` · ${plural(x.calls, "appel", "appels")}` : ""})</small></dd>`;
  const keys = u.keys ? `<div class="d-title">Par clé (administrateur)</div>
    ${u.keys.length ? `<table class="usage-table"><thead><tr><th>Clé</th><th>Ce mois</th><th>Total</th><th>Appels</th></tr></thead><tbody>
      ${u.keys.map((k) => `<tr><td>${esc(k.name)}</td><td>${fmtTok(k.month)}</td><td>${fmtTok(k.total_in + k.total_out)}</td><td>${k.calls}</td></tr>`).join("")}</tbody></table>` : '<p class="hint">Aucune consommation enregistrée.</p>'}` : "";
  await modal({
    title: "Consommation de l'IA", icon: "✨", wide: !!u.keys,
    body: `<dl class="kv">${line("Ce mois-ci", u.month)}${line("Depuis le début", u.total)}</dl>
      ${u.others_on_my_key_month.in + u.others_on_my_key_month.out ? `<p class="hint">Dont ${fmtTok(u.others_on_my_key_month.in + u.others_on_my_key_month.out)} tokens ce mois-ci facturés sur votre clé pour des traitements qu'un administrateur a lancés avec votre configuration.</p>` : ""}
      ${keys}
      <p class="hint">Les tokens sont ceux que l'IA a lus et écrits ; ce compteur ne chiffre pas le coût. Il s'actualise après chaque appel à l'IA, pendant les traitements.</p>`,
    buttons: [{ label: "Fermer", kind: "ghost", value: null }],
  });
}
async function aiDialog() {  // administrateur : IA du serveur, pour tous ceux qui n'ont pas leur propre clé
  const c = await api("/api/settings/llm");
  const r = await modal({
    title: "IA du serveur", icon: "✨",
    body: `<p>L'IA repère le début et la fin de la prédication et retire l'adoration, les témoignages et les annonces. Cette clé Anthropic sert aux utilisateurs qui n'ont pas enregistré la leur.</p>
      <label>Clé API Anthropic ${c.configured ? `<span class="hint">(enregistrée : ${esc(c.key_hint)})</span>` : ""}
        <input name="key" type="password" autocomplete="off" placeholder="${c.configured ? "Laisser vide pour la conserver" : "sk-ant-…"}"></label>
      <label>Modèle<select name="model">${Object.entries(c.models).map(([id, l]) => `<option value="${esc(id)}" ${id === c.model ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
      <label class="check"><input type="checkbox" name="on" ${c.enabled ? "checked" : ""} ${c.configured ? "" : "disabled"}> IA du serveur activée</label>
      <p class="hint">La clé est vérifiée par un petit appel à l'enregistrement, puis stockée chiffrée. Décochez « activée » pour ne rien dépenser sans effacer la clé : repérage par heuristique, adoration, témoignages et annonces non retirés. S'applique aux traitements qui démarrent ensuite ; ceux en cours vont au bout avec l'IA choisie au départ.</p>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Mon IA personnelle…", kind: "ghost", value: "mine" },
      ...(c.configured ? [{ label: "Supprimer la clé", kind: "danger", value: "delete" }] : []), { label: "Enregistrer", primary: true }],
    submit: async (dlg) => {
      const key = dlg.querySelector("[name=key]").value.trim(), model = dlg.querySelector("[name=model]").value;
      let enabled = c.enabled;
      if (key || model !== c.model || !c.configured) {
        if (!key && !c.configured) throw new Error("Saisissez la clé API Anthropic");
        enabled = (await api("/api/settings/llm", { method: "PUT", body: { key, model } })).enabled;
      }
      const want = c.configured ? dlg.querySelector("[name=on]").checked : true;
      if (want !== enabled) await api("/api/settings/ai", { method: "PUT", body: { enabled: want } });
    },
  });
  if (r === "mine") return myAiDialog();
  if (r === "delete") {
    if (!(await confirmBox({ title: "Supprimer la clé du serveur ?", confirmLabel: "Supprimer la clé", danger: true,
      message: "Sans clé, les utilisateurs qui n'ont pas la leur retombent sur le repérage par heuristique, sans retrait des témoignages et annonces." }))) return;
    await api("/api/settings/llm", { method: "DELETE" });
  }
  if (r) { toast(r === "delete" ? "Clé du serveur supprimée" : "IA du serveur enregistrée", "ok"); await loadStatus(); refreshView(); }
}
async function myAiDialog() {  // clé Anthropic personnelle et interrupteur pour ses propres traitements
  const m = await api("/api/me/ai");
  const r = await modal({
    title: "Mon IA", icon: "✨",
    body: `<p>L'IA repère la prédication et retire l'adoration, les témoignages et les annonces de <b>vos</b> traitements.</p>
      ${m.can_toggle ? `<label class="check"><input type="checkbox" name="ai_on" ${m.enabled ? "checked" : ""}> Utiliser l'IA pour mes traitements</label>` : ""}
      ${m.can_key ? `<label>Ma clé Anthropic ${m.has_key ? `<span class="hint">(enregistrée : ${esc(m.key_hint)})</span>` : ""}
          <input name="key" type="password" autocomplete="off" placeholder="${m.has_key ? "Laisser vide pour la conserver" : "sk-ant-…"}"></label>
        <p class="hint">${m.has_key ? "Vos traitements utilisent votre clé : les appels sont facturés sur votre compte Anthropic." : m.server_ai ? "Sans clé personnelle, la clé du serveur est utilisée (si l'administrateur l'a activée)." : "Aucune IA n'est configurée sur le serveur : ajoutez votre clé pour en profiter."}
          Elle est vérifiée à l'enregistrement, stockée chiffrée sur le serveur. Elle sert à vos traitements, et à ceux qu'un administrateur choisit explicitement de lancer avec votre configuration. Créez-en une sur console.anthropic.com.</p>` : ""}`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, ...(m.has_key ? [{ label: "Supprimer ma clé", kind: "danger", value: "delete" }] : []),
      { label: "Enregistrer", primary: true }],
    submit: async (dlg) => {
      const on = dlg.querySelector("[name=ai_on]"), key = dlg.querySelector("[name=key]")?.value.trim();
      if (key) await api("/api/me/ai/key", { method: "PUT", body: { key } });
      if (on && on.checked !== m.enabled) await api("/api/me/ai", { method: "PUT", body: { enabled: on.checked } });
    },
  });
  if (r === "delete") await api("/api/me/ai/key", { method: "DELETE" });
  if (r) { toast(r === "delete" ? "Clé supprimée" : "Réglages de l'IA enregistrés", "ok"); await loadStatus(); refreshView(); }
}

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
$("statusBar").addEventListener("click", (e) => {
  if (e.target.closest("[data-r2]")) r2Dialog();
  else if (e.target.closest("[data-usage]")) usageDialog();
  else if (e.target.closest("[data-ai]")) (state.me.is_admin ? aiDialog : myAiDialog)();
});

async function loadStatus() {
  const s = await api("/api/status").catch(() => null);
  if (!s) return null;
  $("statusBar").innerHTML = `
    ${r2Pill(s)}
    ${aiPill(s)}
    ${usagePill(s)}
    <span class="pill link ${s.running ? "busy" : ""}" data-status="active">▶ ${s.running}/${s.max_parallel} en cours</span>
    <span class="pill link ${s.pending ? "waiting" : ""}" data-status="active">⏳ ${s.pending} en file</span>
    ${s.review ? `<span class="pill link busy" data-status="active" title="Des coupes proposées attendent votre validation">✋ ${s.review} à valider</span>` : ""}`;
  const mb = s.max_upload_mb;
  $("stagingDays").textContent = s.staging_days;
  $("maxUpload").textContent = $("batchMaxUpload").textContent = mb >= 1024 ? `${(mb / 1024).toFixed(1).replace(".0", "")} Go` : `${mb} Mo`;
  const wasSyncing = state.status?.r2_sync?.running;
  state.status = s;
  if (wasSyncing && !s.r2_sync?.running) {
    const f = s.r2_sync?.last?.failed?.length;
    toast(f ? `Synchronisation R2 terminée avec ${f} erreur(s)` : "R2 est à jour", f ? true : "ok");
    refreshView();
  }
  if (state.view === "home") renderHomeStats();
  renderTrSelects();
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

async function loadHome(silent = false, force = false) {
  if (!silent && !state.home.items) { loadingLine($("homeActive")); loadingLine($("homeDone")); }
  const q = $("homeSearch").value;
  try {
    const [act, en] = await Promise.all([api("/api/jobs?status=active&limit=100"), api("/api/english")]);
    state.enAlive = en.alive;
    const sig = act.items.map((j) => j.id + j.status).join(",") + "|" + en.active.map((e) => e.id + e.status).join(",");
    if (state.view !== "home") return;
    $("homeActiveBox").hidden = !(act.total + en.active.length);
    $("homeActiveCount").textContent = act.total + en.active.length || "";
    $("homeActive").innerHTML = act.items.map(activeCard).join("") + en.active.map(enCard).join("");
    if (silent && !force && sig === state.home.sig && q === state.home.q) { state.home.items = [...act.items, ...(state.home.done || [])]; return; }
    const done = await api(`/api/jobs?status=done&limit=12&q=${encodeURIComponent(q)}`);
    state.home = { sig, q, done: done.items, doneTotal: q ? state.home.doneTotal : done.total, items: [...act.items, ...done.items] };
    renderHomeStats();
    $("homeDoneCount").textContent = done.total || "";
    const empty = !state.folders.length && !act.total && !en.active.length && !done.total && !q;
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
  if (j.status === "paused") return `En pause à ${Math.round(j.progress * 100)} %`;
  if (j.status === "review") return "À valider";
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
  const ok = await confirmBox({ title: "Supprimer le dossier ?", confirmLabel: "Mettre à la corbeille",
    message: `Le dossier « <b>${esc(f.name)}</b> » sera déplacé dans la <b>corbeille</b> (vous pourrez le restaurer). Il doit être vide (ni sous-dossier ni traitement).` });
  if (!ok) return;
  try {
    await api(`/api/folders/${f.id}`, { method: "DELETE" });
    state.sel = null;
    await loadFolders();
    toast("Dossier mis à la corbeille", "ok");
  } catch (err) { alertBox({ title: "Suppression impossible", message: esc(err.message), kind: "danger" }); }
}

async function folderIntroDialog(f) {
  const r = await modal({
    title: `Intro du dossier « ${f.name} »`,
    body: `<label>Intro des podcasts de ce dossier (français)<select name="intro">${introOptions([["", "Hériter (parent, sinon intro par défaut)"]], false, f.intro_id ?? "")}</select></label>
      <div data-note="fr" class="hint"></div><div data-preview="fr"></div>
      <label>Intro de la version anglaise<select name="intro_en">${introOptions([["", "Hériter (parent, sinon intro anglaise par défaut)"]], false, f.intro_en_id ?? "", "en")}</select></label>
      <div data-note="en" class="hint"></div><div data-preview="en"></div>
      <a class="page-link" data-go="intros" href="#intros">Gérer la bibliothèque d'intros →</a>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Enregistrer", primary: true }],
    onMount: (dlg) => {
      for (const [lang, name] of [["fr", "intro"], ["en", "intro_en"]]) {
        const sel = dlg.querySelector(`[name=${name}]`);
        const refresh = () => {
          const chosen = sel.value ? { id: +sel.value, name: introName(+sel.value) } : effectiveIntro(byId(f.parent_id), lang);
          dlg.querySelector(`[data-note=${lang}]`).textContent = sel.value ? "" : chosen ? `Hérité : ${chosen.name}` : "Aucune intro à hériter : ajoutez un MP3 dans la bibliothèque d'intros.";
          dlg.querySelector(`[data-preview=${lang}]`).innerHTML = chosen ? `<audio controls preload="none" src="/api/intros/${chosen.id}/audio" style="width:100%"></audio>` : "";
        };
        sel.onchange = refresh; refresh();
      }
      dlg.querySelector("[data-go]").onclick = (ev) => { ev.preventDefault(); dlg.querySelector("[data-close]").click(); go("intros"); };
    },
    submit: async (dlg) => {
      const v = dlg.querySelector("[name=intro]").value, en = dlg.querySelector("[name=intro_en]").value;
      await api(`/api/folders/${f.id}/intro`, { method: "PUT", body: { intro_id: v ? +v : null, intro_en_id: en ? +en : null } });
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
  loadAiUsers();  // les clés enregistrées ont pu changer depuis le chargement de la page
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
const defaultIntro = (lang = "fr") => state.intros.find((i) => i.is_default && i.lang === lang);

function effectiveIntro(folder, lang = "fr") {  // intro du dossier dans cette langue, sinon du parent le plus proche, sinon par défaut
  const key = lang === "en" ? "intro_en_id" : "intro_id";
  for (let f = folder; f; f = f.parent_id ? byId(f.parent_id) : null) {
    if (f[key] && introName(f[key])) return { name: introName(f[key]), id: f[key], from: f };
  }
  const d = defaultIntro(lang);
  return d ? { name: d.name, id: d.id, from: null } : null;
}

// Administrateur : l'IA d'un traitement peut être celle d'un autre utilisateur (sa clé Anthropic) ou celle du serveur
const aiOptions = (extra = [], selected = "") => [...extra, ["", "Automatique (configuration de l'auteur du traitement)"], ["@server", "IA du serveur"],
  ...state.aiUsers.map((u) => [u.username, `Clé de ${u.display_name || u.username}`])]
  .map(([v, l]) => `<option value="${esc(v)}" ${v === selected ? "selected" : ""}>${esc(l)}</option>`).join("");
// Traducteur de la version anglaise : le modèle local (par défaut) ou notre IA configurée, si elle est disponible pour cet utilisateur
const trOptions = (keep = false) => {
  const ai = !!state.status?.ai_enabled;
  return `${keep ? '<option value="keep" selected>Ne pas changer</option>' : ""}<option value="">Par défaut (réglage de l'administrateur)</option>
    <option value="local">Modèle libre local (gratuit, sans IA externe)</option>
    <option value="claude" ${ai ? "" : "disabled"}>Notre IA configurée${ai ? "" : " (indisponible)"}</option>`;
};
function renderTrSelects() {
  for (const id of ["jobTr", "batchTr"]) { const keep = $(id).value; $(id).innerHTML = trOptions(); $(id).value = keep; }
}
const aiLabel = (j) => j.ai_user === "@server" ? "IA du serveur (choisie par un administrateur)"
  : j.ai_user ? `Clé de « ${j.ai_user} » (choisie par un administrateur)` : "Configuration de l'auteur du traitement";

async function loadAiUsers() {
  if (!state.me.is_admin) return;
  state.aiUsers = (await api("/api/users").catch(() => [])).filter((u) => u.ai_key && u.is_active);
  for (const id of ["jobAiSelect", "batchAiSelect"]) $(id).innerHTML = aiOptions([], $(id).value);
  $("jobAiBox").hidden = $("batchAiBox").hidden = false;
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
  renderBatch();  // les sélecteurs d'intro des lignes du lot suivent la bibliothèque
  if (state.view === "intros") renderIntroList();
  if (state.view === "folders") renderExplorer();
}

function renderIntroList() {
  const manage = can("intros.manage");
  $("introList").innerHTML = state.intros.length ? state.intros.map((i) => `
    <div class="job intro-item">
      <div class="top">
        <div><b>${esc(i.name)}</b> <span class="muted">${esc(i.duration)}</span>
          <span class="badge">${i.lang === "en" ? "🇬🇧 Anglais" : "🇫🇷 Français"}</span>
          ${i.is_default ? `<span class="badge default">Par défaut (${i.lang === "en" ? "anglais" : "français"})</span>` : ""}</div>
        ${manage ? `<div class="actions">
          ${i.is_default ? "" : `<button class="btn small ghost" data-intro="default" data-id="${i.id}">★ Par défaut</button>`}
          <button class="btn small ghost" data-intro="rename" data-id="${i.id}">Renommer</button>
          ${state.me.is_admin ? `<button class="btn small ghost danger" data-intro="delete" data-id="${i.id}">Supprimer</button>` : ""}
        </div>` : ""}
      </div>
      <audio controls preload="none" src="/api/intros/${i.id}/audio"></audio>
    </div>`).join("") : '<p class="muted">Aucune intro. Ajoutez un fichier MP3 ci-dessous : la première de chaque langue devient l\'intro par défaut de cette langue.</p>';
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
          message: `« <b>${esc(intro.name)}</b> » sera supprimée <b>définitivement</b> (les intros n'ont pas de corbeille). Les dossiers et traitements qui l'utilisaient repasseront en automatique.` });
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
  fd.append("lang", f.lang.value);
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

function uploadJob(fd, onProgress, url = "/api/jobs/upload") {  // XHR : fetch ne donne pas la progression d'un envoi
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", url);
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
  for (const k of ["title", "date", "start", "end", "intro_id", "ai_user", "condense_pct", "condense_mode", "english", "english_translator"]) fd.append(k, form[k].value);
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
        body.condense_pct = +body.condense_pct;
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
// le choix « me montrer les coupes avant » n'a de sens que si on raccourcit
form.english.onchange = () => ($("jobTrBox").hidden = !form.english.value);  // le traducteur n'a de sens que si la version anglaise est demandée
$("batchEnglish").onchange = () => ($("batchTrBox").hidden = !$("batchEnglish").value);

// ---------- Traitement par lot : liens et fichiers à préparer ----------
// Une ligne = un traitement, avec son propre nom, sa date, ses bornes et son intro.
// kind « url » : lien YouTube ; kind « file » : fichier audio / vidéo, envoyé sur le serveur dès son ajout (zone d'attente) :
// la ligne ne garde que son identifiant (uploadId), elle survit donc à un rechargement de la page.
const ROW_INTRO_FIRST = [["", "Intro : comme le reste de la liste"], ["auto", "Intro : automatique (dossier, sinon par défaut)"]];
let batch = [], batchRunning = false, batchUploads = Promise.resolve();
const batchKey = () => "batch:" + state.me.username;  // un lot par compte, même sur un navigateur partagé
function loadBatch() {
  try { return JSON.parse(localStorage.getItem(batchKey()) ?? localStorage.getItem("batch") ?? "[]").map((r) => ({ kind: "url", intro: null, ...r })); }
  catch { return []; }
}
const saveBatch = () => { try { localStorage.setItem(batchKey(), JSON.stringify(batch.filter((r) => r.kind === "url" || r.uploadId).map(({ progress, ...r }) => r))); } catch {} };
const dropStaged = (rows) => rows.filter((r) => r.kind === "file" && r.uploadId).forEach((r) => api(`/api/uploads/${r.uploadId}`, { method: "DELETE" }).catch(() => {}));

// Au démarrage : les fichiers expirés sont retirés ; ceux qui attendent sur le serveur sans ligne (autre appareil, stockage vidé) reviennent dans la liste
async function syncBatchUploads() {
  batch = loadBatch();
  const mine = await api("/api/uploads").catch(() => null);
  if (mine) {
    const ids = new Set(mine.map((u) => u.id));
    const lost = batch.filter((r) => r.kind === "file" && !ids.has(r.uploadId));
    if (lost.length) { batch = batch.filter((r) => !lost.includes(r)); toast(`${lost.length} fichier(s) du lot ont expiré sur le serveur : renvoyez-les`, true); }
    const known = new Set(batch.filter((r) => r.kind === "file").map((r) => r.uploadId));
    for (const u of mine.filter((u) => !known.has(u.id))) {
      batch.push({ id: newId(), kind: "file", uploadId: u.id, name: u.name, size: u.size, title: u.name.replace(/\.[^.]+$/, "").replace(/_+/g, " "),
        date: form.date.value, start: "", end: "", intro: null, error: "" });
    }
    saveBatch();
  }
  renderBatch();
}
const newId = () => Math.random().toString(36).slice(2, 9);
const fmtBounds = (r) => r.start || r.end ? `${r.start || "début"} → ${r.end || "fin"}` : "";
// intro réellement utilisée par une ligne : "" = automatique, "0" = aucune, sinon id (la ligne l'emporte sur le choix de la liste)
const introFor = (r) => (r.intro ? (r.intro === "auto" ? "" : r.intro) : $("batchIntroSelect").value);

function renderBatch() {
  $("batchCount").textContent = batch.length || "";
  $("batchList").innerHTML = batch.length ? batch.map((r, i) => `
    <div class="batch-row ${r.error ? "err" : ""}" data-id="${r.id}">
      <span class="n">${i + 1}</span>
      <div style="min-width:0"><div class="t">${esc(r.title)} <span class="muted">· ${esc(r.date)}</span>
        ${fmtBounds(r) ? `<span class="chip accent">${esc(fmtBounds(r))}</span>` : ""}</div>
        <div class="u">${r.kind === "file" ? `${ic("upload")} ${esc(r.name)} · ${fmtSize(r.size)}${r.uploadId ? " · sur le serveur" : ""}` : esc(r.url)}</div></div>
      <div class="actions">
        <button class="icon-btn" type="button" data-batch="edit" title="Modifier">${ic("edit")}</button>
        <button class="icon-btn danger" type="button" data-batch="delete" title="Retirer de la liste">${ic("trash")}</button>
      </div>
      <div class="r-intro"><span data-ic="music">${ic("music")}</span>
        <select data-batch-intro aria-label="Intro de cette ligne">${introOptions(ROW_INTRO_FIRST, true, r.intro ?? "")}</select></div>
      ${r.progress != null ? `<div class="batch-prog"><i style="width:${r.progress}%"></i></div>` : ""}
      ${r.error ? `<div class="e">${esc(r.error)}</div>` : ""}
    </div>`).join("") : '<div class="batch-empty">La liste est vide. Ajoutez un lien ou des fichiers ci-dessus.</div>';
  $("batchRunLabel").textContent = batch.length ? `Lancer ${batch.length} traitement${batch.length > 1 ? "s" : ""}` : "Lancer";
  $("batchRunBtn").disabled = !batch.length || batch.some((r) => r.progress != null);  // pas de lancement pendant un envoi
  $("batchClearBtn").disabled = !batch.length;
}

function checkRow(r) {
  if (r.kind === "url" && !/^https?:\/\//i.test(r.url)) return "Le lien doit commencer par http:// ou https://";
  if (r.kind === "file" && !r.uploadId) return "Ce fichier n'a pas été envoyé : retirez la ligne et ajoutez-le à nouveau";
  if (!r.title.trim()) return "Le nom est obligatoire";
  for (const [k, label] of [["start", "Début"], ["end", "Fin"]]) if (r[k] && isNaN(parseClock(r[k]))) return `${label} : format h:mm:ss attendu (ex. 1:05:30)`;
  if (r.start && r.end && parseClock(r.end) <= parseClock(r.start)) return "La fin doit être après le début";
  return "";
}

// Source de l'ajout : liens ou fichiers
function setBatchSource(next) {
  document.querySelectorAll("#batchSource [data-bsrc]").forEach((b) => b.classList.toggle("active", b.dataset.bsrc === next));
  document.querySelectorAll("[data-bsrc-panel]").forEach((el) => (el.hidden = el.dataset.bsrcPanel !== next));
}
$("batchSource").addEventListener("click", (e) => { const b = e.target.closest("[data-bsrc]"); if (b) setBatchSource(b.dataset.bsrc); });

function addBatchRow() {
  const r = { id: newId(), kind: "url", url: $("batchUrl").value.trim(), title: $("batchTitle").value.trim(), intro: null, error: "",
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

// Fichiers : un traitement par fichier, envoyé tout de suite sur le serveur (un à la fois), nom repris du fichier
function addBatchFiles(files) {
  const max = (state.status?.max_upload_mb || 4096) * 1024 * 1024, tooBig = [];
  for (const f of files) {
    if (f.size > max) { tooBig.push(f.name); continue; }
    const r = { id: newId(), kind: "file", uploadId: null, name: f.name, size: f.size, title: f.name.replace(/\.[^.]+$/, "").replace(/_+/g, " "), intro: null, error: "",
      date: $("batchDate").value || form.date.value, start: "", end: "", progress: 0 };
    batch.push(r);
    batchUploads = batchUploads.then(() => stageBatchFile(r, f));
  }
  renderBatch();
  if (tooBig.length) toast(`Trop volumineux (maximum ${fmtSize(max)}) : ${tooBig.join(", ")}`, true);
}
async function stageBatchFile(r, file) {
  if (!batch.includes(r)) return;  // retirée avant son tour
  const fd = new FormData();
  fd.append("file", file);
  try {
    const u = await uploadJob(fd, (done, total) => {
      r.progress = Math.round((100 * done) / total);
      const bar = document.querySelector(`.batch-row[data-id="${r.id}"] .batch-prog i`);
      if (bar) bar.style.width = r.progress + "%";
    }, "/api/uploads");
    r.uploadId = u.id;
    if (!batch.includes(r)) dropStaged([r]);  // retirée pendant l'envoi : on ne garde rien sur le serveur
  } catch (err) { r.error = err.message; }
  r.progress = null;
  saveBatch();
  renderBatch();
}
$("batchFiles").onchange = () => { addBatchFiles([...$("batchFiles").files]); $("batchFiles").value = ""; };
["dragenter", "dragover"].forEach((t) => $("batchDrop").addEventListener(t, () => $("batchDrop").classList.add("over")));
["dragleave", "drop"].forEach((t) => $("batchDrop").addEventListener(t, () => $("batchDrop").classList.remove("over")));

async function editBatchRow(r) {
  const saved = await modal({
    title: "Modifier ce traitement", wide: true,
    body: `${r.kind === "file" ? `<label>Fichier<input value="${esc(r.name)}" disabled></label>` : `<label>Lien YouTube<input name="url" value="${esc(r.url)}"></label>`}
      <div class="row"><label>Nom<input name="title" value="${esc(r.title)}"></label>
      <label>Date<input name="date" type="date" value="${esc(r.date)}"></label></div>
      <div class="row"><label>Début de la prédication (facultatif)<input name="start" placeholder="1:05:30" value="${esc(r.start)}"></label>
      <label>Fin (facultatif)<input name="end" placeholder="2:10:00" value="${esc(r.end)}"></label></div>
      <label>Intro<select name="intro">${introOptions(ROW_INTRO_FIRST, true, r.intro ?? "")}</select></label>
      <p class="hint">Début et fin vides = détection automatique.</p>`,
    buttons: [{ label: "Annuler", kind: "ghost", value: null }, { label: "Enregistrer", primary: true }],
    submit: async (dlg) => {
      const v = (n) => dlg.querySelector(`[name=${n}]`)?.value.trim() ?? "";
      const next = { ...r, url: r.kind === "url" ? v("url") : "", title: v("title"), date: v("date") || r.date, start: v("start"), end: v("end"), intro: v("intro") || null, error: "" };
      const err = checkRow(next);
      if (err) throw new Error(err);
      Object.assign(r, next);
    },
  });
  if (saved) { saveBatch(); renderBatch(); }
}

$("batchList").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-batch]");
  if (!b || batchRunning) return;
  const r = batch.find((x) => x.id === b.closest(".batch-row").dataset.id);
  if (b.dataset.batch === "edit") await editBatchRow(r);
  else { batch = batch.filter((x) => x !== r); dropStaged([r]); saveBatch(); renderBatch(); }
});
$("batchList").addEventListener("change", (e) => {
  const sel = e.target.closest("[data-batch-intro]");
  if (!sel) return;
  batch.find((x) => x.id === sel.closest(".batch-row").dataset.id).intro = sel.value || null;
  saveBatch();
});

$("batchClearBtn").onclick = async () => {
  if (batchRunning) return;
  if (await confirmBox({ title: "Vider la liste ?", message: `Les ${batch.length} ligne(s) préparées seront retirées de la liste (rien n'est supprimé ailleurs).`, confirmLabel: "Vider", danger: true })) {
    dropStaged(batch); batch = []; saveBatch(); renderBatch();
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
        return { id: newId(), kind: "url", url: url || "", title: title || "", date: date || form.date.value, start: start || "", end: end || "", intro: null, error: "" };
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
  if (!batch.length || batchRunning) return;
  batchRunning = true;
  const folder = state.current;
  let ok = 0;
  try {
    for (const r of [...batch]) {
      try {
        const intro = introFor(r);
        const err = checkRow(r);
        if (err) throw new Error(err);
        await api("/api/jobs", { method: "POST", body: { folder_id: folder, ...(r.kind === "file" ? { upload_id: r.uploadId } : { youtube_url: r.url }),
          title: r.title, date: r.date, start: r.start || null, end: r.end || null, intro_id: intro === "" ? null : +intro, ai_user: $("batchAiSelect").value,
          condense_pct: +$("batchCondense").value, condense_mode: $("batchMode").value, english: $("batchEnglish").value, english_translator: $("batchTr").value } });
        batch = batch.filter((x) => x !== r);
        ok++;
      } catch (err) { r.error = err.message; }
      renderBatch();
    }
  } finally { batchRunning = false; }
  saveBatch();
  if (ok) toast(`${ok} traitement(s) ajouté(s) à la file`, "ok");
  const failed = batch.filter((r) => r.error);
  if (failed.length) alertBox({ title: `${failed.length} ligne(s) non lancée(s)`, kind: "danger",
    message: "Elles restent dans la liste avec leur erreur : modifiez-les puis relancez." });
  loadJobs(); loadFolders(); loadStatus();
});
$("batchDate").value = form.date.value;
renderBatch();

// ---------- Détails d'un traitement ----------
// Bloc « Version anglaise » de la fenêtre de détails : état, lecture, téléchargement, actions
function enBlock(j, admin) {
  const e = j.english, can_ = canEnglish(j);
  if (!e) return `<p class="hint">Pas encore de version anglaise.</p><div class="actions"><button class="btn small" data-act="english" data-id="${j.id}">${ic("sparkle")} Générer la version anglaise…</button></div>`;
  const meta = [e.method && `traduit par : ${e.method}`, `moteur : ${e.engine}`, e.duration && `durée ${Math.round(e.duration / 60)} min`, e.size_mp3 && fmtSize(e.size_mp3)].filter(Boolean).join(" · ");
  let body = "";
  if (e.status === "pending") body = `<div class="queued">${ic("clock")} En attente du service de voix${state.enAlive === false ? " — il n'est pas démarré" : ""}</div>`;
  else if (e.status === "paused") body = `<div class="progress paused"><div style="width:${Math.round(e.progress * 100)}%"></div></div><div class="step"><b>⏸ En pause à ${Math.round(e.progress * 100)} %</b> — le texte et les morceaux de voix déjà faits sont gardés</div>`;
  else if (e.status === "running") body = `<div class="progress"><div style="width:${Math.round(e.progress * 100)}%"></div></div><div class="step"><b>${Math.round(e.progress * 100)} %</b> — ${esc(e.step)}</div>`;
  else if (e.status === "review") body = `<div class="review-note"><span>✋ Le texte anglais attend votre relecture : la voix du prédicateur le dira tel quel.</span>${can_ ? `<button class="btn small" data-act="enreview" data-id="${j.id}">${ic("edit")} Relire le texte</button>` : ""}</div>`;
  else if (e.status === "error") body = `<div class="err-box">${esc(e.error || "Erreur")}</div>`;
  else body = `<div class="player-row"><div data-player="${j.id}" data-lang="en"></div>
      ${e.has_mp3 ? `<a class="btn small" href="/api/jobs/${j.id}/english/file?download=true">${ic("download")} Télécharger MP3 anglais</a>` : ""}</div>`;
  return `${body}${admin ? renderSteps(e, false, "ensteps") : ""}<p class="hint">${esc(meta)}</p>
    <div class="actions">
      ${e.on_r2 ? `<button class="btn small ghost" data-act="enlink" data-id="${j.id}">${ic("link")} Copier le lien R2</button>` : ""}
      ${pauseCtl(e, j.id, "en", can_)}${can_ && ["pending", "running", "review", "paused"].includes(e.status) ? stopBtn(e, j.id, "enstop") : ""}
      ${can_ && e.status !== "running" ? `<button class="btn small ghost" data-act="english" data-id="${j.id}">${ic("retry")} ${e.status === "done" ? "Régénérer…" : "Relancer…"}</button>` : ""}
      ${admin && e.status !== "running" ? `<button class="btn small ghost danger" data-act="endelete" data-id="${j.id}">${ic("trash")} Supprimer</button>` : ""}
    </div>
    ${admin && j.english_log ? `<details class="log" data-keep="enlog"><summary>Journal de la version anglaise</summary><pre class="detail-log">${esc(j.english_log)}</pre></details>` : ""}`;
}

$("detailBody").addEventListener("click", (e) => {
  const t = e.target.closest("[data-dtab]");
  if (!t) return;
  state.detailTab = t.dataset.dtab;
  $("detailBody").querySelectorAll("[data-dtab]").forEach((b) => { const on = b === t; b.classList.toggle("active", on); b.setAttribute("aria-selected", on); });
  $("detailBody").querySelectorAll("[data-dpane]").forEach((p) => (p.hidden = p.dataset.dpane !== state.detailTab));
});

async function openDetail(id, silent = false) {
  const j = await api(`/api/jobs/${id}`).catch((err) => { if (!silent) toast(err.message, true); return null; });
  if (!j || (silent && !$("detailDialog").open)) return;  // rafraîchissement tardif : la fenêtre a été fermée entre-temps
  state.detail = j;
  const dlg = $("detailDialog");
  if (!silent && !dlg.open) state.detailTab = "podcast";  // une nouvelle ouverture repart du premier onglet
  // le rafraîchissement refait toute la fenêtre : on garde ouvert ce que l'utilisateur a ouvert (journaux, étapes) et la position de lecture
  const kept = dlg.open ? Object.fromEntries([...dlg.querySelectorAll("details[data-keep]")].map((d) => [d.dataset.keep, { open: d.open, top: d.querySelector("pre")?.scrollTop || 0 }])) : {};
  const keepAudio = { fr: dlg.querySelector('audio[data-lang="fr"]'), en: dlg.querySelector('audio[data-lang="en"]') };  // un son en cours n'est pas coupé
  $("detailTitle").textContent = j.title;
  const admin = state.me.is_admin;  // les autres comptes ne voient ni les étapes, ni le repérage, ni le journal
  const row = (k, v) => v ? `<dt>${k}</dt><dd>${v}</dd>` : "";
  const link = j.links.mp3 ? `<div class="linkrow"><b>MP3</b>
      <input readonly value="${esc(j.links.mp3)}" onfocus="this.select()">
      <button class="btn small" data-copy="mp3">Copier</button>
      <a class="btn small ghost" href="${esc(j.links.mp3)}" target="_blank" rel="noopener">Ouvrir</a></div>` : "";
  const showEn = !!(j.english || canEnglish(j));
  const tabs = [["podcast", "Podcast"], ...(showEn ? [["english", "Version anglaise" + (j.english ? ` · ${EN_LABEL[j.english.status]}` : "")]] : []), ["info", "Informations"], ...(admin ? [["steps", "Étapes et journal"]] : [])];
  if (!tabs.some(([k]) => k === state.detailTab)) state.detailTab = "podcast";
  const pane = (k, html) => `<div data-dpane="${k}" ${state.detailTab === k ? "" : "hidden"}>${html}</div>`;
  $("detailBody").innerHTML = `
    <div class="job-top"><div class="job-sub">${ic("folder")} ${esc(j.folder_path)}</div>
      ${can("folders.manage") && editable(j) ? `<button class="btn small ghost" data-act="rename" data-id="${j.id}">${ic("edit")} Renommer</button>` : ""}
      <span class="badge ${j.status}">${LABELS[j.status]}</span> ${enBadge(j)}</div>
    ${liveBlock(j)}
    ${j.status === "review" && can("jobs.create") && editable(j) ? `<div class="review-note"><span>✋ Le texte attend votre relecture (corrections, phrases à garder ou à retirer).</span>
      <button class="btn small" data-act="review" data-id="${j.id}">${ic("scissors")} Relire le texte</button></div>` : ""}
    ${j.error ? `<div class="err-box">${esc(j.error)}</div>` : ""}
    <div class="tabs" role="tablist" aria-label="Détails du traitement">${tabs.map(([k, l]) =>
      `<button type="button" role="tab" data-dtab="${k}" class="${state.detailTab === k ? "active" : ""}" aria-selected="${state.detailTab === k}">${esc(l)}</button>`).join("")}</div>
    ${pane("podcast", `${j.has_mp3 ? `<div class="player-row"><div data-player="${j.id}" data-auto></div>
        <a class="btn small" href="/api/jobs/${j.id}/file/mp3?download=true">${ic("download")} Télécharger MP3</a></div>` : '<p class="hint">Pas encore de fichier audio.</p>'}
      ${link ? `<div class="d-title">Lien direct de partage (R2)</div>${link}
        <p class="hint">${j.links_public ? "Lien public permanent."
          : `Lien signé valable ${j.links_days} jours, regénéré à chaque ouverture de cette fenêtre. Pour des liens permanents, configurez R2_PUBLIC_BASE_URL.`}</p>` : ""}`)}
    ${showEn ? pane("english", enBlock(j, admin)) : ""}
    ${pane("info", `<dl class="kv">
      ${row("Fichier", esc(j.display_filename))}
      ${admin ? `${row("Intro", esc(j.intro_name))}
      ${row("IA utilisée", esc(aiLabel(j)))}
      ${row("Source", j.from_upload ? `Fichier envoyé : ${esc(j.video_title || "")}` : "")}
      ${row("Vidéo", j.youtube_url && !j.from_upload ? `<a href="${esc(j.youtube_url)}" target="_blank" rel="noopener">${esc(j.video_title || j.youtube_url)}</a>` : "")}
      ${row("Prédication", j.sermon_start ? `${j.sermon_start} → ${j.sermon_end}` : "")}
      ${row("Repérage", esc(j.detection_note || ""))}
      ${row("Montage", esc(j.edit_note || ""))}
      ${row("Bornes forcées", j.start_override || j.end_override ? `${j.start_override || "début"} → ${j.end_override || "fin"}` : "")}
      ${row("Durée de la vidéo", j.duration_source)}` : ""}
      ${row("Durée du podcast", j.duration_output)}
      ${row("Taille", j.size_mp3 ? fmtSize(j.size_mp3) : "")}
      ${row("Condensation", j.condense_pct ? `−${j.condense_pct} % visés, ${j.condense_mode === "review" ? "coupes validées par l'utilisateur" : "coupes appliquées automatiquement"}` : j.condense_mode === "review" ? "Texte relu par l'utilisateur" : "")}
      ${row("Tokens IA", j.tokens_in || j.tokens_out ? `${fmtTok(j.tokens_in + j.tokens_out)} (${fmtTok(j.tokens_in)} envoyés · ${fmtTok(j.tokens_out)} reçus)` : "")}
      ${row("Créé par", esc(j.created_by || ""))}
      ${row("Créé le", fmtDate(j.created_at))}
      ${row("Terminé le", j.finished_at ? fmtDate(j.finished_at) : "")}
    </dl>`)}
    ${admin ? pane("steps", `${renderSteps(j, true)}
      <details class="log" data-keep="log"><summary>Journal complet</summary>
        <pre class="detail-log">${esc(j.log || "(vide)")}</pre></details>`) : ""}
    <div class="dialog-foot">
      ${j.status === "done" && j.has_mp3 && can("jobs.trim") && editable(j) ? `<button class="btn ghost" data-act="trim" data-id="${j.id}">${ic("scissors")} Rogner</button>` : ""}
      ${(j.status === "done" || j.status === "error") && can("jobs.create") && editable(j) ? `<button class="btn ghost" data-act="retry" data-id="${j.id}">Relancer</button>` : ""}
      ${jobPauseCtl(j).replace("btn small", "btn")}${canStop(j) ? stopBtn(j, j.id).replace("btn small", "btn") : ""}
      ${j.status !== "running" && can("jobs.delete") && editable(j) ? `<button class="btn ghost danger" data-act="delete" data-id="${j.id}">Supprimer</button>` : ""}
    </div>`;
  $("detailBody").querySelectorAll("details[data-keep]").forEach((d) => {
    const k = kept[d.dataset.keep];
    if (!k) return;
    d.open = k.open;
    const pre = d.querySelector("pre");
    if (pre) pre.scrollTop = k.top;
  });
  $("detailBody").querySelectorAll("[data-player]").forEach((slot) => {
    const lang = slot.dataset.lang || "fr", kept = keepAudio[lang];
    slot.replaceWith(kept && kept.dataset.job == j.id ? kept : makePlayer(j.id, false, lang));
  });
  if (!dlg.open) dlg.showModal();
}
$("detailBody").addEventListener("click", (e) => {
  const b = e.target.closest("[data-copy]");
  if (b) copyLink(state.detail.links[b.dataset.copy]);
});
$("detailClose").onclick = () => $("detailDialog").close();
$("detailDialog").addEventListener("close", () => { state.detail = null; miniAdopt(); });

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

// ---------- Permissions (administrateur) ----------
const permsState = { id: null, tab: "actions", data: null, sel: new Set(), open: new Set() };
async function loadPerms() {
  state.users = await api("/api/users");
  if (!state.users.some((u) => u.id === permsState.id)) permsState.id = (state.users.find((u) => !u.is_admin) || state.users[0])?.id ?? null;
  renderPermsUsers();
  await renderPermsPanel();
}
function renderPermsUsers() {
  $("permsUsers").innerHTML = state.users.map((u) => `
    <button type="button" class="pu ${u.id === permsState.id ? "active" : ""}" data-pu="${u.id}">
      <span class="avatar">${esc((u.display_name || u.username).slice(0, 1).toUpperCase())}</span>
      <span><b>${esc(u.display_name || u.username)}</b><small>@${esc(u.username)}${u.is_admin ? " · administrateur" : ""}${u.is_active ? "" : " · désactivé"}</small></span>
    </button>`).join("");
}

// Arbre des dossiers (comme le Finder) : une case par dossier.
//  · cocher un dossier donne aussi accès à tout ce qu'il contient (ses cases passent en « inclus », verrouillées) ;
//  · pour n'en donner qu'une partie, on coche seulement les sous-dossiers voulus : le parent apparaît alors « partiel » (tiret).
const ftree = () => {
  const d = permsState.data, byId = new Map(d.folders.map((f) => [f.id, f])), kids = new Map();
  [...d.folders].sort((a, b) => a.name.localeCompare(b.name, "fr")).forEach((f) => kids.set(f.parent_id ?? null, [...(kids.get(f.parent_id ?? null) || []), f]));
  const own = (f) => f.created_by === state.users.find((u) => u.id === permsState.id).username;
  const ancestors = (f) => { const out = []; for (let p = byId.get(f.parent_id); p; p = byId.get(p.parent_id)) out.push(p); return out; };
  const descendants = (f) => (kids.get(f.id) || []).flatMap((k) => [k, ...descendants(k)]);
  // own : créé par lui ; implied : un dossier au-dessus donne l'accès ; direct : attribué ici ; partial : seuls certains sous-dossiers ; none
  const stateOf = (f) => own(f) ? "own"
    : ancestors(f).find((p) => own(p) || permsState.sel.has(p.id)) ? "implied"
    : permsState.sel.has(f.id) ? "direct"
    : descendants(f).some((x) => own(x) || permsState.sel.has(x.id)) ? "partial" : "none";
  return { kids, byId, own, ancestors, descendants, stateOf };
};
function renderFolderTree() {
  const T = ftree(), tag = { own: "créé par lui", implied: "inclus", direct: "attribué" };
  const row = (f) => {
    const st = T.stateOf(f), sub = T.kids.get(f.id) || [], open = permsState.open.has(f.id);
    const by = f.created_by ? `Créé par ${f.created_by}` : "Créé par l'administration";
    const via = st === "implied" ? ` — inclus via « ${T.ancestors(f).find((p) => T.own(p) || permsState.sel.has(p.id)).name} »` : "";
    return `<li><div class="frow ${st}">
      ${sub.length ? `<button type="button" class="tw ${open ? "open" : ""}" data-tw="${f.id}" aria-label="${open ? "Replier" : "Déplier"}" aria-expanded="${open}">▸</button>` : '<span class="tw"></span>'}
      <label title="${esc(by + via)}"><input type="checkbox" data-fid="${f.id}" ${st === "direct" || st === "implied" || st === "own" ? "checked" : ""}
        ${st === "partial" ? "data-partial" : ""} ${st === "own" || st === "implied" ? "disabled" : ""}> ${ic("folder")} <span>${esc(f.name)}</span></label>
      ${tag[st] ? `<small class="ftag ${st}">${tag[st]}</small>` : ""}
    </div>${sub.length && open ? `<ul>${sub.map(row).join("")}</ul>` : ""}</li>`;
  };
  const roots = T.kids.get(null) || [];
  $("ftree").innerHTML = roots.length ? `<ul>${roots.map(row).join("")}</ul>` : '<p class="hint">Aucun dossier pour le moment.</p>';
  $("ftree").querySelectorAll("[data-partial]").forEach((x) => (x.indeterminate = true));
  const dirty = [...permsState.sel].sort().join() !== [...permsState.data.assigned].sort().join();
  $("saveFolders").disabled = !dirty;
  $("folderCount").textContent = permsState.sel.size ? String(permsState.sel.size) : "";
  $("folderDirty").hidden = !dirty;
}
async function renderPermsPanel() {
  const u = state.users.find((x) => x.id === permsState.id), box = $("permsPanel");
  if (!u) { box.innerHTML = ""; return; }
  const name = esc(u.display_name || u.username);
  if (u.is_admin) {
    box.innerHTML = `<div class="card"><h3>${name}</h3><p class="hint">Administrateur : toutes les actions sont autorisées et tous les dossiers sont visibles, y compris la corbeille de chacun. Ses droits ne se règlent pas ici.</p></div>`;
    return;
  }
  const data = await api(`/api/users/${u.id}/folders`);
  if (u.id !== permsState.id) return;  // l'administrateur a changé d'utilisateur pendant le chargement
  permsState.data = data;
  permsState.sel = new Set(data.assigned);
  const T0 = ftree();  // dossiers qui contiennent une attribution : dépliés d'emblée
  permsState.open = new Set(data.assigned.flatMap((id) => T0.ancestors(T0.byId.get(id)).map((p) => p.id)));
  box.innerHTML = `
    <div class="card">
      <h3>${name} <small class="muted">@${esc(u.username)}</small></h3>
      <div class="tabs" role="tablist" aria-label="Permissions de ${name}">
        <button type="button" role="tab" data-ptab="actions" class="${permsState.tab === "actions" ? "active" : ""}" aria-selected="${permsState.tab === "actions"}">Actions autorisées</button>
        <button type="button" role="tab" data-ptab="folders" class="${permsState.tab === "folders" ? "active" : ""}" aria-selected="${permsState.tab === "folders"}">Dossiers <span class="count" id="folderCount"></span></button>
      </div>
      <div data-pane="actions" ${permsState.tab === "actions" ? "" : "hidden"}>
        <p class="hint">Ce que cet utilisateur a le droit de faire.</p>
        <div class="perm-list">${Object.entries(state.me.catalog).map(([k, l]) =>
          `<label><input type="checkbox" name="perm" value="${k}" ${u.permissions.includes(k) ? "checked" : ""}> ${esc(l)}</label>`).join("")}</div>
        <div class="dialog-foot"><button class="btn" data-perms="save">Enregistrer les actions</button></div>
      </div>
      <div data-pane="folders" ${permsState.tab === "folders" ? "" : "hidden"}>
        <p class="hint">Cochez un dossier pour que <b>${name}</b> y travaille : <b>tout ce qu'il contient est alors inclus</b>. Pour ne donner qu'une partie, dépliez et cochez uniquement les sous-dossiers voulus (le dossier au-dessus apparaît alors « partiel »). Il ne peut ni modifier ni supprimer ce qu'il n'a pas créé ; ses propres dossiers sont toujours inclus.</p>
        <div id="ftree" class="ftree"></div>
        <div class="dialog-foot"><span class="hint" id="folderDirty" hidden>Modifications non enregistrées</span>
          <button class="btn" id="saveFolders" data-perms="savefolders" disabled>Enregistrer les dossiers</button></div>
      </div>
    </div>`;
  renderFolderTree();
}
$("permsUsers").addEventListener("click", (e) => {
  const b = e.target.closest("[data-pu]");
  if (!b) return;
  permsState.id = +b.dataset.pu;
  renderPermsUsers();
  renderPermsPanel();
});
$("permsPanel").addEventListener("click", async (e) => {
  const tab = e.target.closest("[data-ptab]");
  if (tab) {  // les deux volets restent dans la page : ce qui est coché n'est pas perdu en changeant d'onglet
    permsState.tab = tab.dataset.ptab;
    $("permsPanel").querySelectorAll("[data-ptab]").forEach((t) => { const on = t === tab; t.classList.toggle("active", on); t.setAttribute("aria-selected", on); });
    $("permsPanel").querySelectorAll("[data-pane]").forEach((p) => (p.hidden = p.dataset.pane !== permsState.tab));
    return;
  }
  const tw = e.target.closest("[data-tw]");
  if (tw) {
    const id = +tw.dataset.tw;
    permsState.open.has(id) ? permsState.open.delete(id) : permsState.open.add(id);
    renderFolderTree();
    return;
  }
  const b = e.target.closest("[data-perms]");
  if (!b) return;
  const u = state.users.find((x) => x.id === permsState.id), act = b.dataset.perms;
  await busy(b, async () => {
    try {
      if (act === "save") {
        const upd = await api(`/api/users/${u.id}`, { method: "PATCH", body: { permissions: [...$("permsPanel").querySelectorAll("[name=perm]:checked")].map((c) => c.value) } });
        Object.assign(u, upd);
        toast(`Actions de ${u.display_name || u.username} enregistrées`, "ok");
      } else {
        permsState.data = await api(`/api/users/${u.id}/folders`, { method: "PUT", body: { folder_ids: [...permsState.sel] } });
        permsState.sel = new Set(permsState.data.assigned);  // le serveur écarte ce qui est déjà inclus par un parent
        renderFolderTree();
        toast(`Dossiers de ${u.display_name || u.username} enregistrés`, "ok");
        loadFolders();
      }
    } catch (err) { toast(err.message, true); }
  });
});
$("permsPanel").addEventListener("change", (e) => {
  const box = e.target.closest("[data-fid]");
  if (!box) return;
  const T = ftree(), f = T.byId.get(+box.dataset.fid);
  if (permsState.sel.has(f.id)) permsState.sel.delete(f.id);
  else { permsState.sel.add(f.id); T.descendants(f).forEach((x) => permsState.sel.delete(x.id)); permsState.open.add(f.id); }  // le contenu est inclus : plus besoin de le lister
  renderFolderTree();
});

// ---------- Voix anglaise : réglages et banc d'essai (administrateur) ----------
const voice = { data: null, sig: "", cards: new Map() };
const verdict = (m) => (m <= 60 ? ["ok", "confortable : presque en temps réel"] : m <= 180 ? ["warn", "acceptable en tâche de fond"] : ["err", "trop lent sur ce serveur"]);
async function loadVoice(silent = false) {
  clearTimeout(state.timers.voice);
  try { [voice.data, voice.en] = await Promise.all([api("/api/voicelab"), api("/api/english")]); } catch (err) { if (!silent) toast(err.message, true); return; }
  if (state.view !== "voice") return;
  const d = voice.data, en = voice.en;
  state.enAlive = d.alive;
  $("voiceStatus").innerHTML = d.alive
    ? '<span class="pill on">Service voicelab actif</span> <span class="hint">Les versions anglaises et les essais sont calculés sur ce serveur, l\'un après l\'autre.</span>'
    : `<span class="pill off">${d.last_seen ? "Service voicelab arrêté" : "Service voicelab jamais démarré"}</span>
       ${d.last_seen ? `<span class="hint">Dernier signe de vie : ${fmtDate(d.last_seen)}.</span>` : ""}
       <p class="hint">Les modèles de voix (PyTorch, plusieurs Go) tournent dans un service à part, <code>voicelab</code>, démarré avec l'application. ${d.last_seen
         ? "Il s'est arrêté : regardez son journal d'exécution (Coolify : le service voicelab, Logs)."
         : "S'il n'a jamais donné signe de vie, sa construction ou son démarrage a échoué ou n'est pas terminé (la première construction dure longtemps) : regardez le journal de construction puis d'exécution du service <code>voicelab</code> (Coolify : Logs) et redéployez."}
       Tant qu'il est arrêté, les demandes restent « en attente ».</p>`;
  const sig = d.podcasts.map((p) => p.id).join(",") + "|" + d.engines.map((e) => e.id).join(",") + "|" + JSON.stringify(en.defaults) + en.claude_available;
  if (sig !== voice.sig) {
    const tr = (sel) => Object.entries(en.translators).map(([k, l]) => `<option value="${k}" ${k === sel ? "selected" : ""}>${esc(l)}${k === "claude" && !en.claude_available ? " — indisponible, le modèle local sera utilisé" : ""}</option>`).join("");
    $("enTranslator").innerHTML = tr(en.defaults.translator);
    $("voiceTranslator").innerHTML = tr("local");
    $("enEngine").innerHTML = Object.entries(en.engines).map(([k, l]) => `<option value="${k}" ${k === en.defaults.engine ? "selected" : ""}>${esc(l)}</option>`).join("");  // le formulaire n'est reconstruit que si ses choix changent : pas de saisie perdue pendant le suivi
    voice.sig = sig;
    $("voicePodcast").innerHTML = d.podcasts.length
      ? d.podcasts.map((p) => `<option value="${p.id}" data-s="${p.seconds}">${esc(p.title)} · ${esc(p.date)}${p.folder ? ` — ${esc(p.folder)}` : ""} (${Math.round(p.seconds / 60)} min)</option>`).join("")
      : '<option value="">Aucun podcast terminé</option>';
    $("voiceEngines").innerHTML = d.engines.map((e, i) => `<label><input type="checkbox" name="engine" value="${e.id}" ${i === 0 ? "checked" : ""}> <b>${esc(e.label)}</b> <span class="muted">— ${esc(e.note)}</span></label>`).join("");
    $("voicePodcast").onchange();
  }
  renderVoiceRuns();
  if (d.runs.some((r) => r.status === "pending" || r.status === "running")) state.timers.voice = setTimeout(() => loadVoice(true), 3000);
}
$("enSettings").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.currentTarget;
  await busy(f.querySelector("button[type=submit]"), async () => {
    try { await api("/api/english/settings", { method: "PUT", body: { translator: f.translator.value, engine: f.engine.value } }); toast("Réglages enregistrés", "ok"); }
    catch (err) { toast(err.message, true); }
  });
};
document.querySelector('[data-vtab]')?.parentElement.addEventListener("click", (e) => {  // onglets Réglages / Banc d'essai
  const t = e.target.closest("[data-vtab]");
  if (!t) return;
  document.querySelectorAll("[data-vtab]").forEach((b) => { const on = b === t; b.classList.toggle("active", on); b.setAttribute("aria-selected", on); });
  document.querySelectorAll("[data-vpane]").forEach((p) => (p.hidden = p.dataset.vpane !== t.dataset.vtab));
});
$("voicePodcast").onchange = () => {  // début proposé : 15 min, ou plus tôt si le podcast est court
  const s = +($("voicePodcast").selectedOptions[0]?.dataset.s || 0);
  $("voiceForm").start.value = Math.max(0, Math.min(15, Math.floor(s / 60) - 4));
};
$("voiceForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.currentTarget, engines = [...f.querySelectorAll("[name=engine]:checked")].map((c) => c.value);
  await busy(f.querySelector("button[type=submit]"), async () => {
    try {
      if (!f.job_id.value) throw new Error("Aucun podcast terminé à utiliser");
      await api("/api/voicelab/runs", { method: "POST", body: { job_id: +f.job_id.value, start: +f.start.value * 60, seconds: +f.seconds.value,
        ref_start: +f.ref_start.value, engines, translator: f.translator.value, text_en: f.text_en.value } });
      toast("Essai ajouté", "ok");
      await loadVoice(true);
    } catch (err) { toast(err.message, true); }
  });
};
function voiceCard(r) {
  const base = `/api/voicelab/runs/${r.id}/file/`, rep = r.report;
  const meta = [fmtDate(r.created_at), `extrait de ${Math.round(r.seconds / 60 * 10) / 10} min à partir de ${Math.floor(r.start / 60)} min`, r.engines.join(", "), r.has_text_en ? "traduction fournie" : (r.report?.translation ? `traduit par : ${r.report.translation}` : r.translator === "claude" ? "traduction Claude" : "traduction locale")].filter(Boolean).join(" · ");
  let body = "";
  if (r.status === "pending") body = `<div class="queued">${ic("clock")} En attente${voice.data.alive ? "" : " — le service voicelab n'est pas démarré"}</div>`;
  else if (r.status === "running") body = `<div class="progress"><div style="width:${Math.round(r.progress * 100)}%"></div></div><div class="step"><b>${Math.round(r.progress * 100)} %</b> — ${esc(r.step)}</div>`;
  else if (r.status === "error") body = `<div class="err-box">${esc(r.error || "Erreur")}</div>`;
  else if (rep) {
    const rows = rep.results.map((m) => {
      if (m.error) return `<tr><td>${esc(m.engine)}</td><td colspan="6" class="vfail">Échec : ${esc(m.error)}${m.hint ? `<br><small>${esc(m.hint)}</small>` : ""}</td></tr>`;
      const [kind, why] = verdict(m.min_per_source_hour);
      return `<tr><td><b>${esc(m.engine)}</b></td><td>${m.load_s} s</td><td>${m.synth_s} s</td><td>${m.audio_s} s</td><td>${m.rtf}</td>
        <td><span class="vv ${kind}" title="${esc(why)}">${m.min_per_source_hour} min</span></td><td><audio controls preload="none" src="${base}${m.file}"></audio></td></tr>`;
    }).join("");
    body = `<div class="vref">Voix de référence : <audio controls preload="none" src="${base}ref.wav"></audio>
        <a href="${base}en.txt" target="_blank" rel="noopener">texte anglais</a>${r.has_text_en ? "" : ` · <a href="${base}fr.txt" target="_blank" rel="noopener">texte français</a>`}</div>
      <table class="usage-table"><thead><tr><th>Moteur</th><th>Chargement</th><th>Synthèse</th><th>Audio</th><th>RTF</th><th>Pour 1 h de sermon</th><th>Écoute</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="hint">RTF inférieur à 1 : la synthèse est plus rapide que l'audio produit. « Pour 1 h de sermon » : minutes de calcul estimées, chargement exclu (vert : moins d'1 h, orange : jusqu'à 3 h, rouge : au-delà). Écoutez pour juger la ressemblance, le naturel et l'accent.</p>`;
  }
  return `<div class="card vrun" data-run="${r.id}">
    <div class="vhead"><div><b>${esc(r.title)}</b> <span class="badge ${r.status}">${{ pending: "En attente", running: "En cours", done: "Terminé", error: "Erreur" }[r.status]}</span>
      <div class="job-sub">${esc(meta)}</div></div>
      <button class="btn small ghost danger" data-vdel="${r.id}" ${r.status === "running" ? "disabled" : ""}>${ic("trash")} Supprimer</button></div>
    ${body}<details class="log"><summary>Journal</summary><pre class="detail-log">${esc(r.log || "(vide)")}</pre></details></div>`;
}
function renderVoiceRuns() {  // chaque carte n'est refaite que si son contenu change : un lecteur audio en cours n'est jamais coupé
  const box = $("voiceRuns"), runs = voice.data.runs;
  if (!runs.length) { box.innerHTML = '<p class="muted">Aucun essai pour le moment.</p>'; voice.cards.clear(); return; }
  if (box.querySelector(":scope > p")) box.innerHTML = "";
  const alive = voice.data.alive, keep = new Set(runs.map((r) => r.id));
  voice.cards.forEach((_, id) => { if (!keep.has(id)) { box.querySelector(`[data-run="${id}"]`)?.remove(); voice.cards.delete(id); } });
  let prev = null;
  for (const r of runs) {
    const sig = [r.status, r.step, r.progress, (r.log || "").length, alive].join("|");
    let node = box.querySelector(`[data-run="${r.id}"]`);
    if (!node || voice.cards.get(r.id) !== sig) {
      const fresh = document.createRange().createContextualFragment(voiceCard(r)).firstElementChild;
      hydrateIcons(fresh);
      node ? node.replaceWith(fresh) : box.insertBefore(fresh, prev ? prev.nextSibling : box.firstChild);
      node = fresh;
      voice.cards.set(r.id, sig);
    }
    prev = node;
  }
}
$("voiceRuns").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-vdel]");
  if (!b || !(await confirmBox({ title: "Supprimer cet essai ?", message: "Ses fichiers audio seront supprimés.", confirmLabel: "Supprimer", danger: true }))) return;
  try { await api(`/api/voicelab/runs/${b.dataset.vdel}`, { method: "DELETE" }); await loadVoice(true); } catch (err) { toast(err.message, true); }
});

// ---------- Corbeille ----------
async function loadTrash() {
  const items = await api("/api/trash"), admin = state.me.is_admin;
  $("trashHint").textContent = admin
    ? "Vous voyez tout ce qui a été supprimé, par tout le monde. Seul un administrateur supprime définitivement."
    : "Ce que vous avez supprimé est ici : restaurez-le quand vous voulez. Seul un administrateur peut le supprimer définitivement.";
  $("trashEmpty").hidden = !admin || !items.length;
  $("trashList").innerHTML = items.length ? items.map((i) => `
    <div class="trash-row">
      <span class="t-ic">${ic(i.kind === "folder" ? "folder" : "music")}</span>
      <div class="t-main"><b>${esc(i.name)}</b>${i.detail ? ` <span class="muted">· ${esc(i.detail)}</span>` : ""}
        <div class="job-sub">${i.kind === "folder" ? "Dossier" : "Podcast"}${i.path ? ` · dans ${esc(i.path)}` : ""} · supprimé ${admin ? `par ${esc(i.deleted_by)} ` : ""}le ${fmtDate(i.deleted_at)}</div></div>
      <div class="actions">
        <button class="btn small ghost" data-trash="restore" data-kind="${i.kind}" data-id="${i.id}" ${i.blocked ? 'disabled title="Restaurez d\'abord le dossier qui le contient"' : ""}>${ic("retry")} Restaurer</button>
        ${admin ? `<button class="btn small ghost danger" data-trash="purge" data-kind="${i.kind}" data-id="${i.id}" data-name="${esc(i.name)}">${ic("trash")} Supprimer définitivement</button>` : ""}
      </div>
    </div>`).join("") : '<div class="card muted">La corbeille est vide.</div>';
}
$("trashList").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-trash]");
  if (!b) return;
  const { kind, id } = b.dataset, base = `/api/trash/${kind}/${id}`;
  try {
    if (b.dataset.trash === "restore") {
      await busy(b, () => api(`${base}/restore`, { method: "POST" }));
      toast("Restauré", "ok");
    } else {
      const ok = await confirmBox({ title: "Supprimer définitivement ?", danger: true, confirmLabel: "Supprimer définitivement",
        message: kind === "folder"
          ? `Le dossier « <b>${esc(b.dataset.name)}</b> » et tout ce qu'il contient (déjà dans la corbeille) seront supprimés <b>pour toujours</b>, y compris sur R2. Cette action est irréversible.`
          : `« <b>${esc(b.dataset.name)}</b> » sera supprimé <b>pour toujours</b>, avec ses fichiers (y compris sur R2). Cette action est irréversible.` });
      if (!ok) return;
      await busy(b, () => api(base, { method: "DELETE" }));
      toast("Supprimé définitivement", "ok");
    }
    await loadTrash();
    loadFolders();
  } catch (err) { alertBox({ title: "Action impossible", message: esc(err.message), kind: "danger" }); }
});
$("trashEmpty").onclick = async (e) => {
  const ok = await confirmBox({ title: "Vider la corbeille ?", danger: true, confirmLabel: "Tout supprimer définitivement",
    message: "Tout ce qui est dans la corbeille, <b>de tous les utilisateurs</b>, sera supprimé pour toujours, y compris sur R2. Cette action est irréversible." });
  if (!ok) return;
  try { await busy(e.currentTarget, () => api("/api/trash", { method: "DELETE" })); toast("Corbeille vidée", "ok"); await loadTrash(); loadFolders(); }
  catch (err) { alertBox({ title: "Action impossible", message: esc(err.message), kind: "danger" }); }
};

// ---------- Démarrage ----------
hydrateIcons();
(async function boot() {
  try {
    state.me = await api("/api/auth/me");
    await startApp();
  } catch { showLogin(); }
})();

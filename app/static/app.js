const state = { folders: [], current: null, jobs: [], expanded: new Set(), timer: null, retryJob: null,
  intros: [], history: false, hist: { items: [], total: 0, timer: null, search: null }, detail: null, detailTimer: null };
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

try { JSON.parse(localStorage.getItem("expanded") || "[]").forEach((id) => state.expanded.add(id)); } catch {}
const saveExpanded = () => { try { localStorage.setItem("expanded", JSON.stringify([...state.expanded])); } catch {} };

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: opts.body && !(opts.body instanceof FormData) ? { "content-type": "application/json" } : {},
    body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Erreur ${res.status}`);
  return data;
}

function toast(msg, error = false) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast" + (error ? " error" : "");
  t.hidden = false;
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.hidden = true), 3500);
}

const fmtSize = (b) => (b ? (b / 1e6).toFixed(1) + " Mo" : "");
const children = (pid) => state.folders.filter((f) => f.parent_id === pid).sort((a, b) => a.name.localeCompare(b.name, "fr"));
const byId = (id) => state.folders.find((f) => f.id === id);
function pathOf(folder) {
  const out = [];
  let cur = folder;
  while (cur) { out.unshift(cur); cur = cur.parent_id ? byId(cur.parent_id) : null; }
  return out;
}

// ---------- Dossiers ----------
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
        <div class="node ${state.current === f.id ? "active" : ""}" data-id="${f.id}">
          <span class="twisty" data-toggle="${f.id}">${hasKids ? (open ? "▾" : "▸") : ""}</span>
          <span>📁</span><span>${esc(f.name)}</span>
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

async function createFolder(parentId) {
  const name = prompt(parentId ? "Nom du sous-dossier :" : "Nom du dossier (ex. CULTE ROYAL) :");
  if (!name || !name.trim()) return;
  try {
    const f = await api("/api/folders", { method: "POST", body: { name, parent_id: parentId } });
    if (parentId) state.expanded.add(parentId);
    saveExpanded();
    await loadFolders();
    openFolder(f.id);
  } catch (err) { toast(err.message, true); }
}

function openFolder(id) {
  state.current = id;
  showHistory(false);
  history.replaceState(null, "", "#" + id);
  pathOf(byId(id)).slice(0, -1).forEach((f) => state.expanded.add(f.id));
  saveExpanded();
  $("sidebar").classList.remove("open");
  renderTree();
  renderFolder();
  loadJobs();
}

function renderFolder() {
  const f = byId(state.current);
  $("emptyState").hidden = !!f || state.history;
  $("folderView").hidden = !f || state.history;
  if (!f) return;
  const path = pathOf(f);
  $("crumbs").innerHTML = path.map((p, i) => i < path.length - 1
    ? `<a data-id="${p.id}">${esc(p.name)}</a> / ` : "").join("");
  $("folderTitle").textContent = f.name;
  $("subfolders").innerHTML = children(f.id).map((c) =>
    `<div class="subfolder" data-id="${c.id}">📁 ${esc(c.name)}</div>`).join("");
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
  const name = prompt("Nouveau nom :", f.name);
  if (!name || !name.trim()) return;
  try { await api(`/api/folders/${f.id}`, { method: "PATCH", body: { name } }); await loadFolders(); renderFolder(); }
  catch (err) { toast(err.message, true); }
};
$("deleteFolderBtn").onclick = async () => {
  const f = byId(state.current);
  if (!confirm(`Supprimer le dossier « ${f.name} » ?`)) return;
  try {
    await api(`/api/folders/${f.id}`, { method: "DELETE" });
    state.current = f.parent_id;
    await loadFolders();
    f.parent_id ? openFolder(f.parent_id) : (history.replaceState(null, "", "#"), renderFolder());
  } catch (err) { toast(err.message, true); }
};
$("menuBtn").onclick = () => $("sidebar").classList.toggle("open");

// ---------- Intros (bibliothèque MP3) ----------
const introName = (id) => state.intros.find((i) => i.id === id)?.name;
const defaultIntro = () => state.intros.find((i) => i.is_default);

function introOptions(first, withNone = false, selected = "") {
  const opts = [...first, ...state.intros.map((i) => [String(i.id), i.name + (i.is_default ? " ★ par défaut" : "")])];
  if (withNone) opts.push(["0", "Aucune intro"]);
  return opts.map(([v, l]) => `<option value="${esc(v)}" ${String(selected) === v ? "selected" : ""}>${esc(l)}</option>`).join("");
}

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
    toast("Intro du dossier enregistrée");
  } catch (err) { toast(err.message, true); }
};

function renderIntroList() {
  $("introList").innerHTML = state.intros.length ? state.intros.map((i) => `
    <div class="intro-item">
      <div class="top">
        <div><b>${esc(i.name)}</b> <span class="muted">${esc(i.duration)}</span>
          ${i.is_default ? '<span class="badge default">Par défaut</span>' : ""}</div>
        <div class="actions">
          ${i.is_default ? "" : `<button class="btn small ghost" data-intro="default" data-id="${i.id}">★ Par défaut</button>`}
          <button class="btn small ghost" data-intro="rename" data-id="${i.id}">Renommer</button>
          <button class="btn small ghost danger" data-intro="delete" data-id="${i.id}">Supprimer</button>
        </div>
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
  try {
    if (b.dataset.intro === "default") {
      await api(`/api/intros/${id}`, { method: "PATCH", body: { is_default: true } });
    } else if (b.dataset.intro === "rename") {
      const name = prompt("Nouveau nom :", intro.name);
      if (!name || !name.trim()) return;
      await api(`/api/intros/${id}`, { method: "PATCH", body: { name } });
    } else if (b.dataset.intro === "delete") {
      if (!confirm(`Supprimer l'intro « ${intro.name} » ? Les dossiers et traitements qui l'utilisaient repasseront en automatique.`)) return;
      const r = await api(`/api/intros/${id}`, { method: "DELETE" });
      if (r.was_default) toast("Attention : plus d'intro par défaut", true);
      await loadFolders();
    }
    await loadIntros();
  } catch (err) { toast(err.message, true); }
});

$("introForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target, fd = new FormData();
  fd.append("file", f.file.files[0]);
  fd.append("name", f.name.value);
  fd.append("is_default", f.is_default.checked);
  try {
    await api("/api/intros", { method: "POST", body: fd });
    f.reset();
    await loadIntros();
    toast("Intro ajoutée");
  } catch (err) { toast(err.message, true); }
};

// ---------- Traitements ----------
const form = $("jobForm");
form.date.value = new Date().toISOString().slice(0, 10);
function slugify(s) {
  return s.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "") || "sans-nom";
}
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
  try {
    await api("/api/jobs", { method: "POST", body });
    form.youtube_url.value = ""; form.title.value = ""; form.start.value = ""; form.end.value = "";
    updateFilenamePreview();
    toast("Traitement ajouté à la file d'attente");
    loadJobs();
    loadStatus();
  } catch (err) { toast(err.message, true); }
};

async function loadJobs() {
  if (!state.current) return;
  const folderId = state.current;
  const jobs = await api(`/api/folders/${folderId}/jobs`).catch(() => null);
  if (!jobs || folderId !== state.current) return;
  state.jobs = jobs;
  renderJobs();
  clearTimeout(state.timer);
  if (jobs.some((j) => j.status === "pending" || j.status === "running")) state.timer = setTimeout(() => { loadJobs(); loadStatus(); }, 2500);
}

const STEP_ICON = { done: "✓", active: "●", pending: "○", skipped: "–", error: "!" };
function renderSteps(j) {
  const rows = j.steps.map((s, i) => `
    <li class="st ${s.state}">
      <span class="st-icon">${STEP_ICON[s.state]}</span>
      <span class="st-name">${i + 1}. ${esc(s.label)}</span>
      <span class="st-bar"><i style="width:${s.pct}%"></i></span>
      <span class="st-pct">${s.state === "skipped" ? "ignorée" : s.pct + "%"}</span>
    </li>`).join("");
  return j.status === "done"
    ? `<details class="steps"><summary>Détail des étapes</summary><ul>${rows}</ul></details>`
    : `<ul class="steps">${rows}</ul>`;
}

const LABELS = { pending: "En attente", running: "En cours", done: "Terminé", error: "Erreur" };

function renderJobs() {
  const box = $("jobs");
  if (!state.jobs.length) { box.innerHTML = '<p class="muted">Aucun traitement dans ce dossier.</p>'; return; }
  // On conserve les lecteurs audio existants pour ne pas couper une écoute en cours
  const players = {};
  box.querySelectorAll("audio[data-job]").forEach((a) => (players[a.dataset.job] = a));
  box.innerHTML = state.jobs.map((j) => {
    const pct = Math.round(j.progress * 100);
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
          <div class="job-sub">${esc(j.video_title || j.youtube_url)}</div>
        </div>
        <span class="badge ${j.status}">${LABELS[j.status]}</span>
      </div>
      ${j.status === "pending" || j.status === "running" ? `
        <div class="progress"><div style="width:${pct}%"></div></div>
        <div class="step"><b>Global ${pct}%</b> — ${esc(j.step)}</div>` : ""}
      ${renderSteps(j)}
      ${stats.length ? `<div class="stats">${stats.map((s) => `<span>${s}</span>`).join("")}</div>` : ""}
      ${j.detection_note && j.status === "done" ? `<div class="hint">${esc(j.detection_note)}</div>` : ""}
      ${j.error ? `<div class="err-box">${esc(j.error)}</div>` : ""}
      ${j.has_mp3 ? `<div data-slot="${j.id}"></div>` : ""}
      <div class="actions">
        ${j.has_mp3 ? `<a class="btn small" href="/api/jobs/${j.id}/file/mp3?download=true">⬇ MP3</a>` : ""}
        ${j.on_r2 ? `<button class="btn small ghost" data-act="link" data-id="${j.id}">🔗 Lien R2</button>` : ""}
        <button class="btn small ghost" data-act="detail" data-id="${j.id}">Détails</button>
        ${j.status === "done" || j.status === "error" ? `<button class="btn small ghost" data-act="retry" data-id="${j.id}">Relancer</button>` : ""}
        ${j.status !== "running" ? `<button class="btn small ghost danger" data-act="delete" data-id="${j.id}">Supprimer</button>` : ""}
      </div>
    </div>`;
  }).join("");
  box.querySelectorAll("[data-slot]").forEach((slot) => {
    const id = slot.dataset.slot;
    let a = players[id];
    if (!a) {
      a = document.createElement("audio");
      a.controls = true; a.preload = "none"; a.dataset.job = id;
      a.src = `/api/jobs/${id}/file/mp3`;
    }
    slot.replaceWith(a);
  });
}

// ---------- Actions communes (liste du dossier, historique, détails) ----------
const findJob = (id) => state.jobs.find((j) => j.id === id) || state.hist.items.find((j) => j.id === id)
  || (state.detail && state.detail.id === id ? state.detail : null);

async function copyLink(url, label = "Lien copié") {
  await navigator.clipboard.writeText(url).catch(() => prompt("Lien :", url));
  toast(label);
}

async function handleAction(act, id) {
  const job = findJob(id);
  try {
    if (act === "detail") {
      openDetail(id);
    } else if (act === "link") {
      const { url, public: pub } = await api(`/api/jobs/${id}/link/mp3`);
      await copyLink(url, pub ? "Lien public copié" : "Lien copié (valable 7 jours)");
    } else if (act === "retry") {
      state.retryJob = id;
      const f = $("retryForm");
      f.start.value = job.start_override || job.sermon_start || "";
      f.end.value = job.end_override || job.sermon_end || "";
      $("retryIntroSelect").innerHTML = introOptions([["keep", "Ne pas changer"], ["", "Automatique (dossier, sinon par défaut)"]], true, "keep");
      $("retryDialog").showModal();
    } else if (act === "delete") {
      if (!confirm(`Supprimer « ${job.title} » ? Les fichiers seront aussi supprimés de R2.`)) return;
      await api(`/api/jobs/${id}`, { method: "DELETE" });
      if (state.detail && state.detail.id === id) $("detailDialog").close();
      loadJobs();
      if (state.history) loadHistory();
    }
  } catch (err) { toast(err.message, true); }
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-act]");
  if (btn) handleAction(btn.dataset.act, +btn.dataset.id);
});

const retryBody = (f) => {
  const body = { start: f.start.value, end: f.end.value };
  if (f.intro_id.value !== "keep") body.intro_id = f.intro_id.value === "" ? null : +f.intro_id.value;
  return body;
};
$("retryCancel").onclick = () => $("retryDialog").close();
$("retryForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api(`/api/jobs/${state.retryJob}/retry`, { method: "POST", body: retryBody(f) });
    $("retryDialog").close();
    toast("Traitement relancé");
    loadJobs();
    if (state.history) loadHistory();
    if (state.detail) openDetail(state.detail.id);
  } catch (err) { toast(err.message, true); }
};

// ---------- Statut ----------
async function loadStatus() {
  const s = await api("/api/status").catch(() => null);
  if (!s) return;
  $("statusBar").innerHTML = `
    <span class="pill ${s.r2 ? "on" : ""}">R2 ${s.r2 ? "connecté" : "non configuré"}</span>
    <span class="pill ${s.llm ? "on" : ""}">Détection ${s.llm ? "IA (" + s.llm + ")" : "heuristique"}</span>
    <span class="pill queue">${s.queue} en file</span>`;
}

// ---------- Historique ----------
const fmtDate = (iso) => iso ? new Date(/Z|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z")
  .toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" }) : "—";

function showHistory(on) {
  state.history = on;
  $("historyView").hidden = !on;
  $("historyBtn").classList.toggle("active", on);
  if (on) {
    state.current = null;
    history.replaceState(null, "", "#history");
    $("sidebar").classList.remove("open");
    renderTree();
    renderFolder();
    loadHistory();
  } else {
    clearTimeout(state.hist.timer);
  }
}

async function loadHistory(more = false) {
  const h = state.hist;
  const keep = Math.max(h.items.length, 50);
  const q = new URLSearchParams({ q: $("histSearch").value, status: $("histStatus").value,
    limit: more ? 50 : keep, offset: more ? h.items.length : 0 });
  const res = await api(`/api/jobs?${q}`).catch(() => null);
  if (!res || !state.history) return;
  h.items = more ? h.items.concat(res.items) : res.items;
  h.total = res.total;
  renderHistory();
  clearTimeout(h.timer);
  if (h.items.some((j) => j.status === "pending" || j.status === "running")) h.timer = setTimeout(() => loadHistory(), 3000);
}

function renderHistory() {
  const h = state.hist;
  $("histCount").textContent = h.total ? `${h.items.length} sur ${h.total} traitement(s)` : "";
  $("histMore").hidden = h.items.length >= h.total;
  if (!h.items.length) { $("histList").innerHTML = '<p class="muted">Aucun traitement.</p>'; return; }
  $("histList").innerHTML = h.items.map((j) => {
    const pct = Math.round(j.progress * 100);
    const live = j.status === "pending" || j.status === "running";
    const meta = [fmtDate(j.created_at),
      j.duration_output && `Podcast ${j.duration_output}`, 
      j.size_mp3 && `MP3 ${fmtSize(j.size_mp3)}`, j.on_r2 && "☁️ R2"].filter(Boolean);
    return `<div class="hrow">
      <div>
        <div class="job-title">${esc(j.title)} <span class="muted">· ${esc(j.date)}</span></div>
        <div class="job-sub">📁 ${esc(j.folder_path || "")}${j.video_title ? " · " + esc(j.video_title) : ""}</div>
      </div>
      <span class="badge ${j.status}">${LABELS[j.status]}</span>
      ${live ? `<div class="progress"><div style="width:${pct}%"></div></div>
        <div class="h-meta"><b>${pct}%</b><span>${esc(j.step)}</span></div>`
        : `<div class="h-meta">${meta.map((m) => `<span>${esc(m)}</span>`).join("")}</div>`}
      <div class="actions" style="grid-column:1/3">
        <button class="btn small ghost" data-act="detail" data-id="${j.id}">Détails</button>
        ${j.has_mp3 ? `<a class="btn small" href="/api/jobs/${j.id}/file/mp3?download=true">⬇ MP3</a>` : ""}
        ${j.on_r2 ? `<button class="btn small ghost" data-act="link" data-id="${j.id}">🔗 Copier le lien</button>` : ""}
      </div>
    </div>`;
  }).join("");
}

$("historyBtn").onclick = () => showHistory(true);
$("histMore").onclick = () => loadHistory(true);
$("histStatus").onchange = () => loadHistory();
$("histSearch").oninput = () => { clearTimeout(state.hist.search); state.hist.search = setTimeout(() => loadHistory(), 300); };

// ---------- Détails d'un traitement ----------
async function openDetail(id) {
  clearTimeout(state.detailTimer);
  const j = await api(`/api/jobs/${id}`).catch((err) => { toast(err.message, true); return null; });
  if (!j) return;
  state.detail = j;
  const open = $("detailDialog");
  const logOpen = open.querySelector("details.log")?.open;
  $("detailTitle").textContent = j.title;
  const row = (k, v) => v ? `<dt>${k}</dt><dd>${v}</dd>` : "";
  const linkRow = (fmt) => j.links[fmt] ? `<div class="linkrow"><b>${fmt.toUpperCase()}</b>
      <input readonly value="${esc(j.links[fmt])}" onfocus="this.select()">
      <button class="btn small" data-copy="${fmt}">Copier</button>
      <a class="btn small ghost" href="${esc(j.links[fmt])}" target="_blank" rel="noopener">Ouvrir</a></div>` : "";
  const links = linkRow("mp3");
  $("detailBody").innerHTML = `
    <div class="job-top"><div class="job-sub">📁 ${esc(j.folder_path)}</div><span class="badge ${j.status}">${LABELS[j.status]}</span></div>
    ${j.status === "pending" || j.status === "running"
      ? `<div class="progress"><div style="width:${Math.round(j.progress * 100)}%"></div></div>
         <div class="step"><b>Global ${Math.round(j.progress * 100)}%</b> — ${esc(j.step)}</div>` : ""}
    ${j.error ? `<div class="err-box">${esc(j.error)}</div>` : ""}

    ${j.has_mp3 || links ? `<div class="d-title">Écouter et télécharger</div>
      ${j.has_mp3 ? `<audio controls preload="none" src="/api/jobs/${j.id}/file/mp3"></audio>` : ""}
      <div class="actions">
        ${j.has_mp3 ? `<a class="btn small" href="/api/jobs/${j.id}/file/mp3?download=true">⬇ MP3</a>` : ""}
      </div>` : ""}
    ${links ? `<div class="d-title">Liens directs de partage (R2)</div>${links}
      <p class="hint">${j.links_public ? "Liens publics permanents."
        : `Liens signés valables ${j.links_days} jours, regénérés à chaque ouverture de cette fenêtre. Pour des liens permanents, configurez R2_PUBLIC_BASE_URL.`}</p>` : ""}

    <div class="d-title">Informations</div>
    <dl class="kv">
      ${row("Fichier", esc(j.filename))}
      ${row("Intro", esc(j.intro_name))}
      ${row("Vidéo", j.youtube_url ? `<a href="${esc(j.youtube_url)}" target="_blank" rel="noopener">${esc(j.video_title || j.youtube_url)}</a>` : "")}
      ${row("Prédication", j.sermon_start ? `${j.sermon_start} → ${j.sermon_end}` : "")}
      ${row("Repérage", esc(j.detection_note || ""))}
      ${row("Bornes forcées", j.start_override || j.end_override ? `${j.start_override || "début"} → ${j.end_override || "fin"}` : "")}
      ${row("Durée de la vidéo", j.duration_source)}
      ${row("Durée du podcast", j.duration_output)}
      ${row("Taille", j.size_mp3 ? fmtSize(j.size_mp3) : "")}
      ${row("Créé le", fmtDate(j.created_at))}
      ${row("Terminé le", j.finished_at ? fmtDate(j.finished_at) : "")}
    </dl>

    <div class="d-title">Étapes</div>
    ${renderSteps({ ...j, status: j.status === "done" ? "running" : j.status })}

    <details class="log" ${logOpen ? "open" : ""}><summary>Journal complet</summary>
      <pre class="detail-log">${esc(j.log || "(vide)")}</pre></details>

    <div class="dialog-foot">
      ${j.status === "done" || j.status === "error" ? `<button class="btn ghost" data-act="retry" data-id="${j.id}">Relancer</button>` : ""}
      ${j.status !== "running" ? `<button class="btn ghost danger" data-act="delete" data-id="${j.id}">Supprimer</button>` : ""}
    </div>`;
  if (!open.open) open.showModal();
  if (j.status === "pending" || j.status === "running") state.detailTimer = setTimeout(() => open.open && openDetail(id), 2500);
}

$("detailBody").addEventListener("click", (e) => {
  const b = e.target.closest("[data-copy]");
  if (b) copyLink(state.detail.links[b.dataset.copy], "Lien copié");
});
$("detailClose").onclick = () => $("detailDialog").close();
$("detailDialog").addEventListener("close", () => { clearTimeout(state.detailTimer); state.detail = null; });

(async function init() {
  await loadFolders();
  loadIntros();
  loadStatus();
  if (location.hash === "#history") return showHistory(true);
  const fromHash = +location.hash.slice(1);
  if (fromHash && byId(fromHash)) openFolder(fromHash);
  else renderFolder();
})();

const state = { folders: [], current: null, jobs: [], expanded: new Set(), timer: null, retryJob: null };
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
  $("emptyState").hidden = !!f;
  $("folderView").hidden = !f;
  if (!f) return;
  const path = pathOf(f);
  $("crumbs").innerHTML = path.map((p, i) => i < path.length - 1
    ? `<a data-id="${p.id}">${esc(p.name)}</a> / ` : "").join("");
  $("folderTitle").textContent = f.name;
  $("subfolders").innerHTML = children(f.id).map((c) =>
    `<div class="subfolder" data-id="${c.id}">📁 ${esc(c.name)}</div>`).join("");
  $("folderIntro").innerHTML = f.has_intro
    ? `<audio controls preload="none" src="/api/intro/${f.id}/audio"></audio>`
    : "Aucune : l'intro du dossier parent ou l'intro par défaut sera utilisée.";
  $("removeIntroBtn").hidden = !f.has_intro;
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

// ---------- Intros ----------
$("folderIntroInput").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  try { await api(`/api/folders/${state.current}/intro`, { method: "POST", body: fd }); await loadFolders(); renderFolder(); toast("Intro du dossier enregistrée"); }
  catch (err) { toast(err.message, true); }
  e.target.value = "";
};
$("removeIntroBtn").onclick = async () => {
  try { await api(`/api/folders/${state.current}/intro`, { method: "DELETE" }); await loadFolders(); renderFolder(); }
  catch (err) { toast(err.message, true); }
};
async function loadDefaultIntro() {
  const d = await api("/api/intro/default");
  $("defaultIntro").innerHTML = d.exists
    ? `<audio controls preload="none" src="/api/intro/default/audio?v=${Date.now()}" style="width:100%;height:32px"></audio>`
    : "Aucune intro par défaut";
}
$("defaultIntroInput").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  try { await api("/api/intro/default", { method: "POST", body: fd }); loadDefaultIntro(); toast("Intro par défaut enregistrée"); }
  catch (err) { toast(err.message, true); }
  e.target.value = "";
};

// ---------- Traitements ----------
const form = $("jobForm");
form.date.value = new Date().toISOString().slice(0, 10);
function slugify(s) {
  return s.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "") || "sans-nom";
}
function updateFilenamePreview() {
  const t = form.title.value.trim();
  $("filenamePreview").textContent = t ? `Fichier : ${slugify(t)}_${form.date.value}.ogg` : "";
}
form.title.oninput = updateFilenamePreview;
form.date.oninput = updateFilenamePreview;

form.onsubmit = async (e) => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(form));
  body.folder_id = state.current;
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
  if (jobs.some((j) => j.status === "pending" || j.status === "running")) state.timer = setTimeout(() => { loadJobs(); loadStatus(); }, 4000);
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
    if (j.size_ogg) stats.push(`OGG <b>${fmtSize(j.size_ogg)}</b>`);
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
        <div class="step">${esc(j.step)} — ${pct}%</div>` : ""}
      ${stats.length ? `<div class="stats">${stats.map((s) => `<span>${s}</span>`).join("")}</div>` : ""}
      ${j.detection_note && j.status === "done" ? `<div class="hint">${esc(j.detection_note)}</div>` : ""}
      ${j.error ? `<div class="err-box">${esc(j.error)}</div>` : ""}
      ${j.has_ogg ? `<div data-slot="${j.id}"></div>` : ""}
      <div class="actions">
        ${j.has_ogg ? `<a class="btn small" href="/api/jobs/${j.id}/file/ogg?download=true">⬇ OGG</a>` : ""}
        ${j.has_mp3 ? `<a class="btn small ghost" href="/api/jobs/${j.id}/file/mp3?download=true">⬇ MP3</a>` : ""}
        ${j.on_r2 ? `<button class="btn small ghost" data-act="link" data-id="${j.id}">🔗 Lien R2</button>` : ""}
        <button class="btn small ghost" data-act="log" data-id="${j.id}">Journal</button>
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
      a.src = `/api/jobs/${id}/file/ogg`;
    }
    slot.replaceWith(a);
  });
}

$("jobs").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const id = +btn.dataset.id;
  const job = state.jobs.find((j) => j.id === id);
  try {
    if (btn.dataset.act === "log") {
      const full = await api(`/api/jobs/${id}`);
      $("logTitle").textContent = `Journal — ${full.title}`;
      $("logBody").textContent = full.log || "(vide)";
      $("logDialog").showModal();
    } else if (btn.dataset.act === "link") {
      const { url, public: pub } = await api(`/api/jobs/${id}/link/ogg`);
      await navigator.clipboard.writeText(url).catch(() => prompt("Lien :", url));
      toast(pub ? "Lien public copié" : "Lien copié (valable 7 jours)");
    } else if (btn.dataset.act === "retry") {
      state.retryJob = id;
      const f = $("retryForm");
      f.start.value = job.start_override || job.sermon_start || "";
      f.end.value = job.end_override || job.sermon_end || "";
      $("retryDialog").showModal();
    } else if (btn.dataset.act === "delete") {
      if (!confirm(`Supprimer « ${job.title} » ? Les fichiers seront aussi supprimés de R2.`)) return;
      await api(`/api/jobs/${id}`, { method: "DELETE" });
      loadJobs();
    }
  } catch (err) { toast(err.message, true); }
});

$("logClose").onclick = () => $("logDialog").close();
$("retryCancel").onclick = () => $("retryDialog").close();
$("retryForm").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api(`/api/jobs/${state.retryJob}/retry`, { method: "POST", body: { start: f.start.value, end: f.end.value } });
    $("retryDialog").close();
    toast("Traitement relancé");
    loadJobs();
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

(async function init() {
  await loadFolders();
  loadDefaultIntro();
  loadStatus();
  const fromHash = +location.hash.slice(1);
  if (fromHash && byId(fromHash)) openFolder(fromHash);
  else renderFolder();
})();

// ============================================================================
// Visite guidée : lancée à la première connexion de chaque compte (par navigateur),
// relançable à tout moment avec le bouton « Tutoriel » de la barre du haut.
// Utilise les fonctions de app.js (state, can, go, $) : à charger après lui.
// ============================================================================
const TOUR_STEPS = [
  { view: "home", title: "Bienvenue sur Studio Podcast 👋",
    text: "En une minute, voyez comment transformer un culte YouTube en podcast de prédication, prêt à partager sur WhatsApp et Telegram." },
  { view: "home", target: '[data-nav="folders"]', title: "Les dossiers",
    text: "Vos podcasts sont classés dans des dossiers et sous-dossiers, comme dans un explorateur de fichiers (ex. <b>CULTE ROYAL / Octobre 2026</b>). Le même classement est reproduit sur R2." },
  { view: "folders", target: "#foldActions", when: () => can("folders.manage") || can("jobs.create"), title: "Créer un dossier, lancer un traitement",
    text: "<b>Nouveau dossier</b> crée un dossier. Ouvrez-le (double-clic) : le bouton <b>Nouveau traitement</b> apparaît. Collez-y un lien YouTube (ou envoyez un fichier audio / vidéo), donnez un nom et une date, puis lancez." },
  { view: "folders", when: () => can("jobs.create"), title: "Ce que fait le traitement",
    text: "Tout est automatique : téléchargement, repérage de la prédication, amélioration de la voix, retrait des silences, des « euh » et des répétitions, ajout de l'intro, compression MP3 et envoi sur R2. Vous pouvez aussi préparer <b>un lot</b> de plusieurs liens, ou forcer le début et la fin de la prédication (<i>Options</i>)." },
  { view: "folders", target: "#statusBar", title: "Suivre l'avancement",
    text: "Ici : les traitements en cours et en file d'attente, l'état de R2 et de l'IA, et le compteur de tokens de l'IA (cliquez pour le détail). Cliquez sur « en cours » pour voir l'avancement détaillé, étape par étape. Il reste visible même si vous fermez la page." },
  { view: "home", target: '[data-nav="home"]', title: "Vos podcasts terminés",
    text: "L'accueil rassemble les podcasts terminés et les traitements actifs. Pour chacun : <b>écouter</b>, <b>télécharger</b>, <b>copier le lien</b> à envoyer, voir les <b>détails</b>, <b>rogner</b> le début ou la fin, ou <b>relancer</b> si la prédication détectée n'est pas la bonne (selon vos droits)." },
  { view: "home", target: '[data-nav="history"]', title: "Historique",
    text: "Tous les traitements, tous dossiers confondus, avec recherche et filtre par statut (en cours, terminés, en erreur)." },
  { view: "home", target: '[data-nav="trash"]', title: "Corbeille",
    text: "Rien n'est supprimé pour de bon : un dossier ou un podcast supprimé arrive ici, d'où vous pouvez le <b>restaurer</b>. Chacun a sa corbeille ; seul un administrateur supprime définitivement." },
  { view: "home", target: '[data-nav="intros"]', title: "Bibliothèque d'intros",
    text: "Les intros sont des fichiers MP3 ajoutés au début des podcasts. Sans choix, le podcast prend l'intro de son dossier, sinon l'intro par défaut (★)." },
  { view: "home", target: "#navPerms", when: () => !!state.me?.is_admin, title: "Permissions",
    text: "Choisissez un utilisateur : l'onglet Actions règle ce qu'il peut faire, l'onglet Dossiers lui attribue des dossiers (arborescence à cocher : un dossier entier, ou seulement certains sous-dossiers). Vous voyez aussi toutes les corbeilles." },
  { view: "home", target: "#navUsers", when: () => !!state.me?.is_admin, title: "Utilisateurs",
    text: "En tant qu'administrateur, créez les comptes et choisissez ce que chacun peut faire (voir, lancer, supprimer, rogner, gérer les dossiers…)." },
  { view: "home", target: "#userBtn", when: () => can("ai.key"), title: "Utiliser votre propre clé Anthropic (IA)",
    text: "L'IA repère la prédication et retire adoration, témoignages et annonces. Pour l'utiliser avec <b>votre</b> clé : 1) créez un compte sur <b>console.anthropic.com</b> et ajoutez du crédit (Billing) ; 2) <i>API Keys → Create Key</i>, copiez la clé (elle commence par <b>sk-ant-</b>) ; 3) ouvrez ce menu → <b>Mon IA</b>, collez-la et enregistrez. Elle est vérifiée, stockée chiffrée, et sert à vos traitements (et à ceux qu'un administrateur choisit de lancer avec votre configuration). Comptez environ 15 000 à 20 000 tokens pour un culte de 3 h." },
  { view: "home", target: "#userBtn", when: () => can("ai.toggle") && !can("ai.key"), title: "Activer ou couper l'IA",
    text: "Dans ce menu → <b>Mon IA</b>, vous pouvez activer ou désactiver l'IA pour vos traitements. Désactivée, le repérage de la prédication se fait par heuristique (moins fiable) et l'adoration, les témoignages et les annonces ne sont pas retirés." },
  { view: "home", target: "#tourBtn", title: "Vous êtes prêt !",
    text: "Ce bouton relance ce tutoriel à tout moment. À côté, le bouton soleil / lune change le thème (clair ou sombre), et votre menu en haut à droite donne accès à votre profil (nom, mot de passe)." },
];

let tour = null;
const tourKey = () => "tour:" + state.me.username;
// sans stockage disponible : pas de lancement automatique à chaque visite (le bouton reste utilisable)
const tourSeen = () => { try { return !!localStorage.getItem(tourKey()); } catch { return true; } };

async function startTour() {
  if (tour) return;
  try { localStorage.setItem(tourKey(), "1"); } catch {}
  const root = document.createElement("div");
  root.className = "tour";
  root.innerHTML = '<div class="tour-spot"></div><section class="tour-card" role="dialog" aria-modal="true" aria-labelledby="tourTitle"></section>';
  document.body.appendChild(root);
  tour = { root, steps: TOUR_STEPS.filter((s) => !s.when || s.when()), i: 0 };
  root.addEventListener("click", (e) => {
    const b = e.target.closest("[data-tour]")?.dataset.tour;
    if (b === "skip") endTour();
    else if (b === "prev") showTourStep(tour.i - 1);
    else if (b === "next") tour.i + 1 < tour.steps.length ? showTourStep(tour.i + 1) : endTour();
  });
  document.addEventListener("keydown", tourOnKey, true);
  window.addEventListener("resize", placeTour);
  await showTourStep(0);
}

function endTour() {
  if (!tour) return;
  tour.root.remove();
  tour = null;
  document.removeEventListener("keydown", tourOnKey, true);
  window.removeEventListener("resize", placeTour);
  $("sidebar").classList.remove("open");
  $("tourBtn").focus();
}

function tourOnKey(e) {
  if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); endTour(); }
  else if (e.key === "ArrowRight") tour.root.querySelector('[data-tour="next"]').click();
  else if (e.key === "ArrowLeft") tour.root.querySelector('[data-tour="prev"]')?.click();
  else if (e.key === "Tab") {  // le focus reste dans la fenêtre du tutoriel
    e.preventDefault();
    const btns = [...tour.root.querySelectorAll("button")], at = btns.indexOf(document.activeElement);
    btns[(at + (e.shiftKey ? -1 : 1) + btns.length) % btns.length].focus();
  }
}

async function showTourStep(i) {
  const t = tour, s = t.steps[i], last = i === t.steps.length - 1;
  t.i = i;
  if (s.view && state.view !== s.view) await go(s.view);
  if (tour !== t) return;  // fermé pendant le chargement de la page
  t.root.querySelector(".tour-card").innerHTML = `
    <div class="tour-count">${i + 1} / ${t.steps.length}</div>
    <h3 id="tourTitle">${s.title}</h3>
    <p>${s.text}</p>
    <div class="tour-bar"><i style="width:${((i + 1) / t.steps.length) * 100}%"></i></div>
    <div class="tour-foot">
      ${last ? "" : '<button type="button" class="btn small ghost" data-tour="skip">Passer</button>'}
      <span class="grow"></span>
      ${i ? '<button type="button" class="btn small ghost" data-tour="prev">Précédent</button>' : ""}
      <button type="button" class="btn small" data-tour="next">${last ? "Terminer" : i ? "Suivant" : "Commencer"}</button>
    </div>`;
  // sur mobile, le menu latéral est un tiroir : on l'ouvre pour montrer ses entrées
  const el = s.target && document.querySelector(s.target);
  const drawer = el?.closest("#sidebar") && matchMedia("(max-width: 820px)").matches;
  $("sidebar").classList.toggle("open", !!drawer);
  if (drawer) await new Promise((r) => setTimeout(r, 250));  // fin de l'animation du tiroir
  if (tour !== t) return;
  placeTour();
  t.root.querySelector('[data-tour="next"]').focus();
}

function placeTour() {
  if (!tour) return;
  const s = tour.steps[tour.i], card = tour.root.querySelector(".tour-card"), spot = tour.root.querySelector(".tour-spot");
  const el = s.target && document.querySelector(s.target);
  el?.scrollIntoView({ block: "nearest" });
  let r = el?.getBoundingClientRect();
  if (r && !(r.width && r.height)) r = null;  // cible absente ou masquée (petit écran, droits) : étape centrée
  tour.root.classList.toggle("center", !r);
  const W = card.offsetWidth, H = card.offsetHeight, vw = innerWidth, vh = innerHeight, gap = 14, m = 12;
  let left = (vw - W) / 2, top = (vh - H) / 2;
  if (r) {
    const pad = 6;
    Object.assign(spot.style, { top: r.top - pad + "px", left: r.left - pad + "px", width: r.width + 2 * pad + "px", height: r.height + 2 * pad + "px" });
    if (el.closest("#sidebar") && vw - r.right - gap - m >= W) { left = r.right + gap; top = r.top + r.height / 2 - H / 2; }
    else if (vh - r.bottom - gap - m >= H) { left = r.left; top = r.bottom + gap; }
    else if (r.top - gap - m >= H) { left = r.left; top = r.top - gap - H; }
    else top = vh - H - m;
  }
  card.style.left = Math.max(m, Math.min(left, vw - W - m)) + "px";
  card.style.top = Math.max(m, Math.min(top, vh - H - m)) + "px";
}

$("tourBtn").onclick = startTour;

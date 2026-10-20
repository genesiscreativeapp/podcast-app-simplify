"""Orchestration complète d'un traitement, du lien YouTube au podcast sur R2."""
import json
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from .. import config, english, r2sync, storage
from ..db import AI_SERVER, AiUsage, Folder, Job, SessionLocal, job_ai, resolve_intro
from ..utils import Paused, Stopped, fmt_time
from . import audio, condense, steps
from .detect import detect_sermon
from .download import download
from .edit import edit_file, sentence_end, word_cuts
from .offtopic import find_offtopic
from .transcribe import transcribe_sampled, transcribe_words


class Reporter:
    """Écrit l'avancement dans la base (lu par l'interface toutes les quelques secondes)."""

    def __init__(self, job_id: int, ai_owner: str | None = None):
        self.job_id = job_id
        self.ai_owner = ai_owner  # à qui facturer les appels à l'IA (propriétaire de la clé, ou « @server »)
        self._last = 0.0

    def _update(self, **fields):
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            if job is None:
                return
            for k, v in fields.items():
                setattr(job, k, v)
            job.updated_at = datetime.utcnow()
            s.commit()

    def _flags(self) -> tuple[bool, bool]:
        with SessionLocal() as s:
            row = s.query(Job.stop_requested, Job.pause_requested).filter(Job.id == self.job_id).one_or_none()
        return (bool(row[0]), bool(row[1])) if row else (False, False)

    def stop_requested(self) -> bool:
        return self._flags()[0]

    def pause_requested(self) -> bool:
        return self._flags()[1]

    def check(self):
        """Interrompt le traitement si l'utilisateur l'a demandé (appelé à chaque étape et à chaque mise à jour d'avancement) :
        l'arrêt passe avant la pause."""
        stop, pause = self._flags()
        if stop:
            raise Stopped()
        if pause:
            raise Paused()

    def log(self, message: str):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n"
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            if job:
                job.log = (job.log or "") + line
                s.commit()

    def tokens(self, n_in: int, n_out: int):
        """Cumule les tokens de l'IA de ce traitement et les inscrit au registre des compteurs
        (l'interface les lit toutes les quelques secondes)."""
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            if job:
                job.tokens_in = (job.tokens_in or 0) + n_in
                job.tokens_out = (job.tokens_out or 0) + n_out
                s.add(AiUsage(username=self.ai_owner or "@server", author=job.created_by, job_id=job.id,
                              tokens_in=n_in, tokens_out=n_out))
                s.commit()
        self.log(f"IA : {n_in} tokens en entrée, {n_out} en sortie")

    def step(self, key: str):
        """Démarre une étape : la barre globale se place au début de sa part."""
        label, lo, _hi = steps.BY_KEY[key]
        self.check()
        self.log(label)
        self._update(step=label, progress=lo)

    def sub(self, key: str, a: float = 0.0, b: float = 1.0):
        """Callback de progression (0 → 1) pour la tranche [a, b] d'une étape (1 écriture / seconde)."""
        _label, lo, hi = steps.BY_KEY[key]

        def cb(frac: float):
            now = time.monotonic()
            if now - self._last > 1:
                self._last = now
                self.check()
                self._update(progress=lo + (hi - lo) * (a + (b - a) * min(max(frac, 0.0), 1.0)))
        return cb


def _save(path: Path, data) -> None:
    """Point de reprise : écrit en entier ou pas du tout (un arrêt brutal ne laisse jamais un fichier à moitié écrit)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


MIN_SENTENCES = 20  # en dessous, le texte est trop court pour juger de ce qui est redondant


def _analyse(rep: Reporter, work: Path, jb, llm: dict | None):
    """Du téléchargement au retrait des témoignages et annonces.
    → (audio nettoyé, mots horodatés, coupes déjà décidées en secondes, bilan du retrait)."""
    use_ai = llm is not None
    # 1-2. Téléchargement de l'audio seul (réutilisé tel quel lors d'un « Relancer »)
    cache = config.CACHE_DIR / str(rep.job_id)
    cached = [p for p in cache.glob("source.*") if p.suffix not in (".part", ".ytdl")]
    if (cache / "ok").exists() and cached:
        src, video_title = cached[0], jb.known_title
        cache.touch()  # le garde parmi les plus récents lors du nettoyage du cache
        rep.log("Fichier envoyé par l'utilisateur" if jb.url.startswith(config.UPLOAD_SCHEME)
                else "Audio YouTube déjà en cache, téléchargement évité")
    elif jb.url.startswith(config.UPLOAD_SCHEME):
        raise RuntimeError("Le fichier envoyé n'est plus conservé sur le serveur : renvoyez-le pour relancer le traitement.")
    else:
        rep.step("download")
        shutil.rmtree(cache, ignore_errors=True)
        cache.mkdir(parents=True)
        src, video_title = download(jb.url, cache, rep.sub("download"))
        (cache / "ok").touch()
    duration = audio.probe_duration(src)
    rep._update(video_title=video_title, duration_source=duration)
    rep.log(f"Vidéo : {video_title} ({fmt_time(duration)})")

    # 3a. Repérage de la prédication (point de reprise : detect.json)
    ck = work / "detect.json"
    if ck.exists():
        saved = json.loads(ck.read_text())
        start, end, note = saved["start"], saved["end"], saved["note"]
        rep.log("Reprise : prédication déjà repérée")
    elif jb.start_ov is not None or jb.end_ov is not None:
        start = jb.start_ov or 0.0
        end = min(jb.end_ov or duration, duration)
        note = "Bornes saisies manuellement"
    else:
        rep.step("detect")
        rep.log(f"Modèle {config.WHISPER_MODEL_DETECT}, {config.WHISPER_WORKERS} transcription(s) en parallèle")
        wav16 = work / "full16k.wav"
        audio.to_whisper(src, wav16, duration, rep.sub("detect", 0.0, 0.1))
        segs = transcribe_sampled(wav16, duration, rep.sub("detect", 0.1, 1.0), work / "detect_batches")
        wav16.unlink(missing_ok=True)
        if not use_ai:
            rep.log("IA désactivée ou non configurée : repérage par heuristique")
        elif llm["owner"] != AI_SERVER:
            rep.log(f"IA : clé Anthropic personnelle de « {llm['owner']} »" + (" (choisie par un administrateur)" if jb.ai_chosen else ""))
        start, end, note = detect_sermon(segs, duration, video_title or jb.title, rep.log, llm, rep.tokens)
    if end - start < 30:
        raise RuntimeError(f"Prédication trop courte détectée ({start:.0f}s → {end:.0f}s)")
    _save(ck, {"start": start, "end": end, "note": note})
    rep._update(sermon_start=start, sermon_end=end, detection_note=note)
    rep.log(f"Prédication : {fmt_time(start)} → {fmt_time(end)} — {note}")

    # Marge autour d'une prédication repérée automatiquement : l'IA retirera ensuite précisément
    # l'adoration qui précède et les annonces qui suivent (sans IA, pas de marge)
    offtopic_on = config.REMOVE_OFFTOPIC and use_ai
    auto = jb.start_ov is None and jb.end_ov is None
    pad_b = min(config.OFFTOPIC_PAD_BEFORE, start) if offtopic_on and auto else 0.0
    # sans IA : petite marge seulement, pour pouvoir finir sur une fin de phrase plutôt qu'en plein mot
    pad_a = min(config.OFFTOPIC_PAD_AFTER if offtopic_on else config.END_MARGIN, duration - end) if auto else 0.0
    win_start, win_end = start - pad_b, end + pad_a

    # 3b. Extraction + amélioration de la voix (un seul passage ffmpeg)
    clean = work / "clean.wav"
    clean16 = work / "clean16k.wav"
    if (work / "voice.ok").exists() and clean.exists():
        rep.log("Reprise : voix déjà extraite")
    else:
        rep.step("voice")
        audio.extract_enhanced(src, win_start, win_end, clean, clean16, rep.sub("voice"))
        (work / "voice.ok").touch()

    # 3c. Transcription fine mot à mot (sur la prédication uniquement, lots en parallèle)
    wj = work / "words.json"
    if wj.exists():
        segs = json.loads(wj.read_text())
        rep.log("Reprise : transcription mot à mot déjà faite")
    else:
        rep.step("words")
        rep.log(f"Modèle {config.WHISPER_MODEL_EDIT}, {config.WHISPER_WORKERS} transcription(s) en parallèle")
        segs = transcribe_words(clean16, win_end - win_start, rep.sub("words"), work / "words_batches")
        _save(wj, segs)
    clean16.unlink(missing_ok=True)
    words = [w for s in segs for w in s["words"]]
    total = win_end - win_start
    tail_cut = []  # fin repérée recalée sur une fin de phrase ; ce qui suit est retiré
    if pad_a:
        cut_at = sentence_end(words, total - pad_a, pad_a)
        tail_cut = [(cut_at, total)]

    # 3c'. Retrait des témoignages, annonces, chants... (IA)
    extra_cuts, offtopic_note = [], ""
    oj = work / "offtopic.json"
    if oj.exists():
        saved = json.loads(oj.read_text())
        extra_cuts, offtopic_note = [tuple(c) for c in saved["extra_cuts"]], saved["note"]
        rep.log("Reprise : témoignages et annonces déjà traités")
    elif offtopic_on:
        rep.step("clean")
        extra_cuts, offtopic_note, ok = find_offtopic(segs, rep.log, llm, rep.tokens)
        if not ok and (pad_b or pad_a):
            # l'IA n'a pas répondu : on revient exactement aux bornes repérées, sans la marge
            extra_cuts = [(0.0, pad_b), *(tail_cut or [(total - pad_a, total)])]
            offtopic_note = "IA indisponible : marge retirée, adoration et annonces éventuelles conservées"
            rep.log(offtopic_note)
        elif offtopic_note:
            rep.log(offtopic_note)
    else:
        extra_cuts = tail_cut
        rep.log("Pas d'IA : témoignages et annonces non retirés")
    _save(oj, {"extra_cuts": extra_cuts, "note": offtopic_note})
    return clean, words, extra_cuts, offtopic_note


def _final_text(words: list[dict], cuts: list[tuple[float, float]]) -> list[str]:
    """Texte final du podcast, phrase par phrase : les mots qui ne sont pas dans une coupe (témoignages, condensation, « euh », redites).
    Il sert de base à la version anglaise : on ne traduit que ce qui est réellement dit dans le podcast."""
    kept = [w for w in words if not any(a <= (w["start"] + w["end"]) / 2 <= b for a, b in cuts)]
    return [s["text"] for s in condense.build_sentences(kept)]


def _condense(rep: Reporter, jb, words, extra_cuts, llm: dict | None) -> dict | None:
    """Propose les phrases à retirer (avec ou sans IA). → la relecture {phrases, coupes proposées…}, ou None si le texte est trop court."""
    rep.step("condense")
    sents = condense.build_sentences(words, extra_cuts)
    if len(sents) < MIN_SENTENCES:
        rep.log("Condensation : texte trop court pour juger de ce qui est redondant, rien n'est retiré")
        return None
    prop = condense.propose(sents, jb.pct, llm, rep.log, rep.tokens)
    rep.log(f"Condensation visée : −{jb.pct} % ({fmt_time(prop['target_s'])}) ; proposé : {len(prop['removed'])} phrase(s), "
            f"{fmt_time(prop['saved_s'])} soit −{100 * prop['saved_s'] / max(prop['total_s'], 1):.0f} % — {prop['method']} ; idées conservées : {100 * prop['coverage']:.0f} %")
    return {"pct": jb.pct, "method": prop["method"], "target_s": prop["target_s"], "total_s": prop["total_s"], "saved_s": prop["saved_s"],
            "coverage": prop["coverage"], "key_points": prop["key_points"], "sentences": sents,
            "removed": [{"id": i, **r} for i, r in prop["removed"].items()], "chosen": list(prop["removed"])}


def run_job(job_id: int) -> None:
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        folder = s.get(Folder, job.folder_id)
        intro = resolve_intro(s, folder, job.intro_id)
        # Décidé au démarrage : le traitement va au bout avec cette IA. Couper l'IA ensuite ne vaut que pour les traitements suivants.
        llm = job_ai(s, job)
        jb = SimpleNamespace(url=job.youtube_url, title=job.title, known_title=job.video_title, ai_chosen=job.ai_user,
                             start_ov=job.start_override, end_ov=job.end_override, pct=job.condense_pct or 0,
                             mode=job.condense_mode or "auto", review_ok=bool(job.review_ok), review_json=job.review_json,
                             english_mode=job.english_mode or "", english_translator=job.english_translator or "")
        date = job.date

    rep = Reporter(job_id, llm and llm["owner"])
    work = config.WORK_DIR / str(job_id)
    # Le travail déjà fait (pause, validation des coupes, redémarrage du serveur) est dans `work` et se reprend là où il s'est arrêté ;
    # « Relancer » et la création vident ce dossier : un dossier vide est donc un nouveau passage
    work.mkdir(parents=True, exist_ok=True)
    if not any(work.iterdir()):
        # consommation de CE passage (un « Relancer » repart de zéro ; le journal garde l'historique)
        rep._update(tokens_in=0, tokens_out=0, review_json=None, review_ok=False)
        jb.review_ok, jb.review_json = False, None
    analysis = work / "analysis.json"
    resume = analysis.exists() and (work / "clean.wav").exists()  # analyse terminée : on reprend après la condensation
    t0 = time.monotonic()
    paused = False

    try:
        if resume:
            saved = json.loads(analysis.read_text())
            words, offtopic_note = saved["words"], saved["offtopic_note"]
            extra_cuts = [tuple(c) for c in saved["extra_cuts"]]
            clean = work / "clean.wav"
            rep.log("Reprise après validation des coupes" if jb.review_ok else "Reprise : analyse déjà faite")
        else:
            clean, words, extra_cuts, offtopic_note = _analyse(rep, work, jb, llm)
            _save(analysis, {"words": words, "extra_cuts": extra_cuts, "offtopic_note": offtopic_note})
        if resume and jb.review_json:  # coupes déjà proposées (et validées si l'utilisateur devait le faire)
            review = json.loads(jb.review_json)
        else:
            review = _condense(rep, jb, words, extra_cuts, llm) if jb.pct else None
            if review and jb.mode == "review" and review["removed"]:
                # validation humaine : on garde l'audio nettoyé et l'analyse, le traitement s'arrête ici sans occuper de place
                rep._update(status="review", step="À valider : coupes proposées", progress=steps.BY_KEY["condense"][2],
                            review_json=json.dumps(review), review_ok=False)
                rep.log("En attente de la validation des coupes proposées")
                paused = True
                return

        cond_cuts, cond_note = [], ""
        if review:  # coupes de condensation : toutes celles proposées (automatique) ou celles que l'utilisateur a gardées
            cond_cuts = condense.cuts_for(review["sentences"], review["chosen"])
            cond_note = (f"condensation : {len(cond_cuts)} phrase(s) retirée(s), {fmt_time(sum(b - a for a, b in cond_cuts))} "
                         f"({review['method']}" + (", validée" if jb.review_ok else "") + ")")
            rep._update(review_json=json.dumps(review))

        # 3d. Montage : silences, « euh », répétitions
        rep.step("edit")
        edited = work / "edited.wav"
        stats = edit_file(clean, edited, words, config.MAX_PAUSE, config.TARGET_PAUSE,
                          config.REMOVE_FILLERS, config.REMOVE_REPEATS, extra_cuts + cond_cuts,
                          config.REPEAT_MAX_GAP, config.REPEAT_MAX_WORDS,
                          config.REMOVE_REACTIONS, config.AMBIENT_ATTEN_DB)
        examples = " ; ".join(f"« {e} »" for e in stats["examples"][:5])
        note = [f"{stats['pauses']} silences raccourcis", f"{stats['fillers']} hésitations retirées",
                f"{stats['repeats']} répétitions retirées" + (f" (ex. : {examples})" if examples else "")]
        if stats["reactions"]:
            note.append(f"{stats['reactions']} réaction(s) du public retirée(s)")
        if offtopic_note:
            note.append(offtopic_note)
        if cond_note:
            note.append(cond_note)
        note.append(f"durée {fmt_time(stats['before'])} → {fmt_time(stats['after'])}")
        rep.log("Montage : " + " · ".join(note))
        rep._update(edit_note="\n".join(note))

        w_cuts, _ = word_cuts(words, config.REMOVE_FILLERS, config.REMOVE_REPEATS, config.REPEAT_MAX_GAP, config.REPEAT_MAX_WORDS)
        rep._update(transcript_json=json.dumps(_final_text(words, w_cuts + stats["reaction_cuts"] + extra_cuts + cond_cuts), ensure_ascii=False))

        # 4. Intro + normalisation du volume
        rep.step("master")
        master = work / "master.wav"
        intro_path = Path(intro[0]) if intro else None
        rep.log(f"Intro : {intro[1]}" if intro else "Aucune intro : podcast sans intro")
        audio.finalize(edited, master, intro_path, on_progress=rep.sub("master"))

        # 6. Compression — le nom a pu être modifié pendant le traitement : on relit celui de la base
        rep.step("encode")
        with SessionLocal() as s2:
            cur = s2.get(Job, job_id)
            title, filename = cur.title, cur.filename
        out_dir = config.OUTPUT_DIR / str(job_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "original.mp3").unlink(missing_ok=True)  # copie d'avant un ancien rognage
        mp3 = out_dir / f"{filename}.mp3"
        audio.encode_mp3(master, mp3, config.MP3_BITRATE, title, config.PODCAST_ARTIST, date,
                         audio.probe_duration(master), rep.sub("encode"))
        rep._update(local_mp3=str(mp3), size_mp3=mp3.stat().st_size,
                    duration_output=audio.probe_duration(mp3))

        # 5. Envoi vers R2
        if storage.enabled():
            rep.step("upload")
            with SessionLocal() as s2:
                key = r2sync.desired_key(s2, s2.get(Job, job_id))
            size, sent, upload_cb = max(mp3.stat().st_size, 1), [0], rep.sub("upload")

            def on_bytes(n):  # appelé depuis les threads de boto3
                sent[0] += n
                upload_cb(sent[0] / size)

            storage.upload(mp3, key, "audio/mpeg", on_bytes)
            rep._update(r2_key_mp3=key)
            rep.log(f"Envoyé sur R2 : {key}")
        else:
            rep.log("R2 non configuré : fichiers conservés uniquement sur le serveur")

        elapsed = time.monotonic() - t0
        rep.log(f"Terminé en {fmt_time(elapsed)} — {mp3.stat().st_size / 1e6:.1f} Mo (MP3)")
        rep._update(status="done", step="Terminé", progress=1.0, error=None, review_ok=False,
                    finished_at=datetime.utcnow())
        if jb.english_mode:  # version anglaise demandée avec le traitement : elle part en file, le service de voix la calculera
            try:
                with SessionLocal() as s2:
                    english.queue(s2, s2.get(Job, job_id), jb.english_mode, s2.get(Job, job_id).created_by, jb.english_translator or None)
                rep.log("Version anglaise mise en file d'attente")
            except Exception:  # le podcast français est terminé : un échec ici ne doit pas le marquer en erreur
                rep.log("Version anglaise non mise en file : " + traceback.format_exc().splitlines()[-1])
    except Exception as exc:
        if isinstance(exc, Stopped) or rep.stop_requested():  # yt-dlp ou un autre module peut avoir enveloppé l'exception
            rep.log("Arrêté à la demande de l'utilisateur")
            rep._update(status="error", step="Arrêté", error="Arrêté par l'utilisateur", review_ok=False,
                        finished_at=datetime.utcnow())
        elif isinstance(exc, Paused) or rep.pause_requested():
            rep.log("Mis en pause à la demande de l'utilisateur : le travail déjà fait est gardé")
            rep._update(status="paused", step="En pause")  # la progression reste celle du moment de la pause
            paused = True
        else:
            rep.log("ERREUR\n" + traceback.format_exc())
            rep._update(status="error", step="Erreur", error=str(exc)[:2000], review_ok=False,
                        finished_at=datetime.utcnow())
    finally:
        if not config.KEEP_WORK_FILES and not paused:
            shutil.rmtree(work, ignore_errors=True)
        _prune_cache()


def _prune_cache() -> None:
    """Ne garde que les audios YouTube des derniers traitements (ils pèsent 100 à 250 Mo).
    Ne touche jamais à celui d'un traitement en cours (plusieurs tournent en parallèle)."""
    with SessionLocal() as s:
        busy = {str(i) for (i,) in s.query(Job.id).filter(
            Job.status.in_(["running", "paused"]) | ((Job.status == "pending") & Job.youtube_url.startswith(config.UPLOAD_SCHEME)))}
    dirs = sorted((d for d in config.CACHE_DIR.iterdir() if d.is_dir() and d.name not in busy),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    for d in dirs[config.KEEP_SOURCES:]:
        shutil.rmtree(d, ignore_errors=True)

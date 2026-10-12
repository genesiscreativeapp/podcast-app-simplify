"""Orchestration complète d'un traitement, du lien YouTube au podcast sur R2."""
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path

from .. import config, r2sync, storage
from ..db import Folder, Job, SessionLocal, ai_enabled, resolve_intro
from ..utils import fmt_time
from . import audio, steps
from .detect import detect_sermon
from .download import download
from .edit import edit_file, sentence_end
from .offtopic import find_offtopic
from .transcribe import transcribe_sampled, transcribe_words


class Reporter:
    """Écrit l'avancement dans la base (lu par l'interface toutes les quelques secondes)."""

    def __init__(self, job_id: int):
        self.job_id = job_id
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

    def log(self, message: str):
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n"
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            if job:
                job.log = (job.log or "") + line
                s.commit()

    def step(self, key: str):
        """Démarre une étape : la barre globale se place au début de sa part."""
        label, lo, _hi = steps.BY_KEY[key]
        self.log(label)
        self._update(step=label, progress=lo)

    def sub(self, key: str, a: float = 0.0, b: float = 1.0):
        """Callback de progression (0 → 1) pour la tranche [a, b] d'une étape (1 écriture / seconde)."""
        _label, lo, hi = steps.BY_KEY[key]

        def cb(frac: float):
            now = time.monotonic()
            if now - self._last > 1:
                self._last = now
                self._update(progress=lo + (hi - lo) * (a + (b - a) * min(max(frac, 0.0), 1.0)))
        return cb


def run_job(job_id: int) -> None:
    rep = Reporter(job_id)
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        folder = s.get(Folder, job.folder_id)
        intro = resolve_intro(s, folder, job.intro_id)
        use_ai = ai_enabled(s)  # décidé au démarrage : tout le traitement suit le même choix
        url, title, date, filename = job.youtube_url, job.title, job.date, job.filename
        known_title = job.video_title
        start_ov, end_ov = job.start_override, job.end_override

    work = config.WORK_DIR / str(job_id)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    t0 = time.monotonic()

    try:
        # 1-2. Téléchargement de l'audio seul (réutilisé tel quel lors d'un « Relancer »)
        cache = config.CACHE_DIR / str(job_id)
        cached = [p for p in cache.glob("source.*") if p.suffix not in (".part", ".ytdl")]
        if (cache / "ok").exists() and cached:
            src, video_title = cached[0], known_title
            cache.touch()  # le garde parmi les plus récents lors du nettoyage du cache
            rep.log("Fichier envoyé par l'utilisateur" if url.startswith(config.UPLOAD_SCHEME)
                    else "Audio YouTube déjà en cache, téléchargement évité")
        elif url.startswith(config.UPLOAD_SCHEME):
            raise RuntimeError("Le fichier envoyé n'est plus conservé sur le serveur : renvoyez-le pour relancer le traitement.")
        else:
            rep.step("download")
            shutil.rmtree(cache, ignore_errors=True)
            cache.mkdir(parents=True)
            src, video_title = download(url, cache, rep.sub("download"))
            (cache / "ok").touch()
        duration = audio.probe_duration(src)
        rep._update(video_title=video_title, duration_source=duration)
        rep.log(f"Vidéo : {video_title} ({fmt_time(duration)})")

        # 3a. Repérage de la prédication
        if start_ov is not None or end_ov is not None:
            start = start_ov or 0.0
            end = min(end_ov or duration, duration)
            note = "Bornes saisies manuellement"
        else:
            rep.step("detect")
            rep.log(f"Modèle {config.WHISPER_MODEL_DETECT}, {config.WHISPER_WORKERS} transcription(s) en parallèle")
            wav16 = work / "full16k.wav"
            audio.to_whisper(src, wav16, duration, rep.sub("detect", 0.0, 0.1))
            segs = transcribe_sampled(wav16, duration, rep.sub("detect", 0.1, 1.0))
            wav16.unlink(missing_ok=True)
            if config.LLM_PROVIDER in ("anthropic", "openai") and not use_ai:
                rep.log("IA désactivée par l'administrateur : repérage par heuristique")
            start, end, note = detect_sermon(segs, duration, video_title or title, rep.log, use_ai)
        if end - start < 30:
            raise RuntimeError(f"Prédication trop courte détectée ({start:.0f}s → {end:.0f}s)")
        rep._update(sermon_start=start, sermon_end=end, detection_note=note)
        rep.log(f"Prédication : {fmt_time(start)} → {fmt_time(end)} — {note}")

        # Marge autour d'une prédication repérée automatiquement : l'IA retirera ensuite précisément
        # l'adoration qui précède et les annonces qui suivent (sans IA, pas de marge)
        offtopic_on = config.REMOVE_OFFTOPIC and use_ai
        auto = start_ov is None and end_ov is None
        pad_b = min(config.OFFTOPIC_PAD_BEFORE, start) if offtopic_on and auto else 0.0
        # sans IA : petite marge seulement, pour pouvoir finir sur une fin de phrase plutôt qu'en plein mot
        pad_a = min(config.OFFTOPIC_PAD_AFTER if offtopic_on else config.END_MARGIN, duration - end) if auto else 0.0
        win_start, win_end = start - pad_b, end + pad_a

        # 3b. Extraction + amélioration de la voix (un seul passage ffmpeg)
        rep.step("voice")
        clean = work / "clean.wav"
        clean16 = work / "clean16k.wav"
        audio.extract_enhanced(src, win_start, win_end, clean, clean16, rep.sub("voice"))

        # 3c. Transcription fine mot à mot (sur la prédication uniquement, lots en parallèle)
        rep.step("words")
        rep.log(f"Modèle {config.WHISPER_MODEL_EDIT}, {config.WHISPER_WORKERS} transcription(s) en parallèle")
        segs = transcribe_words(clean16, win_end - win_start, rep.sub("words"))
        clean16.unlink(missing_ok=True)
        words = [w for s in segs for w in s["words"]]
        total = win_end - win_start
        tail_cut = []  # fin repérée recalée sur une fin de phrase ; ce qui suit est retiré
        if pad_a:
            cut_at = sentence_end(words, total - pad_a, pad_a)
            tail_cut = [(cut_at, total)]

        # 3c'. Retrait des témoignages, annonces, chants... (IA)
        extra_cuts, offtopic_note = [], ""
        if offtopic_on:
            rep.step("clean")
            extra_cuts, offtopic_note, ok = find_offtopic(segs, rep.log)
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

        # 3d. Montage : silences, « euh », répétitions
        rep.step("edit")
        edited = work / "edited.wav"
        stats = edit_file(clean, edited, words, config.MAX_PAUSE, config.TARGET_PAUSE,
                          config.REMOVE_FILLERS, config.REMOVE_REPEATS, extra_cuts,
                          config.REPEAT_MAX_GAP, config.REPEAT_MAX_WORDS)
        examples = " ; ".join(f"« {e} »" for e in stats["examples"][:5])
        note = [f"{stats['pauses']} silences raccourcis", f"{stats['fillers']} hésitations retirées",
                f"{stats['repeats']} répétitions retirées" + (f" (ex. : {examples})" if examples else "")]
        if offtopic_note:
            note.append(offtopic_note)
        note.append(f"durée {fmt_time(stats['before'])} → {fmt_time(stats['after'])}")
        rep.log("Montage : " + " · ".join(note))
        rep._update(edit_note="\n".join(note))

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
        rep._update(status="done", step="Terminé", progress=1.0, error=None,
                    finished_at=datetime.utcnow())
    except Exception as exc:
        rep.log("ERREUR\n" + traceback.format_exc())
        rep._update(status="error", step="Erreur", error=str(exc)[:2000],
                    finished_at=datetime.utcnow())
    finally:
        if not config.KEEP_WORK_FILES:
            shutil.rmtree(work, ignore_errors=True)
        _prune_cache()


def _prune_cache() -> None:
    """Ne garde que les audios YouTube des derniers traitements (ils pèsent 100 à 250 Mo).
    Ne touche jamais à celui d'un traitement en cours (plusieurs tournent en parallèle)."""
    with SessionLocal() as s:
        busy = {str(i) for (i,) in s.query(Job.id).filter(
            (Job.status == "running") | ((Job.status == "pending") & Job.youtube_url.startswith(config.UPLOAD_SCHEME)))}
    dirs = sorted((d for d in config.CACHE_DIR.iterdir() if d.is_dir() and d.name not in busy),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    for d in dirs[config.KEEP_SOURCES:]:
        shutil.rmtree(d, ignore_errors=True)

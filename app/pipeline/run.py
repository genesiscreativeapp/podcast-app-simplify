"""Orchestration complète d'un traitement, du lien YouTube au podcast sur R2."""
import shutil
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from .. import config, storage
from ..db import Folder, Job, SessionLocal, folder_path, resolve_intro
from ..utils import fmt_time
from . import audio
from .detect import detect_sermon
from .download import download
from .edit import edit_file
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

    def step(self, name: str, progress: float):
        self.log(name)
        self._update(step=name, progress=progress)

    def sub(self, lo: float, hi: float):
        """Callback de progression pour une sous-étape (limité à 1 écriture / 2 s)."""
        def cb(frac: float):
            now = time.monotonic()
            if now - self._last > 2:
                self._last = now
                self._update(progress=lo + (hi - lo) * frac)
        return cb


def run_job(job_id: int) -> None:
    rep = Reporter(job_id)
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        folder = s.get(Folder, job.folder_id)
        names = folder_path(s, folder) if folder else []
        intro = resolve_intro(s, folder)
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
            rep.log("Audio YouTube déjà en cache, téléchargement évité")
        else:
            rep.step("Téléchargement depuis YouTube", 0.01)
            shutil.rmtree(cache, ignore_errors=True)
            cache.mkdir(parents=True)
            src, video_title = download(url, cache, rep.sub(0.01, 0.10))
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
            rep.step(f"Repérage de la prédication (modèle {config.WHISPER_MODEL_DETECT}, "
                     f"{config.WHISPER_WORKERS} en parallèle)", 0.10)
            wav16 = work / "full16k.wav"
            audio.to_whisper(src, wav16)
            segs = transcribe_sampled(wav16, duration, rep.sub(0.12, 0.40))
            wav16.unlink(missing_ok=True)
            start, end, note = detect_sermon(segs, duration, video_title or title, rep.log)
        if end - start < 30:
            raise RuntimeError(f"Prédication trop courte détectée ({start:.0f}s → {end:.0f}s)")
        rep._update(sermon_start=start, sermon_end=end, detection_note=note)
        rep.log(f"Prédication : {fmt_time(start)} → {fmt_time(end)} — {note}")

        # 3b. Extraction + amélioration de la voix (un seul passage ffmpeg)
        rep.step("Extraction et amélioration de la voix", 0.41)
        clean = work / "clean.wav"
        clean16 = work / "clean16k.wav"
        audio.extract_enhanced(src, start, end, clean, clean16)

        # 3c. Transcription fine mot à mot (sur la prédication uniquement, lots en parallèle)
        rep.step(f"Transcription mot à mot (modèle {config.WHISPER_MODEL_EDIT})", 0.45)
        segs = transcribe_words(clean16, end - start, rep.sub(0.45, 0.85))
        clean16.unlink(missing_ok=True)
        words = [w for s in segs for w in s["words"]]

        # 3d. Montage : silences, « euh », répétitions
        rep.step("Nettoyage : silences, hésitations, répétitions", 0.86)
        edited = work / "edited.wav"
        stats = edit_file(clean, edited, words, config.MAX_PAUSE, config.TARGET_PAUSE,
                          config.REMOVE_FILLERS, config.REMOVE_REPEATS)
        rep.log(f"{stats['pauses']} silences raccourcis, {stats['fillers']} hésitations et "
                f"{stats['repeats']} répétitions retirées : {fmt_time(stats['before'])} → {fmt_time(stats['after'])}")

        # 4. Intro + normalisation du volume
        rep.step("Ajout de l'intro et normalisation du volume", 0.90)
        master = work / "master.wav"
        intro_path = Path(intro) if intro and Path(intro).exists() else None
        if not intro_path:
            rep.log("Aucune intro configurée : podcast sans intro")
        audio.finalize(edited, master, intro_path)

        # 6. Compression
        rep.step("Compression pour WhatsApp / Telegram", 0.94)
        out_dir = config.OUTPUT_DIR / str(job_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        ogg = out_dir / f"{filename}.ogg"
        mp3 = out_dir / f"{filename}.mp3" if config.MAKE_MP3 else None
        with ThreadPoolExecutor(2) as ex:  # ffmpeg est mono-thread par encodage : on les lance ensemble
            jobs = [ex.submit(audio.encode_opus, master, ogg, config.OPUS_BITRATE,
                              title, config.PODCAST_ARTIST, date)]
            if mp3:
                jobs.append(ex.submit(audio.encode_mp3, master, mp3, config.MP3_BITRATE,
                                      title, config.PODCAST_ARTIST, date))
            for j in jobs:
                j.result()
        out_duration = audio.probe_duration(ogg)
        rep._update(local_ogg=str(ogg), size_ogg=ogg.stat().st_size,
                    local_mp3=str(mp3) if mp3 else None,
                    size_mp3=mp3.stat().st_size if mp3 else None,
                    duration_output=out_duration)

        # 5. Envoi vers R2
        if storage.enabled():
            rep.step("Envoi vers Cloudflare R2", 0.97)
            key_ogg = storage.build_key(names, ogg.name)
            key_mp3 = storage.build_key(names, mp3.name) if mp3 else None
            with ThreadPoolExecutor(2) as ex:
                ups = [ex.submit(storage.upload, ogg, key_ogg, "audio/ogg")]
                if mp3:
                    ups.append(ex.submit(storage.upload, mp3, key_mp3, "audio/mpeg"))
                for u in ups:
                    u.result()
            rep._update(r2_key_ogg=key_ogg, r2_key_mp3=key_mp3)
            rep.log(f"Envoyé sur R2 : {key_ogg}")
        else:
            rep.log("R2 non configuré : fichiers conservés uniquement sur le serveur")

        elapsed = time.monotonic() - t0
        rep.log(f"Terminé en {fmt_time(elapsed)} — {ogg.stat().st_size / 1e6:.1f} Mo (OGG)")
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
    """Ne garde que les audios YouTube des derniers traitements (ils pèsent 100 à 250 Mo)."""
    dirs = sorted((d for d in config.CACHE_DIR.iterdir() if d.is_dir()),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    for d in dirs[config.KEEP_SOURCES:]:
        shutil.rmtree(d, ignore_errors=True)

"""Miroir de l'arborescence de la plateforme sur R2.

Chemin d'un podcast sur R2 :  <R2_PREFIX>/<dossier>/<sous-dossier>/<Nom du podcast>_<AAAA-MM-JJ>.mp3
avec les mêmes noms que dans l'interface (seuls les caractères interdits ou ambigus sont remplacés).
Renommer ou déplacer un dossier ou un podcast déplace les objets sur R2 ; `reconcile` calcule le chemin
voulu de chaque podcast et déplace tout ce qui n'est pas au bon endroit. Il rattrape aussi les podcasts
qui n'ont jamais été envoyés (R2 configuré après coup) et crée les dossiers vides.
Il tourne en arrière-plan (un renommage de dossier peut toucher des centaines de fichiers).
"""
import logging
import re
import threading
from datetime import datetime

from . import config, storage
from .db import EnVersion, Folder, Job, R2Marker, SessionLocal, folder_path

log = logging.getLogger("r2sync")
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize(name: str) -> str:
    """Nom sûr pour une clé S3 : on garde accents et espaces, on retire « / » et autres caractères ambigus."""
    n = re.sub(r"\s+", " ", _BAD.sub(" ", name or "")).strip(" .")
    return n or "sans-nom"


def _prefix() -> list[str]:
    return [config.R2_PREFIX] if config.R2_PREFIX else []


def folder_prefix(s, folder: Folder | None) -> str:
    names = [sanitize(n) for n in folder_path(s, folder)] if folder else []
    return "/".join(_prefix() + names)


def display_filename(job: Job) -> str:
    return f"{sanitize(job.title)}_{job.date}.mp3"


def display_filename_en(job: Job) -> str:
    """Nom du MP3 anglais : celui du podcast français, suffixé _EN."""
    return f"{sanitize(job.title)}_{job.date}_EN.mp3"


def desired_key_en(s, job: Job, taken: set[str] | None = None) -> str:
    """Chemin voulu de la version anglaise : dans le même dossier que le podcast français, sans écraser un autre fichier."""
    if taken is None:
        taken = {k for (k,) in s.query(Job.r2_key_mp3).filter(Job.r2_key_mp3.isnot(None))}
        taken |= {k for (k,) in s.query(EnVersion.r2_key_mp3).filter(EnVersion.r2_key_mp3.isnot(None), EnVersion.job_id != job.id)}
    folder = s.get(Folder, job.folder_id)
    return _unique(f"{folder_prefix(s, folder)}/{display_filename_en(job)}".lstrip("/"), taken)


def _unique(candidate: str, taken: set[str]) -> str:
    if candidate not in taken:
        return candidate
    stem = candidate[:-4]
    n = 2
    while f"{stem} ({n}).mp3" in taken:
        n += 1
    return f"{stem} ({n}).mp3"


def desired_key(s, job: Job, taken: set[str] | None = None) -> str:
    """Chemin voulu de ce podcast, sans écraser le fichier d'un autre podcast."""
    if taken is None:
        taken = {k for (k,) in s.query(Job.r2_key_mp3).filter(Job.r2_key_mp3.isnot(None), Job.id != job.id)}
    folder = s.get(Folder, job.folder_id)
    return _unique(f"{folder_prefix(s, folder)}/{display_filename(job)}".lstrip("/"), taken)


def reconcile(s) -> dict:
    """Met R2 en conformité avec la plateforme. Idempotent : ne touche que ce qui n'est pas au bon endroit."""
    report = {"moved": 0, "uploaded": 0, "markers": 0, "failed": []}
    jobs = s.query(Job).filter(Job.status == "done", Job.local_mp3.isnot(None), Job.deleted_at.is_(None)).order_by(Job.id).all()  # en corbeille : le fichier R2 reste tel quel
    current = {j.id: j.r2_key_mp3 for j in jobs if j.r2_key_mp3}
    for j in jobs:
        taken = {k for i, k in current.items() if i != j.id}
        target = desired_key(s, j, taken)
        try:
            if j.r2_key_mp3 and j.r2_key_mp3 != target:
                storage.move(j.r2_key_mp3, target)
                report["moved"] += 1
            elif not j.r2_key_mp3:
                from pathlib import Path
                if not Path(j.local_mp3).exists():
                    continue
                storage.upload(Path(j.local_mp3), target, "audio/mpeg")
                report["uploaded"] += 1
            else:
                continue
            j.r2_key_mp3 = target
            s.commit()
            current[j.id] = target
        except Exception as exc:
            s.rollback()
            report["failed"].append({"job": j.id, "title": j.title, "error": str(exc)[:240]})
    # versions anglaises : même mise en conformité (déplacement quand le dossier ou le nom change, envoi de ce qui manque)
    for en in s.query(EnVersion).filter(EnVersion.status == "done", EnVersion.local_mp3.isnot(None)).order_by(EnVersion.id).all():
        j = s.get(Job, en.job_id)
        if j is None or j.deleted_at is not None:
            continue
        try:
            target = desired_key_en(s, j)
            if en.r2_key_mp3 and en.r2_key_mp3 != target:
                storage.move(en.r2_key_mp3, target)
                report["moved"] += 1
            elif not en.r2_key_mp3:
                from pathlib import Path
                if not Path(en.local_mp3).exists():
                    continue
                storage.upload(Path(en.local_mp3), target, "audio/mpeg")
                report["uploaded"] += 1
            else:
                continue
            en.r2_key_mp3 = target
            s.commit()
        except Exception as exc:
            s.rollback()
            report["failed"].append({"job": j.id, "title": f"{j.title} (anglais)", "error": str(exc)[:240]})
    # dossiers (y compris vides) : un objet vide « chemin/ » par dossier
    try:
        desired = {folder_prefix(s, f) + "/" for f in s.query(Folder).filter(Folder.deleted_at.is_(None))}
        recorded = {m.key for m in s.query(R2Marker)}
        for key in desired - recorded:
            storage.put_marker(key)
            s.add(R2Marker(key=key))
            report["markers"] += 1
        stale = recorded - desired
        if stale:
            storage.delete(sorted(stale))
            s.query(R2Marker).filter(R2Marker.key.in_(stale)).delete(synchronize_session=False)
        s.commit()
    except Exception as exc:
        s.rollback()
        report["failed"].append({"job": None, "title": "Dossiers", "error": str(exc)[:240]})
    return report


# ---- exécution en arrière-plan
_lock = threading.Lock()
_state = {"running": False, "again": False, "last": None}


def trigger() -> None:
    """Lance (ou relance une fois de plus, si déjà en cours) la mise en conformité de R2. Sans effet sans R2."""
    if not storage.enabled():
        return
    with _lock:
        if _state["running"]:
            _state["again"] = True
            return
        _state["running"] = True
    threading.Thread(target=_loop, daemon=True, name="r2sync").start()


def _loop() -> None:
    while True:
        try:
            with SessionLocal() as s:
                report = reconcile(s)
        except Exception as exc:
            log.exception("Synchronisation R2")
            report = {"moved": 0, "uploaded": 0, "markers": 0, "failed": [{"job": None, "title": "R2", "error": str(exc)[:240]}]}
        with _lock:
            _state["last"] = {**report, "at": datetime.utcnow().isoformat() + "Z"}
            if not _state["again"]:
                _state["running"] = False
                return
            _state["again"] = False


def status() -> dict:
    with _lock:
        return {"enabled": storage.enabled(), "running": _state["running"], "last": _state["last"]}

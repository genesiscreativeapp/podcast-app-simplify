"""Worker : traite les liens en file d'attente, MAX_PARALLEL_JOBS à la fois (réglable dans l'interface)."""
import logging
import shutil
import signal
import time
from datetime import datetime, timedelta
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from . import config
from .db import MAX_PARALLEL_LIMIT, QUEUE_ORDER, Job, SessionLocal, User, get_max_parallel, init_db
from .pipeline.run import run_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("worker")
_stop = False


def _handle_stop(*_):
    global _stop
    _stop = True
    log.info("Arrêt demandé, fin après les traitements en cours…")


def claim_next() -> int | None:
    """Prend le plus ancien traitement en attente dont l'auteur n'a pas atteint son quota de traitements simultanés.
    Le UPDATE conditionnel évite qu'il soit pris deux fois."""
    with SessionLocal() as s:
        quota = dict(s.query(User.username, User.max_parallel).all())
        running = Counter(o for (o,) in s.query(Job.created_by).filter(Job.status == "running"))
        for job_id, owner in s.query(Job.id, Job.created_by).filter(Job.status == "pending", Job.deleted_at.is_(None)).order_by(*QUEUE_ORDER).all():
            if owner in quota and running[owner] >= (quota[owner] or 1):
                continue  # reste en file jusqu'à la fin d'un de ses traitements
            claimed = (s.query(Job).filter(Job.id == job_id, Job.status == "pending")
                       .update({"status": "running", "step": "Démarrage", "progress": 0.0, "stop_requested": False, "pause_requested": False}))
            s.commit()
            if claimed:
                return job_id
    return None


def expire_paused() -> int:
    """Abandonne les traitements en pause depuis plus de PAUSE_DAYS jours : leur travail gardé (des centaines de Mo) est supprimé."""
    limit = datetime.utcnow() - timedelta(days=config.PAUSE_DAYS)
    with SessionLocal() as s:
        old = s.query(Job).filter(Job.status == "paused", Job.updated_at < limit).all()
        for job in old:
            job.status, job.step, job.finished_at = "error", "Pause expirée", datetime.utcnow()
            job.error = f"En pause depuis plus de {config.PAUSE_DAYS} jours : relancez le traitement"
            shutil.rmtree(config.WORK_DIR / str(job.id), ignore_errors=True)
        s.commit()
        return len(old)


def _run(job_id: int) -> None:
    log.info("Traitement #%d démarré", job_id)
    try:
        run_job(job_id)
    except Exception:  # run_job gère ses erreurs ; ceci ne sert qu'à ne jamais tuer le worker
        log.exception("Traitement #%d : erreur inattendue", job_id)
    log.info("Traitement #%d fini", job_id)


def main():
    init_db()
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    # Un traitement interrompu (redémarrage du serveur) est relancé
    with SessionLocal() as s:
        s.query(Job).filter(Job.status == "running", Job.stop_requested).update(
            {"status": "error", "step": "Arrêté", "error": "Arrêté par l'utilisateur"})
        s.query(Job).filter(Job.status == "running", Job.pause_requested).update(
            {"status": "paused", "step": "En pause"})
        n = s.query(Job).filter(Job.status == "running").update(
            {"status": "pending", "step": "Relancé après redémarrage"})  # le travail déjà fait est gardé : le traitement reprend où il en était
        s.commit()
        if n:
            log.info("%d traitement(s) interrompu(s) remis en file", n)
    log.info("Worker prêt")
    running = set()
    last_expire = 0.0
    with ThreadPoolExecutor(MAX_PARALLEL_LIMIT) as pool:
        while not _stop:
            if time.monotonic() - last_expire > 3600:
                last_expire = time.monotonic()
                if n := expire_paused():
                    log.info("%d traitement(s) en pause abandonné(s) (plus de %d jours)", n, config.PAUSE_DAYS)
            running = {f for f in running if not f.done()}
            with SessionLocal() as s:
                limit = get_max_parallel(s)  # relu à chaque tour : le réglage de l'interface s'applique tout de suite
            while len(running) < limit:
                job_id = claim_next()
                if job_id is None:
                    break
                running.add(pool.submit(_run, job_id))
            time.sleep(2)


if __name__ == "__main__":
    main()

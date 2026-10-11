"""Worker : traite les liens en file d'attente, un par un (CPU)."""
import logging
import signal
import time

from .db import Job, SessionLocal, init_db
from .pipeline.run import run_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("worker")
_stop = False


def _handle_stop(*_):
    global _stop
    _stop = True
    log.info("Arrêt demandé, fin après le traitement en cours…")


def claim_next() -> int | None:
    with SessionLocal() as s:
        job = (s.query(Job).filter(Job.status == "pending")
               .order_by(Job.created_at, Job.id).first())
        if job is None:
            return None
        job.status, job.step, job.progress = "running", "Démarrage", 0.0
        s.commit()
        return job.id


def main():
    init_db()
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    # Un traitement interrompu (redémarrage du serveur) est relancé
    with SessionLocal() as s:
        n = s.query(Job).filter(Job.status == "running").update(
            {"status": "pending", "step": "Relancé après redémarrage"})
        s.commit()
        if n:
            log.info("%d traitement(s) interrompu(s) remis en file", n)
    log.info("Worker prêt")
    while not _stop:
        job_id = claim_next()
        if job_id is None:
            time.sleep(3)
            continue
        log.info("Traitement #%d", job_id)
        run_job(job_id)
        log.info("Traitement #%d fini", job_id)


if __name__ == "__main__":
    main()

"""Worker : traite les liens en file d'attente, MAX_PARALLEL_JOBS à la fois (réglable dans l'interface)."""
import logging
import signal
import time
from concurrent.futures import ThreadPoolExecutor

from .db import MAX_PARALLEL_LIMIT, QUEUE_ORDER, Job, SessionLocal, get_max_parallel, init_db
from .pipeline.run import run_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("worker")
_stop = False


def _handle_stop(*_):
    global _stop
    _stop = True
    log.info("Arrêt demandé, fin après les traitements en cours…")


def claim_next() -> int | None:
    """Prend le plus ancien traitement en attente. Le UPDATE conditionnel évite qu'il soit pris deux fois."""
    with SessionLocal() as s:
        for (job_id,) in s.query(Job.id).filter(Job.status == "pending").order_by(*QUEUE_ORDER).limit(5).all():
            claimed = (s.query(Job).filter(Job.id == job_id, Job.status == "pending")
                       .update({"status": "running", "step": "Démarrage", "progress": 0.0}))
            s.commit()
            if claimed:
                return job_id
    return None


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
        n = s.query(Job).filter(Job.status == "running").update(
            {"status": "pending", "step": "Relancé après redémarrage"})
        s.commit()
        if n:
            log.info("%d traitement(s) interrompu(s) remis en file", n)
    log.info("Worker prêt")
    running = set()
    with ThreadPoolExecutor(MAX_PARALLEL_LIMIT) as pool:
        while not _stop:
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

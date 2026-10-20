"""Arrêt d'une opération en cours : `python tests/test_stop.py` (ou pytest). Aucun réseau, aucun modèle : l'arrêt est demandé avant la première étape."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.update(DATA_DIR=tempfile.mkdtemp(), APP_USER="admin", APP_PASSWORD="adminpass1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, english, voicelab, worker  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from app.db import EnVersion, Folder, Job, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.pipeline.run import run_job  # noqa: E402

admin, bob = TestClient(app), TestClient(app)


def ok(r, code=200):
    assert r.status_code == code, (r.request.method, r.request.url.path, r.status_code, r.text)
    return r.json()


ok(admin.post("/api/auth/login", json={"username": "admin", "password": "adminpass1"}))
ok(admin.post("/api/users", json={"username": "bob", "password": "bobpass123", "permissions": ["jobs.view", "jobs.create"]}))
ok(bob.post("/api/auth/login", json={"username": "bob", "password": "bobpass123"}))

mp3 = config.OUTPUT_DIR / "9" / "pod.mp3"
mp3.parent.mkdir(parents=True)
sf.write(str(mp3), np.zeros(8000), 8000, format="WAV")
with SessionLocal() as s:
    s.add(Folder(name="CULTE"))
    s.commit()
    mk = lambda i, status, **kw: Job(id=i, folder_id=1, youtube_url="https://youtube.com/watch?v=x", title=f"T{i}", date="2026-01-01", filename=f"f{i}", status=status, created_by="admin", **kw)  # noqa: E731
    s.add_all([mk(1, "pending"), mk(2, "running"), mk(3, "done"), mk(4, "review"), mk(5, "running", stop_requested=True), mk(6, "pending", stop_requested=True),
               mk(9, "done", local_mp3=str(mp3), transcript_json=json.dumps(["Une phrase.", "Une autre."]))])
    s.commit()
(config.WORK_DIR / "4").mkdir(parents=True)

# --- l'API : en attente ou à valider = arrêté tout de suite ; en cours = arrêt demandé ; terminé = refusé ; seul l'auteur (ou un admin) peut arrêter
j = ok(admin.post("/api/jobs/1/stop"))
assert j["status"] == "error" and j["step"] == "Arrêté" and j["error"] == "Arrêté par l'utilisateur" and "Arrêt demandé par admin" in ok(admin.get("/api/jobs/1"))["log"]
j = ok(admin.post("/api/jobs/2/stop"))
assert j["status"] == "running" and j["stopping"] is True
ok(admin.post("/api/jobs/3/stop"), 400)
ok(admin.post("/api/jobs/4/stop"))
assert not (config.WORK_DIR / "4").exists()                                  # le travail gardé pour la validation est supprimé
assert ok(admin.get("/api/jobs/4"))["status"] == "error"
assert bob.post("/api/jobs/2/stop").status_code in (403, 404)

# --- le worker : l'arrêt demandé interrompt le traitement à la première étape ; un nouveau passage efface la demande
run_job(5)
with SessionLocal() as s:
    j5 = s.get(Job, 5)
    assert (j5.status, j5.step, j5.error) == ("error", "Arrêté", "Arrêté par l'utilisateur") and "Arrêté à la demande" in j5.log and "ERREUR" not in j5.log
assert worker.claim_next() == 6
with SessionLocal() as s:
    assert s.get(Job, 6).status == "running" and not s.get(Job, 6).stop_requested

# --- la version anglaise
with SessionLocal() as s:
    en = english.queue(s, s.get(Job, 9), "auto", "admin")
    en_id = en.id
j = ok(admin.post("/api/jobs/9/english/stop"))
assert j["english"]["status"] == "error" and j["english"]["step"] == "Arrêté"
with SessionLocal() as s:
    s.get(EnVersion, en_id).status = "running"
    s.commit()
j = ok(admin.post("/api/jobs/9/english/stop"))
assert j["english"]["status"] == "running" and j["english"]["stopping"] is True
voicelab.run_english(en_id)                                                   # s'arrête avant la traduction, sans modèle
with SessionLocal() as s:
    e = s.get(EnVersion, en_id)
    assert (e.status, e.step) == ("error", "Arrêté") and "Arrêté à la demande" in e.log and e.error == "Arrêté par l'utilisateur"
ok(admin.post("/api/jobs/9/english/stop"), 400)
ok(admin.post("/api/jobs/3/english/stop"), 404)

# --- la pause : en file = tout de suite ; en cours = demandée ; la reprise remet en file devant les nouveaux ; l'arrêt prime sur la pause
with SessionLocal() as s:
    s.add_all([mk(11, "pending"), mk(12, "running")])
    s.commit()
(config.WORK_DIR / "11").mkdir(parents=True)
j = ok(admin.post("/api/jobs/11/pause"))
assert j["status"] == "paused" and j["step"] == "En pause"
ok(admin.post("/api/jobs/11/pause"), 400)                                      # déjà en pause
j = ok(admin.post("/api/jobs/11/resume"))
assert j["status"] == "pending" and j["step"] == "Reprise"
ok(admin.post("/api/jobs/11/resume"), 400)                                     # n'est plus en pause
ok(admin.post("/api/jobs/3/pause"), 400)                                       # terminé
ok(admin.post("/api/jobs/2/pause"), 400)                                       # arrêt déjà demandé : l'arrêt prime
j = ok(admin.post("/api/jobs/12/pause"))
assert j["status"] == "running" and j["pausing"] is True and j["stopping"] is False
j = ok(admin.post("/api/jobs/12/stop"))
assert j["stopping"] is True and j["pausing"] is False
assert bob.post("/api/jobs/12/pause").status_code in (403, 404)
ok(admin.post("/api/jobs/11/pause"))
ok(admin.post("/api/jobs/11/stop"))                                            # on peut arrêter un traitement en pause : son travail est supprimé
assert ok(admin.get("/api/jobs/11"))["status"] == "error" and not (config.WORK_DIR / "11").exists()

# --- le worker : une pause demandée avant un redémarrage est respectée, le travail déjà fait reste
with SessionLocal() as s:
    s.add_all([mk(13, "running", pause_requested=True), mk(14, "running")])
    s.commit()
    s.get(Job, 13).stop_requested = False
    s.commit()
    s.query(Job).filter(Job.status == "running", Job.stop_requested).update({"status": "error"})
    s.query(Job).filter(Job.status == "running", Job.pause_requested).update({"status": "paused", "step": "En pause"})
    s.commit()
    assert s.get(Job, 13).status == "paused"
# une pause oubliée est abandonnée après PAUSE_DAYS, travail supprimé
from datetime import datetime, timedelta  # noqa: E402

with SessionLocal() as s:
    s.get(Job, 13).updated_at = datetime.utcnow() - timedelta(days=config.PAUSE_DAYS + 1)
    s.commit()
(config.WORK_DIR / "13").mkdir(parents=True)
assert worker.expire_paused() == 1 and not (config.WORK_DIR / "13").exists()
with SessionLocal() as s:
    assert s.get(Job, 13).status == "error" and "Pause expirée" == s.get(Job, 13).step

# --- version anglaise : pause (le travail est gardé), reprise, puis arrêt
with SessionLocal() as s:
    en = english.queue(s, s.get(Job, 9), "auto", "admin")
    en_id = en.id
j = ok(admin.post("/api/jobs/9/english/pause"))
assert j["english"]["status"] == "paused" and j["english"]["step"] == "En pause"
ok(admin.post("/api/jobs/9/english/pause"), 400)
j = ok(admin.post("/api/jobs/9/english/resume"))
assert j["english"]["status"] == "pending" and j["english"]["step"] == "Reprise"
ok(admin.post("/api/jobs/9/english/resume"), 400)
with SessionLocal() as s:
    s.get(EnVersion, en_id).status = "running"
    s.commit()
j = ok(admin.post("/api/jobs/9/english/pause"))
assert j["english"]["pausing"] is True
(english.EN_DIR / str(en_id)).mkdir(parents=True, exist_ok=True)
(english.EN_DIR / str(en_id) / "part_0000.wav").write_bytes(b"x")
voicelab.run_english(en_id)                                                    # la pause est vue avant la traduction
with SessionLocal() as s:
    e = s.get(EnVersion, en_id)
    assert (e.status, e.step) == ("paused", "En pause") and "Mis en pause" in e.log and e.finished_at is not None
assert (english.EN_DIR / str(en_id) / "part_0000.wav").exists()                # les morceaux déjà faits sont gardés
assert voicelab.claim_english() is None                                        # une version en pause n'est pas reprise toute seule
ok(admin.post("/api/jobs/9/english/resume"))
assert voicelab.claim_english() == en_id
with SessionLocal() as s:
    s.get(EnVersion, en_id).status, s.get(EnVersion, en_id).finished_at = "paused", datetime.utcnow() - timedelta(days=config.PAUSE_DAYS + 1)
    s.commit()
assert voicelab.expire_paused() == 1 and not (english.EN_DIR / str(en_id)).exists()
print("ok")

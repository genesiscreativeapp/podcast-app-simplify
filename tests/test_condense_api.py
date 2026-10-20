"""Validation des coupes de condensation, via l'API : `python tests/test_condense_api.py`. Base jetable, sans réseau."""
import io
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

from app import config  # noqa: E402
from app.db import Job, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

admin, bob, eve, nocreate = (TestClient(app) for _ in range(4))


def ok(r, code=200):
    assert r.status_code == code, (r.request.method, r.request.url.path, r.status_code, r.text)
    return r.json()


ok(admin.post("/api/auth/login", json={"username": "admin", "password": "adminpass1"}))
for n, c, perms in (("bob", bob, ["jobs.view", "jobs.create", "jobs.delete", "folders.manage"]), ("eve", eve, ["jobs.view", "jobs.create", "folders.manage"]),
                    ("view", nocreate, ["jobs.view"])):
    ok(admin.post("/api/users", json={"username": n, "password": n + "pass123", "permissions": perms}))
    ok(c.post("/api/auth/login", json={"username": n, "password": n + "pass123"}))
fid = ok(bob.post("/api/folders", json={"name": "B"}))["id"]
ok(admin.put("/api/users/4/folders", json={"folder_ids": [fid]}))   # « view » voit le dossier de bob, sans pouvoir valider ses coupes
mk = lambda **kw: ok(bob.post("/api/jobs", json={"folder_id": fid, "youtube_url": "https://youtu.be/x", "title": "T", "date": "2026-01-01", **kw}))

# --- création : valeurs contrôlées, étape de condensation affichée seulement si demandée
assert mk()["condense_pct"] == 0 and next(x for x in mk()["steps"] if x["key"] == "condense")["state"] == "skipped"
j = mk(condense_pct=20, condense_mode="review")
assert j["condense_pct"] == 20 and j["condense_mode"] == "review" and next(x for x in j["steps"] if x["key"] == "condense")["state"] == "pending"
for bad in ({"condense_pct": 15}, {"condense_pct": 50}, {"condense_mode": "peut-etre"}):
    ok(bob.post("/api/jobs", json={"folder_id": fid, "youtube_url": "https://youtu.be/x", "title": "T", "date": "2026-01-01", **bad}), 400)
jid = j["id"]
ok(bob.get(f"/api/jobs/{jid}/review"), 400)                          # rien à valider tant que le traitement n'est pas arrivé là

# --- le traitement s'arrête : on fabrique l'état que run_job laisse (analyse + audio nettoyé)
SR = 8000
sents = [{"id": i, "start": i * 3.0, "end": i * 3.0 + 2.5, "text": f"Phrase {i}.", "cut": [i * 3.0, i * 3.0 + 2.8]} for i in range(10)]
review = {"pct": 20, "method": "heuristique", "target_s": 6.0, "total_s": 28.0, "saved_s": 5.6, "key_points": None, "sentences": sents,
          "removed": [{"id": 3, "reason": "redite de la phrase 1", "because": 1, "by": "heuristique"},
                      {"id": 7, "reason": "formule de remplissage", "because": None, "by": "heuristique"}], "chosen": [3, 7]}
work = config.WORK_DIR / str(jid)
work.mkdir(parents=True)
sf.write(str(work / "clean.wav"), 0.1 * np.sin(2 * np.pi * 220 * np.arange(SR * 30) / SR), SR)
with SessionLocal() as s:
    jj = s.get(Job, jid)
    jj.status, jj.progress, jj.review_json = "review", 0.86, json.dumps(review)
    s.commit()
d = ok(bob.get(f"/api/jobs/{jid}"))
steps = {x["key"]: x["state"] for x in d["steps"]}
assert d["status"] == "review" and steps["condense"] == "done" and steps["edit"] == "pending" and steps["words"] == "done"
assert ok(bob.get("/api/status"))["review"] == 1                                         # le compteur « à valider »
assert jid in [x["id"] for x in ok(bob.get("/api/jobs?status=active"))["items"]]         # visible parmi les traitements actifs

# --- relecture : propriétaire et administrateur seulement
rv = ok(bob.get(f"/api/jobs/{jid}/review"))
assert rv["chosen"] == [3, 7] and len(rv["sentences"]) == 10 and rv["removed"][0]["reason"] == "redite de la phrase 1" and rv["method"] == "heuristique"
ok(admin.get(f"/api/jobs/{jid}/review"))
assert eve.get(f"/api/jobs/{jid}/review").status_code == 404 and nocreate.get(f"/api/jobs/{jid}/review").status_code == 403

# --- écoute d'une phrase : extrait de l'audio nettoyé, plafonné à 60 s
r = bob.get(f"/api/jobs/{jid}/review/clip", params={"start": 9.0, "end": 12.0})
assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
data, sr = sf.read(io.BytesIO(r.content))
assert sr == SR and abs(len(data) / sr - 3.0) < 0.01
assert len(sf.read(io.BytesIO(bob.get(f"/api/jobs/{jid}/review/clip", params={"start": 0, "end": 500}).content))[0]) / SR <= 30.0
assert nocreate.get(f"/api/jobs/{jid}/review/clip", params={"start": 0, "end": 1}).status_code == 403
assert eve.get(f"/api/jobs/{jid}/review/clip", params={"start": 0, "end": 1}).status_code == 404

# --- validation : droits, identifiants inconnus ignorés, le traitement repart
assert nocreate.post(f"/api/jobs/{jid}/review", json={"removed": []}).status_code == 403
assert eve.post(f"/api/jobs/{jid}/review", json={"removed": [3]}).status_code == 404
# brouillon : enregistré sans valider ; une correction du texte est gardée à côté de l'original ; on ne peut pas tout retirer
d = ok(bob.post(f"/api/jobs/{jid}/review", json={"removed": [3, 5], "texts": {"2": "Phrase corrigée."}, "validate": False}))
assert d["status"] == "review"
rv2 = ok(bob.get(f"/api/jobs/{jid}/review"))
assert rv2["chosen"] == [3, 5] and rv2["sentences"][2]["edited"] == "Phrase corrigée." and rv2["sentences"][2]["text"] != "Phrase corrigée."
d = ok(bob.post(f"/api/jobs/{jid}/review", json={"removed": [3], "texts": {"2": rv2["sentences"][2]["text"]}, "validate": False}))   # retour à l'original
assert "edited" not in ok(bob.get(f"/api/jobs/{jid}/review"))["sentences"][2]
ok(bob.post(f"/api/jobs/{jid}/review", json={"removed": list(range(10))}), 400)
ok(bob.post(f"/api/jobs/{jid}/review", json={"removed": [3], "texts": {"2": "Phrase corrigée."}, "validate": False}))
d = ok(bob.post(f"/api/jobs/{jid}/review", json={"removed": [3, 5, 999]}))               # il garde la 3, ajoute la 5, retire la 7 ; 999 n'existe pas
assert d["status"] == "pending" and d["step"].startswith("Validé")
with SessionLocal() as s:
    jj = s.get(Job, jid)
    assert jj.review_ok is True and json.loads(jj.review_json)["chosen"] == [3, 5] and "Texte validé : 2 phrase(s) retirée(s)" in jj.log
    assert json.loads(jj.review_json)["sentences"][2]["edited"] == "Phrase corrigée." and "Brouillon enregistré" in jj.log   # la correction survit à la validation
ok(bob.post(f"/api/jobs/{jid}/review", json={"removed": []}), 400)                       # déjà validé : plus de validation possible
ok(bob.get(f"/api/jobs/{jid}/review"), 400)

# --- « Tout garder » : liste vide acceptée ; relancer efface la proposition ; l'administrateur peut valider à la place de bob
with SessionLocal() as s:
    jj = s.get(Job, jid)
    jj.status, jj.review_ok, jj.review_json = "review", False, json.dumps(review)
    s.commit()
assert ok(admin.post(f"/api/jobs/{jid}/review", json={"removed": []}))["status"] == "pending"
with SessionLocal() as s:
    assert json.loads(s.get(Job, jid).review_json)["chosen"] == []
    jj = s.get(Job, jid)
    jj.status, jj.review_ok, jj.review_json = "review", False, json.dumps(review)
    s.commit()
d = ok(bob.post(f"/api/jobs/{jid}/retry", json={"condense_pct": 10, "condense_mode": "auto"}))
assert d["condense_pct"] == 10 and d["condense_mode"] == "auto" and d["status"] == "pending"
with SessionLocal() as s:
    jj = s.get(Job, jid)
    assert jj.review_json is None and jj.review_ok is False
ok(bob.post(f"/api/jobs/{jid}/retry", json={"condense_pct": 25}), 400)

# --- suppression définitive : l'analyse conservée disparaît avec le traitement
ok(bob.delete(f"/api/jobs/{jid}"))
ok(admin.delete(f"/api/trash/job/{jid}"))
assert not work.exists()
print("ok")

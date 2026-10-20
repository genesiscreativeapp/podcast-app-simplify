"""Banc d'essai voix dans l'application : API admin + service voicelab. `python tests/test_voicelab.py`
ffmpeg, Whisper, l'IA et les vrais moteurs sont remplacés par des faux ; la logique réelle du service et de l'API s'exécute."""
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

from app import config, vault, voicebench as vb, voicelab  # noqa: E402
from app.pipeline import detect  # noqa: E402
from app.db import AiUsage, Folder, Job, Setting, SessionLocal, VoiceBench  # noqa: E402
from app.main import app  # noqa: E402

admin, bob = TestClient(app), TestClient(app)


def ok(r, code=200):
    assert r.status_code == code, (r.request.method, r.request.url.path, r.status_code, r.text)
    return r.json()


ok(admin.post("/api/auth/login", json={"username": "admin", "password": "adminpass1"}))
ok(admin.post("/api/users", json={"username": "bob", "password": "bobpass123", "permissions": ["jobs.view"]}))
ok(bob.post("/api/auth/login", json={"username": "bob", "password": "bobpass123"}))

# --- un podcast terminé, avec son MP3 (un WAV suffit pour le test)
mp3 = config.OUTPUT_DIR / "1" / "pod.mp3"
mp3.parent.mkdir(parents=True)
sf.write(str(mp3), np.zeros(8000), 8000, format="WAV")
with SessionLocal() as s:
    s.add(Folder(name="CULTE"))
    s.commit()
    s.add_all([Job(id=1, folder_id=1, youtube_url="u", title="Sermon", date="2026-01-01", filename="pod", status="done", local_mp3=str(mp3), duration_output=1800.0, created_by="admin"),
               Job(id=2, folder_id=1, youtube_url="u", title="Sans fichier", date="2026-01-01", filename="x", status="done", local_mp3="/nulle/part.mp3", duration_output=900.0, created_by="admin"),
               Job(id=3, folder_id=1, youtube_url="u", title="En cours", date="2026-01-01", filename="y", status="running", created_by="admin")])
    s.commit()

# --- l'écran est réservé à l'administrateur ; le service est « inactif » tant qu'il n'a pas donné signe de vie
assert bob.get("/api/voicelab").status_code == 403 and bob.post("/api/voicelab/runs", json={}).status_code == 403
v = ok(admin.get("/api/voicelab"))
assert v["alive"] is False and v["last_seen"] is None and [p["id"] for p in v["podcasts"]] == [1] and v["podcasts"][0]["folder"] == "CULTE"   # ni fichier absent, ni en cours
assert [e["id"] for e in v["engines"]] == ["chatterbox-turbo", "chatterbox"] and v["runs"] == []
voicelab.beat()
assert ok(admin.get("/api/voicelab"))["alive"] is True and ok(admin.get("/api/voicelab"))["last_seen"].endswith("Z")

# --- création d'un essai : tout est contrôlé
body = {"job_id": 1, "start": 900, "seconds": 180, "ref_start": 5, "engines": ["chatterbox-turbo"]}
post = lambda **kw: admin.post("/api/voicelab/runs", json={**body, **kw})
for bad in ({"job_id": 2}, {"job_id": 3}, {"job_id": 99}, {"seconds": 10}, {"seconds": 900}, {"start": -1}, {"start": 1790}, {"ref_start": 175},
            {"engines": []}, {"engines": ["dummy", "inconnu"]}, {"text_en": "x" * 20001}, {"translator": "gpt"}):
    ok(post(**bad), 400)
r = ok(post(engines=["chatterbox", "chatterbox", "chatterbox-turbo"]))
assert r["status"] == "pending" and r["engines"] == ["chatterbox", "chatterbox-turbo"] and r["seconds"] == 180 and r["title"] == "Sermon"
assert r["translator"] == "local"                                               # par défaut : le modèle libre local, sans IA externe
assert ok(post(translator="claude"))["translator"] == "claude"
assert ok(post(start=1700))["seconds"] == 100                                  # l'extrait est raccourci pour ne pas dépasser le podcast
assert ok(admin.get("/api/voicelab"))["runs"][0]["id"] == 3

# --- le service : traduction par le modèle libre local (sans IA), un faux moteur qui marche, un vrai moteur absent
vb.excerpt = lambda audio, start, seconds, ref_start, ref_seconds, out: (sf.write(str(out / "fr.wav"), np.zeros(1600), 16000), sf.write(str(out / "ref.wav"), np.zeros(2400), 24000))
vb.transcribe = lambda wav, model: ("Mes frères, Dieu est fidèle. Il tient ses promesses.", 1.5)
vb.translate_local = lambda sentences, on_progress=None: ["EN " + s for s in sentences]


def new_run(**kw):
    with SessionLocal() as s:
        s.add(VoiceBench(created_by="admin", job_id=1, title="Sermon", start=900, seconds=180, ref_start=5, **kw))
        s.commit()
        return s.query(VoiceBench.id).order_by(VoiceBench.id.desc()).first()[0]


for i in range(1, 4):                                                            # les essais créés par l'API ne nous intéressent pas ici
    with SessionLocal() as s:
        s.query(VoiceBench).filter(VoiceBench.id == i).update({"status": "error"})
        s.commit()
local_id = new_run(engines="dummy,chatterbox")                                   # translator : « local » par défaut
assert voicelab.claim_next() == local_id and voicelab.claim_next() is None
voicelab.run_bench(local_id)
d = ok(admin.get(f"/api/voicelab/runs/{local_id}"))
assert d["status"] == "done" and d["progress"] == 1.0 and d["translator"] == "local"
rep = d["report"]
assert rep["sentences"] == 2 and rep["parts"] == 1 and rep["whisper_s"] == 1.5 and rep["excerpt_seconds"] == 180 and rep["translation"] == "modèle local"
good, bad = rep["results"]
assert good["engine"] == "dummy" and good["file"] == "dummy.wav" and good["audio_s"] > 2 and good["rtf"] == 0
assert bad["engine"] == "chatterbox" and "error" in bad and "chatterbox-tts" in bad["hint"]        # le moteur absent n'arrête pas l'essai
assert "chatterbox : ÉCHEC" in d["log"] and "IA :" not in d["log"]
with SessionLocal() as s:
    assert s.query(AiUsage).count() == 0                                         # aucune IA externe n'a servi
dummy_id = local_id

# --- Claude en option : traduction numérotée, consommation comptée ; phrases oubliées ou panne : le modèle local complète
with SessionLocal() as s:
    s.merge(Setting(key="llm_key", value=vault.encrypt("sk-ant-" + "s" * 30)))
    s.merge(Setting(key="llm_model", value="claude-sonnet-5-5"))
    s.commit()
asked = []


def fake_ai(answer):
    def ask(prompt, llm, max_tokens=400, on_usage=None):
        asked.append((llm["owner"], "[0] Mes frères" in prompt))
        if isinstance(answer, Exception):
            raise answer
        on_usage(120, 30)
        return answer
    return ask


detect.ask_llm = fake_ai("[0] Brothers and sisters, God is faithful.\n[1] He keeps his promises.")
claude_id = new_run(engines="dummy", translator="claude")
voicelab.run_bench(claude_id)
d = ok(admin.get(f"/api/voicelab/runs/{claude_id}"))
assert d["status"] == "done" and d["report"]["translation"] == "IA" and asked == [("@server", True)]
assert "IA : 120 tokens en entrée, 30 en sortie" in d["log"]
assert admin.get(f"/api/voicelab/runs/{claude_id}/file/en.txt").text == "Brothers and sisters, God is faithful.\nHe keeps his promises."
with SessionLocal() as s:
    u = s.query(AiUsage).one()
    assert (u.username, u.author, u.tokens_in, u.tokens_out) == ("@server", "admin", 120, 30)
detect.ask_llm = fake_ai("[1] He keeps his promises.")                           # l'IA oublie la phrase 0
partial_id = new_run(engines="dummy", translator="claude")
voicelab.run_bench(partial_id)
d = ok(admin.get(f"/api/voicelab/runs/{partial_id}"))
assert d["status"] == "done" and d["report"]["translation"] == "IA + modèle local" and "modèle local pour celles-ci" in d["log"]
assert admin.get(f"/api/voicelab/runs/{partial_id}/file/en.txt").text == "EN Mes frères, Dieu est fidèle.\nHe keeps his promises."
detect.ask_llm = fake_ai(RuntimeError("API Anthropic 529 : overloaded"))         # l'IA est en panne
down_id = new_run(engines="dummy", translator="claude")
voicelab.run_bench(down_id)
d = ok(admin.get(f"/api/voicelab/runs/{down_id}"))
assert d["status"] == "done" and d["report"]["translation"] == "modèle local" and "Traduction par l'IA impossible" in d["log"]

# --- fichiers servis à l'administrateur seulement, avec une liste blanche de noms
f = admin.get(f"/api/voicelab/runs/{dummy_id}/file/en.txt")
assert f.status_code == 200 and f.text == "EN Mes frères, Dieu est fidèle.\nEN Il tient ses promesses."
assert admin.get(f"/api/voicelab/runs/{dummy_id}/file/dummy.wav").headers["content-type"] == "audio/wav"
assert sf.info(str(config.DATA_DIR / "bench" / str(dummy_id) / "ref.wav")).samplerate == 24000
for name in ("..%2Fapp.db", "secret.key", "x.py", "absent.wav"):
    assert admin.get(f"/api/voicelab/runs/{dummy_id}/file/{name}").status_code == 404, name
assert bob.get(f"/api/voicelab/runs/{dummy_id}/file/en.txt").status_code == 403

# --- traduction fournie : ni Whisper ni traducteur ; Claude demandé sans IA disponible : le modèle local, sans erreur
with SessionLocal() as s:
    s.query(Setting).filter(Setting.key.in_(["llm_key", "llm_model"])).delete(synchronize_session=False)
    s.commit()
own = new_run(engines="dummy", text_en="Hello there.\nAmen.")
voicelab.run_bench(own)
d = ok(admin.get(f"/api/voicelab/runs/{own}"))
assert d["status"] == "done" and "Traduction fournie" in d["log"] and "whisper_s" not in d["report"] and d["report"]["sentences"] == 2
noai = new_run(engines="dummy", translator="claude")
voicelab.run_bench(noai)
d = ok(admin.get(f"/api/voicelab/runs/{noai}"))
assert d["status"] == "done" and d["report"]["translation"] == "modèle local" and "Claude n'est pas disponible" in d["log"]

# --- redémarrage du service : l'essai interrompu est signalé ; suppression d'un essai (jamais pendant son calcul)
with SessionLocal() as s:
    s.query(VoiceBench).filter(VoiceBench.id == 1).update({"status": "running"})
    s.commit()
ok(admin.delete("/api/voicelab/runs/1"), 400)
assert voicelab.mark_interrupted() == 1 and "redémarrage" in ok(admin.get("/api/voicelab/runs/1"))["error"]
ok(admin.delete(f"/api/voicelab/runs/{dummy_id}"))
assert not (config.DATA_DIR / "bench" / str(dummy_id)).exists() and admin.get(f"/api/voicelab/runs/{dummy_id}").status_code == 404
# chargement d'un moteur : le journal dit où en est le téléchargement des modèles
import time  # noqa: E402

os.environ["HF_HOME"] = str(Path(os.environ["DATA_DIR"]) / "hf")
(Path(os.environ["HF_HOME"]) / "hub").mkdir(parents=True)
msgs = []
with voicelab._watch_models(msgs.append, "Chargement", every=0.05):
    (Path(os.environ["HF_HOME"]) / "hub" / "model.bin").write_bytes(b"x" * 3_000_000)
    time.sleep(0.3)
assert msgs and "Go" in msgs[0] and "+3 Mo" in msgs[0] and any("rien de nouveau" in m for m in msgs[1:]), msgs
# sans GPU, torch.load ramène tout sur le processeur (fichiers Chatterbox enregistrés sur CUDA) ; avec un GPU ou un map_location explicite, rien ne change
from types import SimpleNamespace  # noqa: E402

seen = []
fake = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False), device=lambda n: f"dev:{n}", load=lambda *a, **k: seen.append(k) or "obj")
vb._force_cpu_load(fake)
vb._force_cpu_load(fake)
assert fake.load("f") == "obj" and fake.load("f", map_location="cuda") == "obj" and fake.load("f", "cuda") == "obj"
assert seen == [{"map_location": "dev:cpu"}, {"map_location": "cuda"}, {}], seen
gpu = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True), load=lambda *a, **k: None)
before = gpu.load
vb._force_cpu_load(gpu)
assert gpu.load is before
print("ok")

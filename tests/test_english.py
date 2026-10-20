"""Version anglaise des podcasts (traduction sans Claude + voix du prédicateur) : `python tests/test_english.py`.
ffmpeg, Whisper, le modèle de traduction et les vrais moteurs de voix sont remplacés par des faux ; la logique réelle s'exécute."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.update(DATA_DIR=tempfile.mkdtemp(), APP_USER="admin", APP_PASSWORD="adminpass1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, english, r2sync, vault, voicebench as vb, voicelab  # noqa: E402
from app.db import AiUsage, EnVersion, Folder, Job, Setting, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.pipeline import detect  # noqa: E402

# ============ voicebench : fonctions pures ============
assert vb.split_sentences("Un deux. Trois ! Quatre ? Cinq… Six") == ["Un deux.", "Trois !", "Quatre ?", "Cinq…", "Six"]
sr = 16000
t = np.arange(sr * 200) / sr
x = 0.002 * np.random.default_rng(0).standard_normal(len(t))                              # bruit de fond
x[: 45 * sr] += 0.3 * np.sin(2 * np.pi * 440 * t[: 45 * sr])                              # une intro bruyante (écartée)
for a, b in ((60, 62), (64, 66), (68, 70), (72, 74)):                                     # parole hachée
    x[a * sr:b * sr] += 0.1 * np.sin(2 * np.pi * 180 * t[a * sr:b * sr]) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t[a * sr:b * sr]))
x[100 * sr:116 * sr] += 0.1 * np.sin(2 * np.pi * 180 * t[100 * sr:116 * sr])             # parole continue et régulière : la meilleure
assert 98 <= vb.best_window(x.astype(np.float32), sr) <= 104
assert vb.best_window(np.zeros(sr * 5, np.float32), sr) == 0.0 and vb.best_window(np.zeros(10, np.float32), sr) == 0.0   # podcast très court

# traduction : le modèle local par défaut ; Claude en option avec repli phrase par phrase
vb.translate_local = lambda sentences, on_progress=None: ["EN " + s for s in sentences]
logs = []
assert vb.translate(["a", "b"]) == (["EN a", "EN b"], "modèle local")
assert vb.translate(["a"], "claude", None) == (["EN a"], "modèle local")                    # Claude demandé mais aucune IA : local, sans erreur


def fake_claude(answer):
    def ask(prompt, llm, max_tokens=400, on_usage=None):
        if isinstance(answer, Exception):
            raise answer
        if on_usage:
            on_usage(10, 5)
        return answer
    return ask


LLM, used = {"key": "k", "model": "m", "owner": "u"}, []
detect.ask_llm = fake_claude("[0] Zero.\n[1] One.\n[2] Two.\nbruit sans numéro")
assert vb.translate(["z", "o", "t"], "claude", LLM, logs.append, lambda i, o: used.append((i, o))) == (["Zero.", "One.", "Two."], "IA") and used == [(10, 5)]
detect.ask_llm = fake_claude("[0] Zero.\n[2] Two.")                                         # une phrase oubliée : complétée en local
assert vb.translate(["z", "o", "t"], "claude", LLM, logs.append) == (["Zero.", "EN o", "Two."], "IA + modèle local")
detect.ask_llm = fake_claude("[5] hors lot\n[abc] illisible")                               # rien d'exploitable : tout en local
assert vb.translate(["z"], "claude", LLM, logs.append)[1] == "modèle local"
detect.ask_llm = fake_claude(RuntimeError("API 529"))
assert vb.translate(["z"], "claude", LLM, logs.append) == (["EN z"], "modèle local") and "Traduction par l'IA impossible" in logs[-1]
assert english.english_filename("La foi", "2026-10-18") == "La-foi_2026-10-18_EN"

# ============ application ============
admin, bob, eve = TestClient(app), TestClient(app), TestClient(app)


def ok(r, code=200):
    assert r.status_code == code, (r.request.method, r.request.url.path, r.status_code, r.text)
    return r.json()


ok(admin.post("/api/auth/login", json={"username": "admin", "password": "adminpass1"}))
for n, c, perms in (("bob", bob, ["jobs.view", "jobs.create", "jobs.delete", "folders.manage", "english.create"]), ("eve", eve, ["jobs.view", "jobs.create", "folders.manage"])):
    ok(admin.post("/api/users", json={"username": n, "password": n + "pass123", "permissions": perms}))
    ok(c.post("/api/auth/login", json={"username": n, "password": n + "pass123"}))
fid = ok(bob.post("/api/folders", json={"name": "CULTE"}))["id"]
FR = [("Mes frères et sœurs, " + f"{k} " * 100).strip() + "." for k in range(4)]           # 4 phrases d'environ 220 caractères : un morceau chacune
mp3 = config.OUTPUT_DIR / "1" / "La-foi_2026-10-18.mp3"
mp3.parent.mkdir(parents=True)
sf.write(str(mp3), np.zeros(8000), 8000, format="WAV")
with SessionLocal() as s:
    s.add_all([Job(id=1, folder_id=fid, youtube_url="u", title="La foi", date="2026-10-18", filename="La-foi_2026-10-18", status="done", local_mp3=str(mp3),
                   duration_output=1800.0, transcript_json=json.dumps(FR), created_by="bob"),
               Job(id=2, folder_id=fid, youtube_url="u", title="En cours", date="2026-10-18", filename="x", status="pending", created_by="bob")])
    s.commit()

# --- droits, valeurs par défaut, contrôles
info = ok(bob.get("/api/english"))
assert info["can_create"] and info["defaults"] == {"translator": "local", "engine": "chatterbox-nano"} and info["claude_available"] is False and info["active"] == []
assert ok(eve.get("/api/english"))["can_create"] is False
post = lambda c, jid=1, **kw: c.post(f"/api/jobs/{jid}/english", json=kw)
ok(post(eve), 403)
ok(post(bob, 2), 400)                                                                       # un podcast pas terminé
for bad in ({"mode": "peut-etre"}, {"translator": "gpt"}, {"engine": "inconnu"}, {"translator": "claude"}, {"ref_start": 1795}, {"ref_start": -1}):
    ok(post(bob, **bad), 400)
ok(post(admin, 99), 404)
d = ok(post(bob, mode="review"))
assert d["english"]["status"] == "pending" and d["english"]["mode"] == "review" and d["english"]["translator"] == "local" and d["english"]["engine"] == "chatterbox-nano"
assert ok(bob.get("/api/status"))["english"] == 1 and ok(bob.get("/api/english"))["active"][0]["title"] == "La foi"
with SessionLocal() as s:
    s.query(EnVersion).update({"status": "running"})
    s.commit()
ok(post(bob), 400)                                                                          # déjà en cours de calcul
with SessionLocal() as s:
    s.query(EnVersion).update({"status": "pending"})
    s.commit()

# --- réglages de l'administrateur (traducteur et moteur par défaut)
assert bob.put("/api/english/settings", json={"translator": "local", "engine": "chatterbox"}).status_code == 403
ok(admin.put("/api/english/settings", json={"translator": "gpt", "engine": "chatterbox"}), 400)
assert ok(admin.put("/api/english/settings", json={"translator": "local", "engine": "chatterbox-turbo"})) == {"translator": "local", "engine": "chatterbox-turbo"}
assert ok(post(bob, mode="auto"))["english"]["engine"] == "chatterbox-turbo" and ok(post(bob, mode="auto", engine="chatterbox"))["english"]["engine"] == "chatterbox"

# --- demande avec le traitement : permission requise, valeurs contrôlées
mk = lambda c, **kw: c.post("/api/jobs", json={"folder_id": fid, "youtube_url": "https://youtu.be/x", "title": "T", "date": "2026-01-01", **kw})
assert ok(mk(bob, english="auto"))["english_mode"] == "auto" and ok(mk(bob))["english_mode"] == ""
ok(mk(eve), 404)                                                                         # eve ne voit pas le dossier de bob
ok(mk(bob, english="peut-etre"), 400)
ok(admin.put("/api/users/3/folders", json={"folder_ids": [fid]}))
ok(mk(eve, english="auto"), 403)                                                           # eve voit le dossier mais n'a pas la permission
assert ok(mk(eve))["english_mode"] == ""

# ============ le service ============
shutil.copy  # (les faux ci-dessous évitent ffmpeg et les modèles)
voicelab.audio.finalize = lambda body, out, intro=None, xfade=0.6, on_progress=None: shutil.copy(body, out)
voicelab.audio.encode_mp3 = lambda src, out, *a, **k: Path(out).write_bytes(b"MP3DATA")
voicelab.audio.probe_duration = lambda p: 42.0
vb.pick_reference = lambda audio, out, start=None: (sf.write(str(out), np.zeros(2400), 24000), 33.0 if start is None else start)[1]
spoken = []


class Rec:
    sr = 24000

    def __init__(self, ref, work, ov):
        pass

    def say(self, text):
        spoken.append(text)
        return np.zeros(2400)


vb.ENGINES["dummy"] = lambda ref, work, ov: Rec(ref, work, ov)


def prepare(mode="auto", translator="local", engine="dummy", job_id=1):
    with SessionLocal() as s:
        s.query(EnVersion).filter(EnVersion.job_id == job_id).delete()
        s.commit()
        job = s.get(Job, job_id)
        en = english.queue(s, job, mode, "bob", translator, "chatterbox")
        en.engine = engine
        s.commit()
        return en.id


def state(en_id):
    with SessionLocal() as s:
        en = s.get(EnVersion, en_id)
        return {c.name: getattr(en, c.name) for c in EnVersion.__table__.columns}


# 1. automatique : texte du podcast final → traduction locale → voix → MP3, sans rien demander
en_id = prepare("auto")
assert voicelab.claim_english() == en_id and voicelab.claim_english() is None
spoken.clear()
voicelab.run_english(en_id)
e = state(en_id)
assert e["status"] == "done" and e["progress"] == 1.0 and e["method"] == "modèle local" and e["error"] is None
assert [t["en"] for t in json.loads(e["text_json"])] == ["EN " + f for f in FR] and [t["fr"] for t in json.loads(e["text_json"])] == FR
assert spoken == ["EN " + f for f in FR]                                                    # un morceau par phrase (200 caractères)
assert Path(e["local_mp3"]).name == "La-foi_2026-10-18_EN.mp3" and Path(e["local_mp3"]).read_bytes() == b"MP3DATA" and e["size_mp3"] == 7 and e["duration_output"] == 42.0
assert not (english.EN_DIR / str(en_id)).exists() and "Voix de référence prise à 33 s" in e["log"] and "Terminé" in e["log"]
assert not e["r2_key_mp3"]                                                                  # R2 non configuré

# 2. avec validation : le service s'arrête sur le texte ; l'utilisateur le corrige ; la voix dit le texte corrigé
en_id = prepare("review")
spoken.clear()
voicelab.claim_english()
voicelab.run_english(en_id)
e = state(en_id)
assert e["status"] == "review" and e["step"].startswith("À valider") and e["review_ok"] is False and spoken == [] and e["local_mp3"] is None
rv = ok(bob.get("/api/jobs/1/english/review"))
assert rv["engine"] == "dummy" and rv["method"] == "modèle local" and [t["en"] for t in rv["sentences"]][0] == "EN " + FR[0]
assert ok(bob.get("/api/status"))["review"] == 1
assert eve.get("/api/jobs/1/english/review").status_code == 403 and ok(admin.get("/api/jobs/1/english/review"))
ok(bob.post("/api/jobs/1/english/review", json={"texts": {"0": "Brothers, God is good.", "1": ""}}), 200)    # corrige la 0, retire la 1
assert state(en_id)["status"] == "pending" and state(en_id)["review_ok"] is True
ok(bob.get("/api/jobs/1/english/review"), 400)                                              # déjà validé
voicelab.claim_english()
voicelab.run_english(en_id)
assert state(en_id)["status"] == "done" and " ".join(spoken) == f"Brothers, God is good. EN {FR[2]} EN {FR[3]}"   # texte corrigé, phrase 1 retirée
assert "EN " + FR[1] not in " ".join(spoken)
assert json.loads(state(en_id)["text_json"])[1]["en"] == ""                                 # la phrase retirée n'est pas dite
with SessionLocal() as s:
    s.query(EnVersion).update({"status": "review", "review_ok": False})
    s.commit()
ok(bob.post("/api/jobs/1/english/review", json={"texts": {str(i): "" for i in range(4)}}), 400)   # texte entièrement vide refusé

# 3. reprise après une panne : les morceaux déjà faits sont conservés, seuls les autres sont refaits
en_id = prepare("auto")
calls = []


class Flaky(Rec):
    def say(self, text):
        calls.append(text)
        if len(calls) == 3:
            raise RuntimeError("mémoire insuffisante")
        return np.zeros(2400)


vb.ENGINES["dummy"] = lambda ref, work, ov: Flaky(ref, work, ov)
voicelab.claim_english()
voicelab.run_english(en_id)
assert state(en_id)["status"] == "error" and "mémoire insuffisante" in state(en_id)["error"]
work = english.EN_DIR / str(en_id)
assert sorted(p.name for p in work.glob("part_*.wav")) == ["part_0000.wav", "part_0001.wav"]    # 2 morceaux sur 4 déjà faits
with SessionLocal() as s:
    s.query(EnVersion).filter(EnVersion.id == en_id).update({"status": "running"})
    s.commit()
assert voicelab.mark_interrupted() >= 0 and state(en_id)["status"] == "pending"              # redémarrage du service : reprise automatique
vb.ENGINES["dummy"] = lambda ref, work, ov: Rec(ref, work, ov)
spoken.clear()
voicelab.claim_english()
voicelab.run_english(en_id)
e = state(en_id)
assert e["status"] == "done" and spoken == ["EN " + FR[2], "EN " + FR[3]] and "Reprise : 2 morceau(x) sur 4" in e["log"]

# 4. Claude en option : traduction numérotée comptée dans les compteurs ; indisponible : modèle local
with SessionLocal() as s:
    s.merge(Setting(key="llm_key", value=vault.encrypt("sk-ant-" + "s" * 30)))
    s.commit()
detect.ask_llm = fake_claude("\n".join(f"[{i}] Claude {i}." for i in range(4)))
en_id = prepare("auto", translator="claude")
spoken.clear()
voicelab.claim_english()
voicelab.run_english(en_id)
assert state(en_id)["status"] == "done" and state(en_id)["method"] == "IA" and " ".join(spoken) == "Claude 0. Claude 1. Claude 2. Claude 3."
with SessionLocal() as s:
    u = s.query(AiUsage).one()
    assert (u.username, u.author, u.job_id, u.tokens_in, u.tokens_out) == ("@server", "bob", 1, 10, 5)
with SessionLocal() as s:
    s.query(Setting).filter(Setting.key == "llm_key").delete()
    s.commit()
en_id = prepare("auto", translator="claude")
voicelab.claim_english()
voicelab.run_english(en_id)
assert state(en_id)["method"] == "modèle local" and "Claude n'est pas disponible" in state(en_id)["log"]

# 5. podcast produit avant l'enregistrement du texte : retranscrit ; moteur absent : erreur claire avec la commande d'installation
with SessionLocal() as s:
    s.query(Job).filter(Job.id == 1).update({"transcript_json": None})
    s.commit()
voicelab.subprocess.run = lambda cmd, **kw: sf.write(cmd[-1], np.zeros(1600), 16000)
vb.transcribe = lambda wav, model: ("Première phrase. Deuxième phrase.", 1.0)
en_id = prepare("review")
voicelab.claim_english()
voicelab.run_english(en_id)
assert [t["fr"] for t in json.loads(state(en_id)["text_json"])] == ["Première phrase.", "Deuxième phrase."] and "Transcription du podcast" in state(en_id)["log"]
with SessionLocal() as s:
    s.query(Job).filter(Job.id == 1).update({"transcript_json": json.dumps(FR)})
    s.commit()
en_id = prepare("auto", engine="chatterbox")                                                # vrai moteur, non installé ici
voicelab.claim_english()
voicelab.run_english(en_id)
e = state(en_id)
assert e["status"] == "error" and "chatterbox" in e["error"] and "pip install chatterbox-tts" in e["log"]

# ============ fichier, lien, nom sur R2, suppression ============
en_id = prepare("auto")
voicelab.claim_english()
voicelab.run_english(en_id)
f = bob.get("/api/jobs/1/english/file")
assert f.status_code == 200 and f.content == b"MP3DATA" and f.headers["content-type"] == "audio/mpeg"
dispo = bob.get("/api/jobs/1/english/file?download=true").headers["content-disposition"]
assert dispo.startswith("attachment") and ("La foi_2026-10-18_EN.mp3" in dispo or "La%20foi_2026-10-18_EN.mp3" in dispo), dispo
ok(bob.get("/api/jobs/1/english/link"), 404)                                                # R2 non configuré
j = ok(bob.get("/api/jobs/1"))
assert j["english"]["status"] == "done" and j["english"]["has_mp3"] and j["english"]["size_mp3"] == 7 and j["english"]["on_r2"] is False
assert "Terminé" in ok(admin.get("/api/jobs/1"))["english_log"] and "english_log" not in j
with SessionLocal() as s:
    assert r2sync.desired_key_en(s, s.get(Job, 1)) == "podcasts/CULTE/La foi_2026-10-18_EN.mp3"
    s.query(EnVersion).update({"r2_key_mp3": "podcasts/CULTE/La foi_2026-10-18_EN.mp3"})
    s.commit()
    assert r2sync.desired_key_en(s, s.get(Job, 1)) == "podcasts/CULTE/La foi_2026-10-18_EN.mp3"       # le sien : pas de suffixe (2)
ok(bob.delete("/api/jobs/1/english"), 403)                                                  # suppression définitive : administrateur seulement
ok(admin.delete("/api/jobs/1/english"))
assert not Path(state_path := str(mp3.parent / "La-foi_2026-10-18_EN.mp3")).exists() and ok(bob.get("/api/jobs/1"))["english"] is None
ok(admin.delete("/api/jobs/1/english"), 404)

# suppression définitive du podcast : sa version anglaise part avec lui
en_id = prepare("auto")
voicelab.claim_english()
voicelab.run_english(en_id)
ok(bob.delete("/api/jobs/1"))
ok(admin.delete("/api/trash/job/1"))
with SessionLocal() as s:
    assert s.query(EnVersion).count() == 0 and s.get(Job, 1) is None
assert not mp3.parent.exists()
print("ok")

"""Pipeline complet avec condensation : pause de validation, reprise, mode automatique, sans IA.
`python tests/test_run_condense.py` — ffmpeg, Whisper et R2 sont remplacés par des faux ; la logique réelle de run_job s'exécute."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from app import config  # noqa: E402
from app.db import EnVersion, Folder, Job, SessionLocal, init_db  # noqa: E402
from app.pipeline import run as R  # noqa: E402

# --- un faux sermon : 140 phrases de 6 mots ; les phrases 70 et 74 reprennent 68 et 73, la 80 est « Vous voyez ? »
WORD, PAUSE, N = 0.4, 0.5, 140
texts = {k: [f"{k:03d}w{j}" for j in range(6)] for k in range(N)}
texts[70] = texts[68][:5] + ["neuf"]
texts[74] = texts[73][:5] + ["autre"]
texts[80] = ["Vous", "voyez?"]
words, t = [], 0.0
for k in range(N):
    for n, tok in enumerate(texts[k]):
        words.append({"start": t, "end": t + WORD, "word": " " + tok + ("." if n == len(texts[k]) - 1 and not tok.endswith("?") else "")})
        t += WORD
    t += PAUSE
TOTAL, SR = t, 8000

# --- remplacements : audio synthétique, aucune dépendance externe
R.audio.probe_duration = lambda p: sf.info(str(p)).duration if str(p).endswith(".wav") else 100.0
R.audio.extract_enhanced = lambda src, a, b, out, out16, cb=None: (sf.write(str(out), 0.1 * np.sin(2 * np.pi * 220 * np.arange(int(TOTAL * SR)) / SR), SR),
                                                                    sf.write(str(out16), np.zeros(1600), 16000))
R.transcribe_words = lambda wav, dur, cb=None: [{"start": 0, "end": TOTAL, "text": "", "words": words}]
R.audio.finalize = lambda body, out, intro=None, xfade=0.6, on_progress=None: shutil.copy(body, out)
R.audio.encode_mp3 = lambda src, out, *a, **k: Path(out).write_bytes(b"mp3")

init_db()
with SessionLocal() as s:
    s.add(Folder(name="f"))
    s.commit()


def new_job(i, pct, mode, english=""):
    with SessionLocal() as s:
        s.add(Job(id=i, folder_id=1, youtube_url="upload://x.wav", title=f"t{i}", date="2026-01-01", filename=f"t{i}",
                  start_override=0.0, end_override=TOTAL, condense_pct=pct, condense_mode=mode, english_mode=english, created_by="u"))
        s.commit()
    cache = config.CACHE_DIR / str(i)
    cache.mkdir(parents=True)
    sf.write(str(cache / "source.wav"), np.zeros(int(TOTAL * SR) + SR), SR)
    (cache / "ok").touch()


def job(i):
    with SessionLocal() as s:
        return s.get(Job, i)


def seconds(note):  # « durée 0:06:46 → 0:06:40 » dans le bilan du montage
    a, b = [x.strip() for x in note.split("durée")[1].split("→")]
    f = lambda h: sum(int(float(p)) * m for p, m in zip(h.split(":"), (3600, 60, 1)))
    return f(a), f(b)


# 1. validation humaine : le traitement s'arrête après la condensation, sans produire de MP3
new_job(1, 10, "review")
R.run_job(1)
j, work = job(1), config.WORK_DIR / "1"
assert j.status == "review" and j.step.startswith("À valider") and j.review_ok is False and j.local_mp3 is None
assert (work / "analysis.json").exists() and (work / "clean.wav").exists()       # de quoi reprendre sans rien refaire
rev = json.loads(j.review_json)
assert {r["id"] for r in rev["removed"]} == {70, 74, 80} and rev["chosen"] == [70, 74, 80] and rev["method"] == "heuristique"
assert len(rev["sentences"]) == N and rev["key_points"] is None and rev["pct"] == 10
assert abs(j.progress - R.steps.BY_KEY["condense"][2]) < 1e-9 and "En attente de la validation" in j.log

# 2. l'utilisateur garde la redite 74 (la retire de la sélection) et valide : le traitement reprend et se termine
rev["chosen"] = [70, 80]
with SessionLocal() as s:
    jj = s.get(Job, 1)
    jj.review_json, jj.review_ok, jj.status = json.dumps(rev), True, "pending"
    s.commit()
R.run_job(1)
j = job(1)
assert j.status == "done" and j.review_ok is False and j.local_mp3 and Path(j.local_mp3).exists()
assert "Reprise après validation" in j.log and "condensation : 2 phrase(s) retirée(s)" in j.edit_note and "validée" in j.edit_note
before, after = seconds(j.edit_note)
assert 3 <= before - after <= 5, (before, after)                                   # la redite 70 (~2,7 s) et « Vous voyez ? » (~1,1 s)
assert not (config.WORK_DIR / "1").exists()                                        # l'analyse est supprimée une fois fini
tr = json.loads(j.transcript_json)                                                 # le texte FINAL du podcast, base de la version anglaise
assert len(tr) == N - 2 and not any("neuf" in x or "Vous" in x for x in tr) and any("autre" in x for x in tr), len(tr)   # 70 et 80 retirées, 74 gardée
with SessionLocal() as s:
    assert s.query(EnVersion).count() == 0                                         # pas de version anglaise demandée : rien en file

# 3. automatique : tout est appliqué en un seul passage
new_job(2, 10, "auto")
R.run_job(2)
j = job(2)
assert j.status == "done" and "condensation : 3 phrase(s) retirée(s)" in j.edit_note and "validée" not in j.edit_note
assert json.loads(j.review_json)["chosen"] == [70, 74, 80]                         # les coupes appliquées restent consultables
assert len(json.loads(j.transcript_json)) == N - 3                            # les trois phrases retirées ne sont plus dans le texte
b2, a2 = seconds(j.edit_note)
assert before - after < b2 - a2 <= 11

# 4. sans condensation : rien ne change
new_job(3, 0, "auto")
R.run_job(3)
j = job(3)
assert j.status == "done" and j.review_json is None and "condensation" not in j.edit_note
assert len(json.loads(j.transcript_json)) == N and any("Vous voyez" in x for x in json.loads(j.transcript_json))   # sans coupe : tout le texte

# 5. validation sans l'analyse conservée (dossier de travail perdu) : on refait l'analyse et on redemande la validation
new_job(4, 10, "review")
R.run_job(4)
shutil.rmtree(config.WORK_DIR / "4")
with SessionLocal() as s:
    jj = s.get(Job, 4)
    jj.review_ok, jj.status = True, "pending"
    s.commit()
R.run_job(4)
assert job(4).status == "review" and job(4).review_ok is False and (config.WORK_DIR / "4" / "analysis.json").exists()

# 6. texte trop court pour juger : pas de pause, pas de coupe
R.transcribe_words = lambda wav, dur, cb=None: [{"start": 0, "end": 3, "text": "", "words": words[:30]}]
new_job(5, 20, "review")
R.run_job(5)
assert job(5).status == "done" and "trop court" in job(5).log and "condensation" not in job(5).edit_note

# 7. version anglaise demandée avec le traitement : mise en file à la fin, avec les réglages par défaut
R.transcribe_words = lambda wav, dur, cb=None: [{"start": 0, "end": TOTAL, "text": "", "words": words}]
new_job(6, 0, "auto", "review")
R.run_job(6)
with SessionLocal() as s:
    en = s.query(EnVersion).filter(EnVersion.job_id == 6).one()
    assert (en.status, en.mode, en.created_by, en.translator, en.engine) == ("pending", "review", "u", "local", "chatterbox-nano") and en.text_json is None
assert job(6).status == "done" and "Version anglaise mise en file" in job(6).log
print("ok")

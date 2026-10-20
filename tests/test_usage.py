"""Comptage des tokens de l'IA : `python tests/test_usage.py` (ou pytest). Réponses d'API simulées, aucun appel réseau."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.db import AiUsage, Folder, Job, SessionLocal, init_db  # noqa: E402
from app.pipeline import detect  # noqa: E402
from app.pipeline.run import Reporter  # noqa: E402


def fake(payload):
    return lambda *a, **k: httpx.Response(200, json=payload, request=httpx.Request("POST", "http://x"))


seen, LLM = [], {"key": "sk-ant-x", "model": "claude-sonnet-5-5"}
detect.httpx.post = fake({"content": [{"text": "ok"}], "usage": {"input_tokens": 120, "output_tokens": 7}})
assert detect.ask_llm("hi", LLM, on_usage=lambda i, o: seen.append((i, o))) == "ok" and seen == [(120, 7)]

detect.httpx.post = fake({"content": [{"text": "ok"}]})  # réponse sans « usage » : 0, pas de plantage
detect.ask_llm("hi", LLM, on_usage=lambda i, o: seen.append((i, o)))
assert seen[-1] == (0, 0)

init_db()
with SessionLocal() as s:  # le cumul se fait en base, appel après appel
    s.add(Folder(name="f")); s.flush()
    s.add(Job(folder_id=1, youtube_url="u", title="t", date="2026-01-01", filename="t")); s.commit()
rep = Reporter(1, "alice")
rep.tokens(100, 10); rep.tokens(50, 5)
with SessionLocal() as s:
    j = s.get(Job, 1)
    assert (j.tokens_in, j.tokens_out) == (150, 15) and j.log.count("IA :") == 2
    rows = s.query(AiUsage).all()  # et chaque appel est inscrit au registre, à qui il est facturé
    assert [(r.username, r.job_id, r.tokens_in, r.tokens_out) for r in rows] == [("alice", 1, 100, 10), ("alice", 1, 50, 5)]
print("ok")

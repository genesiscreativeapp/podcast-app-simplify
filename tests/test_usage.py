"""Comptage des tokens de l'IA : `python tests/test_usage.py` (ou pytest). Réponses d'API simulées, aucun appel réseau."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import config  # noqa: E402
from app.db import Job, SessionLocal, Folder, init_db  # noqa: E402
from app.pipeline import detect  # noqa: E402
from app.pipeline.run import Reporter  # noqa: E402


def fake(payload):
    return lambda *a, **k: httpx.Response(200, json=payload, request=httpx.Request("POST", "http://x"))


seen = []
detect.httpx.post = fake({"content": [{"text": "ok"}], "usage": {"input_tokens": 120, "output_tokens": 7}})
assert detect.ask_llm("hi", key="sk-ant-x", on_usage=lambda i, o: seen.append((i, o))) == "ok" and seen == [(120, 7)]

config.LLM_PROVIDER = "openai"
detect.httpx.post = fake({"choices": [{"message": {"content": "yo"}}], "usage": {"prompt_tokens": 30, "completion_tokens": 5}})
assert detect.ask_llm("hi", on_usage=lambda i, o: seen.append((i, o))) == "yo" and seen[-1] == (30, 5)

detect.httpx.post = fake({"choices": [{"message": {"content": "yo"}}]})  # API sans « usage » : 0, pas de plantage
detect.ask_llm("hi", on_usage=lambda i, o: seen.append((i, o)))
assert seen[-1] == (0, 0)

init_db()
with SessionLocal() as s:  # le cumul se fait en base, appel après appel
    s.add(Folder(name="f")); s.flush()
    s.add(Job(folder_id=1, youtube_url="u", title="t", date="2026-01-01", filename="t")); s.commit()
rep = Reporter(1)
rep.tokens(100, 10); rep.tokens(50, 5)
with SessionLocal() as s:
    j = s.get(Job, 1)
    assert (j.tokens_in, j.tokens_out) == (150, 15) and j.log.count("IA :") == 2
print("ok")

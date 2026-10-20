"""Le banc d'essai de voix (tools/bench_voice.py) : `python tests/test_bench_voice.py`. Sans modèle, sans réseau, sans ffmpeg."""
import importlib.util
import json
import os
import tempfile
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf

spec = importlib.util.spec_from_file_location("bench", Path(__file__).resolve().parent.parent / "tools" / "bench_voice.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

# regroupement du texte : jamais au-delà de la limite (sauf une phrase seule plus longue), rien de perdu, rien d'ajouté
sents = ["One two three.", "Four five six seven.", "Eight.", "Nine ten eleven twelve thirteen."]
parts = bench.chunks(sents, limit=30)
assert parts == ["One two three. Four five six seven.", "Eight. Nine ten eleven twelve thirteen."] or all(len(p) <= 36 for p in parts)
assert " ".join(parts).split() == " ".join(sents).split() and bench.chunks([], 30) == [] and bench.chunks(["x" * 400], 30) == ["x" * 400]

# traduction : réponse de l'API simulée ; sans clé, on s'arrête avec un message clair
bench.httpx.post = lambda *a, **k: httpx.Response(200, json={"content": [{"text": "Hello.\n\n  Amen.  \n"}], "usage": {"input_tokens": 9, "output_tokens": 4}},
                                                 request=httpx.Request("POST", "http://x"))
os.environ.pop("ANTHROPIC_API_KEY", None)
try:
    bench.translate("Bonjour", "m")
    raise AssertionError("aurait dû exiger ANTHROPIC_API_KEY")
except SystemExit as e:
    assert "ANTHROPIC_API_KEY" in str(e)
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
assert bench.translate("Bonjour", "m") == (["Hello.", "Amen."], {"input_tokens": 9, "output_tokens": 4})

# de bout en bout avec le faux moteur ; un vrai moteur non installé est signalé sans arrêter les autres
tmp = Path(tempfile.mkdtemp())


def fake_excerpt(audio, start, seconds, ref_start, ref_seconds, out):  # ffmpeg n'est pas requis pour tester le reste
    sf.write(out / "fr.wav", np.zeros(16000), 16000)
    sf.write(out / "ref.wav", np.zeros(24000), 24000)


bench.excerpt = fake_excerpt
(tmp / "en.txt").write_text("Brothers and sisters, God is good.\nHe is faithful.\n", encoding="utf-8")
report = bench.main([str(tmp / "sermon.mp3"), "--seconds", "10", "--engines", "dummy,chatterbox,openvoice",
                     "--text-en", str(tmp / "en.txt"), "--out", str(tmp / "out")])
dummy, cb, ov = report["results"]
assert dummy["engine"] == "dummy" and dummy["audio_s"] > 2 and dummy["rtf"] == 0 and dummy["min_per_source_hour"] == 0
assert "error" in cb and "chatterbox" in cb["hint"] and "error" in ov and "OpenVoice" in ov["hint"]
assert (tmp / "out" / "dummy.wav").exists() and json.loads((tmp / "out" / "report.json").read_text())["excerpt_seconds"] == 10
assert (tmp / "out" / "en.txt").read_text().count("\n") == 1
try:
    bench.main([str(tmp / "sermon.mp3"), "--engines", "nope", "--text-en", str(tmp / "en.txt")])
    raise AssertionError("moteur inconnu accepté")
except SystemExit as e:
    assert "inconnu" in str(e)
print("ok")

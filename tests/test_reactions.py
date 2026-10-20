"""Réactions du public : `python tests/test_reactions.py` (ou pytest). Audio synthétique : voix = bruit fort, applaudissements = bruit plus faible."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from app.pipeline.edit import edit_file, reaction_cuts  # noqa: E402

SR, rng = 8000, np.random.default_rng(1)
words, parts, t = [], [], 0.0


def add(text, dur, amp, gap=0.15, spoken=True):
    """Ajoute `dur` s de bruit d'amplitude `amp` (un mot si `spoken`, sinon du son que Whisper ne transcrit pas), puis `gap` s de silence."""
    global t
    parts.append(rng.normal(0, amp, int(dur * SR)))
    if spoken:
        words.append({"word": text, "start": t, "end": t + dur})
    parts.append(rng.normal(0, 0.0005, int(gap * SR)))
    t += dur + gap


for _ in range(12):
    add("Dieu", 0.4, 0.2)
add("", 3.0, 0.1, spoken=False)          # applaudissements : du son, aucun mot, 3 s
for _ in range(12):
    add("foi", 0.4, 0.2)
add("Amen", 0.5, 0.2, gap=0.6)           # « Amen » du prédicateur : fort, il reste
add("Amen", 0.5, 0.03, gap=0.6)          # « Amen » de l'assemblée : faible, isolé, il part
for _ in range(12):
    add("grâce", 0.4, 0.2)
total = t
wav = Path(os.environ["DATA_DIR"]) / "in.wav"
sf.write(wav, np.concatenate(parts).astype("float32"), SR)
audio = np.concatenate(parts).astype("float32")

cuts = reaction_cuts(audio, SR, words, 0.45)
assert len(cuts) == 2, cuts
(a1, b1), (a2, b2) = sorted(cuts)
assert 6.6 < a1 < 7 and 9.3 < b1 < 9.6, cuts                     # les applaudissements, ramenés à une pause
assert abs(a2 - words[-13]["start"]) < 0.01 and b2 - a2 < 0.7, cuts  # le seul « Amen » faible
assert reaction_cuts(audio, SR, [], 0.45) == []

out = Path(os.environ["DATA_DIR"]) / "out.wav"
off = edit_file(wav, out, words, 5.0, 0.45, False, False)           # pauses longues tolérées : seules les réactions raccourcissent
on = edit_file(wav, out, words, 5.0, 0.45, False, False, remove_reactions=True)
assert off["reactions"] == 0 and on["reactions"] == 2, (off, on)
assert 3.0 < off["after"] - on["after"] < 4.2, (off["after"], on["after"])
print("ok")

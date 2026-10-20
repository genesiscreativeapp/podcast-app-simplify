"""Condensation d'une prédication : `python tests/test_condense.py` (ou pytest). Texte et audio synthétiques, sans IA réelle."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from app.pipeline import condense as C  # noqa: E402
from app.pipeline.edit import edit_file  # noqa: E402

WORD, PAUSE, N = 0.4, 0.5, 140   # ~ 7 minutes : introduction (60 s) et conclusion (90 s) laissent un milieu libre


def sentence(k, extra=None):
    """Phrase k : 6 mots porteurs de sens, tous distincts d'une phrase à l'autre ; `extra` remplace un mot (même idée, un mot de plus)."""
    w = [f"{k:03d}w{j}" for j in range(6)]
    if extra:
        w[5] = extra
    return w


texts = {k: sentence(k) for k in range(N)}
texts[70] = sentence(68, "neuf")        # reprise de la phrase 68 (5 mots sur 6 identiques)
texts[74] = sentence(73, "autre")       # reprise de la phrase 73, un peu plus loin
texts[80] = ["Vous", "voyez?"]          # formule de remplissage
texts[76] = ["Lisons", "Jean", "3", "verset", "16."]   # annonce d'une lecture : elle et les 3 phrases suivantes sont protégées
texts[78] = sentence(75, "dix")         # reprise... mais dans la lecture : à ne pas retirer
texts[85] = ["Amen."]
texts[5] = sentence(4, "zero")          # reprise dans l'introduction (60 premières secondes) : protégée
texts[135] = sentence(134, "un")          # reprise dans la conclusion (90 dernières secondes) : protégée

words, t = [], 0.0
for k in range(N):
    toks = texts[k]
    for n, tok in enumerate(toks):
        last = n == len(toks) - 1
        words.append({"start": t, "end": t + WORD, "word": " " + tok + ("." if last and not tok.endswith((".", "?")) else "")})
        t += WORD
    t += PAUSE
TOTAL = t

# --- phrases : une par groupe de mots terminé par un point, avec l'intervalle à couper pour la retirer
sents = C.build_sentences(words)
assert len(sents) == N and sents[0]["start"] == 0 and all(s["id"] == i for i, s in enumerate(sents))
assert sents[1]["text"].startswith("001w0") and abs(sents[70]["end"] - sents[70]["start"] - 6 * WORD) < 1e-6
assert all(sents[i]["cut"][1] <= sents[i + 1]["start"] for i in range(N - 1))           # on ne mord jamais sur la phrase suivante
assert all(s["cut"][0] == s["start"] and s["cut"][1] > s["end"] for s in sents[:-1])    # la phrase entière part, avec sa pause
kept = C.build_sentences(words, exclude=[(sents[10]["start"], sents[12]["end"])])      # déjà retirées par ailleurs : ignorées
assert len(kept) == N - 3 and all(s["id"] == i for i, s in enumerate(kept))
long_run = [{"start": i * 0.3, "end": i * 0.3 + 0.2, "word": "mot"} for i in range(100)]   # sans ponctuation ni pause : coupé par longueur
assert [len(s["text"].split()) for s in C.build_sentences(long_run)] == [45, 45, 10]

# --- protections
prot = C.protected_ids(sents)
assert {5, 135, 0, N - 1} <= prot and {76, 77, 78, 79} <= prot and 85 in prot and not (prot & {68, 70, 73, 74, 80})

# --- sans IA : seules les redites sûres et les formules creuses sont candidates
cands = {i: (why, because) for _s, i, why, because in C.candidates(sents, prot)}
assert cands == {70: ("redite", 68), 74: ("redite", 73), 80: ("formule de remplissage", None)}, cands
logs = []
p10 = C.propose(sents, 10, None, logs.append)
assert p10["method"] == "heuristique" and set(p10["removed"]) == {70, 74, 80} and p10["saved_s"] > 0 and logs == []
assert p10["removed"][70]["reason"] == "redite de la phrase 68" and p10["key_points"] is None
assert p10["saved_s"] < p10["target_s"]                                                # pas assez de redites sûres : on coupe moins que demandé
p1 = C.propose(sents, 1, None, logs.append)
assert set(p1["removed"]) == {70, 74} and p1["saved_s"] >= p1["target_s"]       # objectif atteint avec les 2 redites les plus sûres : on s'arrête avant la formule creuse
assert C.propose(sents, 30, None, logs.append)["removed"].keys() == p10["removed"].keys()   # jamais plus que le sûr, même à −30 %

# --- avec IA : elle choisit, mais ne lève aucune protection ; ses points clés sont gardés
def fake(answer):
    def ask(prompt, llm, max_tokens=400, on_usage=None):
        assert llm == {"key": "k", "model": "m"} and "[PROTÉGÉ]" in prompt and "[70]" in prompt
        if on_usage:
            on_usage(100, 20)
        if isinstance(answer, Exception):
            raise answer
        return answer
    return ask


used = []
C.ask_llm = fake('Voici : {"retirer": [{"de": 70, "a": 70, "raison": "redit la 68"}, {"de": 78, "a": 78}, {"de": 5, "a": 5}], '
                 '"points_cles": ["Dieu est fidèle", "  "]}')
ai = C.propose(sents, 1, {"key": "k", "model": "m"}, logs.append, lambda i, o: used.append((i, o)))
assert ai["method"] == "IA" and set(ai["removed"]) == {70} and ai["removed"][70]["by"] == "IA" and ai["removed"][70]["reason"] == "redit la 68"
assert ai["key_points"] == ["Dieu est fidèle"] and used == [(100, 20)]
ai10 = C.propose(sents, 10, {"key": "k", "model": "m"}, logs.append)                   # IA trop timide : l'heuristique complète
assert ai10["method"] == "IA + heuristique" and set(ai10["removed"]) == {70, 74, 80} and ai10["removed"][74]["by"] == "heuristique"
C.ask_llm = fake('{"retirer": [{"de": 25, "a": 100}]}')                                  # trop gourmande : plafonnée, protections respectées
big = C.propose(sents, 5, {"key": "k", "model": "m"}, logs.append)
assert big["saved_s"] <= big["target_s"] * C.AI_MARGIN and not (set(big["removed"]) & prot) and big["removed"]
for bad in (RuntimeError("API 529"), "pas de JSON ici"):                                # IA en panne ou illisible : même résultat que sans IA
    C.ask_llm = fake(bad)
    logs.clear()
    fb = C.propose(sents, 10, {"key": "k", "model": "m"}, logs.append)
    assert fb["method"] == "heuristique" and set(fb["removed"]) == {70, 74, 80} and "heuristique" in logs[0]

# --- l'audio : retirer des phrases raccourcit exactement de leur durée, sans toucher à l'ordre des autres
sr = 8000
sf.write(Path(os.environ["DATA_DIR"]) / "in.wav", (0.1 * np.sin(2 * np.pi * 220 * np.arange(int(TOTAL * sr)) / sr)).astype("float32"), sr)
cuts = C.cuts_for(sents, p10["removed"])
assert len(cuts) == 3 and all(a < b for a, b in cuts)
stats = edit_file(Path(os.environ["DATA_DIR"]) / "in.wav", Path(os.environ["DATA_DIR"]) / "out.wav", words, 0.8, 0.45,
                  False, False, cuts)
assert abs(stats["before"] - TOTAL) < 0.01 and abs((stats["before"] - stats["after"]) - sum(b - a for a, b in cuts)) < 0.15, stats
assert C.cuts_for(sents, []) == []
print("ok")

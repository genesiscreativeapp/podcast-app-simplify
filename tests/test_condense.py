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


def to_words(sentence_tokens):
    """Liste de phrases (listes de mots) → mots horodatés, comme en sortie de Whisper (ponctuation finale, pause entre phrases)."""
    words, t = [], 0.0
    for toks in sentence_tokens:
        for n, tok in enumerate(toks):
            words.append({"start": t, "end": t + WORD, "word": " " + tok + ("." if n == len(toks) - 1 and not tok.endswith((".", "?")) else "")})
            t += WORD
        t += PAUSE
    return words, t


def unique(k, extra=None):
    """Phrase k : 6 mots porteurs de sens, tous distincts d'une phrase à l'autre ; `extra` remplace le dernier (même idée, un mot de plus)."""
    w = [f"{k:03d}w{j}" for j in range(6)]
    if extra:
        w[5] = extra
    return w


texts = {k: unique(k) for k in range(N)}
texts[70] = unique(68, "neuf")        # reprise de la phrase 68
texts[74] = unique(73, "autre")       # reprise de la phrase 73, un peu plus loin
texts[80] = ["Vous", "voyez?"]          # formule de remplissage
texts[76] = ["Lisons", "Jean", "3", "verset", "16."]   # annonce d'une lecture : elle et les 3 phrases suivantes sont protégées
texts[78] = unique(75, "dix")         # reprise... mais dans la lecture : à ne pas retirer
texts[85] = ["Amen."]
texts[5] = unique(4, "zero")          # reprise dans l'introduction (60 premières secondes) : protégée
texts[135] = unique(134, "un")        # reprise dans la conclusion (90 dernières secondes) : protégée
words, TOTAL = to_words([texts[k] for k in range(N)])

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
dur = lambda ids: sum(C.duration(sents[i]) for i in ids)
free = [i for i in range(N) if i not in prot]

# --- sans IA : d'abord ce qui n'apporte aucune idée, puis ce qui en coûte le moins par seconde gagnée
rm, cov = C.coverage_removal(sents, prot, 6.0)
DUPES = {70, 74, 75, 80}   # 70 reprend 68, 74 reprend 73, 75 reprend 78 (protégée : on retire la 75), 80 est une formule creuse
assert len(rm) == 3 and set(rm) < DUPES and 80 in rm and rm[80]["reason"] == "formule de remplissage" and 0.95 < cov <= 1   # presque rien perdu
assert rm[74]["by"] == "heuristique" and rm[74]["because"] == 73 and "phrase 73" in rm[74]["reason"]
assert C.coverage_removal(sents, prot, 0.0) [0] == {}                                   # objectif nul : rien
last_cov = 1.0
for pct in (10, 20, 40):                                                                 # les objectifs élevés sont atteints, les protections tiennent
    target = TOTAL * pct / 100
    rm, cov = C.coverage_removal(sents, prot, target)
    saved = dur(rm)
    assert target <= saved < target + 3.5 and not (set(rm) & prot) and cov < last_cov, (pct, saved, target)   # à une phrase près
    last_cov = cov
assert DUPES <= set(C.coverage_removal(sents, prot, TOTAL * 0.10)[0])                     # les reprises partent toujours en premier
rm, cov = C.coverage_removal(sents, prot, TOTAL * 0.80)                                  # objectif impossible : tout le non-protégé, honnêtement
assert set(rm) == set(free) and dur(rm) < TOTAL * 0.80 and not (set(rm) & prot) and 0 < cov < last_cov
rm2, _ = C.coverage_removal(sents, prot, TOTAL * 0.2, already={70: {"reason": "x", "because": None, "by": "IA"}})
assert rm2[70]["by"] == "IA" and dur(rm2) >= TOTAL * 0.2                                 # ce que l'IA a déjà retiré compte dans l'objectif

# --- un texte français réaliste : les reprises en mots différents partent, les idées uniques restent
mid = ["La foi vient de ce que l'on entend, et ce que l'on entend vient de la parole de Dieu.",      # 0
       "Mes frères, la foi vient par l'écoute de la parole de Dieu.",                                # 1 : reprend 0
       "Abraham a quitté son pays sans savoir où il allait.",                                        # 2
       "Dieu a appelé Abraham, et Abraham est parti sans savoir où il allait.",                      # 3 : reprend 2
       "Aujourd'hui, Dieu vous appelle à sortir de votre zone de confort.",                          # 4
       "Vous voyez ?",                                                                                # 5
       "Dieu vous appelle aujourd'hui à sortir de votre zone de confort.",                           # 6 : reprend 4
       "La prière change les situations les plus difficiles.",                                       # 7
       "Mon frère, quand tu pries, les situations difficiles changent.",                             # 8 : reprend 7
       "Le pardon libère le cœur de l'amertume.",                                                    # 9
       "Un cœur plein d'amertume ne peut pas recevoir la bénédiction de Dieu.",                      # 10
       "Il faut donc pardonner pour être libre."]                                                    # 11
fill = lambda a, b: [unique(k) for k in range(a, b)]
real_words, real_total = to_words(fill(0, 22) + [m.split() for m in mid] + fill(100, 135))
real = C.build_sentences(real_words)
base = 22
mids = list(range(base, base + 12))
assert len(real) == 22 + 12 + 35 and all(real[base + k]["text"].startswith(mid[k].split()[0]) for k in range(12))
real_prot = C.protected_ids(real)
assert not (real_prot & set(mids))                                                       # le milieu n'est pas protégé
rm, cov = C.coverage_removal(real, real_prot, 14.0)
gone = {i - base for i in rm}
assert gone <= set(range(12)) and 5 in gone                                              # seulement dans le milieu, « Vous voyez ? » en tête
for a, b in ((0, 1), (2, 3), (4, 6), (7, 8)):
    assert len({a, b} & gone) <= 1, (a, b, gone)                                         # jamais les DEUX phrases qui disent la même chose
assert gone & {0, 1, 2, 3, 4, 6, 7, 8} and not ({9, 10, 11} & gone) and cov > 0.9       # des reprises partent ; les idées uniques sont conservées
rm_all, _ = C.coverage_removal(real, real_prot, 60.0)                                    # même en coupant beaucoup plus : chaque idée reste dite au moins une fois
assert all(len({a + base, b + base} & set(rm_all)) <= 1 for a, b in ((0, 1), (2, 3), (4, 6), (7, 8))) or len(rm_all) > 12

# --- avec IA : elle choisit, mais ne lève aucune protection ; ses points clés sont gardés ; l'heuristique complète si elle coupe trop peu
def fake(answer):
    def ask(prompt, llm, max_tokens=400, on_usage=None):
        assert llm == {"key": "k", "model": "m"} and "[PROTÉGÉ]" in prompt and "[70]" in prompt and "jamais un point principal" in prompt
        if on_usage:
            on_usage(100, 20)
        if isinstance(answer, Exception):
            raise answer
        return answer
    return ask


logs, used, LLM = [], [], {"key": "k", "model": "m"}
C.ask_llm = fake('Voici : {"retirer": [{"de": 70, "a": 70, "raison": "redit la 68"}, {"de": 74, "a": 74}, {"de": 80, "a": 80}, {"de": 60, "a": 61}, '
                 '{"de": 78, "a": 78}, {"de": 5, "a": 5}], "points_cles": ["Dieu est fidèle", "  "]}')
ai = C.propose(sents, 3, LLM, logs.append, lambda i, o: used.append((i, o)))
assert ai["method"] == "IA" and set(ai["removed"]) == {60, 61, 70, 74, 80} and ai["removed"][70]["reason"] == "redit la 68"   # 78 et 5 : protégées, ignorées
assert ai["key_points"] == ["Dieu est fidèle"] and used == [(100, 20)] and ai["target_s"] * 0.85 <= ai["saved_s"] <= ai["target_s"] * 1.15
assert 0 < ai["coverage"] <= 1
C.ask_llm = fake('{"retirer": [{"de": 70, "a": 70}]}')                                    # IA trop timide : l'heuristique complète jusqu'à l'objectif
timid = C.propose(sents, 10, LLM, logs.append)
assert timid["method"] == "IA + heuristique" and timid["removed"][70]["by"] == "IA" and timid["saved_s"] >= timid["target_s"]
assert sum(1 for r in timid["removed"].values() if r["by"] == "heuristique") > 3
C.ask_llm = fake('{"retirer": [{"de": 25, "a": 100}]}')                                   # trop gourmande : plafonnée, protections respectées
big = C.propose(sents, 5, LLM, logs.append)
assert big["saved_s"] <= big["target_s"] * C.AI_MARGIN and not (set(big["removed"]) & prot) and big["removed"]
for bad in (RuntimeError("API 529"), "pas de JSON ici"):                                  # IA en panne ou illisible : même résultat que sans IA
    C.ask_llm = fake(bad)
    logs.clear()
    fb = C.propose(sents, 10, LLM, logs.append)
    plain = C.propose(sents, 10, None, logs.append)
    assert fb["method"] == "heuristique" and set(fb["removed"]) == set(plain["removed"]) and "heuristique" in logs[0]
p40 = C.propose(sents, 40, None, logs.append)
assert p40["saved_s"] >= p40["target_s"] > 100 and p40["method"] == "heuristique"          # et à −40 %, sans IA, l'objectif est atteint

# --- l'audio : retirer des phrases raccourcit exactement de leur durée, sans toucher à l'ordre des autres
sr = 8000
wav = Path(os.environ["DATA_DIR"]) / "in.wav"
sf.write(wav, (0.1 * np.sin(2 * np.pi * 220 * np.arange(int(TOTAL * sr)) / sr)).astype("float32"), sr)
p10 = C.propose(sents, 10, None, logs.append)
cuts = C.cuts_for(sents, p10["removed"])
assert len(cuts) == len(p10["removed"]) and all(a < b for a, b in cuts)
stats = edit_file(wav, Path(os.environ["DATA_DIR"]) / "out.wav", words, 0.8, 0.45, False, False, cuts)
assert abs(stats["before"] - TOTAL) < 0.01 and abs((stats["before"] - stats["after"]) - sum(b - a for a, b in cuts)) < 0.3, stats
assert C.cuts_for(sents, []) == []
print("ok")

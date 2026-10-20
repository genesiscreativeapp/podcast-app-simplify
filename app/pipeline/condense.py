"""Condensation d'une prédication : retire des PHRASES ENTIÈRES pour la raccourcir de 10 à 45 %, sans jamais changer l'ordre
ni réécrire quoi que ce soit.

- Sans IA : on retire d'abord ce qui n'apporte aucune idée nouvelle (reprises d'une idée déjà dite, formules de remplissage), puis,
  si l'objectif n'est pas atteint, les phrases dont la perte coûte le moins d'idées par seconde gagnée. Le texte qui reste garde
  autant que possible toutes les idées du sermon (le résultat indique la part des idées conservée).
- Avec une IA : elle choisit en lisant tout le texte ; si elle coupe trop peu, ou ne répond pas, l'heuristique complète.
Dans tous les cas : le début et la fin (introduction, conclusion, prière), les lectures bibliques et les « Amen » sont protégés.
L'audio est coupé aux limites des phrases (voir `cuts_for`).
"""
import heapq
import json
import math
import re
import unicodedata
from typing import Callable

from ..utils import fmt_time
from .detect import ask_llm

BREAK_GAP = 1.0     # pause (s) qui termine une phrase même sans ponctuation
MAX_WORDS = 45      # une phrase plus longue est coupée
HEAD, TAIL = 60.0, 90.0   # secondes de début et de fin jamais touchées : introduction, conclusion, prière
AI_CHUNK = 500      # phrases envoyées par requête à l'IA
AI_MARGIN = 1.15    # l'IA ne peut pas retirer plus de 115 % de l'objectif
AI_MIN = 0.85       # en dessous de 85 % de l'objectif, l'heuristique complète le travail de l'IA

STOP = set("""le la les un une des du de d l et ou mais donc or ni car que qui quoi dont ce cet cette ces se sa son ses ma mon mes ta
ton tes notre nos votre vos leur leurs je tu il elle on nous vous ils elles me te lui y en a as ai ont est es sont suis sommes etes
etait ete etre avoir fait faire dit dire plus pas ne non oui si comme tout tous toute toutes tres bien alors aussi avec sans sur sous
dans par pour au aux cela ca ceci voila c j m n s t qu""".split())
LITURGY = set("amen alleluia gloire hosanna merci jesus christ seigneur dieu louange a".split())
SCRIPTURE = re.compile(
    r"\b(versets?|chapitres?|psaumes?|ecritures?|la bible|epitres?|lisons|ouvrons|il est ecrit|est ecrit)\b"
    r"|\b(genese|exode|levitique|nombres|deuteronome|josue|juges|samuel|rois|chroniques|esdras|nehemie|esther|job|proverbes|ecclesiaste|"
    r"cantique|esaie|isaie|jeremie|lamentations|ezechiel|daniel|osee|joel|amos|abdias|jonas|michee|nahum|habacuc|sophonie|aggee|zacharie|"
    r"malachie|matthieu|marc|luc|jean|actes|romains|corinthiens|galates|ephesiens|philippiens|colossiens|thessaloniciens|timothee|tite|"
    r"philemon|hebreux|jacques|pierre|jude|apocalypse)\s+\d")
HOLLOW = re.compile(r"^(vous voyez|n est ce pas|voyez vous|vous comprenez|comprenez vous|tu vois|d accord|voila|bon|alors|donc|enfin|"
                    r"eh bien|ecoutez|regardez|hein|je dis bien|je repete|je disais|ok|c est ca)$")

PROMPT = """Voici les phrases numérotées d'une prédication chrétienne en français{part}.

Ta tâche : proposer des phrases ENTIÈRES à retirer pour raccourcir ce passage d'environ {pct} % (soit environ {seconds} secondes),
SANS changer l'ordre et en gardant le sens du message. Atteins l'objectif : si les redites ne suffisent pas, retire ensuite les passages
les moins essentiels (détails, exemples secondaires, développements répétitifs), jamais un point principal.

À retirer en priorité :
- une idée déjà exprimée juste avant ou un peu plus haut (garde la formulation la plus claire ou la plus forte) ;
- les reformulations successives de la même chose, les redites d'une illustration déjà racontée ;
- les digressions sans lien avec le message, les formules de remplissage (« vous voyez ? », « je dis bien »…).

Ne retire JAMAIS : les lectures et citations bibliques et la phrase qui annonce le texte, les points principaux (chaque idée garde au
moins une phrase qui l'exprime), les illustrations nécessaires à la compréhension, la conclusion et la prière, les « Amen » et
« Alléluia », ni les phrases marquées [PROTÉGÉ]. Chaque idée principale garde au moins une phrase qui l'exprime.

Réponds UNIQUEMENT avec un objet JSON, sans autre texte :
{{"retirer": [{{"de": 12, "a": 14, "raison": "redit l'idée de la phrase 9"}}], "points_cles": ["…", "…"]}}
"de" et "a" sont des numéros de phrases inclus. « points_cles » : les idées principales de CE passage, en une courte phrase chacune.

Phrases :
{transcript}"""


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _norm(text))


def stems(text: str) -> set[str]:
    """Mots porteurs de sens, ramenés à leurs 6 premières lettres (pluriels, conjugaisons)."""
    return {t[:6] for t in _tokens(text) if len(t) >= 3 and t not in STOP}


def duration(s: dict) -> float:
    return s["cut"][1] - s["cut"][0]


# --- Phrases -----------------------------------------------------------------------------------------------------
def build_sentences(words: list[dict], exclude=()) -> list[dict]:
    """Découpe les mots (avec horodatages) en phrases : ponctuation finale, longue pause, ou longueur maximale.
    Les phrases déjà retirées (`exclude` : intervalles en secondes) sont ignorées. Chaque phrase porte `cut`, l'intervalle à
    couper pour la retirer : de son début à la reprise de la parole, en gardant 0,2 s de pause."""
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        gap = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else BREAK_GAP
        if w["word"].strip()[-1:] in ".!?…" or gap >= BREAK_GAP or len(cur) >= MAX_WORDS:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    sents = []
    for g in groups:
        start, end = g[0]["start"], g[-1]["end"]
        if any(a <= (start + end) / 2 <= b for a, b in exclude):
            continue
        sents.append({"start": start, "end": end, "text": " ".join(w["word"].strip() for w in g)})
    for i, s in enumerate(sents):
        nxt = sents[i + 1]["start"] if i + 1 < len(sents) else s["end"] + 0.3
        s["id"] = i
        s["cut"] = [s["start"], min(max(s["end"] + 0.1, nxt - 0.2), max(nxt, s["end"]))]
    return sents


def protected_ids(sents: list[dict]) -> set[int]:
    """Phrases qu'on ne retire jamais : début et fin, lectures bibliques (l'annonce et les 3 phrases qui suivent), « Amen »…"""
    if not sents:
        return set()
    t0, t1, keep = sents[0]["start"], sents[-1]["end"], set()
    for i, s in enumerate(sents):
        n = _norm(s["text"])
        if s["end"] - t0 < HEAD or t1 - s["start"] < TAIL:
            keep.add(i)
        words = re.findall(r"[a-z]+", n)
        if words and set(words) <= LITURGY:
            keep.add(i)
        if SCRIPTURE.search(n):
            keep.update(range(i, min(i + 4, len(sents))))
    return keep


# --- Sans IA : on perd le moins d'idées possible par seconde gagnée -------------------------------------------------------
def coverage_removal(sents: list[dict], prot: set[int], target_s: float, already: dict[int, dict] | None = None) -> tuple[dict[int, dict], float]:
    """Retire des phrases jusqu'à l'objectif. À chaque pas, on retire la phrase qui coûte le moins d'idées par seconde gagnée : les idées
    (mots porteurs de sens, pondérés par leur rareté dans le sermon) qu'aucune autre phrase conservée n'exprime. Une reprise d'une idée
    déjà dite ne coûte rien et part la première, puis viennent les phrases de moins en moins originales. Les phrases protégées restent.
    → (phrases retirées, part des idées conservée entre 0 et 1). L'objectif peut ne pas être atteint s'il ne reste que du protégé."""
    n = len(sents)
    terms = [set() if HOLLOW.match(" ".join(_tokens(s["text"]))) else stems(s["text"]) for s in sents]  # une formule creuse n'a aucune idée
    df = {}
    for t in terms:
        for w in t:
            df[w] = df.get(w, 0) + 1
    idf = {w: math.log(1 + n / k) for w, k in df.items()}  # un mot rare pèse plus qu'un mot qui revient partout
    count = dict(df)  # nombre de phrases conservées qui expriment chaque mot
    where = {}
    for i, t in enumerate(terms):
        for w in t:
            where.setdefault(w, []).append(i)
    removed = dict(already or {})
    for i in removed:
        for w in terms[i]:
            count[w] -= 1
    saved = sum(duration(sents[i]) for i in removed)
    loss = lambda i: sum(idf[w] for w in terms[i] if count[w] == 1)  # idées que cette phrase est seule à porter
    heap = [(loss(i) / max(duration(sents[i]), 0.1), -i, i) for i in range(n) if i not in prot and i not in removed]  # à égalité : la reprise, pas l'original
    heapq.heapify(heap)
    while heap and saved < target_s:
        ratio, _, i = heapq.heappop(heap)
        now = loss(i) / max(duration(sents[i]), 0.1)
        if now > ratio + 1e-12:  # des phrases retirées depuis ont rendu celle-ci plus précieuse : on la repose avec sa vraie valeur
            heapq.heappush(heap, (now, -i, i))
            continue
        for w in terms[i]:
            count[w] -= 1
        # pour l'affichage : la phrase conservée qui exprime le plus de ses idées
        best, best_w = None, 0.0
        for j in {j for w in terms[i] for j in where[w]}:
            if j != i and j not in removed:
                w_ = sum(idf[w] for w in terms[i] & terms[j])
                if w_ > best_w:
                    best, best_w = j, w_
        if not terms[i]:
            why = "formule de remplissage"
        elif now == 0:
            why = f"reprise d'idées déjà dites (phrase {best})" if best is not None else "reprise d'idées déjà dites"
        else:
            why = "idées secondaires" + (f", proches de la phrase {best}" if best is not None and best_w > 0 else "")
        removed[i] = {"reason": why, "because": best, "by": "heuristique"}
        saved += duration(sents[i])
    total_w = sum(idf.values()) or 1.0
    return removed, sum(idf[w] for w, k in count.items() if k > 0) / total_w


# --- Avec IA ------------------------------------------------------------------------------------------------------
def ask_ai(sents: list[dict], prot: set[int], target_s: float, llm: dict, on_usage=None) -> tuple[dict[int, dict], list[str]]:
    """Phrases à retirer choisies par l'IA, et les points clés qu'elle y a repérés. Lève une exception si elle ne répond pas."""
    total = sum(duration(s) for s in sents) or 1.0
    removed, points = {}, []
    spans = [range(i, min(i + AI_CHUNK, len(sents))) for i in range(0, len(sents), AI_CHUNK)]
    for n, rng in enumerate(spans, 1):
        part_s = sum(duration(sents[i]) for i in rng)
        lines = [f"[{i}] {fmt_time(sents[i]['start'])[2:]} {'[PROTÉGÉ] ' if i in prot else ''}{sents[i]['text']}" for i in rng]
        prompt = PROMPT.format(part=f" (partie {n} sur {len(spans)})" if len(spans) > 1 else "", pct=round(100 * target_s / total),
                               seconds=round(target_s * part_s / total), transcript="\n".join(lines))
        answer = ask_llm(prompt, llm, max_tokens=3000, on_usage=on_usage)
        match = re.search(r"\{.*\}", answer, re.S)
        if not match:
            raise ValueError(f"réponse illisible : {answer[:120]}")
        data = json.loads(match.group(0))
        for item in data.get("retirer", []):
            try:
                a, b = int(item["de"]), int(item["a"])
            except (KeyError, TypeError, ValueError):
                continue
            for i in range(max(a, rng.start), min(b, rng.stop - 1) + 1):
                if i not in prot:  # l'IA ne peut pas lever une protection
                    removed[i] = {"reason": str(item.get("raison", "")).strip() or "redite", "because": None, "by": "IA"}
        points += [str(p).strip() for p in data.get("points_cles", []) if str(p).strip()][:15]
    saved = 0.0
    for i in sorted(removed):  # garde-fou : l'IA ne dépasse pas son objectif de plus de 15 %
        saved += duration(sents[i])
        if saved > target_s * AI_MARGIN:
            del removed[i]
            saved -= duration(sents[i])
    return removed, points


def propose(sents: list[dict], pct: int, llm: dict | None, log: Callable[[str], None], on_usage=None) -> dict:
    """Propose les phrases à retirer pour raccourcir d'environ `pct` %. Fonctionne sans IA (llm=None)."""
    prot = protected_ids(sents)
    total = sum(duration(s) for s in sents)
    target = total * pct / 100
    removed, points, ai_ok = {}, None, False
    if llm:
        try:
            removed, points = ask_ai(sents, prot, target, llm, on_usage)
            ai_ok = True
        except Exception as exc:  # réseau, quota, JSON…
            log(f"Condensation par l'IA impossible ({exc}) : passage à l'heuristique")
            removed = {}
    saved = sum(duration(sents[i]) for i in removed)
    coverage = None
    if not ai_ok or saved < AI_MIN * target:  # sans IA, ou une IA trop timide : l'heuristique complète jusqu'à l'objectif
        removed, coverage = coverage_removal(sents, prot, target, removed)
        saved = sum(duration(sents[i]) for i in removed)
    if coverage is None:  # part des idées conservée, pour juger de la perte
        coverage = coverage_removal(sents, prot, 0.0, removed)[1]
    by = {r["by"] for r in removed.values()}
    method = "IA + heuristique" if by == {"IA", "heuristique"} else "IA" if by == {"IA"} or (ai_ok and not by) else "heuristique"
    return {"method": method, "target_s": round(target, 1), "total_s": round(total, 1), "saved_s": round(saved, 1), "coverage": round(coverage, 3),
            "removed": {i: removed[i] for i in sorted(removed)}, "key_points": points}


def cuts_for(sents: list[dict], ids) -> list[tuple[float, float]]:
    """Intervalles (secondes, dans l'audio d'origine) à couper pour retirer ces phrases."""
    keep = set(ids)
    return [(s["cut"][0], s["cut"][1]) for s in sents if s["id"] in keep]

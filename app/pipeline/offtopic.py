"""Retire d'une prédication les passages qui n'en font pas partie : témoignages, annonces, chants...

Une IA lit la transcription fine (une ligne numérotée par segment Whisper) et renvoie les plages de
lignes à retirer. On coupe donc exactement aux limites des segments, pas à 30 s près.
Sans IA configurée, ou si l'appel échoue, rien n'est retiré (le traitement continue).
"""
import json
import re
from typing import Callable

from ..utils import fmt_time
from .detect import ask_llm

CHUNK_LINES = 400      # lignes envoyées par requête (une longue prédication est lue en plusieurs fois)
MAX_REMOVED = 0.50     # au-delà, l'IA s'est probablement trompée : on ne retire rien (et on revient aux bornes d'origine)

PROMPT = """Voici la transcription d'une prédication chrétienne en français{part}. Chaque ligne est numérotée.

Repère les passages qui NE font PAS partie du message du prédicateur principal :
- moments d'ADORATION, de louange, de chants, prières d'adoration ou d'intercession, exclamations de ferveur (« Alléluia », « Gloire à Dieu », « Merci Jésus » répétés), temps de prière collective, même parlés, même dirigés par le prédicateur AVANT qu'il commence son enseignement (ou après sa conclusion) ;
- témoignages (récits personnels de fidèles ou d'invités) ;
- annonces et informations pratiques ; appels aux offrandes, dîmes, dons ;
- interventions d'une autre personne (animateur, interprète, intercesseur) ;
- bavardages sans rapport avec le message (problème de son, salutations hors message).

Le message commence quand le prédicateur se met à ENSEIGNER (introduction du sujet, lecture du texte). Tout ce qui précède, adoration comprise, doit être retiré, y compris au tout début de la transcription.

Ne retire JAMAIS (sois très prudent) : les illustrations, histoires ou exemples racontés par le prédicateur lui-même pour appuyer son message, la lecture biblique, ni sa prière de fin de message. En cas de doute, ne retire pas.

Réponds UNIQUEMENT avec un objet JSON, sans autre texte :
{{"retirer": [{{"de": 12, "a": 30, "type": "témoignage"}}]}}
"de" et "a" sont des numéros de lignes inclus. Liste vide s'il n'y a rien à retirer.

Transcription :
{transcript}"""


def _ask_chunk(lines: list[str], part: str, key: str | None, on_usage) -> list[dict]:
    answer = ask_llm(PROMPT.format(part=part, transcript="\n".join(lines)), max_tokens=1500, key=key, on_usage=on_usage)
    match = re.search(r"\{.*\}", answer, re.S)
    if not match:
        raise ValueError(f"réponse illisible : {answer[:120]}")
    return json.loads(match.group(0)).get("retirer", [])


def find_offtopic(segments: list[dict], log: Callable[[str], None], key: str | None = None,
                  on_usage=None) -> tuple[list[tuple[float, float]], str, bool]:
    """(plages à retirer en secondes, bilan lisible, ok). `ok` est faux si l'IA n'a pas pu répondre.
    `segments` : {start, end, text}."""
    if not segments:
        return [], "", True
    total = segments[-1]["end"] - segments[0]["start"]
    ranges, kinds, failed = [], [], False
    chunks = [range(i, min(i + CHUNK_LINES, len(segments))) for i in range(0, len(segments), CHUNK_LINES)]
    for n, rng in enumerate(chunks, 1):
        lines = [f"[{i}] {fmt_time(segments[i]['start'])[2:]} {segments[i]['text']}" for i in rng]
        part = f" (partie {n} sur {len(chunks)})" if len(chunks) > 1 else ""
        try:
            found = _ask_chunk(lines, part, key, on_usage)
        except Exception as exc:  # réseau, quota, JSON...
            log(f"Retrait des témoignages impossible ({exc})")
            failed = True
            continue
        for item in found:
            try:
                a, b = int(item["de"]), int(item["a"])
            except (KeyError, TypeError, ValueError):
                continue
            a, b = max(a, rng.start), min(b, rng.stop - 1)
            if a <= b:
                ranges.append((segments[a]["start"], segments[b]["end"]))
                kinds.append(str(item.get("type", "autre")).lower())
    removed = sum(e - s for s, e in ranges)
    if removed > MAX_REMOVED * total:
        log(f"L'IA propose de retirer {fmt_time(removed)} sur {fmt_time(total)} : jugé excessif, rien n'est retiré")
        return [], "", False
    if failed:
        return [], "", False
    if not ranges:
        return [], "aucun passage hors-sujet", True
    detail = " ; ".join(f"{fmt_time(s)[2:]}→{fmt_time(e)[2:]} {k}" for (s, e), k in list(zip(ranges, kinds))[:10])
    summary = ", ".join(f"{k} ×{kinds.count(k)}" for k in dict.fromkeys(kinds))
    return ranges, f"{len(ranges)} passage(s) retiré(s) ({summary}) : {fmt_time(removed)} — {detail}", True

"""Repérage du début et de la fin de la prédication dans le culte complet.

1. Si un LLM est configuré : il lit la transcription horodatée et renvoie les bornes.
2. Sinon (ou en cas d'échec) : heuristique basée sur le débit de parole.
   Une prédication = longue zone de parole dense ; la louange chantée a un débit
   de mots bien plus faible (notes tenues) et les annonces sont courtes.
"""
import json
import re

import httpx

from .. import config
from ..utils import fmt_time, parse_time

CHUNK = 30          # secondes par ligne de transcription envoyée au LLM
WORDS_PER_LINE = 35 # texte tronqué pour limiter les tokens (un culte de 3 h ≈ 18k tokens)

PROMPT = """Voici la transcription automatique et horodatée d'un culte chrétien en français diffusé sur YouTube{title}.
Chaque ligne couvre environ {chunk} secondes ; le texte est approximatif et tronqué.

Ta tâche : trouver le début et la fin de la PRÉDICATION principale (le message prêché par l'orateur principal).
- Le début est le moment où le prédicateur COMMENCE RÉELLEMENT À ENSEIGNER : introduction du sujet, lecture du texte biblique du message. Ce qui précède n'en fait pas partie : moments d'adoration, louange, chants, prières d'adoration ou d'intercession (même parlées, même dirigées par le prédicateur), annonces, offrandes, témoignages. Une longue suite de « Alléluia », « Gloire à Dieu », « Merci Jésus » est de l'adoration, pas le message.
- Si tu hésites sur le début, choisis un moment un peu PLUS TÔT : un traitement ultérieur retirera précisément ce qui n'est pas le message.
- La fin est la conclusion du message, y compris sa prière de fin. Exclus tout ce qui suit : appel, annonces, offrandes, chants, interventions d'autres personnes.

Réponds UNIQUEMENT avec un objet JSON, sans autre texte :
{{"start": "HH:MM:SS", "end": "HH:MM:SS", "raison": "explication courte"}}

Transcription :
{transcript}"""


def build_transcript(segments: list[dict]) -> str:
    buckets: dict[int, list[str]] = {}
    for s in segments:
        buckets.setdefault(int(s["start"] // CHUNK), []).append(s["text"])
    lines = []
    for idx in sorted(buckets):
        words = " ".join(buckets[idx]).split()
        text = " ".join(words[:WORDS_PER_LINE]) + (" …" if len(words) > WORDS_PER_LINE else "")
        lines.append(f"[{fmt_time(idx * CHUNK)}] {text}")
    return "\n".join(lines)


def _check_llm(r: httpx.Response) -> None:
    """Remonte le message de l'API (crédit épuisé, modèle inconnu, clé refusée…) au lieu d'un simple « 400 »."""
    if r.is_success:
        return
    try:
        msg = r.json()["error"]["message"]
    except Exception:
        msg = r.text[:300]
    raise RuntimeError(f"API {config.LLM_PROVIDER} {r.status_code} : {msg}")


def ask_llm(prompt: str, max_tokens: int = 400) -> str:
    timeout = httpx.Timeout(180.0)
    if config.LLM_PROVIDER == "anthropic":
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": config.LLM_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": config.LLM_MODEL or "claude-haiku-4-5-20251001", "max_tokens": max_tokens,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=timeout,
        )
        _check_llm(r)
        return "".join(b.get("text", "") for b in r.json()["content"])
    # API compatible OpenAI (OpenAI, Groq, OpenRouter, Ollama, LM Studio…)
    headers = {"content-type": "application/json"}
    if config.LLM_API_KEY:
        headers["authorization"] = f"Bearer {config.LLM_API_KEY}"
    r = httpx.post(
        f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
        headers=headers,
        json={"model": config.LLM_MODEL or "gpt-4o-mini", "temperature": 0,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=timeout,
    )
    _check_llm(r)
    return r.json()["choices"][0]["message"]["content"]


def detect_with_llm(segments: list[dict], title: str | None) -> tuple[float, float, str]:
    prompt = PROMPT.format(title=f" (titre : « {title} »)" if title else "",
                           chunk=CHUNK, transcript=build_transcript(segments))
    answer = ask_llm(prompt)
    match = re.search(r"\{.*\}", answer, re.S)
    if not match:
        raise ValueError(f"Réponse LLM illisible : {answer[:200]}")
    data = json.loads(match.group(0))
    start, end = parse_time(data["start"]), parse_time(data["end"])
    return start, end, f"IA : {data.get('raison', '')}".strip()


# Mots criés pendant l'adoration : ils ne comptent pas comme de la « parole dense » d'une prédication
ADORATION_WORDS = {"alleluia", "alléluia", "amen", "hosanna", "gloire", "merci", "jesus", "jésus", "oui", "hallelujah"}


def detect_heuristic(segments: list[dict], duration: float, coverage: float = 1.0,
                     window: float = 30.0, min_wps: float = 1.6, max_gap: int = 2) -> tuple[float, float, str]:
    """Plus longue zone continue où le débit dépasse min_wps mots/seconde.
    coverage : part de chaque fenêtre qui a été transcrite (0.5 si un extrait sur deux)."""
    n = int(duration // window) + 1
    counts = [0] * n
    for s in segments:
        if s.get("no_speech_prob", 0) > 0.6 or not re.search(r"[a-zA-ZÀ-ÿ]", s["text"]):
            continue
        idx = min(int(((s["start"] + s["end"]) / 2) // window), n - 1)
        counts[idx] += sum(1 for w in s["text"].split() if re.sub(r"[^\wÀ-ÿ]", "", w.lower()) not in ADORATION_WORDS)
    spoken = [c / (window * coverage) >= min_wps for c in counts]

    best, cur_start, gap, last_spoken = (0, 0, 0), None, 0, None
    for i, is_spoken in enumerate(spoken + [False] * (max_gap + 1)):
        if is_spoken:
            if cur_start is None:
                cur_start = i
            last_spoken, gap = i, 0
        elif cur_start is not None:
            gap += 1
            if gap > max_gap:
                length = last_spoken - cur_start + 1
                if length > best[0]:
                    best = (length, cur_start, last_spoken)
                cur_start, gap = None, 0
    if best[0] == 0:
        return 0.0, duration, "Heuristique : aucune zone de parole nette, culte entier conservé"
    start = best[1] * window
    end = min((best[2] + 1) * window, duration)
    # Affinage : se caler sur les vrais débuts/fins de phrases de la zone
    inside = [s for s in segments if s["end"] > start and s["start"] < end
              and len(s["text"].split()) / max(s["end"] - s["start"], 0.5) >= min_wps]
    if inside:
        start, end = max(inside[0]["start"] - 1, 0), min(inside[-1]["end"] + 1, duration)
    return start, end, "Heuristique : plus longue zone de parole continue"


def detect_sermon(segments: list[dict], duration: float, title: str | None, log, use_ai: bool) -> tuple[float, float, str]:
    if use_ai:
        try:
            start, end, note = detect_with_llm(segments, title)
            if 0 <= start < end <= duration + 5 and end - start >= 120:
                return start, min(end + CHUNK, duration), note  # la ligne citée dure CHUNK s : la fin est dedans
            log(f"Bornes IA incohérentes ({start}–{end}), passage à l'heuristique")
        except Exception as exc:  # réseau, quota, JSON…
            log(f"Détection IA impossible ({exc}), passage à l'heuristique")
    return detect_heuristic(segments, duration, min(config.DETECT_CLIP / CHUNK, 1.0))

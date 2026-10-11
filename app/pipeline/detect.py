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
- Inclus : l'introduction du prédicateur, la lecture biblique liée au message, le message et sa conclusion (y compris sa prière de fin de message).
- Exclus : louange et chants, annonces, offrandes/dîmes, témoignages, interventions des autres personnes, et tout ce qui suit la fin du message.

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


def _ask_llm(prompt: str) -> str:
    timeout = httpx.Timeout(180.0)
    if config.LLM_PROVIDER == "anthropic":
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": config.LLM_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": config.LLM_MODEL or "claude-haiku-5-5", "max_tokens": 400,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=timeout,
        )
        r.raise_for_status()
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
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def detect_with_llm(segments: list[dict], title: str | None) -> tuple[float, float, str]:
    prompt = PROMPT.format(title=f" (titre : « {title} »)" if title else "",
                           chunk=CHUNK, transcript=build_transcript(segments))
    answer = _ask_llm(prompt)
    match = re.search(r"\{.*\}", answer, re.S)
    if not match:
        raise ValueError(f"Réponse LLM illisible : {answer[:200]}")
    data = json.loads(match.group(0))
    start, end = parse_time(data["start"]), parse_time(data["end"])
    return start, end, f"IA : {data.get('raison', '')}".strip()


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
        counts[idx] += len(s["text"].split())
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


def detect_sermon(segments: list[dict], duration: float, title: str | None, log) -> tuple[float, float, str]:
    if config.LLM_PROVIDER in ("anthropic", "openai"):
        try:
            start, end, note = detect_with_llm(segments, title)
            if 0 <= start < end <= duration + 5 and end - start >= 120:
                return start, min(end + 2, duration), note
            log(f"Bornes IA incohérentes ({start}–{end}), passage à l'heuristique")
        except Exception as exc:  # réseau, quota, JSON…
            log(f"Détection IA impossible ({exc}), passage à l'heuristique")
    return detect_heuristic(segments, duration, min(config.DETECT_CLIP / CHUNK, 1.0))

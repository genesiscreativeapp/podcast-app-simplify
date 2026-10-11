"""Transcription CPU avec faster-whisper (int8).

Pour aller vite sur un culte de 4 h 30 :
- le travail est découpé en lots traités en parallèle (WHISPER_WORKERS) par un même modèle ;
- le repérage de la prédication ne transcrit qu'un extrait de chaque fenêtre de 30 s
  (le LLM n'en lit que le début de toute façon) ;
- les lots de la passe fine sont coupés dans un creux de parole, jamais au milieu d'un mot.
Les modèles restent en mémoire entre deux traitements.
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf

from .. import config

SR = 16000           # fréquence attendue par Whisper
WINDOW = 30          # secondes : fenêtre d'échantillonnage du repérage (= CHUNK de detect.py)
GAP = 0.5            # silence inséré entre deux extraits pour que le VAD les sépare
BATCH_SECONDS = 600  # taille d'un lot de la passe fine

_models: dict = {}
_lock = threading.Lock()


def _model(name: str):
    with _lock:
        if name not in _models:
            from faster_whisper import WhisperModel

            _models[name] = WhisperModel(
                name, device="cpu", compute_type="int8",
                cpu_threads=config.WHISPER_THREADS, num_workers=config.WHISPER_WORKERS,
            )
        return _models[name]


class _Progress:
    """Cumule l'avancement (en secondes d'audio traitées) de plusieurs threads."""

    def __init__(self, total: float, cb: Callable[[float], None] | None):
        self.total, self.cb, self.done, self._lock = max(total, 1.0), cb, 0.0, threading.Lock()

    def add(self, seconds: float):
        with self._lock:
            self.done += seconds
            if self.cb:
                self.cb(min(self.done / self.total, 1.0))


def _segments(model_name: str, audio: np.ndarray, words: bool, beam: int, prompt: str | None = None):
    segments, _info = _model(model_name).transcribe(
        audio,
        language=config.WHISPER_LANGUAGE,
        vad_filter=True,                  # saute les zones sans voix -> beaucoup plus rapide
        word_timestamps=words,
        beam_size=beam,
        condition_on_previous_text=False, # évite les boucles d'hallucination sur la musique
        initial_prompt=prompt or None,    # amorce : transcrire aussi les « euh » et les répétitions
    )
    for seg in segments:
        yield seg


def _read(wav: Path, start: float, seconds: float) -> np.ndarray:
    """Lit un extrait mono 16 kHz ; vide si on dépasse la fin du fichier."""
    with sf.SoundFile(str(wav)) as f:
        f.seek(min(int(start * SR), f.frames))
        return f.read(int(seconds * SR), dtype="float32")


def _quiet_point(wav: Path, t: float, radius: float = 10.0) -> float:
    """Instant le plus calme autour de t : endroit sûr pour couper sans casser un mot."""
    start = max(t - radius, 0.0)
    audio = _read(wav, start, 2 * radius)
    hop = SR // 10
    n = len(audio) // hop
    if n < 3:
        return t
    rms = np.sqrt(np.mean(audio[: n * hop].reshape(n, hop) ** 2, axis=1))
    rms = np.convolve(rms, np.ones(3) / 3, mode="same")
    return start + (int(np.argmin(rms[1:-1])) + 1) * 0.1


def _batches(wav: Path, duration: float) -> list[tuple[float, float]]:
    cuts, t = [0.0], float(BATCH_SECONDS)
    while duration - t > BATCH_SECONDS / 2:
        cuts.append(_quiet_point(wav, t))
        t += BATCH_SECONDS
    cuts.append(duration)
    return list(zip(cuts, cuts[1:]))


def transcribe_words(wav16: Path, duration: float,
                     on_progress: Callable[[float], None] | None = None) -> list[dict]:
    """Passe fine, mot à mot, sur toute la prédication. Retourne des segments {start, end, text, words}."""
    progress = _Progress(duration, on_progress)

    def task(span):
        a, b = span
        audio = _read(wav16, a, b - a)
        out, last = [], 0.0
        for seg in _segments(config.WHISPER_MODEL_EDIT, audio, True, config.WHISPER_BEAM_EDIT,
                             config.WHISPER_PROMPT):
            out.append({
                "start": a + seg.start, "end": a + seg.end, "text": seg.text.strip(),
                "words": [{"start": a + w.start, "end": a + w.end, "word": w.word}
                          for w in (seg.words or [])],
            })
            progress.add(seg.end - last)
            last = seg.end
        progress.add(max((b - a) - last, 0.0))  # fin de lot : le reste était du silence
        return out

    with ThreadPoolExecutor(config.WHISPER_WORKERS) as ex:
        return [s for part in ex.map(task, _batches(wav16, duration)) for s in part]


def transcribe_sampled(wav16: Path, duration: float,
                       on_progress: Callable[[float], None] | None = None) -> list[dict]:
    """Passe rapide de repérage : ne transcrit que les `DETECT_CLIP` premières secondes de chaque
    fenêtre de 30 s. Les temps retournés sont ceux de la vidéo d'origine."""
    clip = float(min(config.DETECT_CLIP, WINDOW))
    gap = GAP if clip < WINDOW else 0.0
    stride = clip + gap
    n_windows = int(duration // WINDOW) + 1
    per_batch = BATCH_SECONDS // WINDOW * 2  # 20 min de culte par lot
    progress = _Progress(duration, on_progress)

    def task(k0: int):
        k1 = min(k0 + per_batch, n_windows)
        pieces = []
        for k in range(k0, k1):
            audio = _read(wav16, k * WINDOW, clip)
            pieces.append(np.concatenate([audio, np.zeros(int(gap * SR), dtype="float32")]))
        out = []
        if sum(map(len, pieces)) < SR:
            progress.add((k1 - k0) * WINDOW)
            return out
        for seg in _segments(config.WHISPER_MODEL_DETECT, np.concatenate(pieces), False, 1):
            k, off = divmod(seg.start, stride)
            base = (k0 + int(k)) * WINDOW
            out.append({  # le segment reste dans sa fenêtre, même s'il chevauche deux extraits
                "start": base + min(off, clip),
                "end": base + min(seg.end - int(k) * stride, clip),
                "text": seg.text.strip(),
                "no_speech_prob": getattr(seg, "no_speech_prob", 0.0),
                "words": [],
            })
        progress.add((k1 - k0) * WINDOW)
        return out

    with ThreadPoolExecutor(config.WHISPER_WORKERS) as ex:
        parts = list(ex.map(task, range(0, n_windows, per_batch)))
    return sorted((s for p in parts for s in p), key=lambda s: s["start"])

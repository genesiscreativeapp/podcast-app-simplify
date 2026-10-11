"""Montage automatique : silences raccourcis, « euh » retirés, bégaiements/répétitions retirés.

- Les silences sont détectés sur l'énergie du signal (pas sur la transcription) :
  on ne coupe jamais une zone où il y a du son, même si Whisper l'a ratée.
- Les mots parasites et répétitions viennent des horodatages mot à mot.
  Les répétitions d'emphase volontaires (« Amen, amen ! », « Il est fidèle, il est fidèle ! »
  dites avec une pause) sont préservées : seules les répétitions immédiates sont retirées.
"""
import re
import unicodedata

import numpy as np
import soundfile as sf

FILLERS = {"euh", "euhh", "heu", "heuu", "hum", "hmm", "hmmm", "mmh", "mh", "bah"}
PROTECTED = {"amen", "alleluia", "gloire", "oui", "non", "saint", "merci", "jesus",
             "seigneur", "dieu", "hosanna", "louange"}


def _norm(word: str) -> str:
    w = unicodedata.normalize("NFKD", word.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9']", "", w)


def _frames_db(audio: np.ndarray, sr: int, frame: float = 0.02) -> np.ndarray:
    hop = int(sr * frame)
    n = len(audio) // hop
    if n == 0:
        return np.array([-120.0])
    frames = audio[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9)


def silence_cuts(audio: np.ndarray, sr: int, max_pause: float, target_pause: float,
                 frame: float = 0.02) -> list[tuple[float, float]]:
    db = _frames_db(audio, sr, frame)
    # lissage sur 100 ms pour ignorer les micro-pics
    k = 5
    db = np.convolve(db, np.ones(k) / k, mode="same")
    p10, p90 = np.percentile(db, 10), np.percentile(db, 90)
    threshold = p10 + 0.3 * (p90 - p10)
    quiet = db < threshold

    cuts, i, n = [], 0, len(quiet)
    total = len(audio) / sr
    while i < n:
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < n and quiet[j]:
            j += 1
        start, end = i * frame, j * frame
        if i == 0:                       # silence au tout début
            cuts.append((0.0, max(end - 0.15, 0.0)))
        elif j >= n:                     # silence à la fin
            cuts.append((min(start + 0.3, total), total))
        elif end - start > max_pause:
            half = target_pause / 2
            cuts.append((start + half, end - half))
        i = j
    return cuts


def word_cuts(words: list[dict], remove_fillers: bool, remove_repeats: bool) -> tuple[list, dict]:
    n = len(words)
    norm = [_norm(w["word"]) for w in words]
    remove = [False] * n
    stats = {"fillers": 0, "repeats": 0}

    if remove_fillers:
        for i, w in enumerate(norm):
            if w in FILLERS:
                remove[i] = True
                stats["fillers"] += 1

    if remove_repeats:
        i = 0
        while i < n:
            matched = False
            for k in (3, 2, 1):
                if i + 2 * k > n:
                    continue
                a, b = norm[i:i + k], norm[i + k:i + 2 * k]
                if a != b or not all(a) or any(x in PROTECTED for x in a):
                    continue
                if k == 1 and len(a[0]) > 3:  # 1 mot : seulement les petits (« le le », « je je »)
                    continue
                gap = words[i + k]["start"] - words[i + k - 1]["end"]
                if gap > 0.5:                  # répétition avec pause = emphase volontaire
                    continue
                for j in range(i, i + k):
                    remove[j] = True
                stats["repeats"] += 1
                i += k
                matched = True
                break
            if not matched:
                i += 1

    cuts = []
    for i in range(n):
        if remove[i]:
            start = words[i]["start"]
            nxt = words[i + 1]["start"] if i + 1 < n else words[i]["end"]
            cuts.append((start, min(nxt, words[i]["end"] + 0.12)))
    return cuts, stats


def keep_intervals(cuts: list[tuple[float, float]], total: float,
                   min_keep: float = 0.03) -> list[tuple[float, float]]:
    cuts = sorted((max(0.0, s), min(total, e)) for s, e in cuts if e > s)
    merged: list[list[float]] = []
    for s, e in cuts:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    keep, pos = [], 0.0
    for s, e in merged:
        if s - pos > min_keep:
            keep.append((pos, s))
        pos = max(pos, e)
    if total - pos > min_keep:
        keep.append((pos, total))
    return keep


def render(audio: np.ndarray, sr: int, keep: list[tuple[float, float]], xfade_ms: float = 12) -> np.ndarray:
    """Recolle les morceaux conservés avec un micro fondu enchaîné (évite les clics)."""
    xf = int(sr * xfade_ms / 1000)
    pieces = [audio[int(s * sr):int(e * sr)] for s, e in keep]
    out = np.empty(sum(len(p) for p in pieces), dtype=np.float32)
    fade_in = np.linspace(0, 1, xf, dtype=np.float32)
    fade_out = 1 - fade_in
    pos = 0
    for p in pieces:
        p = p.astype(np.float32)
        if pos >= xf and len(p) > 2 * xf:
            out[pos - xf:pos] = out[pos - xf:pos] * fade_out + p[:xf] * fade_in
            p = p[xf:]
        out[pos:pos + len(p)] = p
        pos += len(p)
    return out[:pos]


def edit_file(src, dst, words: list[dict], max_pause: float, target_pause: float,
              remove_fillers: bool = True, remove_repeats: bool = True) -> dict:
    audio, sr = sf.read(str(src), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    total = len(audio) / sr
    s_cuts = silence_cuts(audio, sr, max_pause, target_pause)
    w_cuts, stats = word_cuts(words, remove_fillers, remove_repeats)
    keep = keep_intervals(s_cuts + w_cuts, total)
    if not keep:
        keep = [(0.0, total)]
    result = render(audio, sr, keep)
    sf.write(str(dst), result, sr, subtype="PCM_16")
    stats.update({
        "pauses": sum(1 for s, e in s_cuts if e - s > 0.05),
        "before": total,
        "after": len(result) / sr,
    })
    return stats

"""Montage automatique : silences raccourcis, « euh » retirés, bégaiements/répétitions retirés.

- Les silences sont détectés sur l'énergie du signal (pas sur la transcription) :
  on ne coupe jamais une zone où il y a du son, même si Whisper l'a ratée.
- Les mots parasites et répétitions viennent des horodatages mot à mot.
  Les répétitions d'emphase volontaires (« Amen, amen ! », « Il est fidèle, il est fidèle ! »
  dites avec une pause) sont préservées : seules les répétitions immédiates sont retirées.
- Les réactions du public (applaudissements, rires, « Amen » de l'assemblée) entre deux phrases du prédicateur sont retirées.
"""
import re
import unicodedata

import numpy as np
import soundfile as sf

FILLERS = {"euh", "euhh", "euhhh", "euhm", "heu", "heuu", "heum", "hum", "hmm", "hmmm", "mmh", "mmm", "mh", "ehm", "bah"}
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


def _smooth_db(audio: np.ndarray, sr: int, frame: float) -> tuple[np.ndarray, float]:
    """Niveau par trame lissé sur 100 ms (ignore les micro-pics), et seuil sous lequel une trame est « silencieuse »."""
    db = np.convolve(_frames_db(audio, sr, frame), np.ones(5) / 5, mode="same")
    p10, p90 = np.percentile(db, 10), np.percentile(db, 90)
    return db, p10 + 0.3 * (p90 - p10)


def silence_cuts(audio: np.ndarray, sr: int, max_pause: float, target_pause: float,
                 frame: float = 0.02) -> list[tuple[float, float]]:
    db, threshold = _smooth_db(audio, sr, frame)
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


def word_cuts(words: list[dict], remove_fillers: bool, remove_repeats: bool,
              max_gap: float = 1.0, max_words: int = 8) -> tuple[list, dict]:
    """Retire les « euh » et les mots ou phrases répétés d'affilée (« la foi, la foi », « Dieu est bon,
    Dieu est bon »). Une pause de plus de `max_gap` secondes entre les deux copies signale une vraie
    reprise : on la garde. On garde la dernière copie, souvent la mieux articulée."""
    n = len(words)
    norm = [_norm(w["word"]) for w in words]
    remove = [False] * n
    stats = {"fillers": 0, "repeats": 0, "examples": []}

    if remove_fillers:
        for i, w in enumerate(norm):
            if w in FILLERS:
                remove[i] = True
                stats["fillers"] += 1

    if remove_repeats:
        i = 0
        while i < n:
            matched = False
            for k in range(min(max_words, (n - i) // 2), 0, -1):
                a, b = norm[i:i + k], norm[i + k:i + 2 * k]
                if a != b or not all(a) or all(x in PROTECTED for x in a):
                    continue
                if words[i + k]["start"] - words[i + k - 1]["end"] > max_gap:
                    continue
                for j in range(i, i + k):
                    remove[j] = True
                stats["repeats"] += 1
                stats["examples"].append(" ".join(w["word"].strip() for w in words[i:i + k]))
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


# Ce que l'assemblée répond : isolés et plus faibles que le prédicateur (micro de proximité), ces mots sont des réactions
REACTION_WORDS = {"amen", "oui", "alleluia", "hallelujah", "hosanna", "gloire", "merci", "jesus", "ah", "oh", "bravo", "hum"}


def reaction_cuts(audio: np.ndarray, sr: int, words: list[dict], target_pause: float, min_gap: float = 1.5,
                  quiet_db: float = 8.0, frame: float = 0.02) -> list[tuple[float, float]]:
    """Réactions du public qui ne sont pas la voix du prédicateur :
    - applaudissements, rires, bruit : un trou de plus de `min_gap` s entre deux mots où le son reste présent
      est ramené à une pause (la voix du prédicateur n'y est pas, Whisper n'y entend aucun mot) ;
    - « Amen », « Alléluia »… de l'assemblée : 1 à 4 mots de réaction, isolés (pause de 0,5 s de chaque côté),
      au moins `quiet_db` dB sous le niveau médian du prédicateur.
    Limite : une réaction qui couvre la voix du prédicateur ne peut pas être retirée sans séparer les voix."""
    if not words:
        return []
    total, half = len(audio) / sr, target_pause / 2
    db, threshold = _smooth_db(audio, sr, frame)
    cuts = []
    # trous entre mots (début et fin compris : les bornes ±half laissent la pause cible au bord du montage)
    edges = [-half] + [w["end"] for w in words], [w["start"] for w in words] + [total + half]
    for a, b in zip(*edges):
        if b - a >= min_gap:
            seg = db[int(max(a, 0) / frame):int(min(b, total) / frame)]
            if len(seg) and np.mean(seg >= threshold) >= 0.4:
                cuts.append((max(a + half, 0.0), min(b - half, total)))

    level = [20 * np.log10(np.sqrt(np.mean(audio[int(w["start"] * sr):int(w["end"] * sr)].astype(np.float64) ** 2)) + 1e-9)
             if w["end"] > w["start"] else -120.0 for w in words]
    speaker = np.median(level)
    i = 0
    while i < len(words):
        j = i + 1
        while j < len(words) and words[j]["start"] - words[j - 1]["end"] < 0.5:
            j += 1
        island = range(i, j)
        if len(island) <= 4 and all(_norm(words[k]["word"]) in REACTION_WORDS for k in island) \
                and np.mean([level[k] for k in island]) < speaker - quiet_db:
            cuts.append((words[i]["start"], words[j - 1]["end"] + 0.12))
        i = j
    return cuts


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


def sentence_end(words: list[dict], nominal: float, horizon: float, min_gap: float = 0.6) -> float:
    """Instant (s) où couper la fin : la première fin de phrase ou pause d'au moins min_gap s à partir de `nominal`
    (2 s plus tôt toléré), dans les `horizon` s qui suivent. Sinon `nominal`. Évite de couper une phrase en plein milieu."""
    for i, w in enumerate(words):
        if w["end"] < nominal - 2:
            continue
        if w["end"] > nominal + horizon:
            break
        pause = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else float("inf")
        if pause >= min_gap or w["word"].strip()[-1:] in ".!?…":
            return w["end"] + 0.25
    return nominal


def edit_file(src, dst, words: list[dict], max_pause: float, target_pause: float,
              remove_fillers: bool = True, remove_repeats: bool = True,
              extra_cuts: list[tuple[float, float]] = (), repeat_gap: float = 1.0, repeat_words: int = 8,
              remove_reactions: bool = False) -> dict:
    audio, sr = sf.read(str(src), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    total = len(audio) / sr
    s_cuts = silence_cuts(audio, sr, max_pause, target_pause)
    w_cuts, stats = word_cuts(words, remove_fillers, remove_repeats, repeat_gap, repeat_words)
    r_cuts = reaction_cuts(audio, sr, words, target_pause) if remove_reactions else []
    stats.update(reactions=len(r_cuts), reaction_cuts=r_cuts)
    keep = keep_intervals(s_cuts + w_cuts + r_cuts + list(extra_cuts), total)
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

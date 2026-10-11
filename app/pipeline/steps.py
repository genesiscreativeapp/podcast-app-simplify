"""Étapes d'un traitement et leur part dans la barre de progression globale (0 → 1).

Les parts reflètent le temps réel sur un long culte : la transcription domine.
`view()` en déduit l'état de chaque étape à partir de la seule progression globale.
"""

STEPS = [
    ("download", "Téléchargement YouTube",          0.00, 0.08),
    ("detect",   "Repérage de la prédication",      0.08, 0.38),
    ("voice",    "Extraction et amélioration voix", 0.38, 0.43),
    ("words",    "Transcription mot à mot",         0.43, 0.85),
    ("edit",     "Montage (silences, hésitations)", 0.85, 0.90),
    ("master",   "Intro et volume",                 0.90, 0.94),
    ("encode",   "Compression OGG / MP3",           0.94, 0.97),
    ("upload",   "Envoi vers Cloudflare R2",        0.97, 1.00),
]
BY_KEY = {k: (label, lo, hi) for k, label, lo, hi in STEPS}


def view(progress: float, status: str, skipped=()) -> list[dict]:
    """[{key, label, state: pending|active|done|skipped|error, pct: 0-100}]"""
    out = []
    for key, label, lo, hi in STEPS:
        if key in skipped:
            state, pct = "skipped", 0
        elif status == "done" or progress >= hi:
            state, pct = "done", 100
        elif status == "pending" or progress < lo:
            state, pct = "pending", 0
        else:
            state = "error" if status == "error" else "active"
            pct = round(100 * (progress - lo) / (hi - lo))
        out.append({"key": key, "label": label, "state": state, "pct": pct})
    return out

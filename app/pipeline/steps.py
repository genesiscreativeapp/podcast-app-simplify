"""Étapes d'un traitement et leur part dans la barre de progression globale (0 → 1).

Les parts reflètent le temps réel sur un long culte : la transcription domine.
`view()` en déduit l'état de chaque étape à partir de la seule progression globale.
"""

STEPS = [
    ("download", "Téléchargement YouTube",          0.00, 0.08),
    ("detect",   "Repérage de la prédication",      0.08, 0.38),
    ("voice",    "Extraction et amélioration voix", 0.38, 0.43),
    ("words",    "Transcription mot à mot",         0.43, 0.80),
    ("clean",    "Retrait des témoignages et annonces", 0.80, 0.84),
    ("condense", "Condensation (redites, formules creuses)", 0.84, 0.86),
    ("edit",     "Montage (silences, hésitations)", 0.86, 0.90),
    ("master",   "Intro et volume",                 0.90, 0.94),
    ("encode",   "Compression MP3",           0.94, 0.97),
    ("upload",   "Envoi vers Cloudflare R2",        0.97, 1.00),
]
BY_KEY = {k: (label, lo, hi) for k, label, lo, hi in STEPS}

# Version anglaise (service voicelab) : mêmes parts que les `progress` que voicelab.run_english enregistre
EN_STEPS = [
    ("text",      "Texte du podcast français",       0.00, 0.08),
    ("translate", "Traduction en anglais",           0.08, 0.20),
    ("ref",       "Voix de référence",               0.20, 0.22),
    ("voice",     "Voix du prédicateur en anglais",  0.22, 0.90),
    ("master",    "Volume et fondu de sortie",       0.90, 0.94),
    ("encode",    "Compression MP3",                 0.94, 0.97),
    ("upload",    "Envoi vers Cloudflare R2",        0.97, 1.00),
]


def view(progress: float, status: str, skipped=(), table=STEPS) -> list[dict]:
    """[{key, label, state: pending|active|done|skipped|error, pct: 0-100}]"""
    out = []
    for key, label, lo, hi in table:
        if key in skipped:
            state, pct = "skipped", 0
        elif status == "done" or progress >= hi:
            state, pct = "done", 100
        elif status in ("pending", "review") or progress < lo:  # en attente de validation : le montage n'a pas commencé
            state, pct = "pending", 0
        else:
            state = "error" if status == "error" else "active"
            pct = round(100 * (progress - lo) / (hi - lo))
        out.append({"key": key, "label": label, "state": state, "pct": pct})
    return out

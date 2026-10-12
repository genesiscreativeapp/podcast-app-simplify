"""Configuration lue depuis les variables d'environnement (.env)."""
import os
from pathlib import Path


def _env(name: str, default=None):
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _bool(name: str, default: bool) -> bool:
    return str(_env(name, str(default))).lower() in ("1", "true", "yes", "oui")


# --- Stockage local -------------------------------------------------------
DATA_DIR = Path(_env("DATA_DIR", "./data")).resolve()
WORK_DIR = DATA_DIR / "work"        # fichiers temporaires d'un traitement
OUTPUT_DIR = DATA_DIR / "outputs"   # copies locales des podcasts finaux
INTRO_DIR = DATA_DIR / "intros"     # intros (globale + par dossier)
CACHE_DIR = DATA_DIR / "cache"      # audio YouTube conservé : un « Relancer » ne le retélécharge pas
DB_PATH = DATA_DIR / "app.db"
for _d in (WORK_DIR, OUTPUT_DIR, INTRO_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

KEEP_WORK_FILES = _bool("KEEP_WORK_FILES", False)
UPLOAD_SCHEME = "upload://"  # youtube_url d'un traitement créé à partir d'un fichier envoyé
MAX_UPLOAD_MB = int(_env("MAX_UPLOAD_MB", "4096"))  # taille maximale d'un fichier audio/vidéo envoyé
KEEP_SOURCES = int(_env("KEEP_SOURCES", "5"))  # nombre d'audios YouTube gardés en cache (0 = aucun)

# --- Accès à l'interface (HTTP Basic) -------------------------------------
# Compte administrateur créé au tout premier démarrage (ensuite, les comptes se gèrent dans l'interface).
# Si APP_PASSWORD est vide, un mot de passe aléatoire est généré et écrit une fois dans les logs de `web`.
APP_USER = _env("APP_USER", "admin")
APP_PASSWORD = _env("APP_PASSWORD")
SESSION_DAYS = int(_env("SESSION_DAYS", "14"))

# --- Téléchargement YouTube -----------------------------------------------
YTDLP_COOKIES = _env("YTDLP_COOKIES")  # chemin vers cookies.txt (si YouTube bloque l'IP)
# Audio léger d'abord (≈ 50-70 kb/s) : téléchargement 2 à 3 fois plus petit, suffisant pour la voix
YTDLP_FORMAT = _env("YTDLP_FORMAT", "bestaudio[abr<=70]/bestaudio/best")

# --- Transcription (faster-whisper, CPU) ----------------------------------
# Passe rapide sur tout le culte pour repérer la prédication,
# puis passe plus précise uniquement sur la prédication.
WHISPER_MODEL_DETECT = _env("WHISPER_MODEL_DETECT", "tiny")
WHISPER_MODEL_EDIT = _env("WHISPER_MODEL_EDIT", "small")
WHISPER_LANGUAGE = _env("WHISPER_LANGUAGE", "fr")
_CORES = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 4)
# Plusieurs transcriptions en parallèle sur le même modèle, chacune avec sa part de cœurs :
# meilleur débit qu'une seule transcription sur tous les cœurs.
WHISPER_WORKERS = max(1, int(_env("WHISPER_WORKERS", str(min(4, _CORES // 2)))))
WHISPER_THREADS = max(1, int(_env("WHISPER_THREADS", str(_CORES // WHISPER_WORKERS))))  # par worker
WHISPER_BEAM_EDIT = int(_env("WHISPER_BEAM_EDIT", "1"))  # 1 = rapide ; 5 = plus précis, ~2x plus lent
# Repérage : secondes transcrites par fenêtre de 30 s (15 = moitié moins de travail ; 30 = tout)
DETECT_CLIP = int(_env("DETECT_CLIP", "15"))

# --- File d'attente ------------------------------------------------------------
# Traitements menés en même temps (modifiable depuis l'interface). Ils partagent les mêmes modèles Whisper
# et les mêmes cœurs : au-delà de 2-3, chacun va plus lentement.
MAX_PARALLEL_JOBS = int(_env("MAX_PARALLEL_JOBS", "2"))

# --- Détection de la prédication par LLM (optionnel) ----------------------
# none | anthropic | openai   (openai = toute API compatible : OpenAI, Groq, Ollama...)
LLM_PROVIDER = _env("LLM_PROVIDER", "none").lower()
LLM_API_KEY = _env("LLM_API_KEY", "")
LLM_MODEL = _env("LLM_MODEL", "")
LLM_BASE_URL = _env("LLM_BASE_URL", "https://api.openai.com/v1")

# --- Qualité de la voix ----------------------------------------------------------
# Réduction de bruit (dB) : une réduction forte donne une voix « métallique ». 0 = désactivée.
DENOISE_DB = float(_env("DENOISE_DB", "6"))

# --- Montage ---------------------------------------------------------------
MAX_PAUSE = float(_env("MAX_PAUSE", "0.8"))        # silence au-delà duquel on raccourcit (s)
TARGET_PAUSE = float(_env("TARGET_PAUSE", "0.45")) # durée du silence conservé (s)
REMOVE_REPEATS = _bool("REMOVE_REPEATS", True)
REPEAT_MAX_GAP = float(_env("REPEAT_MAX_GAP", "1.0"))    # pause max (s) entre deux répétitions pour les retirer
REPEAT_MAX_WORDS = int(_env("REPEAT_MAX_WORDS", "8"))    # longueur max (en mots) d'une phrase répétée retirée
# Amorce Whisper : l'encourage à transcrire les « euh » et répétitions au lieu de les gommer
WHISPER_PROMPT = _env("WHISPER_PROMPT", "Euh... alors, euh, mes frères, mes frères et sœurs, hum, voilà, euh, la foi, la foi.")
# Retire témoignages, annonces, chants et autres voix de la prédication (nécessite LLM_PROVIDER)
REMOVE_OFFTOPIC = _bool("REMOVE_OFFTOPIC", True)
# Marge ajoutée autour de la prédication repérée automatiquement (secondes) : l'IA retire ensuite précisément
# l'adoration qui précède et les annonces qui suivent. Sans marge, un début repéré un peu tard couperait le message.
OFFTOPIC_PAD_BEFORE = float(_env("OFFTOPIC_PAD_BEFORE", "90"))
OFFTOPIC_PAD_AFTER = float(_env("OFFTOPIC_PAD_AFTER", "60"))
# Fin du podcast : fondu de sortie (s) ; et marge (s) lue au-delà de la fin repérée pour la terminer sur une fin de phrase
FADE_OUT = float(_env("FADE_OUT", "2.5"))
END_MARGIN = float(_env("END_MARGIN", "25"))
REMOVE_FILLERS = _bool("REMOVE_FILLERS", True)

# --- Compression -------------------------------------------------------------
MP3_BITRATE = _env("MP3_BITRATE", "64k")
PODCAST_ARTIST = _env("PODCAST_ARTIST", "")

# --- Cloudflare R2 ------------------------------------------------------------
R2_ACCOUNT_ID = _env("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = _env("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = _env("R2_SECRET_ACCESS_KEY")
R2_BUCKET = _env("R2_BUCKET")
R2_PREFIX = _env("R2_PREFIX", "podcasts").strip("/")
R2_PUBLIC_BASE_URL = (_env("R2_PUBLIC_BASE_URL", "") or "").rstrip("/")
R2_LINK_EXPIRES = int(_env("R2_LINK_EXPIRES", str(7 * 24 * 3600)))
R2_ENDPOINT_URL = _env("R2_ENDPOINT_URL")  # facultatif : autre stockage compatible S3 (sinon l'adresse Cloudflare R2 du compte)

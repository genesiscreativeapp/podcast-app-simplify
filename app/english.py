"""Version anglaise d'un podcast : réglages de l'administrateur, mise en file, noms de fichiers.
Partagé par l'API (main.py), le traitement français (pipeline/run.py), le service voicelab et la synchronisation R2."""
import shutil
from datetime import datetime
from pathlib import Path

from . import config
from .db import EnVersion, Job, Setting, setting
from .utils import slugify
from .voicebench import DEFAULT_ENGINE, REAL_ENGINES

TRANSLATORS = {"local": "Modèle libre local (gratuit, sans IA externe)", "claude": "Notre IA configurée (Claude) : meilleure qualité, si elle est disponible"}
EN_DIR = config.DATA_DIR / "en"  # travail en cours : morceaux audio déjà synthétisés (une reprise ne refait pas ce qui est fait)


def defaults(s) -> dict:
    """Réglages de l'administrateur : traducteur et moteur de voix par défaut."""
    tr, engine = setting(s, "en_translator", "local"), setting(s, "en_engine", DEFAULT_ENGINE)
    return {"translator": tr if tr in TRANSLATORS else "local", "engine": engine if engine in REAL_ENGINES else DEFAULT_ENGINE}


def save_defaults(s, translator: str, engine: str) -> None:
    s.merge(Setting(key="en_translator", value=translator))
    s.merge(Setting(key="en_engine", value=engine))
    s.commit()


def english_filename(title: str, day: str) -> str:
    """Nom du MP3 anglais : celui du podcast français avec le suffixe _EN (même dossier sur R2)."""
    return f"{slugify(title)}_{day}_EN"


def drop_files(en: EnVersion) -> None:
    """Retire les fichiers locaux d'une version anglaise (le MP3 et le travail en cours) ; l'objet R2 est géré par l'appelant."""
    shutil.rmtree(EN_DIR / str(en.id), ignore_errors=True)
    if en.local_mp3:
        Path(en.local_mp3).unlink(missing_ok=True)


def queue(s, job: Job, mode: str, user: str, translator: str | None = None, engine: str | None = None, ref_start: float | None = None) -> EnVersion:
    """Met (ou remet) la version anglaise de ce podcast en file : une demande remplace la précédente, fichiers compris."""
    d = defaults(s)
    en = s.query(EnVersion).filter(EnVersion.job_id == job.id).first()
    if en is None:
        en = EnVersion(job_id=job.id, created_by=user)
        s.add(en)
    else:
        drop_files(en)
    en.created_by, en.mode = user, mode
    en.translator, en.engine, en.ref_start = translator or d["translator"], engine or d["engine"], ref_start
    en.status, en.step, en.progress, en.error, en.log = "pending", "En attente", 0.0, None, ""
    en.text_json, en.method, en.review_ok = None, None, False
    en.local_mp3 = en.size_mp3 = en.duration_output = en.finished_at = None  # r2_key_mp3 est gardée : le même objet sera remplacé
    en.created_at = datetime.utcnow()
    s.commit()
    return en

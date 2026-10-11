"""Base SQLite : dossiers (arborescence) et traitements."""
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from . import config
from .config import DB_PATH

engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False, "timeout": 30}
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")  # web + worker en parallèle
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Setting(Base):
    """Réglages modifiables depuis l'interface (clé / valeur)."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


class Intro(Base):
    """Bibliothèque d'intros (MP3). Une seule peut être l'intro par défaut."""
    __tablename__ = "intros"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(500))
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Folder(Base):
    __tablename__ = "folders"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("folders.id"), nullable=True)
    intro_id: Mapped[int | None] = mapped_column(nullable=True)  # intro de la bibliothèque (sinon : parent)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id"))
    youtube_url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(300))
    date: Mapped[str] = mapped_column(String(10))  # AAAA-MM-JJ
    filename: Mapped[str] = mapped_column(String(400))  # sans extension

    # Intro choisie : NULL = automatique (dossier, sinon défaut) ; 0 = aucune ; sinon id dans la bibliothèque
    intro_id: Mapped[int | None] = mapped_column(nullable=True)

    # Bornes forcées par l'utilisateur (secondes) — sinon détection auto
    start_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_override: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|done|error
    step: Mapped[str] = mapped_column(String(200), default="En attente")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    log: Mapped[str] = mapped_column(Text, default="")

    video_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sermon_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    sermon_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    detection_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_source: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_output: Mapped[float | None] = mapped_column(Float, nullable=True)

    local_mp3: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_mp3: Mapped[int | None] = mapped_column(Integer, nullable=True)
    r2_key_mp3: Mapped[str | None] = mapped_column(String(800), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


def init_db() -> None:
    # web et worker démarrent ensemble sur une base neuve : on réessaie si l'autre crée les tables en même temps
    for attempt in range(5):
        try:
            _init_db()
            return
        except OperationalError:
            if attempt == 4:
                raise
            time.sleep(1 + attempt)


def _init_db() -> None:
    Base.metadata.create_all(engine)
    # Bases créées avant la bibliothèque d'intros : ajoute les colonnes manquantes
    with engine.begin() as conn:
        for table, col in (("jobs", "intro_id"), ("folders", "intro_id")):
            cols = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
            if col not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER"))


MAX_PARALLEL_LIMIT = 8


def get_max_parallel(session) -> int:
    row = session.get(Setting, "max_parallel")
    try:
        n = int(row.value) if row else config.MAX_PARALLEL_JOBS
    except ValueError:
        n = config.MAX_PARALLEL_JOBS
    return min(max(n, 1), MAX_PARALLEL_LIMIT)


# Ordre de la file : le plus ancien en attente d'abord (un « Relancer » repart en fin de file)
QUEUE_ORDER = (Job.updated_at, Job.id)


def queue_position(session, job: Job) -> int:
    """Rang (1 = prochain) d'un traitement en attente."""
    ahead = session.query(Job).filter(
        Job.status == "pending",
        (Job.updated_at < job.updated_at) | ((Job.updated_at == job.updated_at) & (Job.id < job.id)),
    ).count()
    return ahead + 1


def folder_path(session, folder: Folder) -> list[str]:
    """Noms des dossiers depuis la racine : ['CULTE ROYAL', 'Octobre']."""
    names, current, seen = [], folder, set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        names.append(current.name)
        current = session.get(Folder, current.parent_id) if current.parent_id else None
    return list(reversed(names))


def resolve_intro(session, folder: Folder | None, intro_id: int | None = None) -> tuple[str, str] | None:
    """(chemin, nom) de l'intro à utiliser : choix du traitement, sinon intro du dossier ou du parent
    le plus proche, sinon intro par défaut. None = pas d'intro."""
    def usable(i):
        return i if i is not None and Path(i.path).exists() else None

    if intro_id == 0:
        return None
    chosen = usable(session.get(Intro, intro_id)) if intro_id else None
    current, seen = folder, set()
    while chosen is None and current is not None and current.id not in seen:
        seen.add(current.id)
        chosen = usable(session.get(Intro, current.intro_id)) if current.intro_id else None
        current = session.get(Folder, current.parent_id) if current.parent_id else None
    if chosen is None:
        chosen = usable(session.query(Intro).filter(Intro.is_default).first())
    return (chosen.path, chosen.name) if chosen else None

"""Base SQLite : dossiers (arborescence) et traitements."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DB_PATH, INTRO_DIR

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


class Folder(Base):
    __tablename__ = "folders"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("folders.id"), nullable=True)
    intro_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id"))
    youtube_url: Mapped[str] = mapped_column(String(1000))
    title: Mapped[str] = mapped_column(String(300))
    date: Mapped[str] = mapped_column(String(10))  # AAAA-MM-JJ
    filename: Mapped[str] = mapped_column(String(400))  # sans extension

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

    local_ogg: Mapped[str | None] = mapped_column(String(500), nullable=True)
    local_mp3: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_ogg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_mp3: Mapped[int | None] = mapped_column(Integer, nullable=True)
    r2_key_ogg: Mapped[str | None] = mapped_column(String(800), nullable=True)
    r2_key_mp3: Mapped[str | None] = mapped_column(String(800), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


def folder_path(session, folder: Folder) -> list[str]:
    """Noms des dossiers depuis la racine : ['CULTE ROYAL', 'Octobre']."""
    names, current, seen = [], folder, set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        names.append(current.name)
        current = session.get(Folder, current.parent_id) if current.parent_id else None
    return list(reversed(names))


def resolve_intro(session, folder: Folder | None) -> str | None:
    """Intro du dossier, sinon du parent le plus proche, sinon l'intro globale."""
    current, seen = folder, set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        if current.intro_path:
            return current.intro_path
        current = session.get(Folder, current.parent_id) if current.parent_id else None
    default = sorted(INTRO_DIR.glob("default.*"))
    return str(default[0]) if default else None

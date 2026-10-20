"""Base SQLite : dossiers (arborescence) et traitements."""
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from . import config, vault
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


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # compte administrateur système : protégé
    permissions: Mapped[str] = mapped_column(Text, default="")  # clés séparées par des virgules
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    max_parallel: Mapped[int] = mapped_column(Integer, default=5)  # traitements simultanés de cet utilisateur ; réglé par un admin
    llm_key: Mapped[str | None] = mapped_column(Text, nullable=True)  # clé Anthropic personnelle, chiffrée (vault)
    ai_on: Mapped[bool] = mapped_column(Boolean, default=True)  # IA voulue pour ses traitements (permission ai.toggle)

    @property
    def perms(self) -> set[str]:
        return {p for p in (self.permissions or "").split(",") if p}


class UserSession(Base):
    """Session de connexion : seul le hash du jeton est stocké."""
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class R2Marker(Base):
    """Objets « dossier » (clé terminée par /) que nous avons créés sur R2, pour pouvoir les déplacer ou les retirer."""
    __tablename__ = "r2_markers"
    key: Mapped[str] = mapped_column(String(900), primary_key=True)


class Setting(Base):
    """Réglages modifiables depuis l'interface (clé / valeur)."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # SQLite n'impose pas de longueur : la clé d'API chiffrée dépasse 200 caractères


class AiUsage(Base):
    """Registre de la consommation de l'IA : une ligne par appel (tokens entrée / sortie), pour les compteurs."""
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60))  # à qui l'appel est facturé : propriétaire de la clé, ou AI_SERVER
    author: Mapped[str | None] = mapped_column(String(60), nullable=True)  # qui a lancé le traitement
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EnVersion(Base):
    """Version anglaise d'un podcast, avec la voix du prédicateur : traduite puis synthétisée par le service voicelab."""
    __tablename__ = "en_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, unique=True)
    created_by: Mapped[str] = mapped_column(String(60))
    mode: Mapped[str] = mapped_column(String(10), default="review")  # auto : publiée telle quelle ; review : le texte anglais est validé avant la voix
    translator: Mapped[str] = mapped_column(String(10), default="local")  # local (modèle libre) | claude
    engine: Mapped[str] = mapped_column(String(40), default="chatterbox-nano")  # moteur de voix
    ref_start: Mapped[float | None] = mapped_column(Float, nullable=True)  # début de la voix de référence dans le podcast ; None = choisi automatiquement
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|review|done|error
    step: Mapped[str] = mapped_column(String(200), default="En attente")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    log: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # [{"id", "fr", "en"}] : le texte, modifiable à la relecture
    method: Mapped[str | None] = mapped_column(String(40), nullable=True)  # comment le texte a été traduit
    review_ok: Mapped[bool] = mapped_column(Boolean, default=False)  # texte validé : la synthèse peut commencer
    local_mp3: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_mp3: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_output: Mapped[float | None] = mapped_column(Float, nullable=True)
    r2_key_mp3: Mapped[str | None] = mapped_column(String(800), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class VoiceBench(Base):
    """Essai de voix en anglais lancé depuis « Banc d'essai voix » ; calculé par le service optionnel voicelab (app/voicelab.py)."""
    __tablename__ = "voice_bench"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_by: Mapped[str] = mapped_column(String(60))
    job_id: Mapped[int] = mapped_column(Integer)  # le podcast dont on prend un extrait
    title: Mapped[str] = mapped_column(String(300))
    start: Mapped[float] = mapped_column(Float)  # début de l'extrait dans le podcast (secondes)
    seconds: Mapped[float] = mapped_column(Float)  # durée de l'extrait
    ref_start: Mapped[float] = mapped_column(Float, default=5.0)  # début de la voix de référence dans l'extrait
    engines: Mapped[str] = mapped_column(String(200))  # séparés par des virgules
    text_en: Mapped[str | None] = mapped_column(Text, nullable=True)  # traduction fournie : sinon Whisper puis la traduction
    translator: Mapped[str] = mapped_column(String(10), default="local")  # local (modèle libre) | claude
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|done|error
    step: Mapped[str] = mapped_column(String(200), default="En attente")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    log: Mapped[str] = mapped_column(Text, default="")
    report_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # mesures par moteur
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    created_by: Mapped[str | None] = mapped_column(String(60), nullable=True)  # NULL = créé par l'administration
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # corbeille : NULL = présent
    deleted_by: Mapped[str | None] = mapped_column(String(60), nullable=True)


class FolderAccess(Base):
    """Dossier de l'administration attribué à un utilisateur (il peut y travailler, sans le modifier)."""
    __tablename__ = "folder_access"
    folder_id: Mapped[int] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)


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

    edit_note: Mapped[str | None] = mapped_column(Text, nullable=True)   # bilan du montage et du nettoyage
    created_by: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Bornes forcées par l'utilisateur (secondes) — sinon détection auto
    start_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_override: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|review (coupes à valider)|done|error
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

    # IA d'un administrateur pour ce traitement : nom d'utilisateur dont on prend la configuration, AI_SERVER, ou NULL = celle de l'auteur
    ai_user: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Condensation : part à retirer (0 = aucune, 10 / 20 / 30 %) ; « auto » l'applique, « review » attend la validation humaine
    condense_pct: Mapped[int] = mapped_column(Integer, default=0)
    condense_mode: Mapped[str] = mapped_column(String(10), default="auto")
    review_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # phrases, coupes proposées puis choisies
    review_ok: Mapped[bool] = mapped_column(Boolean, default=False)  # coupes validées : le traitement reprend où il s'était arrêté
    # Version anglaise : demandée à la création (« auto » : publiée telle quelle ; « review » : l'utilisateur valide d'abord le texte)
    english_mode: Mapped[str] = mapped_column(String(10), default="")
    transcript_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # texte final du podcast, phrase par phrase (JSON)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)   # tokens envoyés à l'IA pendant ce traitement
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)  # tokens reçus de l'IA

    local_mp3: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_mp3: Mapped[int | None] = mapped_column(Integer, nullable=True)
    r2_key_mp3: Mapped[str | None] = mapped_column(String(800), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # corbeille : NULL = présent
    deleted_by: Mapped[str | None] = mapped_column(String(60), nullable=True)


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
        for table, col, sql_type in (("jobs", "intro_id", "INTEGER"), ("folders", "intro_id", "INTEGER"),
                                     ("jobs", "edit_note", "TEXT"), ("jobs", "created_by", "VARCHAR(60)"),
                                     ("users", "is_system", "BOOLEAN DEFAULT 0"), ("users", "max_parallel", "INTEGER DEFAULT 5"),
                                     ("jobs", "deleted_at", "DATETIME"), ("jobs", "deleted_by", "VARCHAR(60)"),
                                     ("folders", "deleted_at", "DATETIME"), ("folders", "deleted_by", "VARCHAR(60)"),
                                     ("jobs", "ai_user", "VARCHAR(60)"), ("voice_bench", "translator", "VARCHAR(10) DEFAULT 'local'"), ("jobs", "english_mode", "VARCHAR(10) DEFAULT ''"), ("jobs", "transcript_json", "TEXT"), ("jobs", "condense_pct", "INTEGER DEFAULT 0"),
                                     ("jobs", "condense_mode", "VARCHAR(10) DEFAULT 'auto'"), ("jobs", "review_json", "TEXT"),
                                     ("jobs", "review_ok", "BOOLEAN DEFAULT 0"), ("jobs", "tokens_in", "INTEGER DEFAULT 0"), ("jobs", "tokens_out", "INTEGER DEFAULT 0"),
                                     ("users", "llm_key", "TEXT"), ("users", "ai_on", "BOOLEAN DEFAULT 1"),
                                     ("folders", "created_by", "VARCHAR(60)")):
            cols = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
            if col not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {sql_type}"))


MAX_PARALLEL_LIMIT = 20


AI_SERVER = "@server"  # IA du serveur : Job.ai_user (choix d'un administrateur) et propriétaire des appels dans AiUsage
DEFAULT_MODEL = "claude-sonnet-5-5"


def setting(session, key: str, default: str = "") -> str:
    row = session.get(Setting, key)
    return row.value if row else default


def server_llm(session) -> dict | None:
    """IA du serveur, réglée par l'administrateur dans l'interface (clé Anthropic chiffrée) : {key, model}, ou None."""
    key = vault.decrypt(setting(session, "llm_key")) if setting(session, "llm_key") else None
    return {"key": key, "model": setting(session, "llm_model") or DEFAULT_MODEL} if key else None


def ai_enabled(session) -> bool:
    """L'IA du serveur sert si elle est configurée ET que l'administrateur ne l'a pas désactivée (interrupteur)."""
    return server_llm(session) is not None and setting(session, "ai_enabled") != "0"


def has_perm(user: User | None, perm: str) -> bool:
    return bool(user) and (user.is_admin or perm in user.perms)


def personal_key(user: User | None) -> str | None:
    """Clé Anthropic personnelle (déchiffrée), si l'utilisateur en a une et en a encore le droit."""
    return vault.decrypt(user.llm_key) if user and user.llm_key and has_perm(user, "ai.key") else None


def personal_llm(session, key: str, owner: str) -> dict:
    """Appel avec une clé personnelle, sur le même modèle que celui réglé pour le serveur."""
    srv = server_llm(session)
    return {"key": key, "model": srv["model"] if srv else DEFAULT_MODEL, "owner": owner}


def ai_for(session, username: str | None) -> dict | None:
    """IA à utiliser pour les traitements de cet utilisateur : {key, model, owner}, ou None = sans IA.
    Sa clé personnelle (permission ai.key) remplace l'IA du serveur, même si l'administrateur a coupé celle-ci.
    Il peut couper l'IA pour lui seul (permission ai.toggle) ; sans cette permission, l'IA suit le réglage du serveur.
    `owner` : à qui la consommation est facturée (propriétaire de la clé, ou AI_SERVER)."""
    user = session.query(User).filter(User.username == username).first() if username else None
    if has_perm(user, "ai.toggle") and not user.ai_on:
        return None
    key = personal_key(user)
    if key:
        return personal_llm(session, key, user.username)
    return {**server_llm(session), "owner": AI_SERVER} if ai_enabled(session) else None


def job_ai(session, job: Job) -> dict | None:
    """IA d'un traitement : configuration (clé, interrupteur) de l'utilisateur qu'un administrateur a choisi, sinon celle de son auteur."""
    if job.ai_user == AI_SERVER:
        return ai_for(session, None)
    return ai_for(session, job.ai_user or job.created_by)


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
        Job.status == "pending", Job.deleted_at.is_(None),
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

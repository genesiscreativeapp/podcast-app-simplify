"""API web + interface."""
import base64
import secrets
import shutil
from datetime import date as date_cls, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import or_

from . import config, storage
from .pipeline import audio
from .db import Folder, Intro, Job, SessionLocal, folder_path, init_db
from .pipeline import steps
from .utils import fmt_time, parse_time, slugify

STATIC = Path(__file__).parent / "static"
MAX_INTRO_BYTES = 25 * 1024 * 1024

app = FastAPI(title="Studio Podcast")
init_db()


# --- Authentification HTTP Basic ---------------------------------------------
@app.middleware("http")
async def basic_auth(request: Request, call_next):
    if config.APP_PASSWORD and request.url.path != "/healthz":
        ok = False
        header = request.headers.get("authorization", "")
        if header.lower().startswith("basic "):
            try:
                user, _, pwd = base64.b64decode(header[6:]).decode().partition(":")
                ok = (secrets.compare_digest(user, config.APP_USER)
                      and secrets.compare_digest(pwd, config.APP_PASSWORD))
            except Exception:
                ok = False
        if not ok:
            return Response("Authentification requise", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Studio Podcast"'})
    return await call_next(request)


def db():
    with SessionLocal() as s:
        yield s


# --- Sérialisation ---------------------------------------------------------------
def folder_dict(f: Folder) -> dict:
    return {"id": f.id, "name": f.name, "parent_id": f.parent_id, "intro_id": f.intro_id}


def job_steps(j: Job) -> list[dict]:
    skipped = set()
    if j.start_override is not None or j.end_override is not None:
        skipped.add("detect")  # bornes saisies : pas de repérage
    if not (j.r2_key_mp3 if j.status == "done" else storage.enabled()):
        skipped.add("upload")
    return steps.view(j.progress or 0.0, j.status, skipped)


def job_dict(j: Job, with_log: bool = False, s=None) -> dict:
    d = {
        "steps": job_steps(j),
        "id": j.id, "folder_id": j.folder_id, "intro_id": j.intro_id, "youtube_url": j.youtube_url,
        "title": j.title, "date": j.date, "filename": j.filename,
        "status": j.status, "step": j.step, "progress": round(j.progress or 0, 3),
        "error": j.error, "video_title": j.video_title,
        "start_override": fmt_time(j.start_override), "end_override": fmt_time(j.end_override),
        "sermon_start": fmt_time(j.sermon_start), "sermon_end": fmt_time(j.sermon_end),
        "detection_note": j.detection_note,
        "duration_source": fmt_time(j.duration_source), "duration_output": fmt_time(j.duration_output),
        "has_mp3": bool(j.local_mp3 and Path(j.local_mp3).exists()),
        "size_mp3": j.size_mp3,
        "on_r2": bool(j.r2_key_mp3),
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }
    if s is not None:  # historique et détail : on indique le dossier
        folder = s.get(Folder, j.folder_id)
        d["folder_path"] = " / ".join(folder_path(s, folder)) if folder else ""
    if with_log:
        d["log"] = j.log
    return d


# --- Dossiers --------------------------------------------------------------------
class FolderIn(BaseModel):
    name: str
    parent_id: int | None = None


class FolderRename(BaseModel):
    name: str


@app.get("/api/folders")
def list_folders(s=Depends(db)):
    return [folder_dict(f) for f in s.query(Folder).order_by(Folder.name).all()]


@app.post("/api/folders")
def create_folder(body: FolderIn, s=Depends(db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Nom de dossier vide")
    if body.parent_id and not s.get(Folder, body.parent_id):
        raise HTTPException(404, "Dossier parent introuvable")
    f = Folder(name=name, parent_id=body.parent_id)
    s.add(f)
    s.commit()
    return folder_dict(f)


@app.patch("/api/folders/{folder_id}")
def rename_folder(folder_id: int, body: FolderRename, s=Depends(db)):
    f = s.get(Folder, folder_id) or _404("Dossier")
    if not body.name.strip():
        raise HTTPException(400, "Nom de dossier vide")
    f.name = body.name.strip()
    s.commit()
    return folder_dict(f)


@app.delete("/api/folders/{folder_id}")
def delete_folder(folder_id: int, s=Depends(db)):
    f = s.get(Folder, folder_id) or _404("Dossier")
    if s.query(Folder).filter(Folder.parent_id == folder_id).count() or \
       s.query(Job).filter(Job.folder_id == folder_id).count():
        raise HTTPException(400, "Le dossier n'est pas vide (sous-dossiers ou traitements)")
    s.delete(f)
    s.commit()
    return {"ok": True}


class FolderIntro(BaseModel):
    intro_id: int | None = None  # None = hériter du parent / intro par défaut


@app.put("/api/folders/{folder_id}/intro")
def set_folder_intro(folder_id: int, body: FolderIntro, s=Depends(db)):
    f = s.get(Folder, folder_id) or _404("Dossier")
    if body.intro_id is not None and not s.get(Intro, body.intro_id):
        raise HTTPException(404, "Intro introuvable")
    f.intro_id = body.intro_id
    s.commit()
    return folder_dict(f)


# --- Bibliothèque d'intros (MP3) -----------------------------------------------------
def intro_dict(i: Intro) -> dict:
    return {"id": i.id, "name": i.name, "is_default": i.is_default,
            "duration": fmt_time(i.duration) if i.duration else ""}


class IntroPatch(BaseModel):
    name: str | None = None
    is_default: bool | None = None


@app.get("/api/intros")
def list_intros(s=Depends(db)):
    return [intro_dict(i) for i in s.query(Intro).order_by(Intro.is_default.desc(), Intro.name).all()]


@app.post("/api/intros")
def upload_intro(file: UploadFile = File(...), name: str = Form(""), is_default: bool = Form(False),
                 s=Depends(db)):
    if Path(file.filename or "").suffix.lower() != ".mp3":
        raise HTTPException(400, "L'intro doit être un fichier MP3")
    dest = config.INTRO_DIR / f"intro_{secrets.token_hex(6)}.mp3"
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    try:
        if dest.stat().st_size > MAX_INTRO_BYTES:
            raise HTTPException(400, "Fichier trop lourd (25 Mo maximum)")
        try:
            duration = audio.probe_duration(dest)
        except Exception:
            raise HTTPException(400, "Fichier MP3 illisible")
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    first = s.query(Intro).count() == 0
    intro = Intro(name=name.strip() or Path(file.filename).stem, path=str(dest), duration=duration,
                  is_default=False)
    s.add(intro)
    s.flush()
    if is_default or first:  # la première intro devient l'intro par défaut
        s.query(Intro).update({"is_default": False})
        intro.is_default = True
    s.commit()
    return intro_dict(intro)


@app.patch("/api/intros/{intro_id}")
def update_intro(intro_id: int, body: IntroPatch, s=Depends(db)):
    intro = s.get(Intro, intro_id) or _404("Intro")
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(400, "Nom vide")
        intro.name = body.name.strip()
    if body.is_default:
        s.query(Intro).update({"is_default": False})
        intro.is_default = True
    s.commit()
    return intro_dict(intro)


@app.delete("/api/intros/{intro_id}")
def delete_intro(intro_id: int, s=Depends(db)):
    intro = s.get(Intro, intro_id) or _404("Intro")
    # Les dossiers et traitements qui l'utilisaient repassent en « automatique »
    s.query(Folder).filter(Folder.intro_id == intro_id).update({"intro_id": None})
    s.query(Job).filter(Job.intro_id == intro_id).update({"intro_id": None})
    Path(intro.path).unlink(missing_ok=True)
    s.delete(intro)
    s.commit()
    return {"ok": True, "was_default": intro.is_default}


@app.get("/api/intros/{intro_id}/audio")
def play_intro(intro_id: int, s=Depends(db)):
    intro = s.get(Intro, intro_id) or _404("Intro")
    if not Path(intro.path).exists():
        raise HTTPException(404, "Fichier d'intro introuvable")
    return FileResponse(intro.path, media_type="audio/mpeg")


# --- Traitements ----------------------------------------------------------------
class JobIn(BaseModel):
    folder_id: int
    youtube_url: str
    title: str
    date: str | None = None
    start: str | None = None
    end: str | None = None
    intro_id: int | None = None  # None = automatique ; 0 = aucune intro


class RetryIn(BaseModel):
    start: str | None = None
    end: str | None = None
    intro_id: int | None = None  # pris en compte seulement s'il est envoyé


def _check_intro(s, intro_id):
    if intro_id and not s.get(Intro, intro_id):
        raise HTTPException(404, "Intro introuvable")


def _times(start, end):
    try:
        s, e = parse_time(start), parse_time(end)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if s is not None and e is not None and e <= s:
        raise HTTPException(400, "L'heure de fin doit être après l'heure de début")
    return s, e


@app.get("/api/folders/{folder_id}/jobs")
def list_jobs(folder_id: int, s=Depends(db)):
    jobs = (s.query(Job).filter(Job.folder_id == folder_id)
            .order_by(Job.date.desc(), Job.id.desc()).all())
    return [job_dict(j) for j in jobs]


@app.post("/api/jobs")
def create_job(body: JobIn, s=Depends(db)):
    if not s.get(Folder, body.folder_id):
        raise HTTPException(404, "Dossier introuvable")
    url = body.youtube_url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Lien YouTube invalide")
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Le nom est obligatoire")
    day = body.date or date_cls.today().isoformat()
    try:
        date_cls.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, "Date invalide (AAAA-MM-JJ)")
    start, end = _times(body.start, body.end)
    _check_intro(s, body.intro_id)
    job = Job(folder_id=body.folder_id, intro_id=body.intro_id, youtube_url=url, title=title, date=day,
              filename=f"{slugify(title)}_{day}", start_override=start, end_override=end)
    s.add(job)
    s.commit()
    return job_dict(job)


@app.get("/api/jobs")
def history(q: str = "", status: str = "", limit: int = 50, offset: int = 0, s=Depends(db)):
    """Historique de tous les traitements, tous dossiers confondus (le plus récent d'abord)."""
    query = s.query(Job)
    if status == "active":
        query = query.filter(Job.status.in_(["pending", "running"]))
    elif status in ("done", "error"):
        query = query.filter(Job.status == status)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Job.title.ilike(like), Job.video_title.ilike(like),
                                 Job.filename.ilike(like), Job.youtube_url.ilike(like)))
    total = query.count()
    jobs = (query.order_by(Job.created_at.desc(), Job.id.desc())
            .offset(max(offset, 0)).limit(min(max(limit, 1), 200)).all())
    return {"total": total, "items": [job_dict(j, s=s) for j in jobs]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, s=Depends(db)):
    job = s.get(Job, job_id) or _404("Traitement")
    d = job_dict(job, with_log=True, s=s)
    # Liens directs R2 (publics si R2_PUBLIC_BASE_URL, sinon signés et limités dans le temps)
    d["links"] = {}
    if storage.enabled():
        if job.r2_key_mp3:
            d["links"]["mp3"] = storage.link(job.r2_key_mp3)
    d["intro_name"] = ("Aucune" if job.intro_id == 0 else
                       (s.get(Intro, job.intro_id).name if job.intro_id and s.get(Intro, job.intro_id)
                        else "Automatique (dossier ou par défaut)"))
    d["links_public"] = bool(config.R2_PUBLIC_BASE_URL)
    d["links_days"] = max(config.R2_LINK_EXPIRES // 86400, 1)
    return d


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int, body: RetryIn, s=Depends(db)):
    job = s.get(Job, job_id) or _404("Traitement")
    if job.status == "running":
        raise HTTPException(400, "Traitement en cours")
    job.start_override, job.end_override = _times(body.start, body.end)
    if "intro_id" in body.model_fields_set:
        _check_intro(s, body.intro_id)
        job.intro_id = body.intro_id
    job.status, job.step, job.progress, job.error = "pending", "En attente", 0.0, None
    job.log = (job.log or "") + f"\n--- Relancé le {datetime.now():%d/%m/%Y %H:%M} ---\n"
    s.commit()
    return job_dict(job)


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int, s=Depends(db)):
    job = s.get(Job, job_id) or _404("Traitement")
    if job.status == "running":
        raise HTTPException(400, "Impossible de supprimer un traitement en cours")
    try:
        storage.delete([job.r2_key_mp3])
    except Exception as exc:
        raise HTTPException(502, f"Suppression R2 impossible : {exc}")
    shutil.rmtree(config.OUTPUT_DIR / str(job.id), ignore_errors=True)
    shutil.rmtree(config.CACHE_DIR / str(job.id), ignore_errors=True)
    s.delete(job)
    s.commit()
    return {"ok": True}


@app.get("/api/jobs/{job_id}/file/{fmt}")
def job_file(job_id: int, fmt: str, download: bool = False, s=Depends(db)):
    job = s.get(Job, job_id) or _404("Traitement")
    path = job.local_mp3 if fmt == "mp3" else None
    if not path or not Path(path).exists():
        raise HTTPException(404, "Fichier indisponible")
    return FileResponse(path, media_type="audio/mpeg",
                        filename=Path(path).name if download else None)


@app.get("/api/jobs/{job_id}/link/{fmt}")
def job_link(job_id: int, fmt: str, s=Depends(db)):
    job = s.get(Job, job_id) or _404("Traitement")
    key = job.r2_key_mp3 if fmt == "mp3" else None
    if not key or not storage.enabled():
        raise HTTPException(404, "Fichier absent de R2")
    return {"url": storage.link(key), "public": bool(config.R2_PUBLIC_BASE_URL)}


@app.get("/api/status")
def status(s=Depends(db)):
    return {
        "r2": storage.enabled(),
        "llm": config.LLM_PROVIDER if config.LLM_PROVIDER in ("anthropic", "openai") else None,
        "queue": s.query(Job).filter(Job.status.in_(["pending", "running"])).count(),
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}


def _404(what: str):
    raise HTTPException(404, f"{what} introuvable")


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


# --- Interface ----------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")

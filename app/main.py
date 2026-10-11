"""API web + interface."""
import base64
import secrets
import shutil
from datetime import date as date_cls, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, storage
from .db import Folder, Job, SessionLocal, init_db
from .pipeline import steps
from .utils import fmt_time, parse_time, slugify

STATIC = Path(__file__).parent / "static"
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".flac"}

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
    return {"id": f.id, "name": f.name, "parent_id": f.parent_id, "has_intro": bool(f.intro_path)}


def job_steps(j: Job) -> list[dict]:
    skipped = set()
    if j.start_override is not None or j.end_override is not None:
        skipped.add("detect")  # bornes saisies : pas de repérage
    if not (j.r2_key_ogg if j.status == "done" else storage.enabled()):
        skipped.add("upload")
    return steps.view(j.progress or 0.0, j.status, skipped)


def job_dict(j: Job, with_log: bool = False) -> dict:
    d = {
        "steps": job_steps(j),
        "id": j.id, "folder_id": j.folder_id, "youtube_url": j.youtube_url,
        "title": j.title, "date": j.date, "filename": j.filename,
        "status": j.status, "step": j.step, "progress": round(j.progress or 0, 3),
        "error": j.error, "video_title": j.video_title,
        "start_override": fmt_time(j.start_override), "end_override": fmt_time(j.end_override),
        "sermon_start": fmt_time(j.sermon_start), "sermon_end": fmt_time(j.sermon_end),
        "detection_note": j.detection_note,
        "duration_source": fmt_time(j.duration_source), "duration_output": fmt_time(j.duration_output),
        "has_ogg": bool(j.local_ogg and Path(j.local_ogg).exists()),
        "has_mp3": bool(j.local_mp3 and Path(j.local_mp3).exists()),
        "size_ogg": j.size_ogg, "size_mp3": j.size_mp3,
        "on_r2": bool(j.r2_key_ogg),
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }
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
    if f.intro_path:
        Path(f.intro_path).unlink(missing_ok=True)
    s.delete(f)
    s.commit()
    return {"ok": True}


def _save_intro(upload: UploadFile, stem: str) -> Path:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in AUDIO_EXT:
        raise HTTPException(400, f"Format non supporté ({ext}). Formats : {', '.join(sorted(AUDIO_EXT))}")
    for old in config.INTRO_DIR.glob(f"{stem}.*"):
        old.unlink()
    dest = config.INTRO_DIR / f"{stem}{ext}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(upload.file, fh)
    return dest


@app.post("/api/folders/{folder_id}/intro")
def upload_folder_intro(folder_id: int, file: UploadFile = File(...), s=Depends(db)):
    f = s.get(Folder, folder_id) or _404("Dossier")
    f.intro_path = str(_save_intro(file, f"folder_{folder_id}"))
    s.commit()
    return folder_dict(f)


@app.delete("/api/folders/{folder_id}/intro")
def delete_folder_intro(folder_id: int, s=Depends(db)):
    f = s.get(Folder, folder_id) or _404("Dossier")
    if f.intro_path:
        Path(f.intro_path).unlink(missing_ok=True)
    f.intro_path = None
    s.commit()
    return folder_dict(f)


@app.get("/api/intro/default")
def get_default_intro():
    files = sorted(config.INTRO_DIR.glob("default.*"))
    return {"exists": bool(files), "name": files[0].name if files else None}


@app.post("/api/intro/default")
def upload_default_intro(file: UploadFile = File(...)):
    dest = _save_intro(file, "default")
    return {"exists": True, "name": dest.name}


@app.get("/api/intro/{kind}/audio")
def play_intro(kind: str, s=Depends(db)):
    if kind == "default":
        files = sorted(config.INTRO_DIR.glob("default.*"))
        path = files[0] if files else None
    else:
        f = s.get(Folder, int(kind)) if kind.isdigit() else None
        path = Path(f.intro_path) if f and f.intro_path else None
    if not path or not path.exists():
        raise HTTPException(404, "Pas d'intro")
    return FileResponse(path)


# --- Traitements ----------------------------------------------------------------
class JobIn(BaseModel):
    folder_id: int
    youtube_url: str
    title: str
    date: str | None = None
    start: str | None = None
    end: str | None = None


class RetryIn(BaseModel):
    start: str | None = None
    end: str | None = None


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
    job = Job(folder_id=body.folder_id, youtube_url=url, title=title, date=day,
              filename=f"{slugify(title)}_{day}", start_override=start, end_override=end)
    s.add(job)
    s.commit()
    return job_dict(job)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, s=Depends(db)):
    return job_dict(s.get(Job, job_id) or _404("Traitement"), with_log=True)


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int, body: RetryIn, s=Depends(db)):
    job = s.get(Job, job_id) or _404("Traitement")
    if job.status == "running":
        raise HTTPException(400, "Traitement en cours")
    job.start_override, job.end_override = _times(body.start, body.end)
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
        storage.delete([job.r2_key_ogg, job.r2_key_mp3])
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
    path = {"ogg": job.local_ogg, "mp3": job.local_mp3}.get(fmt)
    if not path or not Path(path).exists():
        raise HTTPException(404, "Fichier indisponible")
    media = "audio/ogg" if fmt == "ogg" else "audio/mpeg"
    return FileResponse(path, media_type=media,
                        filename=Path(path).name if download else None)


@app.get("/api/jobs/{job_id}/link/{fmt}")
def job_link(job_id: int, fmt: str, s=Depends(db)):
    job = s.get(Job, job_id) or _404("Traitement")
    key = {"ogg": job.r2_key_ogg, "mp3": job.r2_key_mp3}.get(fmt)
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

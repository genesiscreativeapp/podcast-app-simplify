"""API web + interface."""
import re
import secrets
import shutil
from datetime import date as date_cls, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, or_

from . import auth, config, storage
from .pipeline import audio
from .db import (MAX_PARALLEL_LIMIT, Folder, Intro, Job, Setting, SessionLocal, User, folder_path,
                 get_max_parallel, init_db, queue_position)
from .pipeline import steps
from .utils import fmt_time, parse_time, slugify

STATIC = Path(__file__).parent / "static"
MAX_INTRO_BYTES = 25 * 1024 * 1024

app = FastAPI(title="Studio Podcast")
init_db()
auth.bootstrap_admin()


# --- Authentification par session (cookie) ------------------------------------------------
# Publics : l'interface (page de connexion incluse), ses fichiers statiques, /healthz et la connexion.
@app.middleware("http")
async def session_auth(request: Request, call_next):
    request.state.user = None
    path = request.url.path
    if path.startswith("/api/") and path != "/api/auth/login":
        with SessionLocal() as s:
            request.state.user = auth.user_from_token(s, request.cookies.get(auth.COOKIE))
        if request.state.user is None:
            return JSONResponse({"detail": "Non connecté"}, status_code=401)
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
    if not (config.REMOVE_OFFTOPIC and config.LLM_PROVIDER in ("anthropic", "openai")):
        skipped.add("clean")  # témoignages et annonces : nécessite une IA
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
        "duration_output_s": j.duration_output,
        "can_restore": bool(j.local_mp3 and (Path(j.local_mp3).parent / "original.mp3").exists()),
        "size_mp3": j.size_mp3,
        "on_r2": bool(j.r2_key_mp3),
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "edit_note": j.edit_note, "created_by": j.created_by,
    }
    if s is not None:
        folder = s.get(Folder, j.folder_id)
        d["folder_path"] = " / ".join(folder_path(s, folder)) if folder else ""
        d["queue_position"] = queue_position(s, j) if j.status == "pending" else None
    if with_log:
        d["log"] = j.log
    return d


# --- Dossiers --------------------------------------------------------------------
class FolderIn(BaseModel):
    name: str
    parent_id: int | None = None


class FolderPatch(BaseModel):
    name: str | None = None
    parent_id: int | None = None  # déplacement : pris en compte seulement s'il est envoyé (null = racine)


@app.get("/api/folders", dependencies=[Depends(auth.need("jobs.view"))])
def list_folders(s=Depends(db)):
    counts = dict(s.query(Job.folder_id, func.count(Job.id)).group_by(Job.folder_id).all())
    return [{**folder_dict(f), "job_count": counts.get(f.id, 0)} for f in s.query(Folder).order_by(Folder.name).all()]


@app.post("/api/folders", dependencies=[Depends(auth.need("folders.manage"))])
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


@app.patch("/api/folders/{folder_id}", dependencies=[Depends(auth.need("folders.manage"))])
def update_folder(folder_id: int, body: FolderPatch, s=Depends(db)):
    """Renomme et/ou déplace un dossier."""
    f = s.get(Folder, folder_id) or _404("Dossier")
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(400, "Nom de dossier vide")
        f.name = body.name.strip()
    if "parent_id" in body.model_fields_set:
        if body.parent_id:
            if not s.get(Folder, body.parent_id):
                raise HTTPException(404, "Dossier de destination introuvable")
            cur, seen = s.get(Folder, body.parent_id), set()
            while cur is not None and cur.id not in seen:  # on ne peut pas déplacer un dossier dans lui-même
                if cur.id == folder_id:
                    raise HTTPException(400, "Impossible de déplacer un dossier dans lui-même ou l'un de ses sous-dossiers")
                seen.add(cur.id)
                cur = s.get(Folder, cur.parent_id) if cur.parent_id else None
        f.parent_id = body.parent_id or None
    s.commit()
    return folder_dict(f)


@app.delete("/api/folders/{folder_id}", dependencies=[Depends(auth.need("folders.manage"))])
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


@app.put("/api/folders/{folder_id}/intro", dependencies=[Depends(auth.need("folders.manage"))])
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


@app.get("/api/intros", dependencies=[Depends(auth.need("jobs.view"))])
def list_intros(s=Depends(db)):
    return [intro_dict(i) for i in s.query(Intro).order_by(Intro.is_default.desc(), Intro.name).all()]


@app.post("/api/intros", dependencies=[Depends(auth.need("intros.manage"))])
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


@app.patch("/api/intros/{intro_id}", dependencies=[Depends(auth.need("intros.manage"))])
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


@app.delete("/api/intros/{intro_id}", dependencies=[Depends(auth.need("intros.manage"))])
def delete_intro(intro_id: int, s=Depends(db)):
    intro = s.get(Intro, intro_id) or _404("Intro")
    # Les dossiers et traitements qui l'utilisaient repassent en « automatique »
    s.query(Folder).filter(Folder.intro_id == intro_id).update({"intro_id": None})
    s.query(Job).filter(Job.intro_id == intro_id).update({"intro_id": None})
    Path(intro.path).unlink(missing_ok=True)
    s.delete(intro)
    s.commit()
    return {"ok": True, "was_default": intro.is_default}


@app.get("/api/intros/{intro_id}/audio", dependencies=[Depends(auth.need("jobs.view"))])
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


@app.get("/api/folders/{folder_id}/jobs", dependencies=[Depends(auth.need("jobs.view"))])
def list_jobs(folder_id: int, s=Depends(db)):
    jobs = (s.query(Job).filter(Job.folder_id == folder_id)
            .order_by(Job.date.desc(), Job.id.desc()).all())
    return [job_dict(j, s=s) for j in jobs]


@app.post("/api/jobs", dependencies=[Depends(auth.need("jobs.create"))])
def create_job(body: JobIn, request: Request, s=Depends(db)):
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
    job = Job(folder_id=body.folder_id, intro_id=body.intro_id, created_by=request.state.user.username, youtube_url=url, title=title, date=day,
              filename=f"{slugify(title)}_{day}", start_override=start, end_override=end)
    s.add(job)
    s.commit()
    return job_dict(job, s=s)


@app.get("/api/jobs", dependencies=[Depends(auth.need("jobs.view"))])
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


@app.get("/api/jobs/{job_id}", dependencies=[Depends(auth.need("jobs.view"))])
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


class MoveIn(BaseModel):
    folder_id: int


@app.post("/api/jobs/{job_id}/move", dependencies=[Depends(auth.need("folders.manage"))])
def move_job(job_id: int, body: MoveIn, s=Depends(db)):
    """Déplace un traitement dans un autre dossier (les fichiers déjà envoyés sur R2 ne changent pas de nom)."""
    job = s.get(Job, job_id) or _404("Traitement")
    if not s.get(Folder, body.folder_id):
        raise HTTPException(404, "Dossier de destination introuvable")
    job.folder_id = body.folder_id
    s.commit()
    return job_dict(job, s=s)


@app.post("/api/jobs/{job_id}/retry", dependencies=[Depends(auth.need("jobs.create"))])
def retry_job(job_id: int, body: RetryIn, s=Depends(db)):
    job = s.get(Job, job_id) or _404("Traitement")
    if job.status == "running":
        raise HTTPException(400, "Traitement en cours")
    job.start_override, job.end_override = _times(body.start, body.end)
    if "intro_id" in body.model_fields_set:
        _check_intro(s, body.intro_id)
        job.intro_id = body.intro_id
    job.status, job.step, job.progress, job.error = "pending", "En attente", 0.0, None
    job.updated_at = datetime.utcnow()  # repart en fin de file
    job.log = (job.log or "") + f"\n--- Relancé le {datetime.now():%d/%m/%Y %H:%M} ---\n"
    s.commit()
    return job_dict(job, s=s)


@app.delete("/api/jobs/{job_id}", dependencies=[Depends(auth.need("jobs.delete"))])
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


@app.get("/api/jobs/{job_id}/file/{fmt}", dependencies=[Depends(auth.need("jobs.view"))])
def job_file(job_id: int, fmt: str, download: bool = False, s=Depends(db)):
    job = s.get(Job, job_id) or _404("Traitement")
    path = job.local_mp3 if fmt == "mp3" else None
    if not path or not Path(path).exists():
        raise HTTPException(404, "Fichier indisponible")
    return FileResponse(path, media_type="audio/mpeg",
                        filename=Path(path).name if download else None)


class TrimIn(BaseModel):
    start: str | None = None
    end: str | None = None


def _publish_new_audio(s, job: Job, new_file: Path) -> None:
    """Remplace le MP3 d'un traitement terminé (disque, base et R2). R2 d'abord : en cas d'échec, rien ne change.
    Le fichier R2 change de nom : une copie en cache (CDN, navigateur) de l'ancien ne peut pas être resservie."""
    cur = Path(job.local_mp3)
    old_key, new_key = job.r2_key_mp3, None
    if old_key and storage.enabled():
        folder = s.get(Folder, job.folder_id)
        new_key = storage.build_key(folder_path(s, folder) if folder else [], f"{job.filename}-{secrets.token_hex(2)}.mp3")
        try:
            storage.upload(new_file, new_key, "audio/mpeg")
        except Exception as exc:
            new_file.unlink(missing_ok=True)
            raise HTTPException(502, f"Envoi vers R2 impossible : {exc}")
    new_file.replace(cur)
    job.size_mp3 = cur.stat().st_size
    job.duration_output = audio.probe_duration(cur)
    if new_key:
        job.r2_key_mp3 = new_key
    s.commit()
    if new_key and old_key:
        try:
            storage.delete([old_key])
        except Exception:
            pass  # l'ancien fichier reste orphelin sur R2 : sans gravité


def _done_job(s, job_id: int) -> Job:
    job = s.get(Job, job_id) or _404("Traitement")
    if job.status != "done" or not job.local_mp3 or not Path(job.local_mp3).exists():
        raise HTTPException(400, "Seul un podcast terminé peut être rogné")
    return job


@app.post("/api/jobs/{job_id}/trim", dependencies=[Depends(auth.need("jobs.trim"))])
def trim_job(job_id: int, body: TrimIn, s=Depends(db)):
    """Rogne le début et/ou la fin du podcast terminé, sans réencodage. L'original est gardé pour pouvoir revenir."""
    job = _done_job(s, job_id)
    start, end = _times(body.start, body.end)
    cur = Path(job.local_mp3)
    duration = audio.probe_duration(cur)
    start, end = start or 0.0, min(end if end is not None else duration, duration)
    if end - start < 1:
        raise HTTPException(400, "Il doit rester au moins 1 seconde")
    if start < 0.05 and end > duration - 0.05:
        raise HTTPException(400, "Rien à rogner : début et fin sont ceux du podcast")
    original = cur.with_name("original.mp3")
    if not original.exists():
        shutil.copy2(cur, original)
    tmp = cur.with_name("trim.tmp.mp3")
    try:
        audio.trim_mp3(cur, tmp, start, end)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise HTTPException(500, f"Rognage impossible : {exc}")
    _publish_new_audio(s, job, tmp)
    return job_dict(job, s=s)


@app.post("/api/jobs/{job_id}/trim/reset", dependencies=[Depends(auth.need("jobs.trim"))])
def reset_trim(job_id: int, s=Depends(db)):
    job = _done_job(s, job_id)
    cur = Path(job.local_mp3)
    original = cur.with_name("original.mp3")
    if not original.exists():
        raise HTTPException(400, "Aucun original à restaurer")
    tmp = cur.with_name("restore.tmp.mp3")
    shutil.copy2(original, tmp)
    _publish_new_audio(s, job, tmp)
    original.unlink(missing_ok=True)
    return job_dict(job, s=s)


@app.get("/api/jobs/{job_id}/link/{fmt}", dependencies=[Depends(auth.need("jobs.view"))])
def job_link(job_id: int, fmt: str, s=Depends(db)):
    job = s.get(Job, job_id) or _404("Traitement")
    key = job.r2_key_mp3 if fmt == "mp3" else None
    if not key or not storage.enabled():
        raise HTTPException(404, "Fichier absent de R2")
    return {"url": storage.link(key), "public": bool(config.R2_PUBLIC_BASE_URL)}


@app.get("/api/status", dependencies=[Depends(auth.need("jobs.view"))])
def status(s=Depends(db)):
    count = lambda st: s.query(Job).filter(Job.status == st).count()
    return {
        "r2": storage.enabled(),
        "llm": config.LLM_PROVIDER if config.LLM_PROVIDER in ("anthropic", "openai") else None,
        "running": count("running"), "pending": count("pending"),
        "max_parallel": get_max_parallel(s), "max_parallel_limit": MAX_PARALLEL_LIMIT,
    }


class SettingsIn(BaseModel):
    max_parallel: int


@app.put("/api/settings", dependencies=[Depends(auth.need("settings.manage"))])
def put_settings(body: SettingsIn, s=Depends(db)):
    if not 1 <= body.max_parallel <= MAX_PARALLEL_LIMIT:
        raise HTTPException(400, f"Entre 1 et {MAX_PARALLEL_LIMIT} traitements en parallèle")
    s.merge(Setting(key="max_parallel", value=str(body.max_parallel)))
    s.commit()
    return {"max_parallel": body.max_parallel}


# --- Connexion et comptes ---------------------------------------------------------------------
class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    current: str
    new: str


class UserIn(BaseModel):
    username: str
    display_name: str = ""
    password: str
    is_admin: bool = False
    permissions: list[str] = []


class UserPatch(BaseModel):
    display_name: str | None = None
    password: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None
    permissions: list[str] | None = None


def _clean_perms(perms: list[str]) -> str:
    return ",".join(sorted(set(perms) & set(auth.PERMISSIONS)))


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response, s=Depends(db)):
    name = body.username.strip().lower()
    keys = [f"ip:{request.client.host if request.client else '?'}", f"user:{name}"]
    for k in keys:
        auth.throttle_check(k)
    user = s.query(User).filter(User.username == name).first()
    # on vérifie toujours un hash, même si le compte n'existe pas (temps de réponse identique)
    ok = auth.verify_password(body.password, user.password_hash if user else auth.hash_password("x"))
    if not (user and ok and user.is_active):
        for k in keys:
            auth.throttle_fail(k)
        raise HTTPException(401, "Identifiant ou mot de passe incorrect")
    for k in keys:
        auth.throttle_reset(k)
    token = auth.create_session(s, user)
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax", path="/",
                        secure=request.url.scheme == "https", max_age=config.SESSION_DAYS * 86400)
    return auth.user_dict(user)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, s=Depends(db)):
    auth.drop_token(s, request.cookies.get(auth.COOKIE))
    s.commit()
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    return {**auth.user_dict(request.state.user), "catalog": auth.PERMISSIONS}


@app.post("/api/auth/password")
def change_password(body: PasswordIn, request: Request, s=Depends(db)):
    user = s.get(User, request.state.user.id)
    if not auth.verify_password(body.current, user.password_hash):
        raise HTTPException(400, "Mot de passe actuel incorrect")
    auth.check_password_strength(body.new)
    user.password_hash = auth.hash_password(body.new)
    token = request.cookies.get(auth.COOKIE)
    auth.drop_sessions(s, user.id)  # les autres appareils doivent se reconnecter
    s.commit()
    new_token = auth.create_session(s, user)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, new_token, httponly=True, samesite="lax", path="/",
                    secure=request.url.scheme == "https", max_age=config.SESSION_DAYS * 86400)
    return resp


@app.get("/api/users", dependencies=[Depends(auth.need("admin"))])
def list_users(s=Depends(db)):
    return [auth.user_dict(u) for u in s.query(User).order_by(User.username).all()]


@app.post("/api/users", dependencies=[Depends(auth.need("admin"))])
def create_user(body: UserIn, s=Depends(db)):
    name = body.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,40}", name):
        raise HTTPException(400, "Identifiant : 3 à 40 caractères (lettres, chiffres, . _ -)")
    if s.query(User).filter(User.username == name).first():
        raise HTTPException(400, "Cet identifiant existe déjà")
    auth.check_password_strength(body.password)
    user = User(username=name, display_name=body.display_name.strip(), is_admin=body.is_admin,
                permissions=_clean_perms(body.permissions), password_hash=auth.hash_password(body.password))
    s.add(user)
    s.commit()
    return auth.user_dict(user)


def _other_active_admins(s, user_id: int) -> int:
    return s.query(User).filter(User.is_admin, User.is_active, User.id != user_id).count()


@app.patch("/api/users/{user_id}")
def update_user(user_id: int, body: UserPatch, request: Request, s=Depends(db),
                _=Depends(auth.need("admin"))):
    user = s.get(User, user_id) or _404("Utilisateur")
    if user.is_system:
        raise HTTPException(403, auth.SYSTEM_MSG)
    me_id = request.state.user.id
    losing_admin = (body.is_admin is False and user.is_admin) or (body.is_active is False and user.is_admin)
    if losing_admin and not _other_active_admins(s, user_id):
        raise HTTPException(400, "Il doit rester au moins un administrateur actif")
    if user_id == me_id and (body.is_active is False or body.is_admin is False):
        raise HTTPException(400, "Vous ne pouvez pas retirer vos propres droits ni désactiver votre compte")
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    if body.permissions is not None:
        user.permissions = _clean_perms(body.permissions)
    if body.password:
        auth.check_password_strength(body.password)
        user.password_hash = auth.hash_password(body.password)
        auth.drop_sessions(s, user_id)
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            auth.drop_sessions(s, user_id)
    s.commit()
    return auth.user_dict(user)


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, request: Request, s=Depends(db), _=Depends(auth.need("admin"))):
    user = s.get(User, user_id) or _404("Utilisateur")
    if user.is_system:
        raise HTTPException(403, auth.SYSTEM_MSG)
    if user_id == request.state.user.id:
        raise HTTPException(400, "Vous ne pouvez pas supprimer votre propre compte")
    if user.is_admin and not _other_active_admins(s, user_id):
        raise HTTPException(400, "Il doit rester au moins un administrateur actif")
    auth.drop_sessions(s, user_id)
    s.delete(user)
    s.commit()
    return {"ok": True}


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

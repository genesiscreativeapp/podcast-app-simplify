"""API web + interface."""
import json
import re
import secrets
import shutil
import time
from datetime import date as date_cls, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, or_

from . import auth, config, r2sync, storage, vault
from .access import Access
from .pipeline import audio
from .db import (MAX_PARALLEL_LIMIT, Folder, FolderAccess, Intro, Job, Setting, SessionLocal, User, folder_path,
                 ai_enabled, ai_for, get_max_parallel, has_perm, init_db, personal_key, queue_position)
from .pipeline import steps
from .pipeline.detect import ask_llm
from .utils import fmt_time, parse_time, slugify

STATIC = Path(__file__).parent / "static"
MAX_INTRO_BYTES = 25 * 1024 * 1024
UPLOAD_SCHEME = config.UPLOAD_SCHEME
UPLOAD_EXT = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma", ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".mpeg", ".mpg", ".3gp"}

app = FastAPI(title="Studio Podcast")
init_db()
auth.bootstrap_admin()
r2sync.trigger()  # à chaque démarrage : R2 est remis en conformité avec la plateforme (idempotent)


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


def acl(request: Request, s=Depends(db)) -> Access:
    return Access(s, request.state.user)


# --- Sérialisation ---------------------------------------------------------------
def folder_dict(f: Folder) -> dict:
    return {"id": f.id, "name": f.name, "parent_id": f.parent_id, "intro_id": f.intro_id}


def job_steps(j: Job, ai: bool | None = None) -> list[dict]:
    skipped = set()
    if j.youtube_url.startswith(UPLOAD_SCHEME):
        skipped.add("download")  # fichier envoyé par l'utilisateur : rien à télécharger
    if j.start_override is not None or j.end_override is not None:
        skipped.add("detect")  # bornes saisies : pas de repérage
    if not (j.r2_key_mp3 if j.status == "done" else storage.enabled()):
        skipped.add("upload")
    if ai is None:
        ai = config.LLM_PROVIDER in ("anthropic", "openai")
    if not (config.REMOVE_OFFTOPIC and ai):
        skipped.add("clean")  # témoignages et annonces : nécessite une IA
    return steps.view(j.progress or 0.0, j.status, skipped)


def job_dict(j: Job, with_log: bool = False, s=None, a: Access | None = None) -> dict:
    d = {
        "steps": job_steps(j, ai_for(s, j.created_by)[0] if s is not None else None),
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
        "tokens_in": j.tokens_in or 0, "tokens_out": j.tokens_out or 0,
        "edit_note": j.edit_note, "created_by": j.created_by, "from_upload": j.youtube_url.startswith(UPLOAD_SCHEME),
        "display_filename": r2sync.display_filename(j), "r2_key": j.r2_key_mp3,
    }
    if s is not None:
        folder = s.get(Folder, j.folder_id)
        d["folder_path"] = " / ".join(folder_path(s, folder)) if folder else ""
        d["queue_position"] = queue_position(s, j) if j.status == "pending" else None
    if a is not None:
        d["can_edit"] = a.owns_job(j)
    if with_log:
        d["log"] = j.log
    if a is not None and not a.admin:  # utilisateur lambda : pas de détails techniques (source, repérage, montage, journal, chemin R2)
        d.update(youtube_url="", video_title=None, start_override="", end_override="", sermon_start="", sermon_end="",
                 detection_note=None, edit_note=None, duration_source="", r2_key=None,
                 error="Le traitement a échoué. Contactez un administrateur." if j.error else None)
        d.pop("log", None)
    return d


# --- Dossiers --------------------------------------------------------------------
class FolderIn(BaseModel):
    name: str
    parent_id: int | None = None


class FolderPatch(BaseModel):
    name: str | None = None
    parent_id: int | None = None  # déplacement : pris en compte seulement s'il est envoyé (null = racine)


def _check_sibling(s, parent_id, name, exclude_id=None):
    """Deux dossiers frères ne peuvent pas avoir le même nom (ils auraient le même chemin sur R2)."""
    want = r2sync.sanitize(name).lower()
    q = s.query(Folder).filter(Folder.parent_id == parent_id if parent_id else Folder.parent_id.is_(None))
    for f in q:
        if f.id != exclude_id and r2sync.sanitize(f.name).lower() == want:
            raise HTTPException(400, f"Un dossier « {f.name} » existe déjà à cet endroit")


@app.get("/api/folders", dependencies=[Depends(auth.need("jobs.view"))])
def list_folders(request: Request, s=Depends(db), a: Access = Depends(acl)):
    counts = dict(s.query(Job.folder_id, func.count(Job.id)).group_by(Job.folder_id).all())
    active = {(fid, st): n for fid, st, n in s.query(Job.folder_id, Job.status, func.count(Job.id))
              .filter(Job.status.in_(["pending", "running"])).group_by(Job.folder_id, Job.status)}
    shared = {}
    if a.admin:
        for fid, uid in s.query(FolderAccess.folder_id, FolderAccess.user_id):
            shared.setdefault(fid, []).append(uid)
    visible = a.visible_ids()
    out = []
    for f in s.query(Folder).order_by(Folder.name).all():
        if f.id not in visible:
            continue
        d = folder_dict(f)
        if f.parent_id not in visible:
            d["parent_id"] = None  # racine « virtuelle » d'un dossier attribué : on ne montre pas ce qui est au-dessus
        out.append({**d, "job_count": counts.get(f.id, 0), "running": active.get((f.id, "running"), 0),
                    "pending": active.get((f.id, "pending"), 0), "created_by": f.created_by,
                    "can_edit": a.owns_folder(f.id), "assigned": f.id in a.assigned,
                    **({"shared_with": shared.get(f.id, [])} if a.admin else {})})
    return out


@app.post("/api/folders", dependencies=[Depends(auth.need("folders.manage"))])
def create_folder(body: FolderIn, request: Request, s=Depends(db), a: Access = Depends(acl)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Nom de dossier vide")
    if body.parent_id:
        a.need_folder(body.parent_id)
    _check_sibling(s, body.parent_id, name)
    f = Folder(name=name, parent_id=body.parent_id, created_by=request.state.user.username)
    s.add(f)
    s.commit()
    r2sync.trigger()
    return folder_dict(f)


@app.patch("/api/folders/{folder_id}", dependencies=[Depends(auth.need("folders.manage"))])
def update_folder(folder_id: int, body: FolderPatch, s=Depends(db), a: Access = Depends(acl)):
    """Renomme et/ou déplace un dossier."""
    f = a.need_folder_edit(folder_id)
    if body.name is not None and not body.name.strip():
        raise HTTPException(400, "Nom de dossier vide")
    _check_sibling(s, body.parent_id if "parent_id" in body.model_fields_set else f.parent_id,
                   body.name.strip() if body.name is not None else f.name, exclude_id=f.id)
    if body.name is not None:
        f.name = body.name.strip()
    if "parent_id" in body.model_fields_set:
        if body.parent_id:
            a.need_folder(body.parent_id)
            cur, seen = s.get(Folder, body.parent_id), set()
            while cur is not None and cur.id not in seen:  # on ne peut pas déplacer un dossier dans lui-même
                if cur.id == folder_id:
                    raise HTTPException(400, "Impossible de déplacer un dossier dans lui-même ou l'un de ses sous-dossiers")
                seen.add(cur.id)
                cur = s.get(Folder, cur.parent_id) if cur.parent_id else None
        f.parent_id = body.parent_id or None
    s.commit()
    r2sync.trigger()  # les podcasts du dossier changent de chemin sur R2
    return folder_dict(f)


@app.delete("/api/folders/{folder_id}", dependencies=[Depends(auth.need("folders.manage"))])
def delete_folder(folder_id: int, s=Depends(db), a: Access = Depends(acl)):
    f = a.need_folder_edit(folder_id)
    if s.query(Folder).filter(Folder.parent_id == folder_id).count() or \
       s.query(Job).filter(Job.folder_id == folder_id).count():
        raise HTTPException(400, "Le dossier n'est pas vide (sous-dossiers ou traitements)")
    s.query(FolderAccess).filter(FolderAccess.folder_id == folder_id).delete()
    s.delete(f)
    s.commit()
    r2sync.trigger()  # retire l'objet « dossier » devenu inutile sur R2
    return {"ok": True}


class AccessIn(BaseModel):
    user_ids: list[int]


@app.get("/api/folders/{folder_id}/access", dependencies=[Depends(auth.need("admin"))])
def get_folder_access(folder_id: int, s=Depends(db)):
    s.get(Folder, folder_id) or _404("Dossier")
    return {"user_ids": [r[0] for r in s.query(FolderAccess.user_id).filter(FolderAccess.folder_id == folder_id)]}


@app.put("/api/folders/{folder_id}/access", dependencies=[Depends(auth.need("admin"))])
def set_folder_access(folder_id: int, body: AccessIn, s=Depends(db)):
    """Attribue un dossier à des utilisateurs : ils y travaillent (sous-dossiers compris) sans pouvoir le modifier."""
    s.get(Folder, folder_id) or _404("Dossier")
    ids = {u.id for u in s.query(User).filter(User.id.in_(body.user_ids), User.is_admin.is_(False))}
    s.query(FolderAccess).filter(FolderAccess.folder_id == folder_id).delete()
    s.add_all(FolderAccess(folder_id=folder_id, user_id=i) for i in ids)
    s.commit()
    return {"user_ids": sorted(ids)}


class FolderIntro(BaseModel):
    intro_id: int | None = None  # None = hériter du parent / intro par défaut


@app.put("/api/folders/{folder_id}/intro", dependencies=[Depends(auth.need("folders.manage"))])
def set_folder_intro(folder_id: int, body: FolderIntro, s=Depends(db), a: Access = Depends(acl)):
    f = a.need_folder_edit(folder_id)
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
    youtube_url: str = ""
    upload_id: str | None = None  # fichier déjà envoyé (zone d'attente d'un lot) à la place d'un lien
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
def list_jobs(folder_id: int, s=Depends(db), a: Access = Depends(acl)):
    a.need_folder(folder_id)
    jobs = (s.query(Job).filter(Job.folder_id == folder_id)
            .order_by(Job.date.desc(), Job.id.desc()).all())
    return [job_dict(j, s=s, a=a) for j in jobs]


def _job_fields(body_title, body_date, start, end, intro_id, s):
    """Contrôles communs à la création depuis un lien et depuis un fichier."""
    title = (body_title or "").strip()
    if not title:
        raise HTTPException(400, "Le nom est obligatoire")
    day = body_date or date_cls.today().isoformat()
    try:
        date_cls.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, "Date invalide (AAAA-MM-JJ)")
    start, end = _times(start, end)
    _check_intro(s, intro_id)
    return title, day, start, end


# --- Fichiers envoyés : zone d'attente (lots) puis rattachement à un traitement ------------------
STAGED_ID = re.compile(r"[0-9a-f]{16}")


def _purge_staging() -> None:
    """Retire les fichiers en attente depuis trop longtemps (ajoutés à un lot mais jamais lancés) et les envois interrompus."""
    now = time.time()
    for d in config.STAGING_DIR.iterdir():
        limit = 86400 if d.name.endswith(".part") else config.STAGING_DAYS * 86400
        if now - d.stat().st_mtime > limit:
            shutil.rmtree(d, ignore_errors=True)


_purge_staging()


def _stage_file(file: UploadFile, username: str) -> dict:
    """Enregistre un fichier envoyé dans la zone d'attente. Visible seulement une fois complet et lisible."""
    name = Path(file.filename or "").name
    ext = Path(name).suffix.lower()
    if ext not in UPLOAD_EXT:
        raise HTTPException(400, "Format non pris en charge (MP3, M4A, WAV, MP4, MKV, MOV, WEBM…)")
    _purge_staging()
    uid = secrets.token_hex(8)
    part = config.STAGING_DIR / f"{uid}.part"
    try:
        part.mkdir()
        dest, written, limit = part / f"source{ext}", 0, config.MAX_UPLOAD_MB * 1024 * 1024
        with open(dest, "wb") as out:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(413, f"Fichier trop volumineux (maximum {config.MAX_UPLOAD_MB} Mo)")
                out.write(chunk)
        try:
            audio.probe_duration(dest)
        except Exception:
            raise HTTPException(400, "Ce fichier n'est pas un audio ou une vidéo lisible")
        meta = {"id": uid, "name": name, "size": written, "owner": username}
        (part / "meta.json").write_text(json.dumps(meta))
        part.replace(config.STAGING_DIR / uid)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    return meta


def _staged(upload_id: str, user: User) -> tuple[Path, dict]:
    """Dossier et description d'un fichier en attente (réservé à celui qui l'a envoyé)."""
    gone = HTTPException(404, "Fichier envoyé introuvable ou expiré : renvoyez-le")
    if not STAGED_ID.fullmatch(upload_id):
        raise gone
    d = config.STAGING_DIR / upload_id
    try:
        meta = json.loads((d / "meta.json").read_text())
    except (OSError, ValueError):
        raise gone
    if meta.get("owner") != user.username:
        raise gone
    return d, meta


def _job_from_staged(s, a: Access, user: User, upload_id: str, folder_id: int, title: str, day: str,
                     start, end, intro) -> Job:
    """Crée le traitement et lui donne le fichier en attente comme audio source (même suite que pour un lien)."""
    d, meta = _staged(upload_id, user)
    job = Job(folder_id=folder_id, intro_id=intro, created_by=user.username,
              youtube_url=f"{UPLOAD_SCHEME}{meta['name']}", video_title=Path(meta["name"]).stem, title=title, date=day,
              filename=f"{slugify(title)}_{day}", start_override=start, end_override=end)
    s.add(job)
    s.flush()  # id du traitement, sans le rendre visible au worker avant que le fichier soit en place
    final, moved = config.CACHE_DIR / str(job.id), False
    try:
        shutil.rmtree(final, ignore_errors=True)
        d.replace(final)
        moved = True
        (final / "ok").touch()
        s.commit()
    except BaseException:
        s.rollback()
        if moved:
            (final / "ok").unlink(missing_ok=True)
            final.replace(d)  # le fichier reste en attente : rien n'est perdu
        raise
    (final / "meta.json").unlink(missing_ok=True)
    return job


@app.post("/api/uploads", dependencies=[Depends(auth.need("jobs.create"))])
def stage_upload(request: Request, file: UploadFile = File(...)):
    """Envoie un fichier dès son ajout à un lot : il reste sur le serveur jusqu'au lancement (STAGING_DAYS jours)."""
    m = _stage_file(file, request.state.user.username)
    return {k: m[k] for k in ("id", "name", "size")}


@app.get("/api/uploads", dependencies=[Depends(auth.need("jobs.create"))])
def list_uploads(request: Request):
    out = []
    for d in sorted(config.STAGING_DIR.iterdir()):
        if STAGED_ID.fullmatch(d.name):
            try:
                _, m = _staged(d.name, request.state.user)
                out.append({k: m[k] for k in ("id", "name", "size")})
            except HTTPException:
                pass
    return out


@app.delete("/api/uploads/{upload_id}", dependencies=[Depends(auth.need("jobs.create"))])
def delete_upload(upload_id: str, request: Request):
    d, _ = _staged(upload_id, request.state.user)
    shutil.rmtree(d, ignore_errors=True)
    return {"ok": True}


@app.post("/api/jobs", dependencies=[Depends(auth.need("jobs.create"))])
def create_job(body: JobIn, request: Request, s=Depends(db), a: Access = Depends(acl)):
    a.need_folder(body.folder_id)
    if body.upload_id:
        title, day, start, end = _job_fields(body.title, body.date, body.start, body.end, body.intro_id, s)
        job = _job_from_staged(s, a, request.state.user, body.upload_id, body.folder_id, title, day, start, end, body.intro_id)
        return job_dict(job, s=s, a=a)
    url = body.youtube_url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Lien YouTube invalide")
    title, day, start, end = _job_fields(body.title, body.date, body.start, body.end, body.intro_id, s)
    job = Job(folder_id=body.folder_id, intro_id=body.intro_id, created_by=request.state.user.username, youtube_url=url, title=title, date=day,
              filename=f"{slugify(title)}_{day}", start_override=start, end_override=end)
    s.add(job)
    s.commit()
    return job_dict(job, s=s, a=a)


@app.post("/api/jobs/upload", dependencies=[Depends(auth.need("jobs.create"))])
def create_job_from_file(request: Request, file: UploadFile = File(...), folder_id: int = Form(...), title: str = Form(""),
                         date: str = Form(""), start: str = Form(""), end: str = Form(""), intro_id: str = Form(""),
                         s=Depends(db), a: Access = Depends(acl)):
    """Traitement individuel à partir d'un fichier audio/vidéo envoyé (au lieu d'un lien YouTube) : envoi puis rattachement."""
    a.need_folder(folder_id)
    try:
        intro = None if intro_id == "" else int(intro_id)
    except ValueError:
        raise HTTPException(400, "Intro invalide")
    name = Path(file.filename or "").name
    title, day, start_s, end_s = _job_fields(title or Path(name).stem, date, start, end, intro, s)
    user = request.state.user
    meta = _stage_file(file, user.username)
    try:
        job = _job_from_staged(s, a, user, meta["id"], folder_id, title, day, start_s, end_s, intro)
    except BaseException:
        shutil.rmtree(config.STAGING_DIR / meta["id"], ignore_errors=True)
        raise
    return job_dict(job, s=s, a=a)


@app.get("/api/jobs", dependencies=[Depends(auth.need("jobs.view"))])
def history(q: str = "", status: str = "", limit: int = 50, offset: int = 0, s=Depends(db), a: Access = Depends(acl)):
    """Historique de tous les traitements, tous dossiers confondus (le plus récent d'abord)."""
    query = a.jobs(s.query(Job))
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
    return {"total": total, "items": [job_dict(j, s=s, a=a) for j in jobs]}


@app.get("/api/jobs/{job_id}", dependencies=[Depends(auth.need("jobs.view"))])
def get_job(job_id: int, s=Depends(db), a: Access = Depends(acl)):
    job = a.need_job(s, job_id)
    d = job_dict(job, with_log=True, s=s, a=a)
    # Liens directs R2 (publics si R2_PUBLIC_BASE_URL, sinon signés et limités dans le temps)
    d["links"] = {}
    if storage.enabled():
        if job.r2_key_mp3:
            d["links"]["mp3"] = storage.link(job.r2_key_mp3)
    if a.admin:
        d["intro_name"] = ("Aucune" if job.intro_id == 0 else
                           (s.get(Intro, job.intro_id).name if job.intro_id and s.get(Intro, job.intro_id)
                            else "Automatique (dossier ou par défaut)"))
    d["links_public"] = bool(config.R2_PUBLIC_BASE_URL)
    d["links_days"] = max(config.R2_LINK_EXPIRES // 86400, 1)
    return d


class MoveIn(BaseModel):
    folder_id: int


@app.post("/api/jobs/{job_id}/move", dependencies=[Depends(auth.need("folders.manage"))])
def move_job(job_id: int, body: MoveIn, s=Depends(db), a: Access = Depends(acl)):
    """Déplace un traitement dans un autre dossier (les fichiers déjà envoyés sur R2 ne changent pas de nom)."""
    job = a.need_job(s, job_id, edit=True)
    a.need_folder(body.folder_id)
    job.folder_id = body.folder_id
    s.commit()
    r2sync.trigger()
    return job_dict(job, s=s, a=a)


class JobRename(BaseModel):
    title: str


@app.patch("/api/jobs/{job_id}", dependencies=[Depends(auth.need("folders.manage"))])
def rename_job(job_id: int, body: JobRename, s=Depends(db), a: Access = Depends(acl)):
    """Renomme un podcast, même pendant son traitement : nom affiché, nom du fichier local et fichier R2 suivent."""
    job = a.need_job(s, job_id, edit=True)
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Le nom est obligatoire")
    job.title = title
    job.filename = f"{slugify(title)}_{job.date}"
    if job.local_mp3 and Path(job.local_mp3).exists():  # déjà encodé : on renomme aussi le fichier local
        target = Path(job.local_mp3).with_name(f"{job.filename}.mp3")
        if target != Path(job.local_mp3):
            Path(job.local_mp3).replace(target)
            job.local_mp3 = str(target)
    s.commit()
    r2sync.trigger()
    return job_dict(job, s=s, a=a)


@app.post("/api/jobs/{job_id}/retry", dependencies=[Depends(auth.need("jobs.create"))])
def retry_job(job_id: int, body: RetryIn, s=Depends(db), a: Access = Depends(acl)):
    job = a.need_job(s, job_id, edit=True)
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
    return job_dict(job, s=s, a=a)


@app.delete("/api/jobs/{job_id}", dependencies=[Depends(auth.need("jobs.delete"))])
def delete_job(job_id: int, s=Depends(db), a: Access = Depends(acl)):
    job = a.need_job(s, job_id, edit=True)
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
def job_file(job_id: int, fmt: str, download: bool = False, s=Depends(db), a: Access = Depends(acl)):
    job = a.need_job(s, job_id)
    path = job.local_mp3 if fmt == "mp3" else None
    if not path or not Path(path).exists():
        raise HTTPException(404, "Fichier indisponible")
    return FileResponse(path, media_type="audio/mpeg",
                        filename=r2sync.display_filename(job) if download else None)


class TrimIn(BaseModel):
    start: str | None = None
    end: str | None = None


def _publish_new_audio(s, job: Job, new_file: Path) -> None:
    """Remplace le MP3 d'un traitement terminé (disque, base et R2, au même chemin).
    R2 d'abord : en cas d'échec d'envoi, rien ne change."""
    cur = Path(job.local_mp3)
    if job.r2_key_mp3 and storage.enabled():
        try:
            storage.upload(new_file, job.r2_key_mp3, "audio/mpeg")
        except Exception as exc:
            new_file.unlink(missing_ok=True)
            raise HTTPException(502, f"Envoi vers R2 impossible : {exc}")
    new_file.replace(cur)
    job.size_mp3 = cur.stat().st_size
    job.duration_output = audio.probe_duration(cur)
    s.commit()


def _done_job(s, job_id: int, a: Access) -> Job:
    job = a.need_job(s, job_id, edit=True)
    if job.status != "done" or not job.local_mp3 or not Path(job.local_mp3).exists():
        raise HTTPException(400, "Seul un podcast terminé peut être rogné")
    return job


@app.post("/api/jobs/{job_id}/trim", dependencies=[Depends(auth.need("jobs.trim"))])
def trim_job(job_id: int, body: TrimIn, s=Depends(db), a: Access = Depends(acl)):
    """Rogne le début et/ou la fin du podcast terminé, sans réencodage. L'original est gardé pour pouvoir revenir."""
    job = _done_job(s, job_id, a)
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
    return job_dict(job, s=s, a=a)


@app.post("/api/jobs/{job_id}/trim/reset", dependencies=[Depends(auth.need("jobs.trim"))])
def reset_trim(job_id: int, s=Depends(db), a: Access = Depends(acl)):
    job = _done_job(s, job_id, a)
    cur = Path(job.local_mp3)
    original = cur.with_name("original.mp3")
    if not original.exists():
        raise HTTPException(400, "Aucun original à restaurer")
    tmp = cur.with_name("restore.tmp.mp3")
    shutil.copy2(original, tmp)
    _publish_new_audio(s, job, tmp)
    original.unlink(missing_ok=True)
    return job_dict(job, s=s, a=a)


@app.get("/api/jobs/{job_id}/link/{fmt}", dependencies=[Depends(auth.need("jobs.view"))])
def job_link(job_id: int, fmt: str, s=Depends(db), a: Access = Depends(acl)):
    job = a.need_job(s, job_id)
    key = job.r2_key_mp3 if fmt == "mp3" else None
    if not key or not storage.enabled():
        raise HTTPException(404, "Fichier absent de R2")
    return {"url": storage.link(key), "public": bool(config.R2_PUBLIC_BASE_URL)}


@app.get("/api/status", dependencies=[Depends(auth.need("jobs.view"))])
def status(request: Request, s=Depends(db), a: Access = Depends(acl)):
    count = lambda st: a.jobs(s.query(Job)).filter(Job.status == st).count()
    server = config.LLM_PROVIDER if config.LLM_PROVIDER in ("anthropic", "openai") else None
    on, key = ai_for(s, request.state.user.username)  # l'IA telle qu'elle servira à CET utilisateur
    own = personal_key(request.state.user)
    return {
        "r2": storage.enabled(),
        "llm": ("anthropic" if key else server) if on else None,  # fournisseur réellement utilisé (None = heuristique)
        "ai_available": bool(server or own), "ai_enabled": on, "ai_personal": bool(key),
        "ai_global": ai_enabled(s), "server_provider": server,  # réglage du serveur (interrupteur de l'administrateur)
        "llm_provider": "anthropic" if own else server,
        "running": count("running"), "pending": count("pending"),
        "r2_sync": r2sync.status(),
        "max_parallel": get_max_parallel(s), "max_parallel_limit": MAX_PARALLEL_LIMIT,
        "max_upload_mb": config.MAX_UPLOAD_MB, "staging_days": config.STAGING_DAYS,
    }


@app.get("/api/r2/sync", dependencies=[Depends(auth.need("jobs.view"))])
def r2_sync_status():
    return r2sync.status()


@app.post("/api/r2/sync", dependencies=[Depends(auth.need("folders.manage"))])
def r2_sync_run():
    """Remet R2 en conformité avec la plateforme (déplace, envoie les fichiers manquants, crée les dossiers)."""
    if not storage.enabled():
        raise HTTPException(400, "R2 n'est pas configuré")
    r2sync.trigger()
    return r2sync.status()


class AiIn(BaseModel):
    enabled: bool


@app.put("/api/settings/ai", dependencies=[Depends(auth.need("admin"))])
def put_ai(body: AiIn, s=Depends(db)):
    """Active ou coupe l'IA (repérage de la prédication, retrait des témoignages et annonces), sans toucher à la configuration."""
    if body.enabled and config.LLM_PROVIDER not in ("anthropic", "openai"):
        raise HTTPException(400, "Aucun fournisseur d'IA n'est configuré (LLM_PROVIDER et LLM_API_KEY)")
    s.merge(Setting(key="ai_enabled", value="1" if body.enabled else "0"))
    s.commit()
    return {"ai_enabled": ai_enabled(s)}


# --- IA personnelle : clé Anthropic propre à l'utilisateur, et interrupteur pour ses seuls traitements ---------
def _my_ai(user: User) -> dict:
    key = vault.decrypt(user.llm_key) if user.llm_key else None
    return {"has_key": bool(key), "key_hint": f"sk-ant-…{key[-4:]}" if key else "", "enabled": user.ai_on,
            "can_key": has_perm(user, "ai.key"), "can_toggle": has_perm(user, "ai.toggle"),
            "server_ai": config.LLM_PROVIDER in ("anthropic", "openai")}


@app.get("/api/me/ai")
def get_my_ai(request: Request, s=Depends(db)):
    return _my_ai(s.get(User, request.state.user.id))


class MyAiIn(BaseModel):
    enabled: bool


@app.put("/api/me/ai", dependencies=[Depends(auth.need("ai.toggle"))])
def put_my_ai(body: MyAiIn, request: Request, s=Depends(db)):
    user = s.get(User, request.state.user.id)
    user.ai_on = body.enabled
    s.commit()
    return _my_ai(user)


class MyKeyIn(BaseModel):
    key: str


@app.put("/api/me/ai/key", dependencies=[Depends(auth.need("ai.key"))])
def put_my_key(body: MyKeyIn, request: Request, s=Depends(db)):
    key = body.key.strip()
    if not re.fullmatch(r"sk-ant-[A-Za-z0-9_-]{20,}", key):
        raise HTTPException(400, "Ce n'est pas une clé Anthropic (elle commence par « sk-ant- »)")
    try:  # petit appel réel : la clé doit pouvoir servir au traitement (crédit, modèle autorisé…)
        ask_llm("Réponds OK.", max_tokens=5, key=key)
    except Exception as exc:
        raise HTTPException(400, f"Clé refusée ou inutilisable : {exc}")
    user = s.get(User, request.state.user.id)
    user.llm_key = vault.encrypt(key)
    s.commit()
    return _my_ai(user)


@app.delete("/api/me/ai/key")
def delete_my_key(request: Request, s=Depends(db)):
    user = s.get(User, request.state.user.id)
    user.llm_key = None
    s.commit()
    return _my_ai(user)


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
    max_parallel: int = 5


class UserPatch(BaseModel):
    display_name: str | None = None
    password: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None
    permissions: list[str] | None = None
    max_parallel: int | None = None


def _check_quota(n: int) -> int:
    if not 1 <= n <= MAX_PARALLEL_LIMIT:
        raise HTTPException(400, f"Traitements simultanés : entre 1 et {MAX_PARALLEL_LIMIT}")
    return n


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


class ProfileIn(BaseModel):
    display_name: str


@app.patch("/api/auth/me")
def update_me(body: ProfileIn, request: Request, s=Depends(db)):
    """L'utilisateur change son propre nom affiché (l'identifiant, lui, ne change pas)."""
    name = body.display_name.strip()
    if len(name) > 120:
        raise HTTPException(400, "Nom trop long (120 caractères maximum)")
    user = s.get(User, request.state.user.id)
    user.display_name = name
    s.commit()
    return auth.user_dict(user)


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
    user = User(username=name, max_parallel=_check_quota(body.max_parallel), display_name=body.display_name.strip(), is_admin=body.is_admin,
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
    if body.max_parallel is not None:
        user.max_parallel = _check_quota(body.max_parallel)
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
    s.query(FolderAccess).filter(FolderAccess.user_id == user_id).delete()
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
NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers=NO_CACHE)


class RevalidatedStatic(StaticFiles):
    """JS/CSS revalidés à chaque chargement (ETag) : un navigateur ne garde pas un vieux app.js après un déploiement."""
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app.mount("/static", RevalidatedStatic(directory=STATIC), name="static")

"""Intros par langue : `python tests/test_intros.py` (ou pytest). La durée des MP3 est simulée (pas de ffprobe)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.update(DATA_DIR=tempfile.mkdtemp(), APP_USER="admin", APP_PASSWORD="adminpass1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Folder, SessionLocal, resolve_intro  # noqa: E402
from app.main import _check_intro, app  # noqa: E402
from app.pipeline import audio  # noqa: E402

audio.probe_duration = lambda p: 4.0
admin = TestClient(app)


def ok(r, code=200):
    assert r.status_code == code, (r.request.method, r.request.url.path, r.status_code, r.text)
    return r.json()


def upload(name, lang=None, default=False, code=200):
    data = {"name": name, "is_default": str(default).lower(), **({"lang": lang} if lang else {})}
    return ok(admin.post("/api/intros", data=data, files={"file": (f"{name}.mp3", b"ID3fake", "audio/mpeg")}), code)


ok(admin.post("/api/auth/login", json={"username": "admin", "password": "adminpass1"}))
fr, en1 = upload("FR"), upload("EN", "en")
assert fr["lang"] == "fr" and fr["is_default"] and en1["lang"] == "en" and en1["is_default"]       # la première de chaque langue est la défaut de sa langue
upload("X", "de", code=400)
en2 = upload("EN2", "en", default=True)
by = {i["name"]: i for i in ok(admin.get("/api/intros"))}
assert by["FR"]["is_default"] and by["EN2"]["is_default"] and not by["EN"]["is_default"]           # le changement de défaut reste dans sa langue
assert [i["name"] for i in ok(admin.get("/api/intros"))][0] == "FR"                                # le français d'abord

with SessionLocal() as s:
    s.add(Folder(name="CULTE"))
    s.commit()
    folder = s.query(Folder).first()
    assert resolve_intro(s, folder, None, "fr")[1] == "FR" and resolve_intro(s, folder, None, "en")[1] == "EN2"
    assert resolve_intro(s, folder, en1["id"], "fr")[1] == "FR"                                    # un choix d'une autre langue est ignoré
    fid = folder.id

# intro d'un dossier : une par langue, chacune à sa place, et seuls les champs envoyés changent
ok(admin.put(f"/api/folders/{fid}/intro", json={"intro_id": en1["id"]}), 400)
ok(admin.put(f"/api/folders/{fid}/intro", json={"intro_en_id": fr["id"]}), 400)
f = ok(admin.put(f"/api/folders/{fid}/intro", json={"intro_en_id": en1["id"]}))
assert f["intro_en_id"] == en1["id"] and f["intro_id"] is None
with SessionLocal() as s:
    folder = s.get(Folder, fid)
    assert resolve_intro(s, folder, None, "en")[1] == "EN" and resolve_intro(s, folder, None, "fr")[1] == "FR"
f = ok(admin.put(f"/api/folders/{fid}/intro", json={"intro_id": fr["id"]}))
assert f["intro_id"] == fr["id"] and f["intro_en_id"] == en1["id"]                                 # le champ anglais n'a pas été touché

# un podcast français ne peut pas choisir une intro anglaise
with SessionLocal() as s:
    try:
        _check_intro(s, en1["id"])
        raise AssertionError("intro anglaise acceptée")
    except HTTPException as exc:
        assert exc.status_code == 400
    _check_intro(s, fr["id"])
    _check_intro(s, 0)

# supprimer une intro libère les dossiers qui l'utilisaient ; sans intro anglaise, la version anglaise n'a pas d'intro (jamais la française)
ok(admin.delete(f"/api/intros/{en1['id']}"))
ok(admin.delete(f"/api/intros/{en2['id']}"))
with SessionLocal() as s:
    folder = s.get(Folder, fid)
    assert folder.intro_en_id is None and resolve_intro(s, folder, None, "en") is None and resolve_intro(s, folder, None, "fr")[1] == "FR"
print("ok")

"""Corbeille, droits et attribution de dossiers, via l'API : `python tests/test_trash.py` (ou pytest). Base jetable, sans réseau."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.update(DATA_DIR=tempfile.mkdtemp(), APP_USER="admin", APP_PASSWORD="adminpass1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PERMS = ["jobs.view", "jobs.create", "jobs.delete", "folders.manage", "intros.manage"]
admin, bob, eve = TestClient(app), TestClient(app), TestClient(app)


def ok(r, code=200):
    assert r.status_code == code, (r.request.method, r.request.url.path, r.status_code, r.text)
    return r.json()


def login(c, name, pw):
    ok(c.post("/api/auth/login", json={"username": name, "password": pw}))


login(admin, "admin", "adminpass1")
for n in ("bob", "eve"):
    ok(admin.post("/api/users", json={"username": n, "password": n + "pass123", "permissions": PERMS}))
    login({"bob": bob, "eve": eve}[n], n, n + "pass123")

job = lambda c, fid, t: ok(c.post("/api/jobs", json={"folder_id": fid, "youtube_url": "https://youtu.be/x", "title": t, "date": "2026-01-01"}))["id"]
ids = lambda c, fid: [j["id"] for j in ok(c.get(f"/api/folders/{fid}/jobs"))]
trash = lambda c: {(i["kind"], i["id"]): i for i in ok(c.get("/api/trash"))}

# --- podcasts : corbeille personnelle, l'administrateur voit tout
fb = ok(bob.post("/api/folders", json={"name": "Bob"}))["id"]
j1, j2 = job(bob, fb, "Un"), job(bob, fb, "Deux")
ok(bob.delete(f"/api/jobs/{j1}"))
assert ids(bob, fb) == [j2]                                             # disparu des listes
assert [j["id"] for j in ok(bob.get("/api/jobs"))["items"]] == [j2]     # et de l'historique
assert ok(bob.get("/api/status"))["pending"] == 1                       # et du compte de la file
assert bob.get(f"/api/jobs/{j1}").status_code == 404                    # un élément en corbeille n'est plus accessible
assert ("job", j1) in trash(bob) and ("job", j1) in trash(admin) and ("job", j1) not in trash(eve)
assert bob.delete(f"/api/trash/job/{j1}").status_code == 403            # pas de suppression définitive pour un utilisateur
assert bob.delete("/api/trash").status_code == 403
ok(eve.post(f"/api/trash/job/{j1}/restore"), 404)                        # la corbeille d'un autre est invisible
ok(bob.post(f"/api/trash/job/{j1}/restore"))
assert set(ids(bob, fb)) == {j1, j2} and ("job", j1) not in trash(admin)

# l'administrateur supprime un podcast de Bob : c'est dans la corbeille de l'admin, pas dans celle de Bob
ok(admin.delete(f"/api/jobs/{j2}"))
assert ("job", j2) in trash(admin) and ("job", j2) not in trash(bob)

# --- dossiers : doivent être vides, restaurés avec leur parent d'abord
ok(bob.delete(f"/api/folders/{fb}"), 400)                               # j1 est encore dedans
ok(bob.delete(f"/api/jobs/{j1}"))
sub = ok(bob.post("/api/folders", json={"name": "Sous", "parent_id": fb}))["id"]
ok(bob.delete(f"/api/folders/{sub}"))
ok(bob.delete(f"/api/folders/{fb}"))                                    # vide (ses éléments sont en corbeille)
assert fb not in [f["id"] for f in ok(bob.get("/api/folders"))]
ok(bob.post(f"/api/trash/job/{j1}/restore"), 400)                       # son dossier est en corbeille
ok(bob.post(f"/api/trash/folder/{sub}/restore"), 400)
ok(bob.post("/api/folders", json={"name": "Bob"}))                      # le nom est libre : un homonyme est créé
ok(bob.post(f"/api/trash/folder/{fb}/restore"), 400)                    # conflit de nom à la restauration
ok(admin.delete(f"/api/folders/{[f['id'] for f in ok(bob.get('/api/folders')) if f['name'] == 'Bob'][0]}"))
ok(bob.post(f"/api/trash/folder/{fb}/restore"))
ok(bob.post(f"/api/trash/folder/{sub}/restore"))
ok(bob.post(f"/api/trash/job/{j1}/restore"))
assert ids(bob, fb) == [j1] or set(ids(bob, fb)) == {j1}

# --- suppression définitive : administrateur seulement, en cascade pour un dossier en corbeille
ok(bob.delete(f"/api/jobs/{j1}")); ok(bob.delete(f"/api/folders/{sub}")); ok(bob.delete(f"/api/folders/{fb}"))
ok(admin.delete(f"/api/trash/folder/{fb}"))
t = trash(admin)
assert ("folder", fb) not in t and ("folder", sub) not in t and ("job", j1) not in t   # tout est parti avec le dossier
from app.db import Folder, Job, SessionLocal  # noqa: E402
with SessionLocal() as s:
    assert s.get(Job, j1) is None and s.get(Folder, fb) is None and s.get(Folder, sub) is None
ok(admin.delete(f"/api/trash/job/{j2}"), 404)                           # j2 (en corbeille dans ce dossier) est parti avec lui
fx = ok(admin.post("/api/folders", json={"name": "X"}))["id"]
j3, j4 = job(admin, fx, "Trois"), job(admin, fx, "Quatre")
ok(admin.delete(f"/api/jobs/{j3}")); ok(admin.delete(f"/api/jobs/{j4}")); ok(admin.delete(f"/api/folders/{fx}"))
assert {("job", j3), ("job", j4), ("folder", fx)} <= set(trash(admin))
ok(admin.delete(f"/api/trash/job/{j3}"))                                # un seul élément
ok(admin.delete("/api/trash"))                                          # puis tout
assert trash(admin) == {}
with SessionLocal() as s:
    assert s.get(Job, j4) is None and s.get(Folder, fx) is None

# --- attribution des dossiers d'autres utilisateurs
fe = ok(eve.post("/api/folders", json={"name": "Eve"}))["id"]
uid = {u["username"]: u["id"] for u in ok(admin.get("/api/users"))}
v = ok(admin.get(f"/api/users/{uid['bob']}/folders"))
assert fe in [f["id"] for f in v["available"]] and v["assigned"] == []
assert bob.get(f"/api/users/{uid['bob']}/folders").status_code == 403
ok(admin.put(f"/api/users/{uid['bob']}/folders", json={"folder_ids": [fe]}))
assert fe in [f["id"] for f in ok(bob.get("/api/folders"))]                # Bob voit maintenant le dossier d'Eve
ok(bob.delete(f"/api/folders/{fe}"), 403)                                  # sans pouvoir le supprimer
assert [f["id"] for f in ok(admin.get(f"/api/users/{uid['bob']}/folders"))["assigned"]] == [fe]
ok(admin.put(f"/api/users/{uid['bob']}/folders", json={"folder_ids": []}))
assert fe not in [f["id"] for f in ok(bob.get("/api/folders"))]
ok(admin.put(f"/api/users/{uid['admin']}/folders", json={"folder_ids": []}), 400)  # un admin voit déjà tout
# un dossier attribué puis mis en corbeille garde son attribution à la restauration
ok(admin.put(f"/api/users/{uid['bob']}/folders", json={"folder_ids": [fe]}))
ok(eve.delete(f"/api/folders/{fe}")); ok(admin.put(f"/api/users/{uid['bob']}/folders", json={"folder_ids": []}))
ok(eve.post(f"/api/trash/folder/{fe}/restore"))
assert fe in [f["id"] for f in ok(bob.get("/api/folders"))]

# --- intros : suppression définitive réservée à l'administrateur
ok(admin.post("/api/intros", files={"file": ("x.mp3", b"nope", "audio/mpeg")}), 400)  # fichier illisible : refusé, sans effet
assert bob.delete("/api/intros/1").status_code == 403
print("ok")

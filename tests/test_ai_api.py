"""IA du serveur réglée par l'administrateur, clé personnelle et compteurs, via l'API : `python tests/test_ai_api.py`.
Les appels à Anthropic sont simulés : aucun réseau, aucune vraie clé."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.update(DATA_DIR=tempfile.mkdtemp(), APP_USER="admin", APP_PASSWORD="adminpass1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.db import AiUsage, SessionLocal  # noqa: E402

calls = []


def fake_ask(prompt, llm, max_tokens=400, on_usage=None):
    calls.append(llm)
    if llm["key"].endswith("BAD"):
        raise RuntimeError("API Anthropic 401 : invalid x-api-key")
    return "OK"


main.ask_llm = fake_ask
GOOD, BAD = "sk-ant-" + "g" * 30, "sk-ant-" + "b" * 27 + "BAD"
admin, bob = TestClient(main.app), TestClient(main.app)


def ok(r, code=200):
    assert r.status_code == code, (r.request.method, r.request.url.path, r.status_code, r.text)
    return r.json()


ok(admin.post("/api/auth/login", json={"username": "admin", "password": "adminpass1"}))
ok(admin.post("/api/users", json={"username": "bob", "password": "bobpass123", "permissions": ["jobs.view", "ai.key", "ai.toggle"]}))
ok(bob.post("/api/auth/login", json={"username": "bob", "password": "bobpass123"}))
status = lambda c: ok(c.get("/api/status"))

# --- rien n'est configuré au départ ; seul l'administrateur règle l'IA du serveur
assert ok(admin.get("/api/settings/llm"))["configured"] is False and status(bob)["ai_available"] is False
assert bob.get("/api/settings/llm").status_code == 403 and bob.put("/api/settings/llm", json={"key": GOOD}).status_code == 403
ok(admin.put("/api/settings/llm", json={"key": "nope"}), 400)                              # pas une clé Anthropic
ok(admin.put("/api/settings/llm", json={"key": GOOD, "model": "gpt-4o"}), 400)             # seul Anthropic : modèle inconnu
assert "refusée" in ok(admin.put("/api/settings/llm", json={"key": BAD}), 400)["detail"]   # l'appel de vérification échoue
ok(admin.put("/api/settings/ai", json={"enabled": True}), 400)                             # rien à activer sans clé

c = ok(admin.put("/api/settings/llm", json={"key": GOOD, "model": "claude-haiku-5-5"}))
assert c["configured"] and c["enabled"] and c["model"] == "claude-haiku-5-5" and c["key_hint"].endswith("gggg") and GOOD not in str(c)
assert calls[-1] == {"key": GOOD, "model": "claude-haiku-5-5"}                             # la clé a bien été vérifiée par un appel
assert status(bob)["ai_available"] and status(bob)["ai_enabled"] and not status(bob)["ai_personal"]

# changer seulement le modèle garde la clé enregistrée
c = ok(admin.put("/api/settings/llm", json={"key": "", "model": "claude-opus-5-5"}))
assert calls[-1]["key"] == GOOD and c["model"] == "claude-opus-5-5"

# --- interrupteur du serveur : coupé, bob (sans clé à lui) n'a plus d'IA
ok(admin.put("/api/settings/ai", json={"enabled": False}))
assert status(bob)["ai_enabled"] is False and status(admin)["ai_global"] is False and status(bob)["ai_available"] is True

# --- clé personnelle de bob : son IA marche même quand celle du serveur est coupée
ok(bob.put("/api/me/ai/key", json={"key": BAD}), 400)
ok(bob.put("/api/me/ai/key", json={"key": GOOD.replace("g", "p")}))
assert calls[-1]["model"] == "claude-opus-5-5"                                              # même modèle que le serveur
assert status(bob)["ai_enabled"] and status(bob)["ai_personal"]
ok(bob.put("/api/me/ai", json={"enabled": False}))                                          # il la coupe pour lui
assert status(bob)["ai_enabled"] is False
ok(bob.put("/api/me/ai", json={"enabled": True}))

# --- compteurs : un appel est inscrit à la clé facturée ; chacun voit les siens, l'administrateur voit tout
with SessionLocal() as s:
    s.add_all([AiUsage(username="bob", author="bob", job_id=1, tokens_in=1000, tokens_out=100),
               AiUsage(username="bob", author="admin", job_id=2, tokens_in=300, tokens_out=30),   # l'admin a choisi la clé de bob
               AiUsage(username="@server", author="admin", job_id=3, tokens_in=5000, tokens_out=500)])
    s.commit()
u = ok(bob.get("/api/ai/usage"))
assert u["month"]["in"] == 1300 and u["month"]["out"] == 130 and u["total"]["calls"] == 2 and "keys" not in u
assert u["others_on_my_key_month"] == {"in": 300, "out": 30}
assert status(bob)["ai_usage"] == {"month": 1430, "total": 1430}                            # le compteur de l'en-tête
a = ok(admin.get("/api/ai/usage"))
assert a["month"]["in"] == 5300 and {k["owner"]: k["month"] for k in a["keys"]} == {"bob": 1430, "@server": 5500}
assert {k["owner"]: k["name"] for k in a["keys"]}["@server"] == "IA du serveur"

# --- suppression de la clé du serveur
c = ok(admin.delete("/api/settings/llm"))
assert c["configured"] is False and status(bob)["ai_available"] is True                    # bob garde sa clé
print("ok")

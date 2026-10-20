"""Qui utilise l'IA, avec quelle clé : `python tests/test_ai.py` (ou pytest). Base et clé de chiffrement jetables."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as J

os.environ["DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import vault  # noqa: E402
from app.db import AI_SERVER, DEFAULT_MODEL, SessionLocal, Setting, User, ai_for, init_db, job_ai  # noqa: E402

init_db()
KEY, SRV = "sk-ant-" + "x" * 30, "sk-ant-" + "s" * 30


def user(s, name, perms="", admin=False, key=None, on=True):
    s.add(User(username=name, password_hash="x", is_admin=admin, permissions=perms,
               llm_key=vault.encrypt(key) if key else None, ai_on=on))
    s.commit()


def owner(llm):
    return llm and llm["owner"]


with SessionLocal() as s:
    assert vault.decrypt(vault.encrypt(KEY)) == KEY and vault.decrypt("pas-un-jeton") is None
    user(s, "plain"); user(s, "keyed", "ai.key", key=KEY); user(s, "nokeyperm", "", key=KEY)
    user(s, "off", "ai.toggle", on=False); user(s, "offnoperm", "", on=False); user(s, "offkeyed", "ai.key,ai.toggle", key=KEY, on=False)
    user(s, "boss", admin=True)

    # serveur sans IA configurée : seuls ceux qui ont leur clé en ont une
    assert ai_for(s, "plain") is None and ai_for(s, None) is None and ai_for(s, "boss") is None
    assert owner(ai_for(s, "keyed")) == "keyed" and ai_for(s, "keyed")["key"] == KEY
    assert ai_for(s, "keyed")["model"] == DEFAULT_MODEL
    assert ai_for(s, "nokeyperm") is None                  # clé stockée mais permission retirée

    # l'administrateur configure l'IA du serveur (interface) : clé chiffrée + modèle
    s.merge(Setting(key="llm_key", value=vault.encrypt(SRV))); s.merge(Setting(key="llm_model", value="claude-haiku-5-5")); s.commit()
    assert "x" * 5 not in s.get(Setting, "llm_key").value and SRV not in s.get(Setting, "llm_key").value  # jamais en clair
    srv = ai_for(s, "plain")
    assert owner(srv) == AI_SERVER and srv["key"] == SRV and srv["model"] == "claude-haiku-5-5"
    assert owner(ai_for(s, "nokeyperm")) == AI_SERVER      # sans la permission : l'IA du serveur
    assert ai_for(s, "keyed")["model"] == "claude-haiku-5-5"  # la clé personnelle prend le modèle réglé pour le serveur
    assert ai_for(s, "off") is None                        # a coupé l'IA pour lui
    assert owner(ai_for(s, "offnoperm")) == AI_SERVER      # sans la permission, son choix ne compte pas
    assert ai_for(s, "offkeyed") is None                   # couper l'IA coupe aussi sa clé
    assert owner(ai_for(s, "boss")) == AI_SERVER and owner(ai_for(s, "supprimé")) == AI_SERVER

    # IA choisie par un administrateur pour un traitement
    assert owner(job_ai(s, J(ai_user=None, created_by="plain"))) == AI_SERVER
    assert owner(job_ai(s, J(ai_user="keyed", created_by="plain"))) == "keyed"       # clé de « keyed » pour un traitement de « plain »
    assert owner(job_ai(s, J(ai_user=None, created_by="keyed"))) == "keyed"          # sans choix : celle de l'auteur
    assert owner(job_ai(s, J(ai_user=AI_SERVER, created_by="keyed"))) == AI_SERVER   # IA du serveur malgré la clé de l'auteur
    assert job_ai(s, J(ai_user="off", created_by="keyed")) is None                   # la configuration choisie coupe l'IA

    # l'administrateur coupe l'IA du serveur : ses clients sans clé n'en ont plus, les clés personnelles continuent
    s.merge(Setting(key="ai_enabled", value="0")); s.commit()
    assert ai_for(s, "plain") is None and ai_for(s, "boss") is None
    assert owner(ai_for(s, "keyed")) == "keyed"
print("ok")

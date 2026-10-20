"""Qui utilise l'IA, avec quelle clé : `python tests/test_ai.py` (ou pytest). Base et clé de chiffrement jetables."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, vault  # noqa: E402
from app.db import SessionLocal, Setting, User, ai_for, init_db  # noqa: E402

init_db()
KEY = "sk-ant-" + "x" * 30


def user(s, name, perms="", admin=False, key=None, on=True):
    s.add(User(username=name, password_hash="x", is_admin=admin, permissions=perms,
               llm_key=vault.encrypt(key) if key else None, ai_on=on))
    s.commit()


with SessionLocal() as s:
    assert vault.decrypt(vault.encrypt(KEY)) == KEY and vault.decrypt("pas-un-jeton") is None
    user(s, "plain"); user(s, "keyed", "ai.key", key=KEY); user(s, "nokeyperm", "", key=KEY)
    user(s, "off", "ai.toggle", on=False); user(s, "offnoperm", "", on=False); user(s, "offkeyed", "ai.key,ai.toggle", key=KEY, on=False)
    user(s, "boss", admin=True)

    config.LLM_PROVIDER = "anthropic"  # serveur avec IA
    assert ai_for(s, "plain") == (True, None)
    assert ai_for(s, "keyed") == (True, KEY)
    assert ai_for(s, "nokeyperm") == (True, None)        # clé stockée mais permission retirée : clé du serveur
    assert ai_for(s, "off") == (False, None)             # a coupé l'IA pour lui
    assert ai_for(s, "offnoperm") == (True, None)        # sans la permission, son choix ne compte pas
    assert ai_for(s, "offkeyed") == (False, None)        # couper l'IA coupe aussi sa clé
    assert ai_for(s, "boss") == (True, None) and ai_for(s, None) == (True, None) and ai_for(s, "supprimé") == (True, None)

    s.merge(Setting(key="ai_enabled", value="0")); s.commit()  # l'administrateur coupe l'IA du serveur
    assert ai_for(s, "plain") == (False, None)
    assert ai_for(s, "keyed") == (True, KEY)             # sa propre clé continue de servir

    config.LLM_PROVIDER = "none"  # serveur sans IA
    s.merge(Setting(key="ai_enabled", value="1")); s.commit()
    assert ai_for(s, "plain") == (False, None) and ai_for(s, "keyed") == (True, KEY)
print("ok")

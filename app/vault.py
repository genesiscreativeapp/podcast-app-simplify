"""Chiffrement des clés d'API personnelles (Fernet).
La clé de chiffrement vient de SECRET_KEY, sinon d'un fichier data/secret.key créé au premier besoin.
shortcut: ce fichier est à côté de la base ; il protège une sauvegarde de app.db seule, pas un vol de tout data/."""
import base64
import hashlib
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from . import config


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    if config.SECRET_KEY:
        raw = hashlib.sha256(config.SECRET_KEY.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(raw))
    path = config.DATA_DIR / "secret.key"
    try:  # O_EXCL : web et worker peuvent démarrer ensemble, un seul crée le fichier
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(Fernet.generate_key())
    except FileExistsError:
        pass
    return Fernet(path.read_bytes().strip())


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str | None:
    """None si le jeton est illisible (SECRET_KEY ou secret.key changé) : la clé est alors comme absente."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None

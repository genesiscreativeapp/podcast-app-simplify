"""Comptes, mots de passe, sessions et permissions."""
import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timedelta

from fastapi import HTTPException, Request

from . import config
from .db import SessionLocal, User, UserSession

log = logging.getLogger("auth")
COOKIE = "sp_session"

# Fonctionnalités de l'application ; l'administrateur les a toutes et gère seul les comptes.
PERMISSIONS = {
    "jobs.view": "Voir les traitements et télécharger les podcasts",
    "jobs.create": "Lancer et relancer des traitements",
    "jobs.delete": "Supprimer des traitements",
    "jobs.trim": "Rogner les podcasts terminés (début et fin)",
    "folders.manage": "Créer, renommer et supprimer des dossiers",
    "intros.manage": "Gérer la bibliothèque d'intros",
    "settings.manage": "Régler le nombre de traitements en parallèle",
    "english.create": "Générer la version anglaise d'un podcast (voix du prédicateur)",
    "ai.key": "Utiliser sa propre clé Anthropic pour l'IA",
    "ai.toggle": "Activer ou désactiver l'IA pour ses traitements",
}


# --- Mots de passe (scrypt, bibliothèque standard) -------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1)
        return hmac.compare_digest(got.hex(), digest)
    except Exception:
        return False


def check_password_strength(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(400, "Le mot de passe doit contenir au moins 8 caractères")


# --- Sessions ----------------------------------------------------------------------------
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(s, user: User) -> str:
    token = secrets.token_urlsafe(32)
    s.query(UserSession).filter(UserSession.expires_at < datetime.utcnow()).delete()  # ménage
    s.add(UserSession(token_hash=_hash(token), user_id=user.id,
                      expires_at=datetime.utcnow() + timedelta(days=config.SESSION_DAYS)))
    user.last_login = datetime.utcnow()
    s.commit()
    return token


def user_from_token(s, token: str | None) -> User | None:
    if not token:
        return None
    sess = s.get(UserSession, _hash(token))
    if sess is None or sess.expires_at < datetime.utcnow():
        return None
    user = s.get(User, sess.user_id)
    return user if user and user.is_active else None


def drop_sessions(s, user_id: int) -> None:
    s.query(UserSession).filter(UserSession.user_id == user_id).delete()


def drop_token(s, token: str | None) -> None:
    if token:
        s.query(UserSession).filter(UserSession.token_hash == _hash(token)).delete()


# --- Protection contre les essais de mots de passe ----------------------------------------
_fails: dict[str, list[float]] = {}
MAX_FAILS, WINDOW = 5, 300  # 5 échecs en 5 minutes -> blocage jusqu'à la fin de la fenêtre


def throttle_check(key: str) -> None:
    now = time.time()
    recent = [t for t in _fails.get(key, []) if now - t < WINDOW]
    _fails[key] = recent
    if len(recent) >= MAX_FAILS:
        wait = int(WINDOW - (now - recent[0]))
        raise HTTPException(429, f"Trop d'essais. Réessayez dans {wait // 60 + 1} min.")


def throttle_fail(key: str) -> None:
    _fails.setdefault(key, []).append(time.time())


def throttle_reset(key: str) -> None:
    _fails.pop(key, None)


# --- Permissions -----------------------------------------------------------------------------
def user_perms(user: User) -> list[str]:
    return list(PERMISSIONS) if user.is_admin else sorted(user.perms & set(PERMISSIONS))


def user_dict(user: User) -> dict:
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "is_admin": user.is_admin, "is_active": user.is_active, "is_system": user.is_system, "max_parallel": user.max_parallel, "permissions": user_perms(user),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None}


def need(perm: str):
    """Dépendance FastAPI : exige une permission (l'administrateur les a toutes)."""
    def dep(request: Request) -> User:
        user = request.state.user
        if user is None:
            raise HTTPException(401, "Non connecté")
        if perm == "admin":
            if not user.is_admin:
                raise HTTPException(403, "Réservé aux administrateurs")
        elif not user.is_admin and perm not in user.perms:
            raise HTTPException(403, "Vous n'avez pas la permission pour cette action")
        return user
    return dep


# --- Premier démarrage ------------------------------------------------------------------------
SYSTEM_MSG = "Le compte administrateur système est protégé : il ne peut pas être modifié, désactivé ni supprimé."


def bootstrap_admin() -> None:
    """Crée le compte administrateur système s'il n'existe aucun compte, et marque ce compte comme protégé.
    Sur une base existante sans compte système, c'est l'administrateur APP_USER (sinon le plus ancien) qui le devient."""
    with SessionLocal() as s:
        try:
            if not s.query(User).count():
                password = config.APP_PASSWORD
                if not password:
                    password = secrets.token_urlsafe(12)
                    log.warning("APP_PASSWORD vide : mot de passe généré pour « %s » : %s", config.APP_USER, password)
                s.add(User(username=config.APP_USER, display_name="Administrateur", is_admin=True, is_system=True,
                           password_hash=hash_password(password)))
            elif not s.query(User).filter(User.is_system).count():
                admins = s.query(User).filter(User.is_admin).order_by(User.id).all()
                chosen = next((u for u in admins if u.username == config.APP_USER.lower()), admins[0] if admins else None)
                if chosen:
                    chosen.is_system = True
            s.commit()
        except Exception:  # web et worker démarrent ensemble : l'autre l'a déjà fait
            s.rollback()

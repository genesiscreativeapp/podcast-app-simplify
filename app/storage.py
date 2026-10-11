"""Envoi, déplacement et liens Cloudflare R2 (API compatible S3)."""
from pathlib import Path
from urllib.parse import quote

from . import config


def enabled() -> bool:
    return all([config.R2_ACCOUNT_ID, config.R2_ACCESS_KEY_ID,
                config.R2_SECRET_ACCESS_KEY, config.R2_BUCKET])


def _client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=config.R2_ENDPOINT_URL or f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 5}, s3={"addressing_style": "path"}),
    )


def upload(path: Path, key: str, content_type: str, on_bytes=None) -> None:
    """on_bytes(n) est appelé avec le nombre d'octets envoyés à chaque morceau.
    Cache court : un fichier peut être renommé, déplacé ou rogné (même chemin, contenu différent)."""
    _client().upload_file(
        str(path), config.R2_BUCKET, key,
        ExtraArgs={"ContentType": content_type, "CacheControl": "public, max-age=300"},
        Callback=on_bytes,
    )


def move(old_key: str, new_key: str) -> None:
    """« Renomme » un objet : S3 n'a pas de renommage, on copie puis on supprime l'ancien.
    Si l'on est interrompu entre les deux, l'opération se rejoue sans dégât."""
    c = _client()
    c.copy_object(Bucket=config.R2_BUCKET, Key=new_key, CopySource={"Bucket": config.R2_BUCKET, "Key": old_key})
    c.delete_object(Bucket=config.R2_BUCKET, Key=old_key)


def put_marker(key: str) -> None:
    """Objet vide dont la clé se termine par « / » : fait apparaître un dossier vide dans les explorateurs R2."""
    _client().put_object(Bucket=config.R2_BUCKET, Key=key, Body=b"")


def link(key: str) -> str:
    if config.R2_PUBLIC_BASE_URL:
        return f"{config.R2_PUBLIC_BASE_URL}/{quote(key)}"
    return _client().generate_presigned_url(
        "get_object", Params={"Bucket": config.R2_BUCKET, "Key": key},
        ExpiresIn=config.R2_LINK_EXPIRES,
    )


def delete(keys: list[str]) -> None:
    keys = [k for k in keys if k]
    if keys and enabled():
        _client().delete_objects(
            Bucket=config.R2_BUCKET, Delete={"Objects": [{"Key": k} for k in keys]}
        )

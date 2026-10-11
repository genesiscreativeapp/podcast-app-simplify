"""Envoi et liens Cloudflare R2 (API compatible S3)."""
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
        endpoint_url=f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 5}),
    )


def build_key(folder_names: list[str], filename: str) -> str:
    from .utils import slugify

    parts = [config.R2_PREFIX] if config.R2_PREFIX else []
    parts += [slugify(n) for n in folder_names]
    parts.append(filename)
    return "/".join(parts)


def upload(path: Path, key: str, content_type: str, on_bytes=None) -> None:
    """on_bytes(n) est appelé avec le nombre d'octets envoyés à chaque morceau."""
    _client().upload_file(
        str(path), config.R2_BUCKET, key,
        ExtraArgs={"ContentType": content_type, "CacheControl": "public, max-age=31536000"},
        Callback=on_bytes,
    )


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

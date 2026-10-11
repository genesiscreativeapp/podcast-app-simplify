"""Étape 1 : téléchargement de l'audio YouTube avec yt-dlp."""
from pathlib import Path
from typing import Callable

from .. import config


def download(url: str, workdir: Path, on_progress: Callable[[float], None]) -> tuple[Path, str | None]:
    import yt_dlp

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                on_progress(min(d.get("downloaded_bytes", 0) / total, 1.0))

    opts = {
        "format": config.YTDLP_FORMAT,  # audio seul, pas besoin de la vidéo
        "concurrent_fragment_downloads": 4,
        "outtmpl": str(workdir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "progress_hooks": [hook],
    }
    if config.YTDLP_COOKIES:
        opts["cookiefile"] = config.YTDLP_COOKIES

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    downloads = info.get("requested_downloads") or []
    path = Path(downloads[0]["filepath"]) if downloads else None
    if path is None or not path.exists():
        candidates = sorted(workdir.glob("source.*"))
        if not candidates:
            raise RuntimeError("Téléchargement terminé mais fichier introuvable")
        path = candidates[0]
    return path, info.get("title")

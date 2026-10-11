import re
import unicodedata


def slugify(text: str) -> str:
    """'Culte Royal : la foi !' -> 'Culte-Royal-la-foi'"""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return text or "sans-nom"


def parse_time(value) -> float | None:
    """'1:02:30' | '62:30' | '3750' -> secondes. Vide -> None."""
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    parts = value.split(":")
    if len(parts) > 3 or not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        raise ValueError(f"Horodatage invalide : {value!r} (format attendu hh:mm:ss)")
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60 + float(p)
    return seconds


def fmt_time(seconds: float | None) -> str:
    if seconds is None:
        return ""
    s = int(round(seconds))
    return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"

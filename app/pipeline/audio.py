"""Opérations ffmpeg : extraction, amélioration de la voix, intro, compression."""
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .. import config

SR = 24000  # fréquence de travail : le MP3 final est lui aussi en 24 kHz (12 kHz de bande, largement assez pour la voix), inutile de traiter plus (2x moins de calcul et de mémoire)
SR_WHISPER = 16000


def run(cmd: list[str], duration: float | None = None,
        on_progress: Callable[[float], None] | None = None) -> str:
    """Lance une commande. Avec `duration` et `on_progress`, ffmpeg rapporte son avancement (0 → 1)."""
    track = bool(on_progress and duration)
    if track:
        cmd = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]
    out = []
    with tempfile.TemporaryFile("w+") as err:  # fichier plutôt que pipe : pas de blocage si ffmpeg est bavard
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
        for line in proc.stdout:
            if track and line.startswith("out_time_us="):
                try:
                    on_progress(min(max(int(line.split("=")[1]) / 1e6 / duration, 0.0), 1.0))
                except ValueError:  # « N/A » au démarrage
                    pass
            else:
                out.append(line)
        if proc.wait() != 0:
            err.seek(0)
            tail = "\n".join(err.read().strip().splitlines()[-15:])
            raise RuntimeError(f"Échec de {cmd[0]} :\n{tail}")
    return "".join(out)


def probe_duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


def to_whisper(src: Path, out: Path, duration: float | None = None,
               on_progress: Callable[[float], None] | None = None) -> None:
    """WAV mono 16 kHz de tout le culte, lu par morceaux pour la transcription."""
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(src), "-vn", "-ac", "1", "-ar", str(SR_WHISPER),
         "-c:a", "pcm_s16le", str(out)], duration, on_progress)


# Chaîne d'amélioration de la voix, volontairement légère : un traitement trop fort rend la voix métallique.
#  - mono 24 kHz d'abord : tout le reste coûte 2 à 4x moins cher
#  - coupe les basses (ronflements, vibrations de micro)
#  - réduction de bruit FFT douce (DENOISE_DB, 0 = aucune)
#  - compresseur très léger pour homogénéiser les passages criés / chuchotés
def enhance_filter() -> str:
    parts = [f"aresample={SR}", "aformat=channel_layouts=mono", "highpass=f=70"]
    if config.DENOISE_DB > 0:
        parts.append(f"afftdn=nr={config.DENOISE_DB:g}:nf=-50:tn=1")
    parts.append("acompressor=threshold=0.125:ratio=2:attack=20:release=300:makeup=1.2")
    return ",".join(parts)


def extract_enhanced(src: Path, start: float, end: float, out: Path, out_whisper: Path,
                     on_progress: Callable[[float], None] | None = None) -> None:
    """Découpe la prédication et l'améliore en un seul passage ffmpeg.
    Produit le WAV de travail (24 kHz) et sa copie 16 kHz pour Whisper."""
    graph = f"[0:a]{enhance_filter()},asplit=2[a][b];[b]aresample={SR_WHISPER}[c]"
    run(["ffmpeg", "-y", "-hide_banner", "-ss", f"{start:.3f}", "-i", str(src),
         "-t", f"{max(end - start, 1):.3f}", "-vn", "-filter_complex", graph,
         "-map", "[a]", "-c:a", "pcm_s16le", str(out),
         "-map", "[c]", "-c:a", "pcm_s16le", str(out_whisper)], max(end - start, 1), on_progress)


LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"  # standard podcast


def finalize(body: Path, out: Path, intro: Path | None = None, xfade: float = 0.6,
             on_progress: Callable[[float], None] | None = None) -> None:
    """Normalise le volume (-16 LUFS) et ajoute l'intro avec un fondu enchaîné."""
    norm = f"aresample={SR},aformat=channel_layouts=mono,{LOUDNORM},aresample={SR}"
    if intro:
        fc = (f"[0:a]{norm}[i];[1:a]{norm}[b];"
              f"[i][b]acrossfade=d={xfade}:c1=tri:c2=tri[out]")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-i", str(intro), "-i", str(body),
               "-filter_complex", fc, "-map", "[out]"]
    else:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-i", str(body), "-af", norm]
    total = probe_duration(body) + (probe_duration(intro) - xfade if intro else 0)
    run(cmd + ["-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(out)], total, on_progress)


def _meta(title: str, artist: str, date: str) -> list[str]:
    args = ["-metadata", f"title={title}", "-metadata", f"date={date}"]
    if artist:
        args += ["-metadata", f"artist={artist}"]
    return args


def encode_mp3(src: Path, out: Path, bitrate: str, title: str, artist: str, date: str,
               duration: float | None = None, on_progress: Callable[[float], None] | None = None) -> None:
    """MP3 mono : lisible partout (WhatsApp, Telegram, lecteurs de voiture…)."""
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(src), "-c:a", "libmp3lame",
         "-b:a", bitrate, "-ac", "1", "-ar", str(SR), "-id3v2_version", "3",
         *_meta(title, artist, date), str(out)], duration, on_progress)

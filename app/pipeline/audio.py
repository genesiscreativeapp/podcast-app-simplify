"""Opérations ffmpeg : extraction, amélioration de la voix, intro, compression."""
import subprocess
from pathlib import Path

SR = 24000  # fréquence de travail : Opus 24 kb/s ne dépasse pas 8 kHz de bande, inutile de traiter plus (2x moins de calcul et de mémoire)
SR_WHISPER = 16000


def run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"Échec de {cmd[0]} :\n{tail}")
    return proc.stdout


def probe_duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


def to_whisper(src: Path, out: Path) -> None:
    """WAV mono 16 kHz de tout le culte, lu par morceaux pour la transcription."""
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(src), "-vn", "-ac", "1", "-ar", str(SR_WHISPER),
         "-c:a", "pcm_s16le", str(out)])


# Chaîne d'amélioration de la voix (100 % CPU, rapide) :
#  - passage en mono 24 kHz d'abord, pour que tout le reste coûte 2 à 4x moins cher
#  - coupe les basses (ronflements, vibrations de micro) et les très hautes fréquences
#  - réduction de bruit FFT avec suivi du bruit de fond
#  - léger compresseur pour homogénéiser les passages criés / chuchotés
ENHANCE_FILTER = ",".join([
    f"aresample={SR}",
    "aformat=channel_layouts=mono",
    "highpass=f=70",
    "lowpass=f=10000",
    "afftdn=nr=12:nf=-40:tn=1",
    "acompressor=threshold=0.1:ratio=3:attack=10:release=250:makeup=1.5",
])


def extract_enhanced(src: Path, start: float, end: float, out: Path, out_whisper: Path) -> None:
    """Découpe la prédication et l'améliore en un seul passage ffmpeg.
    Produit le WAV de travail (24 kHz) et sa copie 16 kHz pour Whisper."""
    graph = f"[0:a]{ENHANCE_FILTER},asplit=2[a][b];[b]aresample={SR_WHISPER}[c]"
    run(["ffmpeg", "-y", "-hide_banner", "-ss", f"{start:.3f}", "-i", str(src),
         "-t", f"{max(end - start, 1):.3f}", "-vn", "-filter_complex", graph,
         "-map", "[a]", "-c:a", "pcm_s16le", str(out),
         "-map", "[c]", "-c:a", "pcm_s16le", str(out_whisper)])


LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"  # standard podcast


def finalize(body: Path, out: Path, intro: Path | None = None, xfade: float = 0.6) -> None:
    """Normalise le volume (-16 LUFS) et ajoute l'intro avec un fondu enchaîné."""
    norm = f"aresample={SR},aformat=channel_layouts=mono,{LOUDNORM},aresample={SR}"
    if intro:
        fc = (f"[0:a]{norm}[i];[1:a]{norm}[b];"
              f"[i][b]acrossfade=d={xfade}:c1=tri:c2=tri[out]")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-i", str(intro), "-i", str(body),
               "-filter_complex", fc, "-map", "[out]"]
    else:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-i", str(body), "-af", norm]
    run(cmd + ["-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(out)])


def _meta(title: str, artist: str, date: str) -> list[str]:
    args = ["-metadata", f"title={title}", "-metadata", f"date={date}"]
    if artist:
        args += ["-metadata", f"artist={artist}"]
    return args


def encode_opus(src: Path, out: Path, bitrate: str, title: str, artist: str, date: str) -> None:
    """Opus mono : la meilleure qualité vocale pour la plus petite taille."""
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(src), "-c:a", "libopus",
         "-b:a", bitrate, "-vbr", "on", "-compression_level", "10",
         "-ac", "1", "-ar", "48000", *_meta(title, artist, date), str(out)])


def encode_mp3(src: Path, out: Path, bitrate: str, title: str, artist: str, date: str) -> None:
    """MP3 mono de secours, lisible partout."""
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(src), "-c:a", "libmp3lame",
         "-b:a", bitrate, "-ac", "1", "-ar", "22050",
         *_meta(title, artist, date), str(out)])

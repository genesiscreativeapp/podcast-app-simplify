"""Voix du prédicateur en anglais : extrait audio, transcription, TRADUCTION et moteurs de synthèse (modèles libres, CPU).
Partagé par la version anglaise des podcasts et le banc d'essai (service voicelab, app/voicelab.py) et par la ligne de commande
(tools/bench_voice.py). Aucun import lourd au chargement : chaque moteur importe ses propres bibliothèques quand on l'utilise.

La traduction ne dépend d'aucune IA externe : un modèle libre local (Marian opus-mt fr→en, licence CC-BY 4.0) fait le travail.
Claude n'est qu'une option, meilleure en qualité, avec repli sur le modèle local s'il ne répond pas."""
import re
import subprocess
import time
from pathlib import Path

import numpy as np
import soundfile as sf

GAP = 0.3  # silence entre deux morceaux de texte (secondes)
REF_SECONDS = 12.0  # durée de la voix de référence prise dans l'extrait
LOCAL_MT = "Helsinki-NLP/opus-mt-fr-en"
CLAUDE_BATCH = 120  # phrases traduites par requête
PROMPT = """Traduis en anglais cet extrait d'une prédication chrétienne, pour qu'il soit lu à voix haute par un synthétiseur vocal.
- Garde le ton oral du prédicateur (exhortation, ferveur), sans ajouter ni retirer d'idée.
- Phrases courtes (25 mots maximum), une phrase par ligne, sans numérotation ni commentaire.
- Versets bibliques : traduction anglaise usuelle. « Amen » reste « Amen », « Alléluia » devient « Hallelujah ».

Extrait :
{text}"""
PROMPT_NUMBERED = """Voici, numérotées, les phrases d'une prédication chrétienne en français. Traduis chacune en anglais pour qu'elle soit lue à voix haute.
- Garde le ton oral du prédicateur (exhortation, ferveur), fidèlement : n'ajoute, ne retire ni ne regroupe rien.
- Versets bibliques : traduction anglaise usuelle. « Amen » reste « Amen », « Alléluia » devient « Hallelujah ».
- Réponds UNIQUEMENT par les traductions, avec la MÊME numérotation, une ligne par phrase : « [12] traduction ».

Phrases :
{lines}"""
# moteurs réellement proposés dans l'interface (id → libellé, remarque)
REAL_ENGINES = {
    "chatterbox-nano": ("Chatterbox Nano", "le plus léger, annoncé utilisable sur CPU"),
    "chatterbox-turbo": ("Chatterbox Turbo", "intermédiaire"),
    "chatterbox": ("Chatterbox complet", "meilleure qualité attendue, plus lent"),
}
DEFAULT_ENGINE = "chatterbox-nano"
HINTS = {
    "chatterbox": "pip install chatterbox-tts   (Python 3.11 conseillé)",
    "openvoice": "voir tools/bench_voice.md (OpenVoice + MeloTTS, Python 3.9, --openvoice-dir)",
}


# --- Préparation : extrait, transcription, découpage en phrases ---------------------------------------------------
def excerpt(audio: Path, start: float, seconds: float, ref_start: float, ref_seconds: float, out: Path) -> None:
    """fr.wav : l'extrait (16 kHz, pour Whisper). ref.wav : la voix à cloner, une fenêtre propre de l'extrait (24 kHz)."""
    def cut(t, d, sr, dst):
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(t), "-t", str(d), "-i", str(audio),
                        "-vn", "-ac", "1", "-ar", str(sr), str(dst)], check=True)
    cut(start, seconds, 16000, out / "fr.wav")
    cut(start + ref_start, ref_seconds, 24000, out / "ref.wav")


def transcribe(wav: Path, model: str) -> tuple[str, float]:
    from faster_whisper import WhisperModel

    t0 = time.time()
    segments, _ = WhisperModel(model, device="cpu", compute_type="int8").transcribe(str(wav), language="fr", vad_filter=True)
    return " ".join(s.text.strip() for s in segments), time.time() - t0


def lines(answer: str) -> list[str]:
    """Réponse de la traduction → une phrase par ligne, sans lignes vides."""
    return [ln.strip() for ln in answer.splitlines() if ln.strip()]


def split_sentences(text: str) -> list[str]:
    """Texte continu → phrases (ponctuation finale suivie d'un espace)."""
    return [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text) if p.strip()]


def chunks(sentences: list[str], limit: int = 250) -> list[str]:
    """Regroupe les phrases en morceaux d'environ `limit` caractères : plus naturel qu'une phrase isolée, et le calcul de la voix
    de référence n'est pas refait à chaque phrase."""
    out, cur = [], ""
    for s in sentences:
        if cur and len(cur) + 1 + len(s) > limit:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    return out + ([cur] if cur else [])


def assemble(waves: list[np.ndarray], sr: int) -> np.ndarray:
    gap = np.zeros(int(GAP * sr), np.float32)
    return np.concatenate([x for w in waves for x in (np.asarray(w, np.float32).reshape(-1), gap)])


# --- Voix de référence : le meilleur passage du podcast ---------------------------------------------------------
def best_window(x: np.ndarray, sr: int, seconds: float = REF_SECONDS, skip: float = 45.0, frame: float = 0.05) -> float:
    """Début (s) de la fenêtre où le prédicateur parle le plus continûment et le plus régulièrement : peu de silence, volume stable.
    Les `skip` premières secondes (l'intro) et la fin sont écartées. Sans meilleure option, on garde le début permis."""
    hop = int(sr * frame)
    n = len(x) // hop
    if n == 0:
        return 0.0
    db = 20 * np.log10(np.sqrt(np.mean(x[: n * hop].reshape(n, hop).astype(np.float64) ** 2, axis=1)) + 1e-9)
    speech = db > (np.percentile(db, 30) + 10)
    w = int(seconds / frame)
    lo, hi = int(skip / frame), n - w - int(10 / frame)
    if hi <= lo:  # podcast court : on prend ce qu'il y a
        lo, hi = 0, max(n - w, 0)
    best, start = -9.0, lo
    for i in range(lo, hi + 1, int(3 / frame)):
        seg = speech[i:i + w]
        frac = seg.mean() if len(seg) else 0.0
        loud = db[i:i + w][seg]
        score = frac - 0.03 * (loud.std() if len(loud) > 1 else 0.0)
        if score > best:
            best, start = score, i
    return start * frame


def pick_reference(audio: Path, out: Path, manual_start: float | None = None) -> float:
    """Écrit `out` (12 s, 24 kHz mono) : la voix à cloner. Début choisi automatiquement, ou imposé (`manual_start`). → le début retenu."""
    start = manual_start
    if start is None:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                             check=True, capture_output=True).stdout
        start = best_window(np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0, 16000)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", str(REF_SECONDS), "-i", str(audio),
                    "-vn", "-ac", "1", "-ar", "24000", str(out)], check=True)
    return start


# --- Traduction ---------------------------------------------------------------------------------------------------
_mt: dict = {}


def translate_local(sentences: list[str], on_progress=None, batch: int = 16) -> list[str]:
    """Français → anglais, phrase par phrase, par un modèle libre (Marian opus-mt) sur CPU : aucune IA externe, aucune clé."""
    import torch
    from transformers import MarianMTModel, MarianTokenizer

    if "model" not in _mt:
        _mt["tok"], _mt["model"] = MarianTokenizer.from_pretrained(LOCAL_MT), MarianMTModel.from_pretrained(LOCAL_MT).eval()
    tok, model = _mt["tok"], _mt["model"]
    order = sorted(range(len(sentences)), key=lambda i: len(sentences[i]))  # phrases de longueur proche ensemble : moins de remplissage
    out = [""] * len(sentences)
    for k in range(0, len(order), batch):
        ids = order[k:k + batch]
        enc = tok([sentences[i] for i in ids], return_tensors="pt", padding=True, truncation=True, max_length=256)
        with torch.no_grad():
            gen = model.generate(**enc, num_beams=4, max_new_tokens=256)
        for i, text in zip(ids, tok.batch_decode(gen, skip_special_tokens=True)):
            out[i] = text.strip()
        if on_progress:
            on_progress(min(k + batch, len(order)) / len(order))
    return out


def translate_claude(sentences: list[str], llm: dict, on_usage=None, on_progress=None) -> list[str | None]:
    """Traduction par l'IA, par lots numérotés. Une phrase que l'IA n'a pas rendue vaut None (l'appelant la fait traduire en local)."""
    from .pipeline.detect import ask_llm

    out: list[str | None] = [None] * len(sentences)
    for k in range(0, len(sentences), CLAUDE_BATCH):
        batch = sentences[k:k + CLAUDE_BATCH]
        answer = ask_llm(PROMPT_NUMBERED.format(lines="\n".join(f"[{k + i}] {s}" for i, s in enumerate(batch))), llm,
                         max_tokens=8000, on_usage=on_usage)
        for m in re.finditer(r"^\[(\d+)\]\s*(.+)$", answer, re.M):
            i = int(m.group(1))
            if k <= i < k + len(batch):
                out[i] = m.group(2).strip()
        if on_progress:
            on_progress(min(k + CLAUDE_BATCH, len(sentences)) / len(sentences))
    return out


def translate(sentences: list[str], translator: str = "local", llm: dict | None = None, log=lambda m: None, on_usage=None,
              on_progress=None) -> tuple[list[str], str]:
    """Traduit chaque phrase. `translator` : « local » (modèle libre, par défaut) ou « claude » (si `llm` est fourni) ; si l'IA ne répond pas
    ou oublie des phrases, le modèle local prend le relais. → (traductions alignées, méthode employée)."""
    if translator == "claude" and llm:
        try:
            got = translate_claude(sentences, llm, on_usage, on_progress)
        except Exception as exc:  # réseau, quota, JSON…
            log(f"Traduction par l'IA impossible ({exc}) : modèle local")
            got = [None] * len(sentences)
        missing = [i for i, g in enumerate(got) if not g]
        if not missing:
            return got, "IA"
        if len(missing) < len(sentences):
            log(f"L'IA n'a pas traduit {len(missing)} phrase(s) sur {len(sentences)} : modèle local pour celles-ci")
        for i, text in zip(missing, translate_local([sentences[i] for i in missing])):
            got[i] = text
        return got, "IA + modèle local" if len(missing) < len(sentences) else "modèle local"
    return translate_local(sentences, on_progress), "modèle local"


# --- Moteurs de voix : un objet par moteur, `say(texte)` donne l'audio d'un morceau ---------------------------------
class Dummy:
    """Faux moteur : un bip par morceau. Sert à vérifier le banc et la chaîne sans rien télécharger."""
    sr = 24000

    def __init__(self, ref, work, openvoice_dir):
        pass

    def say(self, text: str) -> np.ndarray:
        return 0.1 * np.sin(2 * np.pi * 220 * np.arange(int(0.06 * len(text) * self.sr)) / self.sr)


class Chatterbox:
    def __init__(self, variant, ref, work, openvoice_dir):
        self.ref = str(ref)
        if variant == "chatterbox":
            from chatterbox.tts import ChatterboxTTS
            self.model = ChatterboxTTS.from_pretrained(device="cpu")
        else:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            self.model = ChatterboxTurboTTS.from_pretrained(device="cpu", **({"nano": True} if variant == "chatterbox-nano" else {}))
        self.sr = self.model.sr

    def say(self, text: str) -> np.ndarray:
        return self.model.generate(text, audio_prompt_path=self.ref).squeeze().cpu().numpy()


class OpenVoice:
    """OpenVoice V2 : MeloTTS lit le texte avec une voix anglaise de base, puis le « tone color converter » lui donne le timbre de ref."""
    def __init__(self, ref, work, openvoice_dir):
        import torch
        from melo.api import TTS
        from openvoice import se_extractor
        from openvoice.api import ToneColorConverter

        root = Path(openvoice_dir)
        self.conv = ToneColorConverter(str(root / "checkpoints_v2/converter/config.json"), device="cpu")
        self.conv.load_ckpt(str(root / "checkpoints_v2/converter/checkpoint.pth"))
        self.target_se, _ = se_extractor.get_se(str(ref), self.conv, vad=True)
        self.tts = TTS(language="EN", device="cpu")
        self.speakers = self.tts.hps.data.spk2id
        self.key = "EN-US" if "EN-US" in self.speakers else next(iter(self.speakers))
        self.source_se = torch.load(str(root / f"checkpoints_v2/base_speakers/ses/{self.key.lower().replace('_', '-')}.pth"), map_location="cpu")
        self.base, self.dst, self.sr = Path(work) / "openvoice_base.wav", Path(work) / "openvoice_out.wav", 22050

    def say(self, text: str) -> np.ndarray:
        self.tts.tts_to_file(text, self.speakers[self.key], str(self.base), speed=1.0)
        self.conv.convert(audio_src_path=str(self.base), src_se=self.source_se, tgt_se=self.target_se, output_path=str(self.dst), message="@MyShell")
        w, self.sr = sf.read(self.dst, dtype="float32")
        return w if w.ndim == 1 else w.mean(axis=1)


ENGINES = {"dummy": lambda ref, work, ov: Dummy(ref, work, ov),
           "chatterbox-nano": lambda ref, work, ov: Chatterbox("chatterbox-nano", ref, work, ov),
           "chatterbox-turbo": lambda ref, work, ov: Chatterbox("chatterbox-turbo", ref, work, ov),
           "chatterbox": lambda ref, work, ov: Chatterbox("chatterbox", ref, work, ov),
           "openvoice": lambda ref, work, ov: OpenVoice(ref, work, ov)}


def load_engine(name: str, ref: Path, work: Path, openvoice_dir: str = "OpenVoice"):
    """Charge le moteur (télécharge ses modèles au premier usage). Lève une exception s'il n'est pas installé."""
    return ENGINES[name](ref, work, openvoice_dir)


def synthesize(name: str, parts: list[str], ref: Path, work: Path, seconds: float, openvoice_dir: str = "OpenVoice") -> tuple[np.ndarray, int, dict]:
    """Fait lire `parts` par le moteur `name` avec la voix de `ref`. → (audio complet, fréquence, mesures).
    `seconds` : durée de l'extrait d'origine, pour estimer le calcul d'une heure de sermon. Lève une exception si le moteur échoue."""
    t0 = time.time()
    engine = load_engine(name, ref, work, openvoice_dir)
    load = time.time() - t0
    t1 = time.time()
    waves = [engine.say(p) for p in parts]
    synth = time.time() - t1
    audio = assemble(waves, engine.sr)
    dur = len(audio) / engine.sr
    return audio, engine.sr, {"engine": name, "load_s": round(load, 1), "synth_s": round(synth, 1), "audio_s": round(dur, 1),
                              "rtf": round(synth / dur, 2) if dur else None,
                              "min_per_source_hour": round(synth / seconds * 60, 1)}  # calcul pour 1 h de sermon, chargement exclu


def failure(name: str, exc: Exception) -> dict:
    """Un moteur absent ou en échec n'arrête pas les autres : on garde le motif et, si on la connaît, la commande d'installation."""
    return {"engine": name, "error": f"{type(exc).__name__}: {exc}", "hint": next((h for k, h in HINTS.items() if name.startswith(k)), "")}

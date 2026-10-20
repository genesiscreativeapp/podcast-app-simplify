#!/usr/bin/env python3
"""Banc d'essai : un extrait de sermon français → anglais, avec la voix du prédicateur (modèles libres, sur CPU).

Pour chaque moteur demandé, le script mesure le temps de chargement, le temps de synthèse et le « facteur temps réel »
(temps de calcul ÷ durée de l'audio produit), puis estime le calcul nécessaire pour une heure de sermon. Il écrit aussi un
fichier audio par moteur, à écouter pour juger la ressemblance et le naturel. Mode d'emploi complet : tools/bench_voice.md.

    python tools/bench_voice.py sermon.mp3 --start 900 --seconds 180 --engines chatterbox-nano,chatterbox

Moteurs : chatterbox-nano, chatterbox-turbo, chatterbox, openvoice, et « dummy » (faux moteur pour vérifier le banc lui-même).
Traduction : Claude, avec la variable d'environnement ANTHROPIC_API_KEY (une clé à vous, jamais écrite sur disque) ;
ou --text-en fichier.txt (une phrase par ligne) pour s'en passer.
"""
import argparse
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import soundfile as sf

GAP = 0.3  # silence entre deux morceaux de texte (secondes)
MODEL = "claude-sonnet-5-5"
PROMPT = """Traduis en anglais cet extrait d'une prédication chrétienne, pour qu'il soit lu à voix haute par un synthétiseur vocal.
- Garde le ton oral du prédicateur (exhortation, ferveur), sans ajouter ni retirer d'idée.
- Phrases courtes (25 mots maximum), une phrase par ligne, sans numérotation ni commentaire.
- Versets bibliques : traduction anglaise usuelle. « Amen » reste « Amen », « Alléluia » devient « Hallelujah ».

Extrait :
{text}"""
HINTS = {
    "chatterbox": "pip install chatterbox-tts   (Python 3.11 conseillé)",
    "openvoice": "voir tools/bench_voice.md (OpenVoice + MeloTTS, Python 3.9, --openvoice-dir)",
}


# --- Préparation : extrait audio, transcription, traduction -------------------------------------------
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


def translate(text: str, model: str) -> tuple[list[str], dict]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("Définissez ANTHROPIC_API_KEY pour traduire, ou fournissez la traduction avec --text-en fichier.txt")
    r = httpx.post("https://api.anthropic.com/v1/messages",
                   headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                   json={"model": model, "max_tokens": 4000, "messages": [{"role": "user", "content": PROMPT.format(text=text)}]},
                   timeout=180)
    if not r.is_success:
        sys.exit(f"Traduction refusée par l'API ({r.status_code}) : {r.text[:300]}")
    data = r.json()
    lines = "".join(b.get("text", "") for b in data["content"]).splitlines()
    return [ln.strip() for ln in lines if ln.strip()], data.get("usage", {})


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


# --- Moteurs : chacun renvoie (morceaux audio, fréquence, secondes de chargement, secondes de synthèse) -------------
def run_dummy(parts, ref, work, args):
    """Faux moteur : un bip par morceau. Sert à vérifier le banc sans rien télécharger."""
    sr = 24000
    waves = [0.1 * np.sin(2 * np.pi * 220 * np.arange(int(0.06 * len(p) * sr)) / sr) for p in parts]
    return waves, sr, 0.0, 0.0


def run_chatterbox(variant):
    def run(parts, ref, work, args):
        t0 = time.time()
        if variant == "chatterbox":
            from chatterbox.tts import ChatterboxTTS
            model = ChatterboxTTS.from_pretrained(device="cpu")
        else:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            model = ChatterboxTurboTTS.from_pretrained(device="cpu", **({"nano": True} if variant == "chatterbox-nano" else {}))
        load = time.time() - t0
        t1 = time.time()
        waves = [model.generate(p, audio_prompt_path=str(ref)).squeeze().cpu().numpy() for p in parts]
        return waves, model.sr, load, time.time() - t1
    return run


def run_openvoice(parts, ref, work, args):
    """OpenVoice V2 : MeloTTS lit le texte avec une voix anglaise de base, puis le « tone color converter » lui donne le timbre de ref."""
    import torch
    from melo.api import TTS
    from openvoice import se_extractor
    from openvoice.api import ToneColorConverter

    root = Path(args.openvoice_dir)
    t0 = time.time()
    conv = ToneColorConverter(str(root / "checkpoints_v2/converter/config.json"), device="cpu")
    conv.load_ckpt(str(root / "checkpoints_v2/converter/checkpoint.pth"))
    target_se, _ = se_extractor.get_se(str(ref), conv, vad=True)
    tts = TTS(language="EN", device="cpu")
    speakers = tts.hps.data.spk2id
    key = "EN-US" if "EN-US" in speakers else next(iter(speakers))
    source_se = torch.load(str(root / f"checkpoints_v2/base_speakers/ses/{key.lower().replace('_', '-')}.pth"), map_location="cpu")
    load = time.time() - t0
    base, waves, sr, t1 = work / "openvoice_base.wav", [], None, time.time()
    for i, p in enumerate(parts):
        tts.tts_to_file(p, speakers[key], str(base), speed=1.0)
        dst = work / f"openvoice_{i}.wav"
        conv.convert(audio_src_path=str(base), src_se=source_se, tgt_se=target_se, output_path=str(dst), message="@MyShell")
        w, sr = sf.read(dst, dtype="float32")
        waves.append(w if w.ndim == 1 else w.mean(axis=1))
    return waves, sr, load, time.time() - t1


ENGINES = {"dummy": run_dummy, "chatterbox-nano": run_chatterbox("chatterbox-nano"),
           "chatterbox-turbo": run_chatterbox("chatterbox-turbo"), "chatterbox": run_chatterbox("chatterbox"),
           "openvoice": run_openvoice}


# --- Banc ---------------------------------------------------------------------------------------------------------
def peak_mb() -> int:
    kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(kb / (1024 * 1024 if sys.platform == "darwin" else 1024))  # macOS : octets ; Linux : Ko


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("audio", type=Path, help="le sermon (ou un podcast déjà produit par l'application)")
    ap.add_argument("--start", type=float, default=600, help="début de l'extrait, en secondes (défaut 600)")
    ap.add_argument("--seconds", type=float, default=180, help="durée de l'extrait (défaut 180 = 3 minutes)")
    ap.add_argument("--ref-start", type=float, default=5, help="début de la voix de référence DANS l'extrait (défaut 5)")
    ap.add_argument("--ref-seconds", type=float, default=12, help="durée de la voix de référence (défaut 12) : le prédicateur seul, sans musique")
    ap.add_argument("--engines", default="chatterbox-nano,chatterbox", help="liste séparée par des virgules, parmi : " + ", ".join(ENGINES))
    ap.add_argument("--text-en", type=Path, help="traduction déjà prête (une phrase par ligne) : ni Whisper ni Claude")
    ap.add_argument("--whisper", default="small", help="modèle Whisper pour la transcription (défaut small)")
    ap.add_argument("--model", default=MODEL, help=f"modèle Claude pour la traduction (défaut {MODEL})")
    ap.add_argument("--openvoice-dir", default="OpenVoice", help="dépôt OpenVoice cloné, contenant checkpoints_v2/")
    ap.add_argument("--out", type=Path, default=Path("bench_out"))
    args = ap.parse_args(argv)

    unknown = [e for e in args.engines.split(",") if e not in ENGINES]
    if unknown:
        sys.exit(f"Moteur inconnu : {', '.join(unknown)} (disponibles : {', '.join(ENGINES)})")
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"env": {"cpu_count": os.cpu_count(), "machine": platform.machine(), "platform": platform.platform()},
              "excerpt_seconds": args.seconds}
    print("→ extrait audio et voix de référence")
    excerpt(args.audio, args.start, args.seconds, args.ref_start, args.ref_seconds, args.out)

    if args.text_en:
        sentences = [ln.strip() for ln in args.text_en.read_text(encoding="utf-8").splitlines() if ln.strip()]
    else:
        print(f"→ transcription (Whisper {args.whisper}, CPU)")
        fr, asr_s = transcribe(args.out / "fr.wav", args.whisper)
        (args.out / "fr.txt").write_text(fr, encoding="utf-8")
        print(f"→ traduction ({args.model})")
        sentences, usage = translate(fr, args.model)
        report.update(whisper_s=round(asr_s, 1), translation_tokens=usage)
    (args.out / "en.txt").write_text("\n".join(sentences), encoding="utf-8")
    parts = chunks(sentences)
    print(f"→ {len(sentences)} phrases, {len(parts)} morceaux à synthétiser")

    report["results"] = results = []
    for name in args.engines.split(","):
        print(f"→ moteur {name}")
        try:
            waves, sr, load, synth = ENGINES[name](parts, args.out / "ref.wav", args.out, args)
        except Exception as exc:  # un moteur absent ou en échec n'arrête pas les autres
            hint = next((h for k, h in HINTS.items() if name.startswith(k)), "")
            results.append({"engine": name, "error": f"{type(exc).__name__}: {exc}", "hint": hint})
            print(f"   ÉCHEC : {exc}" + (f"\n   Installation : {hint}" if hint else ""))
            continue
        audio = assemble(waves, sr)
        sf.write(args.out / f"{name}.wav", audio, sr)
        dur = len(audio) / sr
        results.append({"engine": name, "load_s": round(load, 1), "synth_s": round(synth, 1), "audio_s": round(dur, 1),
                        "rtf": round(synth / dur, 2) if dur else None,
                        "min_per_source_hour": round(synth / args.seconds * 60, 1),  # calcul pour 1 h de sermon, chargement exclu
                        "peak_mb_so_far": peak_mb()})

    (args.out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{'moteur':<18}{'chargement':>11}{'synthèse':>10}{'audio':>8}{'RTF':>7}{'min / h de sermon':>19}{'RAM max':>9}")
    for r in results:
        print(f"{r['engine']:<18}" + (f"{'ÉCHEC':>11}  {r['error'][:70]}" if "error" in r else
              f"{r['load_s']:>10}s{r['synth_s']:>9}s{r['audio_s']:>7}s{r['rtf']:>7}{r['min_per_source_hour']:>19}{r['peak_mb_so_far']:>7}Mo"))
    print("\nRTF < 1 : la synthèse est plus rapide que l'audio produit. « min / h de sermon » = minutes de calcul pour 1 h de sermon.")
    print(f"Écoutez les fichiers de {args.out}/ (un .wav par moteur, ref.wav = la voix de référence) ; détail dans report.json.")
    return report


if __name__ == "__main__":
    main()

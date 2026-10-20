#!/usr/bin/env python3
"""Banc d'essai : un extrait de sermon français → anglais, avec la voix du prédicateur (modèles libres, sur CPU).

Pour chaque moteur demandé, le script mesure le temps de chargement, le temps de synthèse et le « facteur temps réel »
(temps de calcul ÷ durée de l'audio produit), puis estime le calcul nécessaire pour une heure de sermon. Il écrit aussi un
fichier audio par moteur, à écouter pour juger la ressemblance et le naturel. Mode d'emploi complet : tools/bench_voice.md.
(La même chose se fait depuis l'application, écran « Banc d'essai voix », avec le service voicelab.)

    python tools/bench_voice.py sermon.mp3 --start 900 --seconds 180 --engines chatterbox-nano,chatterbox

Moteurs : chatterbox-nano, chatterbox-turbo, chatterbox, openvoice, et « dummy » (faux moteur pour vérifier le banc lui-même).
Traduction : par défaut un modèle libre local (--translator local, sans clé ni IA externe : il faut `pip install transformers sentencepiece torch`) ;
--translator claude utilise Claude avec ANTHROPIC_API_KEY (une clé à vous, jamais écrite sur disque) ; --text-en fichier.txt fournit sa propre traduction.
"""
import argparse
import json
import os
import platform
import resource
import sys
from pathlib import Path

import httpx
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.voicebench import ENGINES, PROMPT, chunks, excerpt, failure, lines, split_sentences, synthesize, transcribe, translate_local  # noqa: E402

MODEL = "claude-sonnet-5-5"


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
    return lines("".join(b.get("text", "") for b in data["content"])), data.get("usage", {})


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
    ap.add_argument("--translator", choices=["local", "claude"], default="local", help="local : modèle libre (défaut) ; claude : IA, avec ANTHROPIC_API_KEY")
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
        sentences = lines(args.text_en.read_text(encoding="utf-8"))
    else:
        print(f"→ transcription (Whisper {args.whisper}, CPU)")
        fr, asr_s = transcribe(args.out / "fr.wav", args.whisper)
        (args.out / "fr.txt").write_text(fr, encoding="utf-8")
        print(f"→ traduction ({'Claude, ' + args.model if args.translator == 'claude' else 'modèle libre local'})")
        if args.translator == "claude":
            sentences, usage = translate(fr, args.model)
            report.update(whisper_s=round(asr_s, 1), translation_tokens=usage)
        else:
            sentences = translate_local(split_sentences(fr))
            report.update(whisper_s=round(asr_s, 1), translation="modèle libre local")
    (args.out / "en.txt").write_text("\n".join(sentences), encoding="utf-8")
    parts = chunks(sentences)
    print(f"→ {len(sentences)} phrases, {len(parts)} morceaux à synthétiser")

    report["results"] = results = []
    for name in args.engines.split(","):
        print(f"→ moteur {name}")
        try:
            audio, sr, res = synthesize(name, parts, args.out / "ref.wav", args.out, args.seconds, args.openvoice_dir)
        except Exception as exc:  # un moteur absent ou en échec n'arrête pas les autres
            results.append(failure(name, exc))
            print(f"   ÉCHEC : {exc}" + (f"\n   Installation : {results[-1]['hint']}" if results[-1]["hint"] else ""))
            continue
        sf.write(args.out / f"{name}.wav", audio, sr)
        results.append({**res, "peak_mb_so_far": peak_mb()})

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

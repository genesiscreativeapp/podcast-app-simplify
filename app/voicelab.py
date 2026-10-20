"""Service voicelab : calcule la VERSION ANGLAISE des podcasts (traduction + voix du prédicateur) et les essais du « Banc d'essai voix ».

Optionnel et séparé de l'application : son image (Dockerfile.voicelab) est lourde (PyTorch, modèles), il n'est démarré que si on
l'active (profil « voicelab » de docker-compose). Il lit le travail en attente dans la base partagée, comme le worker lit les
traitements, et signale sa présence par un battement de cœur que l'application affiche."""
import json
import logging
import os
import platform
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import soundfile as sf

from . import config, english, r2sync, storage, voicebench as vb
from .db import AiUsage, EnVersion, Job, Setting, SessionLocal, VoiceBench, ai_for, init_db
from .pipeline import audio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("voicelab")
BENCH_DIR = config.DATA_DIR / "bench"
_stop = False


def beat() -> None:
    with SessionLocal() as s:
        s.merge(Setting(key="voicelab_seen", value=datetime.utcnow().isoformat()))
        s.commit()


def _heartbeat() -> None:  # pendant un long calcul aussi : l'écran sait que le service est vivant
    while True:
        try:
            beat()
        except Exception:
            log.exception("battement de cœur")
        time.sleep(5)


def _set(run_id: int, **fields) -> None:
    with SessionLocal() as s:
        run = s.get(VoiceBench, run_id)
        if run:
            for k, v in fields.items():
                setattr(run, k, v)
            s.commit()


def _say(run_id: int, message: str) -> None:
    with SessionLocal() as s:
        run = s.get(VoiceBench, run_id)
        if run:
            run.log = (run.log or "") + f"[{datetime.now():%H:%M:%S}] {message}\n"
            s.commit()


def claim_next() -> int | None:
    """Prend l'essai en attente le plus ancien ; le UPDATE conditionnel évite qu'il soit pris deux fois."""
    with SessionLocal() as s:
        for (run_id,) in s.query(VoiceBench.id).filter(VoiceBench.status == "pending").order_by(VoiceBench.id).all():
            claimed = s.query(VoiceBench).filter(VoiceBench.id == run_id, VoiceBench.status == "pending").update(
                {"status": "running", "step": "Démarrage", "progress": 0.0})
            s.commit()
            if claimed:
                return run_id
    return None


# --- Version anglaise d'un podcast -------------------------------------------------------------------------------------
def _en_set(en_id: int, **fields) -> None:
    with SessionLocal() as s:
        en = s.get(EnVersion, en_id)
        if en:
            for k, v in fields.items():
                setattr(en, k, v)
            s.commit()


def _en_say(en_id: int, message: str) -> None:
    with SessionLocal() as s:
        en = s.get(EnVersion, en_id)
        if en:
            en.log = (en.log or "") + f"[{datetime.now():%H:%M:%S}] {message}\n"
            s.commit()


def claim_english() -> int | None:
    """Prend la version anglaise en attente la plus ancienne (nouvelle demande, ou texte validé qui attend sa voix)."""
    with SessionLocal() as s:
        for (en_id,) in s.query(EnVersion.id).filter(EnVersion.status == "pending").order_by(EnVersion.created_at, EnVersion.id).all():
            claimed = s.query(EnVersion).filter(EnVersion.id == en_id, EnVersion.status == "pending").update({"status": "running", "step": "Démarrage"})
            s.commit()
            if claimed:
                return en_id
    return None


def run_english(en_id: int) -> None:
    """Texte français du podcast → traduction → (validation éventuelle du texte) → voix du prédicateur → MP3 → R2.
    Reprenable : le texte traduit et chaque morceau de voix terminé sont conservés ; un redémarrage ne refait pas ce qui est fait."""
    with SessionLocal() as s:
        en = s.get(EnVersion, en_id)
        job = s.get(Job, en.job_id)
        e = {"job_id": job.id, "title": job.title, "date": job.date, "by": en.created_by, "mode": en.mode, "translator": en.translator,
             "engine": en.engine, "ref_start": en.ref_start, "text": json.loads(en.text_json) if en.text_json else None,
             "review_ok": en.review_ok, "mp3": Path(job.local_mp3) if job.local_mp3 else None,
             "transcript": json.loads(job.transcript_json) if job.transcript_json else None}
    work = english.EN_DIR / str(en_id)
    work.mkdir(parents=True, exist_ok=True)

    def step(label: str, progress: float) -> None:
        _en_say(en_id, label)
        _en_set(en_id, step=label, progress=progress)

    try:
        if not (e["mp3"] and e["mp3"].exists()):
            raise RuntimeError("Le podcast français n'est plus disponible sur le serveur")
        text = e["text"]
        # 1. Le texte : phrases du podcast final, puis traduction (modèle libre local par défaut ; Claude en option, repli sur le local)
        if text is None:
            sentences = e["transcript"]
            if not sentences:  # podcast produit avant l'enregistrement du texte final : on le retranscrit
                step(f"Transcription du podcast (Whisper {config.WHISPER_MODEL_EDIT})", 0.03)
                wav = work / "fr16k.wav"
                subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(e["mp3"]), "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
                sentences = vb.split_sentences(vb.transcribe(wav, config.WHISPER_MODEL_EDIT)[0])
                wav.unlink(missing_ok=True)
            if not sentences:
                raise RuntimeError("Aucun texte à traduire dans ce podcast")
            llm = None
            if e["translator"] == "claude":
                with SessionLocal() as s:
                    llm = ai_for(s, e["by"])
                if llm is None:
                    _en_say(en_id, "Claude n'est pas disponible pour cet utilisateur : modèle local")

            def ledger(n_in: int, n_out: int) -> None:  # la consommation entre dans les compteurs, comme pour un traitement
                with SessionLocal() as s2:
                    s2.add(AiUsage(username=llm["owner"], author=e["by"], job_id=e["job_id"], tokens_in=n_in, tokens_out=n_out))
                    s2.commit()
                _en_say(en_id, f"IA : {n_in} tokens en entrée, {n_out} en sortie")

            step(f"Traduction de {len(sentences)} phrases ({'Claude' if llm else 'modèle libre local'})", 0.08)
            last = [0.0]

            def progress(frac: float) -> None:
                if frac - last[0] >= 0.05 or frac >= 1:
                    last[0] = frac
                    _en_set(en_id, progress=0.08 + 0.12 * frac)

            translated, method = vb.translate(sentences, e["translator"], llm, lambda m: _en_say(en_id, m), ledger if llm else None, progress)
            text = [{"id": i, "fr": f, "en": t} for i, (f, t) in enumerate(zip(sentences, translated))]
            _en_set(en_id, text_json=json.dumps(text, ensure_ascii=False), method=method)
            _en_say(en_id, f"Texte anglais prêt ({method})")
            if e["mode"] == "review":  # le texte sera dit avec la voix du prédicateur : on s'arrête pour que l'utilisateur le relise
                _en_set(en_id, status="review", step="À valider : texte anglais", progress=0.2, review_ok=False)
                _en_say(en_id, "En attente de la validation du texte anglais")
                return
        # 2. La voix : référence automatique (meilleur passage du podcast) ou imposée, puis un morceau après l'autre
        parts = vb.chunks([t["en"].strip() for t in text if t["en"].strip()])
        if not parts:
            raise RuntimeError("Le texte anglais est vide")
        ref = work / "ref.wav"
        if not ref.exists():
            step("Choix de la voix de référence", 0.21)
            _en_say(en_id, f"Voix de référence prise à {vb.pick_reference(e['mp3'], ref, e['ref_start']):.0f} s du podcast")
        step(f"Chargement du moteur de voix ({e['engine']})", 0.22)
        engine = vb.load_engine(e["engine"], ref, work)
        todo = [i for i in range(len(parts)) if not (work / f"part_{i:04d}.wav").exists()]
        if len(todo) < len(parts):
            _en_say(en_id, f"Reprise : {len(parts) - len(todo)} morceau(x) sur {len(parts)} déjà synthétisé(s)")
        for k, i in enumerate(todo):
            tmp = work / f"part_{i:04d}.tmp.wav"
            sf.write(str(tmp), engine.say(parts[i]), engine.sr, format="WAV")
            tmp.replace(work / f"part_{i:04d}.wav")  # atomique : un morceau n'existe que complet
            done = len(parts) - len(todo) + k + 1
            _en_set(en_id, step=f"Voix : morceau {done}/{len(parts)}", progress=0.22 + 0.68 * done / len(parts))
            if done % 10 == 0 or done == len(parts):
                _en_say(en_id, f"Voix : {done}/{len(parts)} morceaux")
        # 3. Assemblage, volume, MP3, R2
        waves = [sf.read(str(work / f"part_{i:04d}.wav"), dtype="float32") for i in range(len(parts))]
        sr = waves[0][1]
        body, master = work / "body.wav", work / "master.wav"
        sf.write(str(body), vb.assemble([w for w, _ in waves], sr), sr)
        step("Volume et fondu de sortie", 0.91)
        audio.finalize(body, master)
        step("Compression MP3", 0.94)
        out_dir = config.OUTPUT_DIR / str(e["job_id"])
        out_dir.mkdir(parents=True, exist_ok=True)
        mp3 = out_dir / f"{english.english_filename(e['title'], e['date'])}.mp3"
        audio.encode_mp3(master, mp3, config.MP3_BITRATE, f"{e['title']} (English)", config.PODCAST_ARTIST, e["date"], audio.probe_duration(master))
        key = None
        if storage.enabled():
            step("Envoi vers Cloudflare R2", 0.97)
            with SessionLocal() as s:
                key = r2sync.desired_key_en(s, s.get(Job, e["job_id"]))
            storage.upload(mp3, key, "audio/mpeg")
            _en_say(en_id, f"Envoyé sur R2 : {key}")
        _en_set(en_id, status="done", step="Terminé", progress=1.0, local_mp3=str(mp3), size_mp3=mp3.stat().st_size,
                duration_output=audio.probe_duration(mp3), r2_key_mp3=key, error=None, finished_at=datetime.utcnow())
        _en_say(en_id, f"Terminé : {mp3.stat().st_size / 1e6:.1f} Mo")
        shutil.rmtree(work, ignore_errors=True)  # le MP3 suffit : le travail en cours n'a plus d'utilité
    except Exception as exc:
        log.exception("version anglaise #%d", en_id)
        hint = vb.failure(e["engine"], exc)["hint"]
        _en_say(en_id, f"ERREUR — {exc}" + (f" ({hint})" if hint else ""))
        _en_set(en_id, status="error", step="Erreur", error=str(exc)[:2000], finished_at=datetime.utcnow())


def run_bench(run_id: int) -> None:
    with SessionLocal() as s:
        run = s.get(VoiceBench, run_id)
        job = s.get(Job, run.job_id)
        src = Path(job.local_mp3) if job and job.local_mp3 else None
        r = {"start": run.start, "seconds": run.seconds, "ref_start": run.ref_start, "engines": run.engines.split(","),
             "text_en": run.text_en, "by": run.created_by, "translator": run.translator}
    work = BENCH_DIR / str(run_id)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    def step(label: str, progress: float) -> None:
        _say(run_id, label)
        _set(run_id, step=label, progress=progress)

    try:
        if not (src and src.exists()):
            raise RuntimeError("Le podcast source n'est plus disponible sur le serveur")
        step("Extrait audio et voix de référence", 0.03)
        vb.excerpt(src, r["start"], r["seconds"], r["ref_start"], vb.REF_SECONDS, work)
        report = {"env": {"cpu_count": os.cpu_count(), "machine": platform.machine()}, "excerpt_seconds": r["seconds"]}
        if r["text_en"]:
            sentences = vb.lines(r["text_en"])
            _say(run_id, "Traduction fournie : ni Whisper ni IA")
        else:
            step(f"Transcription (Whisper {config.WHISPER_MODEL_EDIT})", 0.08)
            fr, asr_s = vb.transcribe(work / "fr.wav", config.WHISPER_MODEL_EDIT)
            (work / "fr.txt").write_text(fr, encoding="utf-8")
            report["whisper_s"] = round(asr_s, 1)
            llm = None
            if r["translator"] == "claude":
                with SessionLocal() as s:
                    llm = ai_for(s, r["by"])
                if llm is None:
                    _say(run_id, "Claude n'est pas disponible pour cet utilisateur : modèle local")

            def ledger(n_in: int, n_out: int) -> None:  # la consommation entre dans les compteurs, comme pour un traitement
                with SessionLocal() as s2:
                    s2.add(AiUsage(username=llm["owner"], author=r["by"], tokens_in=n_in, tokens_out=n_out))
                    s2.commit()
                _say(run_id, f"IA : {n_in} tokens en entrée, {n_out} en sortie")

            step(f"Traduction en anglais ({'Claude' if llm else 'modèle libre local'})", 0.25)
            sentences, method = vb.translate(vb.split_sentences(fr), r["translator"], llm, lambda m: _say(run_id, m), ledger if llm else None)
            report["translation"] = method
        if not sentences:
            raise RuntimeError("Aucun texte à synthétiser (extrait sans parole ?)")
        (work / "en.txt").write_text("\n".join(sentences), encoding="utf-8")
        parts = vb.chunks(sentences)
        report.update(sentences=len(sentences), parts=len(parts))
        _say(run_id, f"{len(sentences)} phrases, {len(parts)} morceaux à synthétiser")

        report["results"] = results = []
        for k, name in enumerate(r["engines"]):
            step(f"Moteur {name} ({k + 1}/{len(r['engines'])}) : chargement puis synthèse", 0.3 + 0.7 * k / len(r["engines"]))
            try:
                audio, sr, res = vb.synthesize(name, parts, work / "ref.wav", work, r["seconds"])
                sf.write(work / f"{name}.wav", audio, sr)
                results.append({**res, "file": f"{name}.wav"})
                _say(run_id, f"{name} : {res['synth_s']} s de calcul pour {res['audio_s']} s d'audio (RTF {res['rtf']})")
            except Exception as exc:  # un moteur absent ou en échec n'arrête pas les autres
                results.append(vb.failure(name, exc))
                _say(run_id, f"{name} : ÉCHEC — {exc}")
        _set(run_id, status="done", step="Terminé", progress=1.0, report_json=json.dumps(report), finished_at=datetime.utcnow())
    except Exception as exc:
        log.exception("essai #%d", run_id)
        _say(run_id, f"ERREUR — {exc}")
        _set(run_id, status="error", step="Erreur", error=str(exc)[:2000], finished_at=datetime.utcnow())


def mark_interrupted() -> int:
    """Une version anglaise interrompue par un redémarrage reprend toute seule (ce qui est fait est conservé). Un essai du banc
    d'essai n'est pas repris : il peut durer longtemps, on laisse l'admin le relancer."""
    with SessionLocal() as s:
        s.query(EnVersion).filter(EnVersion.status == "running").update({"status": "pending", "step": "Reprise après redémarrage"})
        n = s.query(VoiceBench).filter(VoiceBench.status == "running").update(
            {"status": "error", "step": "Erreur", "error": "Interrompu par le redémarrage du service : relancez l'essai",
             "finished_at": datetime.utcnow()})
        s.commit()
    return n


def _handle_stop(*_):
    global _stop
    _stop = True


def main() -> None:
    init_db()
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    if n := mark_interrupted():
        log.info("%d essai(s) interrompu(s)", n)
    threading.Thread(target=_heartbeat, daemon=True).start()
    log.info("voicelab prêt")
    while not _stop:
        en_id = claim_english()  # les versions anglaises passent avant les essais
        if en_id is not None:
            log.info("version anglaise #%d démarrée", en_id)
            run_english(en_id)
            log.info("version anglaise #%d finie", en_id)
            continue
        run_id = claim_next()
        if run_id is None:
            time.sleep(3)
            continue
        log.info("essai #%d démarré", run_id)
        run_bench(run_id)
        log.info("essai #%d fini", run_id)


if __name__ == "__main__":
    main()

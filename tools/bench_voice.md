# Banc d'essai : voix du prédicateur en anglais (ligne de commande)

> L'application propose la même chose avec une interface : menu **Banc d'essai voix** (voir le README), avec le service optionnel `voicelab`. Ce mode d'emploi sert quand on préfère la ligne de commande, ou pour essayer OpenVoice.

But : savoir, **avant d'intégrer quoi que ce soit**, si un modèle libre sait refaire en anglais la voix du prédicateur, et en
combien de temps sur **votre** serveur. Le script `tools/bench_voice.py` ne touche ni à l'application ni à ses données.

Il prend un extrait de sermon, le transcrit (Whisper, déjà dans le projet), le traduit (Claude), puis le fait lire par chaque
moteur demandé avec la voix de référence prise dans l'extrait. Il affiche les temps et écrit un fichier audio par moteur.

## Ce qu'il faut

- Un sermon : le plus simple est de télécharger un **podcast déjà produit** depuis l'application (« Télécharger MP3 »).
  Choisissez un passage où le prédicateur parle seul, **sans musique ni réponse de l'assemblée**.
- Pour traduire : **rien**, par défaut : un modèle libre local (`--translator local`, installé avec `transformers` et `sentencepiece`).
  Claude est une option (`--translator claude`, avec une clé Anthropic **à vous** dans `ANTHROPIC_API_KEY`, rien n'est écrit sur disque).
  Vous pouvez aussi fournir votre traduction (une phrase par ligne) avec `--text-en en.txt`.
- Quelques Go d'espace disque : PyTorch et les modèles se téléchargent à la première utilisation.

## Chatterbox (à essayer en premier : MIT, la variante « nano » est annoncée utilisable sur CPU)

Dans un conteneur jetable, sur le serveur, depuis le dossier du projet (le podcast copié à côté, ici `sermon.mp3`) :

```bash
docker run --rm -it -v "$PWD":/work -v voicebench:/root/.cache -w /work -e ANTHROPIC_API_KEY python:3.11-slim bash
```

puis, dans le conteneur :

```bash
apt-get update && apt-get install -y ffmpeg libsndfile1 git build-essential
pip install faster-whisper httpx soundfile numpy transformers sentencepiece
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu   # évite la version CUDA, très lourde
pip install chatterbox-tts
python tools/bench_voice.py sermon.mp3 --start 900 --seconds 180 --engines chatterbox-nano,chatterbox-turbo,chatterbox
```

`--start 900` : l'extrait commence à 15 minutes (après l'intro du podcast). Si la voix de référence tombe sur un silence ou un
chant, changez `--ref-start` (les 12 secondes prises à partir de ce point de l'extrait).

## OpenVoice V2 (MIT, français/anglais pris en charge ; installation plus délicate)

Autre conteneur (OpenVoice demande Python 3.9) :

```bash
docker run --rm -it -v "$PWD":/work -v voicebench:/root/.cache -w /work -e ANTHROPIC_API_KEY python:3.9-slim bash
```

```bash
apt-get update && apt-get install -y ffmpeg libsndfile1 git build-essential wget unzip
pip install faster-whisper httpx soundfile numpy
git clone https://github.com/myshell-ai/OpenVoice.git && (cd OpenVoice && pip install -e .)
pip install git+https://github.com/myshell-ai/MeloTTS.git && python -m unidic download
wget https://myshell-public-repo-host.s3.amazonaws.com/openvoice/checkpoints_v2_0417.zip && unzip checkpoints_v2_0417.zip -d OpenVoice
ls OpenVoice/checkpoints_v2/converter/config.json     # doit exister (sinon déplacez le dossier décompressé)
python tools/bench_voice.py sermon.mp3 --start 900 --seconds 180 --engines openvoice --openvoice-dir OpenVoice
```

## Lire le résultat

Le tableau final donne, par moteur : le chargement (une fois par lancement), la synthèse, la durée de l'audio produit, le **RTF**
(inférieur à 1 = plus rapide que l'audio) et **« min / h de sermon »** : les minutes de calcul pour une heure de sermon.

| Calcul pour 1 h de sermon | Verdict |
|---|---|
| moins de 60 min | confortable : la version anglaise suit presque en temps réel |
| 1 à 3 h | acceptable en tâche de fond (la version française est publiée sans attendre) |
| plus de 3 h | trop lent sur ce serveur, sauf à ne traiter que quelques sermons |

Puis **écoutez** `bench_out/<moteur>.wav` à côté de `ref.wav` : ressemblance du timbre, naturel, accent, mots avalés ou répétés,
énergie par rapport à l'original. Les chiffres seuls ne suffisent pas : un moteur rapide dont la voix ne ressemble pas ne sert à rien.

`bench_out/report.json` garde tout (machine, temps, jetons de traduction) : envoyez-le avec vos impressions d'écoute.

## À savoir

- Les temps dépendent beaucoup du nombre de cœurs : lancez le test **sur le serveur de production**, pas sur un autre poste.
- « RAM max » est le pic cumulé du processus : pour la mesure propre d'un moteur, lancez-le seul (`--engines nom`).
- La synthèse se fait par morceaux d'environ 250 caractères ; la voix de référence est la même pour tous les moteurs.
- XTTS-v2 n'est pas proposé : sa licence est non commerciale. Aucun service payant n'est utilisé, hors la traduction par Claude.

# Studio Podcast

Transforme automatiquement un culte YouTube en podcast de prédication, prêt à partager sur WhatsApp et Telegram.

**Lien YouTube → téléchargement audio → repérage de la prédication → amélioration de la voix → suppression des silences, « euh » et répétitions → intro → compression Opus/MP3 → Cloudflare R2**

L'interface web permet de classer les traitements dans des dossiers et sous-dossiers (ex. `CULTE ROYAL / Octobre 2026`).
Chaque fichier est nommé `Nom_AAAA-MM-JJ.ogg` à partir du nom et de la date saisis avec le lien.

## Installation

```bash
cp .env.example .env      # puis remplir APP_PASSWORD, R2_*, LLM_*
mkdir -p data
docker compose up -d --build
```

L'interface est accessible sur `http://<serveur>:8000` (identifiants : `APP_USER` / `APP_PASSWORD`).
Sur Coolify, déployez en « Docker Compose » et routez le domaine vers le service `web` (port 8000).

Au premier traitement, les modèles Whisper sont téléchargés dans `data/models` (≈ 150 Mo pour `base`, ≈ 500 Mo pour `small`).

## Utilisation

1. Créer un dossier (ex. **CULTE ROYAL**), éventuellement des sous-dossiers.
2. Déposer une **intro** : par défaut (barre latérale) ou propre à un dossier. Un sous-dossier hérite de l'intro de son parent.
3. Coller le lien YouTube, le nom et la date, puis **Lancer le traitement**.
4. Suivre l'avancement en direct, écouter le résultat, télécharger l'OGG/MP3 ou copier le lien R2.
5. Si la prédication détectée n'est pas la bonne : **Relancer** en saisissant le début et la fin (format `1:05:30`).

## Comment la prédication est repérée

- **Avec un LLM** (`LLM_PROVIDER=anthropic` ou `openai`) : une transcription rapide du culte entier est envoyée à l'IA, qui renvoie le début et la fin du message. C'est la méthode la plus fiable. Coût : environ 15 à 20 000 tokens pour un culte de 3 h.
- **Sans LLM** : une heuristique retient la plus longue zone de parole dense. La louange chantée a un débit de mots plus faible et les annonces sont courtes. Cela fonctionne bien quand le culte est classique, moins bien avec un long temps de prière parlée.
- **Bornes manuelles** : si vous les saisissez, l'étape de repérage est sautée et le traitement est bien plus rapide.

## Nettoyage

| Élément | Méthode | Réglage |
|---|---|---|
| Silences | Détection sur l'énergie du signal : une zone sonore n'est jamais coupée | `MAX_PAUSE`, `TARGET_PAUSE` |
| Bruit, souffle | Filtres ffmpeg (passe-haut, réduction de bruit FFT, compresseur) | `app/pipeline/audio.py` |
| « euh », « hum » | Horodatages mot à mot de Whisper | `REMOVE_FILLERS` |
| Bégaiements (« le le », « je vais je vais ») | Répétitions **immédiates** uniquement | `REMOVE_REPEATS` |
| Volume | Normalisation à -16 LUFS (standard podcast) | — |

Les répétitions d'emphase dites avec une pause (« Il est fidèle… il est fidèle ! ») et les mots comme « amen » ou « alléluia » sont volontairement préservés.

## Durées sur CPU (ordre de grandeur, 4 cœurs, à mesurer sur votre serveur)

Le traitement est optimisé pour les cultes de 4 h 30 et plus :
- **repérage** : modèle `tiny`, seulement 15 s transcrites par fenêtre de 30 s (le LLM n'en lit que le début), lots traités en parallèle ;
- **passe mot à mot** : la prédication est découpée en lots de 10 min (coupés dans un creux de parole) transcrits en parallèle, `beam_size=1` ;
- **ffmpeg** : extraction et amélioration de la voix en un seul passage, travail en 24 kHz mono (Opus 24 kb/s n'utilise pas plus), OGG et MP3 encodés ensemble, envoi R2 en parallèle ;
- **YouTube** : audio léger (≈ 50-70 kb/s) téléchargé par 4 fragments simultanés ; il est gardé en cache, donc **Relancer** ne retélécharge rien.

Pour aller plus vite : saisir les bornes (le repérage disparaît), `DETECT_CLIP=10`. Pour plus de précision : `WHISPER_MODEL_DETECT=base`, `WHISPER_BEAM_EDIT=5`, `YTDLP_FORMAT=bestaudio/best`.
Les traitements sont faits un par un, dans l'ordre d'arrivée.

## Taille des fichiers

Opus mono à 24 kb/s ≈ **11 Mo par heure** ; MP3 mono à 40 kb/s ≈ 18 Mo par heure.
Pour des fichiers encore plus petits, `OPUS_BITRATE=16k` (≈ 7 Mo/h) reste très intelligible.

## Si YouTube bloque le serveur

Message « Sign in to confirm you're not a bot » : exportez les cookies d'un compte YouTube (extension « Get cookies.txt LOCALLY ») dans `data/cookies.txt`, puis ajoutez `YTDLP_COOKIES=/data/cookies.txt` au `.env`. Mettez aussi yt-dlp à jour régulièrement : `docker compose build --no-cache`.

## Structure

```
app/
  main.py          API + interface
  worker.py        file d'attente
  db.py            dossiers, traitements (SQLite)
  storage.py       Cloudflare R2
  pipeline/
    download.py    yt-dlp
    transcribe.py  faster-whisper (CPU, int8)
    detect.py      repérage de la prédication (LLM / heuristique)
    edit.py        montage : silences, hésitations, répétitions
    audio.py       ffmpeg : voix, intro, compression
    run.py         enchaînement des étapes
  static/          interface web
data/              base, intros, sorties, modèles (volume Docker)
```

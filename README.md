# Studio Podcast

Transforme automatiquement un culte YouTube en podcast de prédication, prêt à partager sur WhatsApp et Telegram.

**Lien YouTube → téléchargement audio → repérage de la prédication → amélioration de la voix → suppression des silences, « euh » et répétitions → intro → compression MP3 → Cloudflare R2**

L'interface web permet de classer les traitements dans des dossiers et sous-dossiers (ex. `CULTE ROYAL / Octobre 2026`).
Chaque fichier est nommé `Nom_AAAA-MM-JJ.mp3` à partir du nom et de la date saisis avec le lien.

## Installation

```bash
cp .env.example .env      # puis remplir APP_PASSWORD, R2_* (et SECRET_KEY, voir plus bas)
mkdir -p data
docker compose up -d --build
```

À la première connexion, le compte administrateur est celui de `APP_USER` / `APP_PASSWORD` (créé une seule fois ; ensuite les comptes se gèrent dans l'interface). L'interface écoute sur le port **3000** du conteneur `web` Le port n'est pas publié sur l'hôte : en local, ajoutez `ports: ["3000:3000"]` au service `web` pour ouvrir `http://localhost:3000`.
Sur Coolify, déployez en « Docker Compose » et routez le domaine vers le service `web`, avec le port : `https://votre-domaine:3000`.

**IA : rien à mettre dans `.env`.** Une fois connecté, l'administrateur clique sur la pastille **« IA non configurée »** en haut de l'interface et saisit sa clé API Anthropic (seule l'IA d'Anthropic est prise en charge) et le modèle. Les anciennes variables `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` et `LLM_BASE_URL` ne sont plus lues : supprimez-les de votre `.env` et des variables de Coolify.

**À sauvegarder : le volume `data`.** Il contient la base (comptes, dossiers, corbeille, réglages, clés Anthropic **chiffrées**), les podcasts, les modèles Whisper et `secret.key`, la clé qui chiffre ces clés. Pour la maîtriser vous-même, définissez `SECRET_KEY` (une longue phrase secrète) dans `.env` ou dans les variables de Coolify avant d'enregistrer la première clé, puis ne la changez plus : sinon les clés enregistrées deviennent illisibles et sont à ressaisir.

Au premier traitement, les modèles Whisper sont téléchargés dans `data/models` (≈ 150 Mo pour `base`, ≈ 500 Mo pour `small`).

## Utilisation

1. Menu **Dossiers** : la page se présente comme un explorateur de fichiers. Créez un dossier (ex. **CULTE ROYAL**) et des sous-dossiers ; double-clic pour ouvrir, fil d'Ariane et bouton ↑ pour remonter, vue icônes ou liste, recherche dans le dossier.
   - **Clic droit** sur un élément : ouvrir, renommer, déplacer, intro du dossier, supprimer, télécharger, rogner, relancer…
   - **Glisser-déposer** un dossier ou un podcast sur un dossier (ou sur un segment du fil d'Ariane) pour le déplacer ; « Déplacer vers… » fait la même chose sans souris.
   - Raccourcis : Entrée (ouvrir), F2 (renommer), Suppr (supprimer), Retour arrière (dossier parent).
2. Ajouter vos **intros** (fichiers **MP3**) dans la bibliothèque (menu **Intros**, dans la barre latérale). La première devient l'intro par défaut ; on peut en changer à tout moment. Chaque dossier peut avoir la sienne (un sous-dossier hérite de son parent), et chaque traitement peut en choisir une autre, ou aucune, dans le formulaire.
3. Coller le lien YouTube, le nom et la date, puis **Lancer le traitement** — ou **Ajouter plusieurs liens d'un coup** : on prépare une liste (ajouter, modifier avec début/fin facultatifs, retirer, ou coller plusieurs lignes `lien | nom | date`), puis **Lancer** envoie tout dans la file.
4. Suivre l'avancement en direct, écouter le résultat, télécharger le MP3 ou copier le lien R2.
5. Si la prédication détectée n'est pas la bonne : **Relancer** en saisissant le début et la fin (format `1:05:30`).

## Structure sur R2 = structure de la plateforme

Les fichiers sont rangés sur R2 comme dans l'interface, avec les mêmes noms :

```
podcasts/                          ← R2_PREFIX (vide = racine du bucket)
  CULTE ROYAL/
    Octobre 2026/
      La foi qui déplace les montagnes_2026-10-11.mp3
```

- Renommer ou déplacer un **dossier** ou un **podcast** (menu clic droit, glisser-déposer) déplace aussi les fichiers sur R2, en arrière-plan. Les dossiers vides existent aussi sur R2 (objet vide `chemin/`). Un nom de dossier ne peut pas être utilisé deux fois au même endroit.
- Seuls les caractères interdits ou ambigus (`/ \ : * ? " < > |`) sont remplacés par une espace ; accents et espaces sont conservés.
- **Les anciens liens de partage cessent de fonctionner** quand un fichier change de chemin : à utiliser en connaissance de cause (l'interface le rappelle dans les fenêtres de renommage et de déplacement).
- La pastille **R2** en haut ouvre l'état de la synchronisation. **Resynchroniser** rattrape ce qui aurait échoué, déplace les fichiers déposés à l'ancien format de chemin (versions précédentes) et envoie les podcasts jamais envoyés. Elle est aussi lancée à chaque démarrage.
- Le cache des fichiers est court (5 minutes) puisqu'un fichier peut changer de contenu (rognage) ou de chemin. `R2_ENDPOINT_URL` permet d'utiliser un autre stockage compatible S3.

## Rogner un podcast terminé

Bouton **Rogner** sur un podcast terminé : on écoute, on place le curseur et « Marquer ici » fixe le début ou la fin conservés (ou on saisit `h:mm:ss`). Le rognage **ne réencode pas** (aucune perte de qualité, précision d'environ 26 ms). L'original est gardé : **Restaurer l'original** revient en arrière. Sur R2, le fichier est remplacé au même chemin. Permission `jobs.trim`.

## Connexion, utilisateurs et permissions

- Écran de connexion avec session (cookie `HttpOnly`) ; 5 échecs en 5 minutes bloquent les essais pendant quelques minutes.
- **Utilisateurs** (administrateur) : le compte administrateur système (créé au démarrage) est protégé, on ne peut ni le modifier, ni le désactiver, ni le supprimer ; créer des comptes, les activer/désactiver, réinitialiser un mot de passe et choisir les fonctions autorisées : voir et télécharger, lancer/relancer, supprimer, gérer les dossiers, gérer les intros, régler le parallélisme, utiliser sa propre clé Anthropic, activer/désactiver l'IA pour ses traitements. L'administrateur a tous les droits et seul gère les comptes. Chaque utilisateur peut changer son mot de passe (menu en haut à droite).

## Historique, détails et liens directs

- **🕘 Historique des traitements** (barre latérale) : tous les traitements, tous dossiers confondus, avec recherche et filtre par statut.
- **Détails** (sur chaque traitement) : lecteur, téléchargements, informations (bornes, durées, tailles, dates), étapes et journal complet.
- **Liens directs** : le lien R2 du MP3 se copie ou s'ouvrent depuis les détails. Avec `R2_PUBLIC_BASE_URL` ils sont permanents ; sinon ils sont signés et valables `R2_LINK_EXPIRES` secondes (7 jours), puis regénérés à chaque ouverture des détails. Sans R2, seuls les téléchargements via l'interface (avec identifiants) existent.

## Comment la prédication est repérée

- **Avec l'IA** (clé Anthropic de l'administrateur, ou clé personnelle de l'utilisateur) : une transcription rapide du culte entier est envoyée à l'IA, qui renvoie le début et la fin du message. C'est la méthode la plus fiable. Coût : environ 15 à 20 000 tokens pour un culte de 3 h.
- **Sans IA** : une heuristique retient la plus longue zone de parole dense. La louange chantée a un débit de mots plus faible et les annonces sont courtes. Cela fonctionne bien quand le culte est classique, moins bien avec un long temps de prière parlée.
- **Bornes manuelles** : si vous les saisissez, l'étape de repérage est sautée et le traitement est bien plus rapide.

**IA du serveur (administrateur).** La pastille « IA » en haut de l'interface ouvre le réglage : clé API Anthropic (vérifiée par un petit appel, stockée chiffrée), modèle, et interrupteur « activée ». Sans crédit ou pour ne rien dépenser, décochez-le : la clé reste en place. Désactivée, le repérage passe par l'heuristique et l'adoration, les témoignages et les annonces ne sont pas retirés. **Un traitement garde l'IA choisie à son démarrage jusqu'au bout** ; couper l'IA (le serveur, ou l'utilisateur pour lui seul) ne vaut que pour les traitements qui démarrent ensuite, qui retombent alors sur l'heuristique.

**Consommation de l'IA (compteurs).** Les tokens échangés avec l'IA sont comptés après chaque appel : par traitement (carte « en cours » de l'accueil, détails, journal ; un « Relancer » repart de zéro), et en **compteur global** dans la barre du haut (« ✨ N tokens » ce mois-ci). Un clic ouvre le détail : ce mois-ci et depuis le début pour l'utilisateur ; pour l'administrateur, aussi le détail **par clé** (chaque utilisateur, et l'IA du serveur). Un utilisateur y retrouve aussi ce qui a été facturé sur sa clé pour des traitements qu'un administrateur a lancés avec sa configuration. Le compteur ne chiffre pas le coût.

**IA personnelle (clé Anthropic par utilisateur).** Avec la permission **« Utiliser sa propre clé Anthropic »**, un utilisateur enregistre sa clé via le menu en haut à droite (« Mon IA ») : elle est vérifiée par un petit appel à l'enregistrement, puis stockée **chiffrée** et ne sert qu'à **ses** traitements (appels facturés sur son compte Anthropic, y compris si le serveur n'a aucune IA configurée ou si l'administrateur a coupé celle du serveur). Avec la permission **« Activer ou désactiver l'IA pour ses traitements »**, il peut aussi la couper pour lui seul (pastille « IA » ou « Mon IA ») ; sans elle, l'IA suit le réglage du serveur. Si l'administrateur retire une permission, elle cesse de s'appliquer aussitôt (la clé reste stockée, mais inutilisée). **Choix de l'IA par l'administrateur.** Pour un traitement (formulaire individuel, lot entier, ou « Relancer »), l'administrateur peut choisir le champ **« IA utilisée »** : la configuration (clé Anthropic, interrupteur) d'un utilisateur qui a enregistré sa clé, ou l'IA du serveur ; par défaut, celle de l'auteur du traitement. Les tokens sont consommés sur la clé choisie ; le choix est visible dans les détails et le journal du traitement, et les utilisateurs en sont informés dans « Mon IA ». Les autres utilisateurs ne voient pas ce champ et le serveur le refuse.

Le chiffrement utilise `SECRET_KEY` ou, à défaut, `data/secret.key` : **sauvegardez-le avec `data/`**, sinon les clés enregistrées deviennent illisibles (elles sont alors à ressaisir).

**Traitement par lot.** Une ligne = un traitement : un lien YouTube **ou** un fichier audio / vidéo, avec son propre nom, sa date, son début / fin et son intro (celle de la liste par défaut). Les fichiers ajoutés à un lot sont **envoyés sur le serveur dès leur ajout** (zone d'attente `data/staging`) : ils restent dans la liste après un rechargement de la page, un autre navigateur ou un autre appareil, et sont supprimés s'ils ne sont pas lancés au bout de `STAGING_DAYS` jours (7 par défaut). Retirer une ligne supprime aussi son fichier du serveur.

**Fin du podcast.** Le podcast se termine par un **fondu de sortie** (`FADE_OUT`, 2,5 s ; 0 = coupure nette). Sans IA, la fin repérée est recalée sur la fin de phrase la plus proche (jusqu'à `END_MARGIN`, 25 s, lues au-delà), pour ne plus couper un mot ou une phrase en plein milieu. Avec l'IA, la fin donnée par le modèle inclut la ligne de 30 s citée, et le retrait précis des annonces fait le reste. **Si l'IA ne répond pas** (crédit épuisé, clé refusée…), le journal du traitement l'indique avec le motif de l'API et on retombe sur l'heuristique : la fin est alors moins fiable.

## Adoration, témoignages, annonces

Avec une IA disponible, le traitement est prudent à deux niveaux :
1. **Repérage** : le début est l'instant où le prédicateur commence à enseigner, pas l'adoration, la louange ni les prières qui précèdent ; en cas de doute, l'IA choisit plus tôt.
2. **Retrait précis** : une marge (`OFFTOPIC_PAD_BEFORE` / `OFFTOPIC_PAD_AFTER`, 90 s et 60 s) est ajoutée autour de la prédication, puis l'IA relit la transcription fine et retire, ligne par ligne, l'adoration, les témoignages, les annonces, les offrandes et les autres voix. Elle ne retire jamais une illustration du prédicateur ni sa prière de fin ; en cas de doute, elle garde. Si elle veut retirer plus de la moitié, ou si elle ne répond pas, rien n'est retiré et on revient aux bornes repérées.

Le bilan (passages retirés, avec leurs horaires) est visible dans les détails du traitement (« Montage »). **Vérifiez les premiers podcasts à l'écoute.** Sans IA, ces passages ne sont pas retirés ; saisir les bornes à la main reste possible.

## Nettoyage

| Élément | Méthode | Réglage |
|---|---|---|
| Silences | Détection sur l'énergie du signal : une zone sonore n'est jamais coupée | `MAX_PAUSE`, `TARGET_PAUSE` |
| Bruit, souffle | Filtres ffmpeg (passe-haut, réduction de bruit FFT, compresseur) | `app/pipeline/audio.py` |
| « euh », « hum » | Horodatages mot à mot de Whisper | `REMOVE_FILLERS` |
| Mots et phrases répétés (« la foi, la foi », « Dieu est bon, Dieu est bon ») | Répétitions **immédiates** (pause < `REPEAT_MAX_GAP`, jusqu'à `REPEAT_MAX_WORDS` mots) ; la dernière copie est gardée | `REMOVE_REPEATS` |
| Volume | Normalisation à -16 LUFS (standard podcast) | — |
| Fin | Fondu de sortie ; coupure sur une fin de phrase | `FADE_OUT`, `END_MARGIN` |

Les mots comme « amen » ou « alléluia » répétés seuls sont préservés. Whisper est amorcé (`WHISPER_PROMPT`) pour transcrire aussi les « euh » et répétitions. Pour une voix moins métallique : `DENOISE_DB` (réduction de bruit, 0 = aucune).

## Durées sur CPU (ordre de grandeur, 4 cœurs, à mesurer sur votre serveur)

Le traitement est optimisé pour les cultes de 4 h 30 et plus :
- **repérage** : modèle `tiny`, seulement 15 s transcrites par fenêtre de 30 s (l'IA n'en lit que le début), lots traités en parallèle ;
- **passe mot à mot** : la prédication est découpée en lots de 10 min (coupés dans un creux de parole) transcrits en parallèle, `beam_size=1` ;
- **ffmpeg** : extraction et amélioration de la voix en un seul passage, travail en 24 kHz mono (le MP3 final, en 22 kHz, n'utilise pas plus) ;
- **YouTube** : audio léger (≈ 50-70 kb/s) téléchargé par 4 fragments simultanés ; il est gardé en cache, donc **Relancer** ne retélécharge rien.

Pour aller plus vite : saisir les bornes (le repérage disparaît), `DETECT_CLIP=10`. Pour plus de précision : `WHISPER_MODEL_DETECT=base`, `WHISPER_BEAM_EDIT=5`, `YTDLP_FORMAT=bestaudio/best`.
Plusieurs traitements peuvent tourner en même temps (réglage **Parallèle** en haut de l'interface, 1 à 20, `MAX_PARALLEL_JOBS` au démarrage). Les autres attendent en file, affichés « n° 1, n° 2… », et le suivant démarre dès qu'une place se libère. Ils partagent les mêmes cœurs et les mêmes modèles Whisper : le gain vient surtout du chevauchement des étapes (téléchargement, ffmpeg, envoi) avec la transcription ; au-delà de 2-3, chacun va plus lentement. Chaque traitement garde l'audio de sa prédication en mémoire : surveillez la RAM avant d'augmenter le parallélisme.

**Quota par utilisateur** : chaque compte a un nombre maximal de traitements simultanés (5 par défaut). Seul un administrateur le modifie, dans *Utilisateurs → Modifier*. Au-delà, les traitements de cet utilisateur restent en file sans bloquer ceux des autres ; le réglage global **Parallèle** reste le plafond du serveur.

**Dossiers : propriétaire et attribution.** Chaque dossier garde le compte qui l'a créé. Un utilisateur voit ses propres dossiers et ceux que l'administrateur lui a **attribués** (clic droit sur un dossier → *Attribuer à des utilisateurs…*, sous-dossiers compris). Dans un dossier attribué il lance des traitements, écoute et télécharge, mais il ne peut **ni renommer, ni déplacer, ni supprimer** le dossier ni ce qui a été créé par un autre compte ; il garde la main sur ce qu'il y crée lui-même. Un dossier non attribué lui est invisible (accueil, historique et statistiques compris). Les dossiers et traitements existants avant cette version appartiennent à l'administration : les utilisateurs non administrateurs ne les voient qu'une fois les dossiers attribués.

**Fichier envoyé au lieu d'un lien YouTube.** Dans *Nouveau traitement*, l'onglet *Fichier audio / vidéo* envoie un MP3, M4A, WAV, MP4, MKV… (`MAX_UPLOAD_MB`, 4096 par défaut). Le fichier remplace l'audio téléchargé, le reste du traitement est identique. Il est conservé dans le cache (`KEEP_SOURCES`) : s'il en est retiré, un « Relancer » demande de le renvoyer.

**Renommage pendant un traitement.** Le nom affiché, le nom du fichier, l'étiquette ID3 et le fichier R2 suivent, même si le traitement est en cours.

**Thème.** Bouton clair / sombre dans la barre du haut (par défaut : celui du système, choix mémorisé dans le navigateur).

## Taille des fichiers

MP3 mono à 64 kb/s ≈ **29 Mo par heure** (`MP3_BITRATE`) : une voix naturelle. `48k` (≈ 22 Mo/h) est plus léger, `96k` (≈ 43 Mo/h) très fidèle. Si la voix vous semble métallique, baissez `DENOISE_DB` (réduction de bruit, 0 = aucune) ou montez `MP3_BITRATE`.

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
    detect.py      repérage de la prédication (IA / heuristique)
    edit.py        montage : silences, hésitations, répétitions
    audio.py       ffmpeg : voix, intro, compression
    run.py         enchaînement des étapes
  static/          interface web
data/              base, intros, sorties, modèles (volume Docker)
```

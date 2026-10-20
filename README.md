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

**Dossiers : propriétaire et attribution.** Chaque dossier garde le compte qui l'a créé. Un utilisateur voit ses propres dossiers et ceux que l'administrateur lui a **attribués** (clic droit sur un dossier → *Attribuer à des utilisateurs…*, ou menu **Permissions**, voir ci-dessous). Dans un dossier attribué il lance des traitements, écoute et télécharge, mais il ne peut **ni renommer, ni déplacer, ni supprimer** le dossier ni ce qui a été créé par un autre compte ; il garde la main sur ce qu'il y crée lui-même. Un dossier non attribué lui est invisible (accueil, historique et statistiques compris). Les dossiers et traitements existants avant cette version appartiennent à l'administration : les utilisateurs non administrateurs ne les voient qu'une fois les dossiers attribués.

**Condensation : raccourcir sans changer l'ordre.** Dans *Nouveau traitement* (individuel, lot ou « Relancer »), le champ **Durée du podcast** propose de raccourcir de **10 à 80 %**. Le traitement retire des **phrases entières**, **sans jamais changer l'ordre ni réécrire**. Le début (60 s) et la fin (90 s), les lectures bibliques (l'annonce du texte et les phrases qui suivent) et les « Amen » sont protégés. Les coupes se font aux limites des phrases, avec les fondus habituels. Au-delà de 40 %, il reste surtout les idées essentielles et la parole peut sembler saccadée : validez les coupes.
- **Sans IA, ça fonctionne et l'objectif est atteint.** À chaque pas, l'heuristique retire la phrase qui fait perdre le **moins d'idées par seconde gagnée** : les mots porteurs de sens (pondérés par leur rareté dans le sermon) qu'aucune autre phrase conservée n'exprime. Les reprises d'une idée déjà dite partent donc en premier, avec les formules de remplissage, puis les phrases de moins en moins originales. Le résultat indique la part des **idées conservées** (journal, relecture) ; si seul du texte protégé reste, l'objectif peut ne pas être atteint, et c'est indiqué.
- **Avec une IA**, c'est elle qui choisit en lisant tout le texte et qui indique les idées principales repérées ; elle ne peut pas lever les protections, ne dépasse pas son objectif de plus de 15 %, et l'heuristique la complète si elle coupe moins de 85 % de l'objectif ou ne répond pas.
- **Validation** : *automatique* (les coupes sont appliquées) ou *Me les montrer avant de publier* : le traitement s'arrête après l'analyse (sans occuper de place dans la file) et apparaît **« À valider »** (accueil, pastille « ✋ à valider »). *Relire les coupes* liste chaque phrase proposée avec sa raison ; on peut **l'écouter** (▶, avec 1,5 s de contexte), décocher pour la garder, cocher d'autres phrases à retirer, voir le gain en direct, puis valider ou *Tout garder*. Le traitement reprend aussitôt, sans rien refaire. Les données de l'analyse (audio nettoyé, mots) restent sur le serveur tant qu'il n'est pas validé : supprimez un traitement abandonné pour les libérer.
- Le bilan (nombre de phrases, durée retirée, méthode, idées conservées) est dans les détails et le journal. La future version anglaise partira du texte retenu : moins de texte, donc moins de synthèse vocale.

**Version anglaise (traduction + voix du prédicateur).** Pour un podcast terminé, l'application peut produire `Nom_date_EN.mp3` : le texte est traduit en anglais, puis lu **avec la voix du prédicateur** par un modèle libre, sur le CPU du serveur. Permission : **« Générer la version anglaise »**. On la demande dans *Nouveau traitement* (champ « Version anglaise », aussi pour un lot et dans « Relancer »), ou depuis les **détails d'un podcast terminé** (« Générer la version anglaise… », avec choix du traducteur, du moteur de voix et de la voix de référence).
- **Aucune dépendance à Claude.** La traduction est faite par un **modèle libre local** (Marian opus-mt fr→en, licence CC-BY 4.0), sans clé ni IA externe. **Notre IA configurée n'est qu'une option** (Claude, meilleur sur le ton oral ; c'est l'IA du serveur ou la clé personnelle de l'utilisateur) : s'il n'est pas disponible, ne répond pas ou oublie des phrases, le modèle local prend le relais. Le choix se fait par **réglage par défaut** de l'administrateur (*Voix anglaise → Réglages*, le modèle local d'origine), **à la création** du traitement (champ « Traduction de la version anglaise », aussi pour un lot et dans « Relancer ») ou **à chaque demande** depuis les détails d'un podcast ; l'IA n'est proposée que si elle est disponible pour l'utilisateur. Sa consommation, quand elle sert, entre dans les compteurs de tokens.
- **Le texte traduit est celui du podcast final** : coupes de condensation, témoignages, « euh » et redites déjà retirés. Un podcast produit avant cette fonction est retranscrit par Whisper.
- **Validation du texte (recommandée).** La voix dira exactement le texte : avec « je valide le texte anglais », le calcul s'arrête après la traduction, le podcast apparaît « à valider » et *Relire l'anglais* montre chaque phrase en français à côté de sa traduction, modifiable (un texte effacé retire la phrase). En mode automatique, la voix est générée sans relecture.
- **Voix de référence** : 12 secondes, choisies automatiquement dans le podcast (le passage où le prédicateur parle le plus régulièrement, hors intro), ou imposées à la demande. Le **moteur de voix** (Chatterbox Nano, Turbo ou complet) et le traducteur par défaut se règlent dans *Voix anglaise → Réglages* (administrateur).
- **Reprenable** : chaque morceau de voix terminé est conservé ; un arrêt ou un redémarrage du serveur ne fait pas tout recommencer. Une version anglaise **remplace** la précédente quand on la redemande ; relancer le podcast français n'y touche pas.
- **Publication** : MP3 normalisé (-16 LUFS, sans intro, fondu de sortie), lecteur, téléchargement et lien R2 dans les détails, rangé sur R2 à côté du français (`…_EN.mp3`, déplacé avec lui). Un utilisateur **ne supprime pas** une version anglaise : seul un administrateur la supprime définitivement (elle part aussi quand son podcast est supprimé définitivement).
- **Le calcul se fait dans le service `voicelab`**, démarré avec l'application mais dans une image à part (PyTorch et les modèles pèsent plusieurs Go : la première construction est longue). S'il échoue ou n'a pas fini de démarrer, l'application continue de fonctionner : l'écran *Voix anglaise* affiche « jamais démarré » ou « arrêté » (avec le dernier signe de vie), et les demandes restent « en attente ». Dans ce cas, regardez le journal de construction puis d'exécution du service `voicelab` (Coolify : *Logs*). Le premier calcul télécharge les modèles dans le volume `data`. Pour ne pas l'installer du tout, retirez le service `voicelab` de `docker-compose.yaml`.
- **Durée** : sur CPU, plusieurs heures par sermon sont possibles ; la vitesse dépend de votre serveur et du moteur. Le **banc d'essai** (*Voix anglaise → Banc d'essai*) la mesure sur un extrait de l'un de vos podcasts (2, 3 ou 5 min), avec le **temps estimé pour 1 h de sermon** (vert : moins d'1 h ; orange : jusqu'à 3 h ; rouge : au-delà), un lecteur par moteur à côté de la voix de référence, et le choix du traducteur : **écoutez** pour juger ressemblance, naturel et accent. Rien n'est publié par le banc d'essai.
- Les calculs se font **l'un après l'autre**, les versions anglaises avant les essais. Lancez-les quand aucun traitement ne tourne : ils partagent les cœurs du serveur. Équivalent en ligne de commande (sans le service) : `tools/bench_voice.md`.

**Détails d'un traitement et mini-lecteur.** La fenêtre de détails est en onglets (*Podcast*, *Version anglaise*, *Informations*, et *Étapes et journal* pour l'administrateur) ; le bouton de téléchargement est sur la même ligne que le lecteur. Un son **en cours** ne s'arrête pas quand on ferme la fenêtre ou qu'on change de page : un **mini-lecteur** (pause, position, ouvrir les détails, fermer) apparaît en haut à droite de la page, dans son conteneur et non dans l'en-tête. Il s'efface si un autre son démarre, et n'existe pas dans l'éditeur de rognage, qui a son propre lecteur.

**Écran Permissions (administrateur).** Deux onglets par utilisateur : **Actions autorisées** (les droits) et **Dossiers**. L'onglet Dossiers montre l'arborescence, comme le Finder : cocher un dossier donne accès à **tout ce qu'il contient** (ses sous-dossiers apparaissent « inclus », verrouillés) ; pour ne donner qu'une partie, dépliez et cochez **seulement** les sous-dossiers voulus, sans le parent (qui apparaît alors « partiel »). Un sous-dossier attribué seul s'affiche à la racine chez l'utilisateur. Ses propres dossiers sont toujours inclus. Les changements ne s'appliquent qu'au clic sur *Enregistrer* ; l'attribution d'un dossier déjà couvert par un parent est écartée. Limite : on ne peut pas donner un dossier **sans** son contenu, ni retirer un sous-dossier à l'intérieur d'un dossier attribué (décochez le parent, puis cochez les autres).

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

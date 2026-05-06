# components/help_locales/fr.py
"""
Dwarfium Scope Archive — French help content.

Each key is a route string. Each value has 'title' and 'content' (Markdown).
Routes not present here fall back to English at runtime.

Placeholders like {t:add_dwarf} are resolved at display time
using the active language's translation strings — no duplication needed.
"""

HELP: dict[str, dict[str, str]] = {

    '/': {
        'title': 'Accueil — Dwarfium Scope Archive',
        'content': '''
## Bienvenue

Dwarfium Scope Archive vous aide à sauvegarder, organiser et explorer vos sessions avec votre télescope Dwarf.

## Fonctionnalités principales

- **{t:dwarf_label}** — configurer vos appareils Dwarf (chemin USB, adresse IP, type)
- **Sauvegarde** — configurer vos disques de sauvegarde et scanner les nouvelles sessions
- **{t:page_explore}** — parcourir et rechercher toutes les sessions sauvegardées
- **{t:menu_manual_sessions}** — importer des fichiers FITS/PNG/JPG personnalisés depuis n'importe quel outil
- **{t:page_darks}** — gérer les images de calibration (darks) pour le traitement Siril
- **{t:transfer}** — copier des sessions entre le Dwarf et un disque de sauvegarde

## Workflow typique

1. Configurer votre Dwarf sur la page **{t:dwarf_label}**
2. Utiliser **Analyser le lecteur Dwarf** pour indexer les sessions sur votre Dwarf
3. Configurer votre disque de sauvegarde sur la page **Sauvegarde**
4. Utiliser **Analyser le disque actuel** sur la page Sauvegarde pour indexer les sessions
5. Utiliser la page **{t:transfer}** pour copier les sessions du Dwarf vers votre sauvegarde
6. Parcourir tout sur la page **{t:page_explore}**
7. La page **{t:page_explore}** permet aussi de sauvegarder directement une session sélectionnée
''',
    },

    '/Dwarf': {
        'title': 'Configuration Dwarf',
        'content': '''
## Objectif

Configurez les télescopes Dwarf que vous possédez. Chaque entrée Dwarf stocke son chemin USB,
son adresse IP (pour le transfert FTP/WiFi) et son type (Dwarf2, Dwarf3, Dwarf Mini).

## Ajouter un nouveau Dwarf

1. Cliquez sur **{t:add_dwarf}**
2. Entrez un nom (ex. `Dwarf Mini New`)
3. Définissez le **{t:astronomy_dir}** — le chemin complet vers le dossier `Astronomy`
   sur le disque du Dwarf connecté en USB (ex. `I:\\Astronomy`)
4. Si vous utilisez le Dwarf 2, la connexion USB directe n'est pas disponible.
   Utilisez l'une des méthodes suivantes :
   1. Connexion FTP : configurez le Dwarf en mode STA avec l'application mobile DwarfLab
      1. Trouvez l'adresse IP du Dwarf et entrez-la sur cette page
      2. Vous pourrez alors utiliser toutes les fonctions disponibles sur cette page.
   2. Mode MTP, spécifique à Windows
      Vous pouvez quand même enregistrer votre Dwarf dans les paramètres
      1. Connectez le Dwarf 2 en USB
      2. Allumez le Dwarf 2 et connectez-vous à lui avec l'application mobile Dwarflab
      3. Dans l'application, allez dans **Advanced Settings** pour activer le MTP
      4. Sur cette page, cliquez sur **Scan for MTP Devices**
      5. Vous pouvez alors enregistrer votre Dwarf, mais la fonction de scan ne sera pas disponible
      6. Pour transférer une session, vous devez utiliser la page MTP
5. Définissez l'**{t:ip_sta_mode}** si vous souhaitez un transfert WiFi/FTP
6. Cliquez sur **{t:save_update_dwarf}**

## Analyser le lecteur Dwarf

Scanne le répertoire USB du Dwarf et indexe toutes les sessions dans la base de données.
À exécuter après avoir connecté le Dwarf en USB.

## Afficher les données Dwarf

Ouvre la page **{t:page_explore}**r pour visualiser les données stockées sur votre Dwarf.
Vous pouvez ensuite les importer dans votre sauvegarde.
Activez **{t:only_backed_not_dwarf}**
pour afficher les sessions en attente et le bouton Sauvegarder.
À exécuter après : **Analyser le lecteur Dwarf**.

## Sessions avec erreurs

Ouvre les sessions sans fichier stacké final.

**Raisons possibles :**

    1. Aucune image enregistrée → Normal (session arrêtée prématurément)
    2. Session mosaïque → Les images existent mais pas de stack final
       → Réparez-la depuis la page Mosaïque

## Conseils

- Le chemin USB doit être accessible lorsque vous cliquez sur **Analyser le lecteur Dwarf**
- Le FTP nécessite que le Dwarf soit sur le même réseau WiFi que votre ordinateur
- Vous pouvez avoir plusieurs Dwarfs — chacun a sa propre entrée

## Supprimer les entrées Dwarf

Supprime toutes les données de sessions indexées pour ce Dwarf de la base de données.
Les fichiers sur le disque **ne sont pas** supprimés.
''',
    },

    '/Backup': {
        'title': 'Configuration du disque de sauvegarde',
        'content': '''
## Objectif

Configurez les disques de sauvegarde où vos sessions Dwarf sont stockées.
Chaque disque de sauvegarde est lié à un Dwarf.

## Ajouter un nouveau disque de sauvegarde

1. Cliquez sur **{t:add_backup_drive}**
2. Entrez un nom (ex. `DWARF_MINI_NEW`)
3. Cliquez sur **{t:select_folder}** pour choisir le dossier racine du disque de sauvegarde
4. Définissez optionnellement un sous-répertoire **{t:astronomy_dir}**
5. Sélectionnez le **{t:dwarf_label}** auquel ce disque appartient
6. Cliquez sur **{t:save_update_drive}**

## Analyser le disque actuel

Scanne le disque de sauvegarde et indexe toutes les sessions dans la base de données.
À exécuter après avoir copié de nouvelles sessions depuis le Dwarf.

Affiche l'historique des transferts de sessions avec la date, la session et le statut.

## Vérifier l'intégrité des sessions

Compare le nombre de fichiers FITS présents à ceux enregistrés dans la session.
Les comptages peuvent différer si des images rejetées ont été supprimées sur le Dwarf.

## Afficher toutes les données de sauvegarde

Ouvre la page **{t:page_explore}**r pour visualiser les données stockées sur votre disque.
Vous pouvez ensuite les restaurer sur votre Dwarf.
Activez **{t:only_backed_not_dwarf}**
pour lister les sessions supprimées et afficher le bouton Restaurer.

## Supprimer les entrées de sauvegarde

Supprime toutes les données de sessions indexées pour ce disque de la base de données.
Les fichiers sur le disque **ne sont pas** supprimés. Après suppression, exécutez
**Analyser le disque actuel** pour re-indexer.

## Supprimer les entrées manuelles

Supprime les liens ManualSessionEntry pour ce disque.
Les métadonnées ManualSession sont conservées pour que les sessions puissent être
re-liées automatiquement depuis les fichiers `shotsInfo.json` lors d'une nouvelle analyse.

## Conseils

- Vous pouvez avoir plusieurs disques de sauvegarde par Dwarf
- Le disque de sauvegarde n'a pas besoin d'être connecté pour sauvegarder sa configuration
''',
    },

    '/Explore/': {
        'title': 'Explorer les sessions',
        'content': '''
## Objectif

Parcourez et recherchez toutes les sessions indexées depuis vos disques de sauvegarde.
Pour voir les sessions actuellement stockées sur votre Dwarf, allez sur la page **{t:page_dwarf}**
et cliquez sur le bouton « Show Dwarf Data ».

## Filtres

- **{t:backup_drive}** — filtrer par disque de sauvegarde (ou afficher tout)
- **{t:dwarf_label}** — filtrer par appareil Dwarf
- **{t:filter_objects}** — rechercher par nom de cible
- **Qualité** — filtrer les sessions par score de qualité d'image :
  - 🌐 Toutes les sessions (défaut)
  - 🟢 Bonnes (score ≥ 65)
  - 🟡 Moyennes (score ≥ 40)
  - Les sessions non évaluées sont toujours visibles quel que soit le filtre
- **🔭 Objet proche** — trouver les sessions dans un rayon autour d'un DSO ou de coordonnées personnalisées

## Détail d'une session

Cliquez sur une cible dans le panneau gauche, puis sélectionnez une session dans le
menu déroulant **Liste des sessions** pour voir :

- Cible, RA/Dec, classification
- Exposition, gain, filtre, température
- Images stackées et temps de pose total avec **score de qualité** (⭐⭐⭐⭐ 78.2)
- **🎯 Dark match** — combien de darks de calibration sont disponibles pour cette session

## Score de qualité d'image

Chaque session peut être évaluée sur une échelle de 0 à 100 en deux passes :

- **Passe A (métadonnées)** — taux de stack, temps de pose total, calibration darks, type de capteur (Dwarf 3 / Mini obtiennent un bonus)
- **Passe B (analyse image)** — plage dynamique, contraste et entropie du JPEG stacké

Seuils de score :
- ⭐⭐⭐⭐⭐ Excellent (≥ 80)
- ⭐⭐⭐⭐ Bon (≥ 65)
- ⭐⭐⭐ Moyen (≥ 50)
- ⭐⭐ Passable (≥ 35)
- ⭐ Faible (< 35)

Les sessions sont évaluées automatiquement après chaque scan de sauvegarde.
Vous pouvez aussi évaluer manuellement avec le bouton **🌟 Evaluer** dans la barre d'actions
(Evalue toutes les sessions de l'objet courant) ou le bouton **Évaluer la qualité** dans
le panneau de détail (évalue uniquement la session sélectionnée).

## Actions

- **{t:open_folder_btn}** — ouvrir le dossier de session dans l'Explorateur Windows
- **{t:show_fullscreen_btn}** — afficher l'image stackée en plein écran
- **🌟 Évaluer** — scorer toutes les sessions de l'objet sélectionné
- **Backup/Restore** — effectuer des actions sur la session sélectionnée
- **Availability** — dépend des cases cochées. Voir les conseils pour plus de détails.
- **{t:delete_session}** — supprime définitivement toutes les données de session du disque de sauvegarde.
- **{t:delete_session}** — disponible uniquement si une sauvegarde existe.
    Accessible via le bouton **« Show Dwarf Data »** sur la page Paramètres Dwarf.
- **{t:view_linked_manual}** — accéder à toute session manuelle liée à cette entrée
- **Add/Remove Favorite** — basculer le titre de la session pour l'afficher ou le masquer sur la page d'accueil
- **{t:show_details}** — afficher/masquer les statistiques de fichiers et infos de répertoire

## Conseils

- Utilisez les cases **supprimées du Dwarf** / **non encore sauvegardées** pour trouver les sessions qui existent à un seul endroit
- Le badge 🎯 indique l'état de correspondance des darks — vert = température dans la plage, orange = plus proche, rouge = aucune
- Les sessions sans score apparaissent toujours quel que soit le filtre qualité
- Lancez un scan complet depuis la ligne de commande : `python tools/quality_scan.py --report`
''',
    },

    '/ManualExplore/': {
        'title': 'Explorer les sessions manuelles',
        'content': '''
## Objectif

Parcourez les sessions importées manuellement — images stackées depuis Stellar Studio,
Siril, GraXpert ou tout autre outil de traitement.

## Filtres

- **{t:backup_drive}** — filtrer par disque
- **{t:dwarf_label}** — filtrer par appareil Dwarf
- **{t:session_list}** — sélectionner une session spécifique à afficher

## Détail d'une session

La sélection d'une session affiche :

- Cible, RA/Dec, classification
- Date, type de session, exposition, filtre, température
- Nombre de fichiers FITS dans le dossier de session
- Aperçu de l'image stackée

## Actions

- **{t:open_folder_btn}** — ouvrir le dossier de session dans l'Explorateur
- **{t:show_fullscreen_btn}** — afficher l'image stackée en plein écran
- **{t:view_linked_dwarf}** — accéder à la session brute originale dans Explorer
- **Add Favorite / Remove Favorite** — marquer pour le traitement
- **{t:edit_session}** — mettre à jour les métadonnées ou ajouter des fichiers
- **{t:delete_session_btn}** — supprimer les fichiers et l'entrée de la base de données

## Conseils

- Les sessions sont regroupées par objet cible dans le panneau gauche
- Le groupe **manual** contient les sessions sans cible DSO reconnue
- Utilisez **{t:edit_session}** pour ajouter des variantes Starless ou Denoise après traitement
''',
    },

    '/AddManualSession/': {
        'title': 'Importer une session manuelle',
        'content': '''
## Objectif

Importez des images stackées produites en dehors du Dwarf — depuis Stellar Studio,
Siril, GraXpert ou tout autre outil — dans l'archive.

## Workflow

### 1. Sélectionner la destination

Choisissez un **{t:backup_drive}** et définissez le **{t:destination_dir2}** où le
dossier de session sera créé.

### 2. Nommer la session

Entrez un **{t:session_name_label}** (ex. `Cave_Nebula_Duo-Band_20260409`).
Ajoutez optionnellement un **{t:tag}** (ex. `Siril`) pour distinguer les variantes.

### 3. Uploader les fichiers

- **JPG** — image de prévisualisation → sauvegardée en `stacked.jpg`
- **PNG** — PNG stacké → sauvegardé en `stacked-16_{session}.png` (premier fichier)
- **FITS** — FITS stacké → premier fichier sauvegardé en `stacked-16_{session}.fits`,
  les fichiers supplémentaires conservent leur nom d'origine

### 4. URL Stellar Studio

Collez une URL vers un fichier FITS hébergé en ligne. Choisissez un suffixe **{t:sky_search_type}** :
- **Auto** → `stacked-16_{session}__Auto.fits`
- **Denoise** → `stacked-16_{session}__Denoise.fits`
- **Starless** → `stacked-16_{session}__Starless.fits`

### 5. Importer

Cliquez sur **{t:import_files}** pour copier tous les fichiers dans le dossier de destination
et enregistrer la session dans la base de données.

Après une importation réussie, cliquez sur **{t:view_session}** pour accéder
directement à la session dans Explorer Manuel.

## Conseils

- Le premier fichier FITS fournit les métadonnées de session (RA, Dec, exposition, filtre)
- Les fichiers FITS supplémentaires avec des noms significatifs (ex. `Cave_Nebula_Starless.fits`)
  conservent leurs noms originaux — pas besoin de les renommer
- Vous pouvez modifier une session existante pour ajouter des fichiers ultérieurement
''',
    },

    '/DarkLibrary': {
        'title': 'Bibliothèque de darks',
        'content': '''
## Objectif

Gérez les bibliothèques de darks de calibration pour le traitement Siril.
Chaque bibliothèque pointe vers un dossier `CALI_FRAME` sur un disque de sauvegarde.

## Convention de nommage des darks

Les fichiers darks doivent suivre ce format pour que la correspondance fonctionne :
```
dark_exp_15.0_gain_80_bin_1_14C.fits
```
Où : `exp` = temps de pose en secondes, `gain` = valeur du gain,
`bin` = binning (1 ou 2), température en °C.

## Ajouter une bibliothèque

1. Cliquez sur **{t:add_library}**
2. Sélectionnez le **{t:dwarf_label}** et le **{t:backup_drive}**
3. Cliquez sur **{t:select_folder}** pour choisir le dossier `CALI_FRAME`
   (la boîte de dialogue s'ouvre à la racine du disque de sauvegarde — naviguez un niveau en dessous)
4. Cliquez sur **{t:save_update_library}**

## Scanner la bibliothèque

Lit le répertoire `CALI_FRAME/dark/` et affiche un inventaire regroupé
par caméra (cam_0 = Télé, cam_1 = Grand angle) et par exposition/gain/binning.

## Télécharger les darks

Ouvre la page **{t:transfer}** avec :
- La source pré-définie sur le dossier `CALI_FRAME` du Dwarf
- La destination commençant à la racine du disque de sauvegarde

Naviguez vers votre dossier `CALI_FRAME` de destination et démarrez le transfert.
La structure de répertoires `CALI_FRAME` (`dark/`, `bias/`, `flat/`) est
créée automatiquement.

## Conseils

- Les bibliothèques de darks sont associées dans Explorer en utilisant l'exposition, le gain, le binning et
  la température — le badge 🎯 indique combien de darks correspondent à chaque session
- Une bibliothèque par disque de sauvegarde est typique, mais vous pouvez en avoir plusieurs
- Le Dwarf2 n'a pas de capteur de température — la correspondance par température sera
  ajoutée dans une future version
''',
    },

    '/Transfer': {
        'title': 'Transfert',
        'content': '''
## Objectif

Copiez des sessions entre le Dwarf et un disque de sauvegarde.

## Modes

- **{t:archive_mode}** — copier du Dwarf → Disque de sauvegarde (sauvegarde normale)
- **{t:restore_mode}** — copier du Disque de sauvegarde → Dwarf (remettre des sessions)

## Modes de transfert

- **USB** — Dwarf connecté par câble USB (le plus rapide)
- **FTP** — Dwarf connecté par WiFi (plus lent, le Dwarf doit être sur le même réseau)

## Workflow

1. Sélectionnez le **{t:dwarf_label}** et le **{t:backup_drive}**
2. Choisissez **USB** ou **FTP** dans le sélecteur de mode de transfert
3. Définissez le **{t:source_directory}** (ou utilisez Select Source)
4. Définissez le **{t:destination_dir2}** (ou utilisez Select Destination)
5. Cliquez sur **{t:start_backup}** / **{t:start_restore}**

## Conseils

- Après un transfert, la page Sauvegarde re-analysera automatiquement le disque
  pour indexer les nouvelles sessions
- Vous pouvez transférer une seule session en sélectionnant son dossier comme source
- Transfert multi-sessions : le menu déroulant source affiche toutes les sessions —
  sélectionnez-en plusieurs en les parcourant
- **Mode téléchargement darks** (depuis la page Bibliothèque de darks) : la source est pré-définie sur
  `CALI_FRAME` et la destination commence à la racine du disque de sauvegarde
''',
    },

    '/Settings': {
        'title': 'Paramètres',
        'content': '''
## Objectif

Configurez les paramètres globaux de l'application.

## Options

- **Thème** — basculer entre le mode clair et le mode sombre
- **Chemins de stockage** — configurer où les données de session locales sont mises en cache
- **Clés API** — définir la clé astrometry.net pour la résolution automatique des cibles

## Conseils

- Le mode sombre et le mode clair peuvent aussi être basculés rapidement depuis le menu
- Les paramètres sont sauvegardés par utilisateur dans le stockage du navigateur
''',
    },

    '/Mosaic': {
        'title': 'Mosaïque',
        'content': '''
## Objectif

Gérez et traitez les sessions mosaïque capturées avec le télescope Dwarf.
Les mosaïques sont des images multi-panneaux où le Dwarf capture plusieurs champs
adjacents qui sont assemblés en une seule image grand champ.

## Workflow

1. Sélectionnez un **{t:dwarf_label}** et un **{t:backup_drive}**
2. Parcourez la liste des sessions mosaïque détectées sur le disque
3. Sélectionnez les panneaux à inclure dans l'assemblage
4. Cliquez sur **Generate Panorama** pour assembler les panneaux

## Actions

- **Show Panel** — prévisualiser un panneau mosaïque individuel
- **Generate Panorama** — assembler les panneaux sélectionnés en image grand champ
- **{t:repair_transfer}** — corriger une mosaïque partiellement transférée
- **{t:merge_transfer}** — fusionner des panneaux de plusieurs sessions

## Conseils

- Les sessions mosaïque sont stockées dans les dossiers `RESTACKED_DWARF_RAW_*_MOSAIC_*`
- L'assemblage utilise les coordonnées WCS des en-têtes FITS pour l'alignement
- Les grandes mosaïques avec de nombreux panneaux peuvent prendre plusieurs minutes à traiter
''',
    },

    '/MtpDevice': {
        'title': 'Appareil MTP',
        'content': '''
## Objectif

Connectez-vous à un télescope Dwarf 2 via MTP (Media Transfer Protocol).

## Workflow

1. Connectez le Dwarf 2 en USB
2. Allumez le Dwarf 2 et connectez-vous à lui avec l'application mobile Dwarflab
3. Dans l'application, allez dans **Advanced Settings** pour activer le MTP
4. Sur cette page, cliquez sur **Scan for MTP Devices**
5. Sélectionnez le Dwarf détecté dans la liste
6. Utilisez **{t:open_folder}** pour naviguer dans le système de fichiers de l'appareil
7. Sélectionnez les sessions à transférer

## Conseils

- Le MTP est plus lent que l'accès direct au lecteur USB
- Si le Dwarf apparaît comme un lecteur USB normal, utilisez plutôt la page **{t:transfer}**
- Windows peut nécessiter que l'appareil soit en mode « File Transfer »
  dans les paramètres de connexion USB du Dwarf
''',
    },

    '/Catalog': {
        'title': 'Catalogue',
        'content': '''
## Objectif

Parcourez le catalogue intégré d'objets astronomiques utilisé pour l'identification
automatique des cibles et la classification des sessions.

## Fonctionnalités

- Rechercher par nom d'objet, type ou constellation
- Voir les coordonnées RA/Dec, la taille et la magnitude
- Voir quelles sessions de votre archive correspondent à chaque objet

## Types d'objets

- **Galaxy** — galaxies extérieures (M31, NGC 891...)
- **Nebula** — nébuleuses en émission, réflexion, planétaires
- **Cluster** — amas ouverts et globulaires
- **HII Region** — régions d'hydrogène ionisé

## Conseils

- Le catalogue est utilisé automatiquement lorsque vous analysez un disque de sauvegarde —
  les cibles de session sont associées et classifiées
- Utilisez **{t:identify_target_btn}** sur toute session non résolue dans Explorer pour
  la lier manuellement à un objet du catalogue
- Le catalogue est basé sur les bases de données DSO standard (NGC, IC, Messier)
''',
    },

}

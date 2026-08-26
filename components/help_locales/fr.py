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
- **{t:menu_backup}** — configurer vos disques de sauvegarde et scanner les nouvelles sessions
- **{t:page_explore}** — parcourir et rechercher toutes les sessions sauvegardées
- **{t:menu_manual_sessions}** — importer des fichiers FITS/PNG/JPG depuis n'importe quel outil
- **{t:page_darks}** — gérer les images de calibration (darks) pour le traitement Siril
- **{t:transfer}** — copier des sessions entre le Dwarf et un disque de sauvegarde
- **{t:menu_report}** — visualiser la taille des sessions et l'espace disque par lecteur

## Diaporama de la page d'accueil

La page d'accueil affiche un diaporama de vos sessions favorites.
La première image s'affiche immédiatement ; les autres favoris se chargent en arrière-plan.
Utilisez ⭐ pour retirer une session de vos favoris.

## Workflow typique

1. Configurer votre Dwarf sur la page **{t:dwarf_label}**
2. Utiliser **{t:analyze_dwarf_drive}** pour indexer les sessions sur votre Dwarf
3. Configurer votre disque de sauvegarde sur la page **{t:menu_backup}**
4. Utiliser **{t:analyze_drive}** pour indexer les sessions du disque de sauvegarde
5. Utiliser la page **{t:transfer}** pour copier les sessions du Dwarf vers la sauvegarde
6. Parcourir tout sur la page **{t:page_explore}**
7. Utiliser **{t:menu_report}** pour identifier les sessions volumineuses et libérer de l'espace
''',
    },
    '/RecommendTonight': {
        'title': 'Que shooter ce soir',
        'content': '''
## Objectif

Cette page propose des cibles de ciel profond à shooter ce soir, en fonction de votre
lieu d'observation, de la date choisie et de votre historique de sessions.

## Sélection du lieu et de la date

- **{t:tonight_location}** — choisissez parmi vos lieux d'observation enregistrés
- **{t:tonight_date}** — date de la nuit à analyser (icône calendrier)
- **{t:tonight_refresh}** — relance le calcul pour le lieu/date sélectionnés

## Catégories

- ✨ **{t:tonight_new_targets}** — objets jamais capturés jusqu'ici
- 🔧 **{t:tonight_incomplete_targets}** — objets avec quelques sessions mais un temps
  d'intégration cumulé insuffisant (ou, pour les mosaïques, au moins un panel encore
  sous-exposé)
- ✅ **{t:tonight_well_covered_targets}** — objets déjà bien couverts, masqués par défaut

## Filtres

- **{t:tonight_max_magnitude}** — masque les objets trop faibles pour votre équipement
- **{t:tonight_type}** — restreint la liste aux nébuleuses, galaxies ou amas
- **{t:tonight_hide_covered}** — garde la liste centrée sur les cibles qui ont encore besoin de temps

## Classement des cibles

Les cibles sont notées selon la durée et la hauteur au-dessus de l'horizon ce soir,
avec un bonus pour les cibles nouvelles ou incomplètes. Une pénalité s'applique si la
cible est proche d'une lune bien éclairée — plus forte pour les nébuleuses faibles,
plus sensibles à la pollution lumineuse que les galaxies ou amas.

## Cibles combinables

Quand deux objets du catalogue sont assez proches dans le ciel pour tenir dans une
seule prise wide-field, une note apparaît sur celui avec le meilleur score.

## Lien Aladin

Le bouton 🔭 sur chaque carte ouvre la cible dans Aladin Lite (navigateur externe)
pour visualiser le champ avant d'observer.

## Rattachement des sessions

Votre historique d'intégration est rattaché aux objets du catalogue via, dans l'ordre :
un lien manuel existant, une correspondance de nom, ou l'objet du catalogue le plus
proche par coordonnées. Les sessions qui ne correspondent à rien (trop loin de tout
objet du catalogue, ou sans coordonnées) ne sont pas comptées ici.

## Conseils

- Le premier calcul après un changement de lieu/date peut prendre quelques secondes
  (calcul astronomique pour chaque objet du catalogue)
- Le catalogue de référence peut être enrichi si des cibles récurrentes n'y figurent pas encore
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
À exécuter après : **{t:analyze_dwarf_drive}**.

## Sessions avec erreurs

Ouvre les sessions sans fichier stacké final.

**Raisons possibles :**

    1. Aucune image enregistrée → Normal (session arrêtée prématurément)
    2. Session mosaïque → Les images existent mais pas de stack final
       → Réparez-la depuis la page Mosaïque

## Conseils

- Le chemin USB doit être accessible lorsque vous cliquez sur **{t:analyze_dwarf_drive}**
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
3. Cliquez sur **{t:select_folder}** pour choisir le dossier racine du disque
4. Définissez optionnellement un sous-répertoire **{t:astronomy_dir}**
5. Sélectionnez le **{t:dwarf_label}** auquel ce disque appartient
6. Cliquez sur **{t:save_update_drive}**

## Espace disque

Quand un disque de sauvegarde est sélectionné, un indicateur affiche l'espace libre / total
avec une barre colorée (vert → jaune → orange → rouge selon le remplissage).
Les dernières valeurs sont mises en cache dans `db/diskinfo.json` et s'affichent
même si le disque est déconnecté.

## Analyser le disque actuel

Scanne le disque de sauvegarde et indexe toutes les sessions dans la base de données.
À exécuter après avoir copié de nouvelles sessions depuis le Dwarf.
Une barre de progression indique le dossier en cours et l'avancement global.

## Historique des transferts

Affiche l'historique des transferts de sessions avec la date, la session et le statut.

## Vérifier l'intégrité des sessions

Compare le nombre de fichiers FITS présents à ceux enregistrés dans la session.

## Afficher toutes les données de sauvegarde

Ouvre la page **{t:page_explore}** pour visualiser les données stockées sur votre disque.
Activez **{t:only_backed_not_dwarf}** pour lister les sessions supprimées et afficher le bouton Restaurer.

## Supprimer les entrées de sauvegarde

Supprime toutes les données de sessions indexées pour ce disque de la base de données.
Les fichiers sur le disque **ne sont pas** supprimés. Après suppression, exécutez
**{t:analyze_drive}** pour re-indexer.

## Conseils

- Vous pouvez avoir plusieurs disques de sauvegarde par Dwarf
- Le disque de sauvegarde n'a pas besoin d'être connecté pour sauvegarder sa configuration
- Utilisez **{t:menu_report}** pour voir la taille des sessions et identifier les plus volumineuses
''',
    },

    '/Explore/': {
        'title': 'Explorer les sessions',
        'content': '''
## Objectif

Parcourez et recherchez toutes les sessions indexées depuis vos disques de sauvegarde.
Pour voir les sessions actuellement stockées sur votre Dwarf, allez sur la page **{t:page_dwarf}**
et cliquez sur le bouton **{t:show_dwarf_data}**.

## Filtres

- **{t:backup_drive}** — filtrer par disque de sauvegarde (ou afficher tout). Un indicateur d'espace
  disque s'affiche pour le disque sélectionné, avec les valeurs mises en cache si le disque est déconnecté.
- **{t:dwarf_label}** — filtrer par appareil Dwarf
- **{t:filter_objects}** — rechercher par nom de cible
- **{t:quality_filter_label}** — filtrer les sessions par score de qualité d'image
- **{t:sky_search_title}** — trouver les sessions dans un rayon autour d'un DSO

## Galerie

Quand plusieurs sessions existent pour un objet, un bouton **{t:show_gallery}** apparaît.
La galerie s'ouvre immédiatement avec la première image et charge les autres en arrière-plan.
Utilisez Précédent / Suivant pour parcourir, ou Sélectionner pour accéder directement à une session.

## Détail d'une session

Cliquez sur une cible dans le panneau gauche, puis sélectionnez une session dans le
menu déroulant **{t:session_list}** pour voir :

- Cible, RA/Dec, classification
- Exposition, gain, filtre, température
- Images stackées et temps de pose total avec **score de qualité** (⭐⭐⭐⭐ 78.2)
- **🎯 Dark match** — combien de darks de calibration sont disponibles

## Score de qualité d'image

Chaque session est évaluée sur une échelle de 0 à 100 en deux passes :

- **Passe A (métadonnées)** — taux de stack, temps de pose total, calibration darks, type de capteur
- **Passe B (analyse image)** — plage dynamique, contraste et entropie du JPEG stacké

Seuils : ⭐⭐⭐⭐⭐ Excellent (≥ 80) · ⭐⭐⭐⭐ Bon (≥ 65) · ⭐⭐⭐ Moyen (≥ 50) · ⭐⭐ Passable (≥ 35) · ⭐ Faible (< 35)

## Actions

- **{t:open_folder_btn}** — ouvrir le dossier de session dans l'Explorateur Windows
- **{t:show_fullscreen_btn}** — afficher l'image stackée en plein écran
- **{t:score_session_btn}** — scorer toutes les sessions de l'objet sélectionné
- **{t:backup_session}** / **{t:restore_mode}** — copier des sessions entre le Dwarf et le disque de sauvegarde
- **{t:delete_session}** — supprime définitivement toutes les données de session
- **{t:view_linked_manual}** — accéder à toute session manuelle liée
- **{t:favorite_add}** / **{t:favorite_remove}** — afficher ou masquer la session sur la page d'accueil

## Conseils

- Utilisez les cases **{t:only_not_backed}** / **{t:only_already_backed}** pour les sessions présentes à un seul endroit
- Le badge 🎯 indique l'état des darks — vert = température dans la plage, orange = plus proche, rouge = aucun
- Utilisez **{t:menu_report}** pour voir les tailles de sessions et identifier celles à nettoyer ou supprimer
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

## Galerie

Quand plusieurs sessions existent pour un objet, un bouton **{t:show_gallery}** apparaît
dans la barre d'actions. La galerie affiche une image par session et permet de naviguer
et d'accéder directement à n'importe quelle session. Un bouton **{t:show_gallery}** distinct
dans le détail de session affiche toutes les images trouvées dans cette session.

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
- **{t:favorite_add}** / **{t:favorite_remove}** — marquer pour le traitement
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

- Après un transfert, la page **{t:page_backup}** re-analysera automatiquement le disque
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

Configurez les paramètres globaux de l'application : langue, chemin de stockage local,
solveurs astrométriques et paramètres de mosaïque.

## Langue

Basculez entre l'anglais et le français. L'interface se recharge immédiatement.

## Chemin de stockage local

Le dossier où les données de session traitées (FITS, PNG, JPG) sont mises en cache localement.
Choisissez un disque avec suffisamment d'espace — cela peut dépasser 10 Go avec de nombreuses sessions.

## Clé API Nova (solveur en ligne)

[Astrometry.net](https://nova.astrometry.net) est un solveur de plaque gratuit en ligne.
Créez un compte, générez une clé API et collez-la ici.
Nova est utilisé en secours quand ASTAP échoue.

## ASTAP (solveur local)

ASTAP est un solveur astrométrique rapide qui fonctionne localement sur votre machine.
Il est fortement recommandé pour les utilisateurs Windows — pas de connexion internet requise.

**Téléchargement :** [https://www.hnsky.org/astap.htm](https://www.hnsky.org/astap.htm)

### Bases de données d'étoiles

ASTAP nécessite une base de données d'étoiles installée à côté de l'exécutable :

| Base | Taille | Idéal pour |
|------|--------|-----------|
| **D50** | ~5 Go | Usage général — recommandé par défaut |
| **D20** | ~2 Go | Plus rapide, légèrement moins précis |
| **D80** | ~8 Go | Longue focale, champs étroits (<1°) |
| **G05** | ~1 Go | Grands champs >5° (Dwarf en mode WIDE) |

- **Petit FOV** (< 5°) — utilisez D50 ou D20
- **Grand FOV** (> 5°, ex: objectif 24 mm) — utilisez G05

L'application bascule automatiquement vers G05 quand le champ de vue estimé
dépasse 5°. Les deux bases peuvent être installées simultanément.

### Workflow de résolution

1. ASTAP tente de résoudre l'image localement (rapide, ~1–5 s)
2. Si ASTAP échoue, Nova est utilisé en secours en ligne
3. Les résultats sont stockés en base de données et affichés sur la Carte du Ciel

## Paramètres de mosaïque

Configurez les paramètres d'assemblage pour les sessions mosaïque.
Consultez l'aide de la page **Mosaïque** pour plus de détails.
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
4. Cliquez sur **{t:generate_panorama}** pour assembler les panneaux

## Actions

- **{t:show_panel}** — prévisualiser un panneau mosaïque individuel
- **{t:generate_panorama}** — assembler les panneaux sélectionnés en image grand champ
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

    '/Report': {
        'title': 'Rapport de stockage',
        'content': '''
## Objectif

Le Rapport de stockage vous aide à identifier les sessions les plus volumineuses
et décider quoi nettoyer ou supprimer — particulièrement utile quand le disque
d'un Dwarf ou d'un disque de sauvegarde est presque plein.

## Sélecteur de disque

Choisissez entre le mode **Backup** et **Dwarf**, puis sélectionnez un disque spécifique.
Un indicateur d'espace disque affiche libre / total avec une barre colorée.
Les valeurs sont mises en cache dans `db/diskinfo.json` et s'affichent même si le disque est déconnecté.

## Tableau des sessions

Chaque ligne affiche :

- **Date** — date de la session
- **Objet** — nom de la cible (survolez pour voir le chemin complet)
- **Taille backup** — taille totale de la session sur le disque de sauvegarde
- **Dwarf total** — taille totale sur la copie locale du Dwarf (si présente)
- **Dwarf -FITS** — taille après suppression des fichiers FITS bruts (ce que libérerait Clean Fits)
- **Qualité** — score de qualité d'image (coloré)
- **Explore** — ouvre la session directement dans la page Explore

## Tri et filtrage

- **{t:report_biggest}** — trier par taille backup, les plus grandes en premier
- **{t:report_latest}** — trier par date, les plus récentes en premier
- **{t:report_show}** — limiter à 20 / 50 / 100 sessions, ou **{t:report_all}**

## Calculer les tailles

- **{t:report_calc_sizes}** — mesure les tailles des dossiers de sessions backup non encore calculées
- **{t:report_calc_dwarf_sizes}** — mesure les tailles des sessions présentes sur la copie locale du Dwarf,
  en calculant la taille totale et la taille après un Clean Fits

## Conseils

- Les sessions affichant `—` n'ont pas encore été mesurées — cliquez sur **{t:report_calc_sizes}**
- **Dwarf -FITS** = taille restante après **Clean Fits** — comparez à **Dwarf total** pour voir
  l'espace récupérable sans perdre le résultat stacké
- Cliquez sur **Explore** pour ouvrir la session et lancer Clean Fits ou la supprimer
- Le bouton Retour dans Explore revient à ce rapport avec les mêmes filtres actifs
''',
    },

    '/SkyMap': {
        'title': 'Carte du Ciel',
        'content': '''
## Objectif

La Carte du Ciel affiche toutes vos sessions résolues par astrométrie sur une
carte céleste interactive propulsée par Aladin Lite. Chaque rectangle coloré
représente une session d'observation, avec un code couleur selon le score de qualité.

## Couleurs de qualité

- 🟢 **Vert** — score ≥ 80 (excellent)
- 🟡 **Orange** — score 65–79 (bon)
- 🔴 **Rouge** — score < 65 (faible)
- ⬜ **Gris** — pas de score

## Scanner les sessions

Chaque Dwarf a sa propre ligne dans le tableau indiquant :
- **Total** — toutes les sessions dans la base de données
- **Résolues** — sessions avec astrométrie résolue
- **En attente** — sessions non résolues au-dessus du seuil de qualité
- **Sans score** — sessions sans score de qualité

Utilisez le curseur **Qualité min** pour ajuster les sessions éligibles au scan.
Cliquez sur **{t:sky_map_btn_scan}** pour lancer le solveur astrométrique pour ce Dwarf.

## Ouvrir la carte

Cliquez sur **{t:sky_map_open_browser}** pour ouvrir la carte interactive Aladin Lite
dans votre navigateur.

## Navigation dans la carte

- **Cliquez** sur un footprint pour voir les détails et un aperçu de l'image
- **Faites pivoter** l'aperçu avec le bouton ↻
- **Zoomez** l'aperçu avec + / −
- Chaque Dwarf possède sa propre **couche** dans Aladin — activez/désactivez
  la visibilité depuis le panneau de contrôle des couches (en haut à gauche de la carte)
- Si plusieurs sessions se chevauchent, une liste vous permet de choisir laquelle ouvrir

## Sessions mosaïque

Les sessions mosaïque affichent un cadre englobant couvrant tous les panels résolus.
Si la mosaïque a été re-stichée, le WCS global est utilisé à la place des panels individuels.
''',
    },

}
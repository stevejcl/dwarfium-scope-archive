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
    '/AnalyzeAll': {
        'title': 'Tout analyser',
        'content': '''
## Objectif

Analyse, l'un après l'autre, la copie locale de chaque Dwarf et chaque disque de sauvegarde de la base -
ce que font **{t:analyze_dwarf_drive}** et **{t:analyze_drive}**, pour tous. La base correspond alors de
nouveau aux fichiers.

## Quand

- Une autre installation de Scope Archive (par exemple l'exécutable et une version source, chacune avec
  sa base) partage le même Dwarf_Local et les mêmes disques de sauvegarde, et y a importé, transféré ou
  supprimé des sessions.
- Un dossier de session a été déplacé ou supprimé à la main.

## Comment

- **Pour un Dwarf**, c'est sa copie locale (`Dwarf_Local/DWARF_<id>`) qui est analysée : le Dwarf
  lui-même n'a pas besoin d'être connecté, rien n'est lu dessus.
- Un dossier injoignable (disque débranché) ne peut pas être coché.
- Décochez ce que vous ne voulez pas analyser, puis **{t:analyze_all_start}** : chaque ligne affiche son
  résultat (+ nouvelles sessions, - entrées supprimées) et le journal suit les analyses.
- Le journal est aussi écrit dans un fichier, `logs/analyze_all_<date>.log` dans le dossier de
  l'application (les 20 derniers gardés), avec l'heure de chaque ligne : **{t:analyze_all_open_log}**
  l'ouvre, pour une analyse fine.
- Avant chaque analyse, les dossiers `FIXED_FOREGROUND`, `PHOTOMETRY` et `MOSAIC_WCS` créés à côté des
  sessions par les versions précédentes sont déplacés à la racine du dossier analysé (au niveau de
  `RESTACKED`) sous les noms `_FIXED_FOREGROUND`, `_PHOTOMETRY` et `_WCS_MOSAIC`, fusionnés avec ceux déjà présents (un même fichier gardé une fois, un différent renommé
  `_1`) ; chaque déplacement est dans le journal. La photométrie d'une session, avant dans
  `_PHOTOMETRY/<session>/`, va dans `_PHOTOMETRY/<étoile>/<session>/` (les sessions d'une étoile côte à côte).
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

Le bouton <i class="q-icon material-icons text-primary" style="font-size:1.2em;vertical-align:-0.2em">travel_explore</i> sur chaque carte ouvre la cible dans Aladin Lite (navigateur externe)
pour visualiser le champ avant d'observer.

## Programmer sur le Dwarf

Le bouton <i class="q-icon material-icons text-primary" style="font-size:1.2em;vertical-align:-0.2em">event</i> de chaque carte propose deux choix :

- **Programmer cette cible cette nuit** — ouvre la page de planification d'Astro Dwarf
  Session (navigateur externe) avec la cible et son créneau cette nuit (au-dessus de 25°).
- **Ajouter au plan de la nuit** — l'ajoute à une liste de cibles (5 au plus par défaut, voir
  Paramètres › Session), affichée en
  bas de la fenêtre avec le créneau de chacune : ✕ en retire une, **Vider** la vide, et
  **Programmer ces cibles** ouvre la page de planification avec toutes, enchaînées sur la
  nuit. Quand la liste est pleine, ajouter une cible propose d'en remplacer une. Le
  bouton ⌄ replie la liste en une petite ligne (un clic la rouvre).
  La liste est liée à une nuit et un site, et reste quand on change de page.

Sur la page de planification, choisissez le Dwarf, des programmes ou un planning natif,
l'exposition et le filtre (et ajustez les créneaux), puis envoyez. Astro Dwarf Session
(3.2.3 et plus) doit être lancé, avec l'adresse de cette application dans ses Settings :
il se signale toutes les 30 s, c'est ainsi que cette application le trouve.

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
   En dessous, ✅ / ❌ indique si ce dossier est présent maintenant
   (Dwarf branché en USB) ; ⟳ vérifie à nouveau une fois le Dwarf branché.
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
   **{t:session_ip}** (facultatif) : une deuxième IP FTP pour ce Dwarf, gardée sur ce PC seulement (pas
   dans la base) - par exemple son IP sur un site distant joint par Tailscale (une route de sous-réseau
   sur l'ordinateur là-bas). Les fonctions FTP (cette page, **{t:transfer}**, Import Session) utilisent
   celle des deux IP qui répond. Un lien depuis Dwarfium Lite donnant l'IP du Dwarf la remplit.
6. Renseignez l'**{t:dwarf_ble_id}** : les 6 derniers caractères de l'adresse MAC inscrite sur le
   Dwarf (l'adresse entière peut être collée), qui terminent aussi son nom Bluetooth (`DWARF3_A1B2C3`).
   Dwarf allumé sur le réseau : **{t:dwarf_ble_id_read}** le demande au Dwarf à son IP.
   Dwarfium-Hub s'en sert pour lier ce Dwarf au même Dwarf dans Dwarfium Lite.
   Plusieurs Dwarfs allumés : **{t:dwarf_identify}** fait clignoter l'anneau lumineux du Dwarf à cette IP
   (via Dwarfium Lite, lancée ; jamais pendant une capture).
7. Cliquez sur **{t:save_update_dwarf}**

## Analyser le lecteur Dwarf

Scanne le répertoire USB du Dwarf et indexe toutes les sessions dans la base de données.
À exécuter après avoir connecté le Dwarf en USB.

Avant l'analyse, Scope Archive vérifie que le Dwarf branché est bien celui choisi :
- son modèle, d'après ses images ;
- en FTP, son identifiant : le Dwarf qui répond à l'IP doit avoir l'**{t:dwarf_ble_id}** enregistré ;
- ses sessions : si celles du lecteur sont déjà archivées sous un autre Dwarf et aucune sous celui
  choisi, c'est le lecteur de l'autre Dwarf - même entre deux Dwarfs du même modèle.

Un avertissement propose alors de choisir le bon Dwarf, ou de continuer quand même.

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
- **{t:fits_filter_label}** (mode Dwarf) — les sessions dont les FITS bruts sont encore sur le Dwarf, ou non,
  d'après la mesure du Rapport de stockage (**{t:report_calc_dwarf_sizes}**) ; une session jamais mesurée n'est dans aucun des deux

## Galerie

Quand plusieurs sessions existent pour un objet, un bouton **{t:show_gallery}** apparaît.
La galerie s'ouvre immédiatement avec la première image et charge les autres en arrière-plan.
Utilisez Précédent / Suivant pour parcourir, ou Sélectionner pour accéder directement à une session.
La molette de la souris les fait aussi défiler - un cran une session, tournée vite plusieurs (leur petite
vignette pendant le défilement, l'image complète à l'arrêt) ; le diaporama automatique se met en pause
pendant ce temps. La position (12 / 240) est affichée sous l'image.

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

Sous les actions, deux onglets : **{t:explore_tab_infos}** (le détail de la session) et **{t:explore_tab_image}** (son image empilée ; cliquez pour le plein écran). Ils glissent l'un vers l'autre ; sur téléphone ou tablette, balayez pour passer de l'un à l'autre.

Les actions sont affichées en icônes : survolez-en une pour voir son nom (sur téléphone ou tablette, le nom est sous l'icône).

- **{t:open_folder_btn}** — ouvrir le dossier de session dans l'Explorateur Windows
- **{t:show_fullscreen_btn}** — afficher l'image stackée en plein écran
- **{t:score_session_btn}** — scorer toutes les sessions de l'objet sélectionné
- **{t:explore_plan_tonight}** — le créneau de l'objet sélectionné cette nuit au lieu par défaut (calculé au clic), puis le programmer sur un Dwarf dans Astro Dwarf Session ou l'ajouter au plan de la nuit (voir l'aide de Recommended tonight)
- **{t:backup_session}** / **{t:restore_mode}** — copier des sessions entre le Dwarf et le disque de sauvegarde
- **{t:delete_session}** — supprime définitivement toutes les données de session
- **{t:view_linked_manual}** — accéder à toute session manuelle liée
- **{t:favorite_add}** / **{t:favorite_remove}** — afficher ou masquer la session sur la page d'accueil
- **{t:megastack_title_short}** (mode Dwarf) — voir ci-dessous
- **{t:frames_title}** — voir ci-dessous
- **{t:wcs_mosaic_btn}** (mode Sauvegarde, session d'une tuile de mosaïque) — l'onglet **{t:milky_way_mode}** de la page Mosaïque, sur la mosaïque de cette tuile
- **{t:fg_fix_btn}** (mode Sauvegarde, session grand champ prise avant DWARF 3 V1.5.3.9 / DWARF mini V1.1.4.4, poses brutes conservées) — le décor filé réparé : à partir des poses brutes, le ciel empilé sur les étoiles sans le décor (le sol tourne de 15° par heure par rapport au ciel), le décor empilé sur lui-même, puis les deux fusionnés, quel que soit le suivi (la rotation de chaque pose - rotation de champ, mise en station - est dans son recalage). Dans `_FIXED_FOREGROUND` à la racine de l'archive (le dossier Astronomy du backup, au niveau de `RESTACKED`) : un FITS, un aperçu, le ciel seul et le décor seul en TIFF 16 bits avec transparence (Affinity, Photoshop, GIMP). Environ 1 à 2 minutes ; la réparation continue si la fenêtre est fermée ou la page quittée, chaque page est prévenue à la fin
  Une fois réparée, la session montre un onglet **{t:explore_tab_fixed}** à côté d'**{t:explore_tab_image}** : l'aperçu réparé - un clic l'ouvre dans votre visionneuse d'images -, et le dossier avec le FITS réparé sélectionné
- Sous les détails, la ligne qui dit que la session est aussi sur le Dwarf (mode Sauvegarde) ou sur un disque de
  sauvegarde (mode Dwarf) : **{t:explore_view_copy}** l'ouvre là-bas dans Explorer
- À côté du score de qualité : ⌫ **{t:score_clear}** (elle passe alors « sans score » ;
  **{t:score_session_btn}** la note à nouveau), et pour une session résolue **{t:sky_map_hide}** / **{t:sky_map_unhide}**

## Megastack sur le Dwarf

Le Dwarf empile ensemble plusieurs de ses propres sessions d'une cible - ou en ré-empile une seule - dans
`Astronomy/RESTACKED/`, comme le megastack de l'appli officielle. C'est Dwarfium Lite (Astro Dwarf Session 3.2.6+)
qui parle au Dwarf et suit l'empilement.

1. Mode Dwarf, un Dwarf et un objet sélectionnés : cliquez **{t:megastack_title_short}**.
2. La fenêtre montre les sessions de l'objet qui peuvent être empilées, groupées par cible, avec leur vignette,
   date, images empilées, exposition et filtre. Non proposées : les résultats de megastack, et les sessions
   dont on sait que les FITS bruts ne sont plus là (nettoyées par Clean Fits) - lu sur le Dwarf branché en USB,
   sinon d'après la mesure du Rapport de stockage. Survolez une vignette pour le nom du dossier de la session.
3. Cliquez les sessions à empiler : une seule cible, captures simples ou mosaïques (sans les mélanger). Les
   filtres peuvent être mélangés (Duo-Band avec Astro).
4. **{t:megastack_start}** : Dwarfium Lite doit être lancé et le Dwarf connecté dedans. Il revérifie les FITS,
   puis le Dwarf vérifie le reste lui-même (binning, darks) - un refus s'affiche avec sa raison.

Suivez-le sur la page du Dwarf dans Dwarfium Lite (images empilées, l'image qui se construit dans la vue Télé) ;
le Dwarf ne fait rien d'autre pendant ce temps (environ 1 h pour 600 images). Le résultat apparaît ensuite
dans les sessions du Dwarf (`RESTACKED_…`), avec son exposition totale lue dans son FITS.

## Images de la session

Le Dwarf écrit un JPG de chaque image dans le dossier `Thumbnail` de la session, au même nom que son FITS ;
les images qu'il a rejetées à l'empilement ont le préfixe `failed_`, les deux. **{t:frames_title}** les
montre : un clic en agrandit une (flèches ou molette de la souris : précédente / suivante - tournée vite, ça
défile vite ; espace : la marquer). Marquez les mauvaises
(nuages, traînées, rotation) puis **Supprimer les images cochées** - leur FITS et leur JPG sont retirés, un
megastack ou un restack ne prend alors que les bonnes ; **Supprimer les images rejetées** prend d'un coup
toutes les `failed_`. Les tailles de la session sont remesurées.

Où elles vont :
- **Sur le Dwarf** (branché en USB - sa copie locale n'est pas le Dwarf, son FTP est en lecture seule) :
  supprimées définitivement. Une session sauvegardée les a en même temps mises dans la corbeille de sa copie
  de sauvegarde (son disque branché) ; une session non sauvegardée les perd - c'est dit avant.
- **Sur un disque de sauvegarde** : dans la corbeille de la session (un dossier `.trash`, dans chaque panneau
  pour une mosaïque). Le Dwarf branché en USB avec la session encore dessus, une case (décochée) les supprime
  aussi du Dwarf, définitivement - sinon une prochaine sauvegarde de la session les ramène.

**La corbeille** : sous les FITS de la session dans Explorer, « N images dans la corbeille » avec
**{t:trash_view}** et **{t:trash_empty_btn}**. Voir les montre : marquez chacune **{t:trash_restore}** (elle
revient dans la session) ou **{t:trash_delete}**, c'est fait en sortant ou avec **{t:trash_apply}**. Le Dwarf
branché en USB avec la session dessus, les images restaurées peuvent y être recopiées aussi ; sinon la
restauration de la session (Restore FITS, Transfert) les remettra plus tard. La corbeille n'est jamais copiée
sur le Dwarf, ni vue comme une session, ni comptée dans les FITS.

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

Chaque session de darks du Dwarf laisse ses bruts dans `DWARF_DARK` (à côté de
`CALI_FRAME`), dans un dossier daté à elle (`wide_exp_15_gain_60_bin_1_2026-10-20-...`,
la température à la fin du nom de chaque fichier), et le master construit à partir
d'eux dans `CALI_FRAME` pour les firmwares qui en font un (un master par réglage et
par température, remplacé par une nouvelle session à la même température ; un
firmware récent n'en fait pas). Chaque master est affiché avec ses bruts (nombre,
date) ; les bruts sans master (tous, avec un firmware qui n'en fait pas, une session
plus ancienne à une température refaite depuis, un master supprimé, des dossiers
sans date) sont listés en dessous.

Pour une session, les darks sont choisis parmi les masters de `CALI_FRAME` et ces
bruts sans distinction : mêmes gain, binning, exposition et caméra ; puis les darks
du firmware de la session (l'en-tête `FIRMWARE` de ses FITS et des darks bruts, un
master prenant celui de ses bruts) - une mise à jour du firmware peut changer les
bruts ; quand le firmware est inconnu d'un côté, les darks de l'époque de la
session à la place, datés à moins de 3 mois d'elle, avant ou après (un capteur
gagne des pixels chauds avec le temps) ; tous quand aucun ne l'est. Puis la
température la plus proche de celle de la session (à 1 °C près) ; puis le plus de
poses (le `_stack_N` d'un master : les poses de sa session à cette température -
un master d'une pose est aussi bruité qu'un brut) ; puis la date la plus proche
(date de la session de darks du master, date du dossier) ; le master en cas
d'égalité. L'optimisation des darks de Siril compense un écart de température
restant. Avec les bruts de
`DWARF_DARK`, Siril construit le master ; le badge 🎯 l'indique.

## Télécharger les darks

Ouvre la page **{t:transfer}** avec :
- La source pré-définie sur le dossier `CALI_FRAME` du Dwarf
- La destination commençant à la racine du disque de sauvegarde

Le dossier `DWARF_DARK` du Dwarf (les bruts de ses sessions de darks) est copié en
même temps, à côté de `CALI_FRAME`.

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

## Session

- **{t:settings_max_sessions}** — nombre maximum de cibles du plan de la nuit (1 à 10, 5 par
  défaut), chacune une session sur le Dwarf
- **{t:settings_day_change_hour}** — avant cette heure, « cette nuit » reste la nuit en cours
  (08:00 par défaut : à 2 h du matin, la nuit commencée la veille ; à 10 h, la nuit à venir).
  Sert à la date par défaut de Recommended tonight et au plan de la nuit (Recommended tonight,
  Explore)

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

## Onglet {t:milky_way_mode} : mosaïque par astrométrie

Une mosaïque planifiée tuile par tuile (le Milky Way planner d'Astro Dwarf Session : « MW Tile R1C1 »,
« MW Tile R1C2 »...) donne une session par tuile. Choisissez le **{t:backup_drive}** : **{t:wcs_mosaic_found}**
liste ses mosaïques - les sessions dont le nom contient R<rangée>C<colonne>, regroupées par nom et par nuit (la
plus récente en premier) - ou **{t:wcs_mosaic_add_folder}** prend les FITS d'un dossier (les siens, et les FITS
empilés de ses sous-dossiers). Décochez les tuiles à écarter, puis **{t:wcs_mosaic_run}** :
- chaque tuile est placée là où est son ciel : son WCS (dans son en-tête, sinon dans un fichier `.wcs` à côté),
  sinon elle est résolue - d'abord sur le catalogue d'étoiles brillantes de l'application, près du pointage noté
  par le Dwarf (hors ligne, quelques dizaines de secondes, fait pour ces grands champs), puis par ASTAP,
  solve-field ou Nova comme le scan d'astrométrie - et la solution est écrite à côté de la tuile, `<nom>.wcs` (la
  tuile n'est pas modifiée : l'assemblage suivant et d'autres outils la relisent) ; puis recalée sur les étoiles
  brillantes avec la distorsion de l'objectif ;
- l'avant-plan (toit, arbres) est écarté, la luminosité et la couleur de chaque tuile accordées à ses
  voisines, et dans les recouvrements la tuile vue plus près de son centre l'emporte (étoiles plus fines) ;
- le résultat, dans un dossier `_WCS_MOSAIC` à la racine de l'archive (le dossier Astronomy du backup, au niveau de `RESTACKED`) : un FITS linéaire avec son WCS - à traiter
  dans Siril (extraction du fond, calibration photométrique des couleurs, étirement) - un aperçu étiré, et le
  ciel seul, étiré, en TIFF 16 bits avec le décor transparent (`_sky.tif`) : à poser sur une photo du décor (un
  panorama à l'heure bleue par exemple) dans Affinity Photo, Photoshop ou GIMP, sans détourage à la main.

**{t:wcs_mosaic_open_folder}** (à côté de la sortie, et avec le résultat) ouvre le dossier `_WCS_MOSAIC`.
Les zones du ciel qu'aucune tuile ne couvre restent noires. Environ 2 minutes et 1 Go de mémoire pour 5 tuiles.
L'assemblage continue si vous changez de page : de retour sur l'onglet, un bandeau l'indique en cours (durée,
étape) au-dessus de ses étapes (résolution, étoiles du catalogue, ciel gardé, accord des luminosités...), puis son
résultat ; chaque page ouverte est prévenue à la fin. Un seul assemblage à la fois.
Dans Explore, **{t:wcs_mosaic_btn}** sur la session d'une tuile ouvre cet onglet sur sa mosaïque.

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
        'title': 'Édition du catalogue',
        'content': '''
## Rôle

Relie les **objets** de votre archive (un par nom de cible trouvé dans les
dossiers de session, plus les groupes = sous-dossiers) au **catalogue DSO**
intégré (Messier, NGC, IC, Caldwell...), et garde l'archive cohérente :
sessions reliées au mauvais DSO, sessions rangées dans le mauvais groupe.

## La liste

- **{t:catalog_filter_all}** / **{t:catalog_filter_objects}** /
  **{t:catalog_filter_groups}** : toutes les lignes, seulement les objets ou
  seulement les groupes (les groupes par défaut Unknown / MOSAIC_Unknown /
  Manual sont listés avec les groupes). Le choix est mémorisé.
- Par ligne :
  - **Assign/Change DSO** : recherche dans le catalogue (nom, constellation,
    type), choix du DSO, et si besoin votre propre description
  - **{t:move_sessions_btn}** : les sessions archivées de cet objet ou groupe
    (voir plus bas)
  - 🗑️ : retire le **lien DSO** de l'objet (l'objet lui-même est conservé)

## Boutons

- **{t:dso_wizard_open}** : un par un, chaque objet sans DSO. L'objet du
  catalogue le plus proche d'une de ses sessions est proposé, avec l'image
  empilée de la session pour vérifier : **{t:dso_wizard_yes}**,
  **{t:dso_wizard_no}**, un autre candidat proche, ou
  **{t:dso_wizard_manual}**. Le centre plate-solvé de la session est utilisé
  s'il existe, sinon sa position de goto.
- **{t:dso_check_open}**, deux vérifications :
  - **{t:dso_check_mode_objects}** : objets ayant des sessions plus loin que
    la distance choisie (le double pour une mosaïque) de leur DSO, avec le DSO
    détecté à la position de chaque session — **{t:dso_check_relink}** corrige
    (conservé au prochain rescan)
  - **{t:dso_check_mode_groups}** : tous les groupes d'un coup, en ne listant
    que les sessions éloignées de leur groupe (son DSO, ou la position de la
    plupart de ses sessions)
- **{t:export_csv}** : les liens objet ↔ DSO dans un fichier CSV.
- **{t:delete_unused}** : les objets qu'aucune session n'utilise plus.

## Sessions d'un objet ou d'un groupe

Les sessions archivées, les plus récentes d'abord, avec Dwarf, archive,
sous-dossier et objet. Pour chacune :
- 🖼️ l'image empilée en grand (avec un lien Aladin), pour vérifier un champ
  large ou une mosaïque quand plusieurs objets du catalogue sont proches
- 🔍 l'ouvrir dans Explore (par exemple pour identifier à nouveau sa cible) —
  le bouton retour revient ici avec cette liste ouverte
- **{t:move_button}** : déplace le dossier de la session dans les archives de
  son Dwarf — à la **{t:move_root}**, dans un **{t:move_existing}** (les
  sous-dossiers contenant déjà cet objet sont proposés) ou un
  **{t:move_new}**, dans la même archive ou une autre. Le dossier n'est jamais
  renommé ; seul ce dossier est rescanné, et ses notes, scores et plate
  solving le suivent.

**{t:dso_check_open}** dans cette liste ne fait que l'annoter : objet du
catalogue détecté à la position de chaque session, sessions trop éloignées
de l'objet ou du groupe. Rien n'est modifié.

## Conseils

- Le nom d'un objet vient du nom du dossier de session et n'est jamais
  modifié ici : corrigez une mauvaise correspondance en reliant l'objet au
  bon DSO.
- Les objets Unknown / MOSAIC_Unknown / Manual sont créés un par position
  par le scan : chacun peut donc être relié à son propre DSO.
- Lancez la vérification des groupes de temps en temps après avoir ajouté des
  sessions dans des sous-dossiers.
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
- **{t:report_size}** — taille du dossier de la session sur le disque de sauvegarde ; **{t:report_backup_missing}**
  (orange) quand le disque est branché mais que le dossier n'y est plus (déplacé, ou remis sur un autre disque)
  - analysez à nouveau le disque
- **{t:report_dwarf_size}** — sa taille sur le Dwarf (branché en USB, sinon sa copie locale)
- **{t:report_dwarf_no_fits}** — la même sans ses FITS bruts (ce que laisserait Clean Fits) ; écrite sur
  toutes les copies de sauvegarde de la session
- **Qualité** — score de qualité d'image (coloré)
- **Explore** — ouvre la session directement dans la page Explore

## Tri et filtrage

- **{t:report_biggest}** — trier par taille backup, les plus grandes en premier
- **{t:report_latest}** — trier par date, les plus récentes en premier
- **{t:report_show}** — limiter à 20 / 50 / 100 sessions, ou **{t:report_all}**

## Calculer les tailles

- **{t:report_calc_sizes}** — mesure les dossiers de sauvegarde pas encore mesurés (colonne **{t:report_size}**)
- **{t:report_calc_dwarf_sizes}** — mesure les sessions du Dwarf pas encore mesurées, avec et sans leurs FITS
  bruts (colonnes **{t:report_dwarf_size}** / **{t:report_dwarf_no_fits}**) - alimente aussi le filtre
  **{t:fits_filter_label}** d'Explore et la fenêtre du megastack
- ⟳ à côté de chaque bouton — **{t:report_calc_sizes_force}** (après un Clean Fits par exemple)

## Conseils

- Les sessions affichant `—` n'ont pas encore été mesurées — cliquez sur **{t:report_calc_sizes}**
- **{t:report_dwarf_no_fits}** = taille restante après **Clean Fits** — comparez à **{t:report_dwarf_size}**
  pour voir l'espace récupérable sans perdre le résultat stacké
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
- **{t:sky_map_best_only}** (barre d'outils) — seule la session au meilleur score de chaque objet
  (la plus récente en cas d'égalité) : 10 sessions d'une même nébuleuse, une seule sur la carte
- **{t:sky_map_hide}** (fenêtre d'une session) — la session quitte la carte ; elle reste résolue, le
  prochain scan ne la résout donc pas à nouveau. **{t:sky_map_show_hidden}** les affiche en gris, leur
  fenêtre propose **{t:sky_map_unhide}**. Les deux cases sont retenues par le navigateur.

## Sessions mosaïque

Les sessions mosaïque affichent un cadre englobant couvrant tous les panels résolus.
Si la mosaïque a été re-stichée, le WCS global est utilisé à la place des panels individuels.
''',
    },

}
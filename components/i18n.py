# components/i18n.py
"""
Dwarfium Scope Archive — Internationalization (i18n)
Usage:
    from components.i18n import t, set_language, get_language

    ui.label(t("save"))
    ui.button(t("cancel"))
"""

from nicegui import app

SUPPORTED_LANGUAGES = ["en", "fr"]
DEFAULT_LANGUAGE = "en"

# ─────────────────────────────────────────────────────────────────────────────
# Translation dictionary
# Keys are short identifiers. Each key maps to {lang: text}.
# ─────────────────────────────────────────────────────────────────────────────
_T = {
    # ── Common actions ────────────────────────────────────────────────────────
    "save":             {"en": "💾 Save",              "fr": "💾 Sauvegarder"},
    "cancel":           {"en": "Cancel",               "fr": "Annuler"},
    "confirm":          {"en": "Confirm",              "fr": "Confirmer"},
    "close":            {"en": "Close",                "fr": "Fermer"},
    "delete":           {"en": "🗑️ Delete",            "fr": "🗑️ Supprimer"},
    "add":              {"en": "Add",                  "fr": "Ajouter"},
    "edit":             {"en": "Edit",                 "fr": "Modifier"},
    "update":           {"en": "Update",               "fr": "Mettre à jour"},
    "select":           {"en": "Select",               "fr": "Sélectionner"},
    "deselect_all":     {"en": "Deselect All",         "fr": "Tout désélectionner"},
    "select_all":       {"en": "Select All",           "fr": "Tout sélectionner"},
    "connect":          {"en": "Connect",              "fr": "Connecter"},
    "disconnect":       {"en": "Disconnect",           "fr": "Déconnecter"},
    "refresh":          {"en": "Refresh",              "fr": "Actualiser"},
    "back":             {"en": "← Back",               "fr": "← Retour"},
    "search":           {"en": "Search",               "fr": "Rechercher"},
    "filter":           {"en": "Filter",               "fr": "Filtrer"},
    "export":           {"en": "Export",               "fr": "Exporter"},
    "import":           {"en": "Import",               "fr": "Importer"},
    "yes":              {"en": "Yes",                  "fr": "Oui"},
    "no":               {"en": "No",                   "fr": "Non"},
    "loading":          {"en": "Loading...",           "fr": "Chargement..."},
    "error":            {"en": "Error",                "fr": "Erreur"},
    "success":          {"en": "Success",              "fr": "Succès"},
    "warning":          {"en": "Warning",              "fr": "Avertissement"},

    # ── Navigation / Menu ─────────────────────────────────────────────────────
    "menu_home":        {"en": "Home",                 "fr": "Accueil"},
    "menu_explore":     {"en": "Explore",              "fr": "Explorer"},
    "menu_backup":      {"en": "Backup",               "fr": "Sauvegarde"},
    "menu_transfer":    {"en": "Transfer",             "fr": "Transfert"},
    "menu_settings":    {"en": "Settings",             "fr": "Paramètres"},
    "menu_catalog":     {"en": "Catalog",              "fr": "Catalogue"},
    "menu_darks":       {"en": "Dark Library",         "fr": "Bibliothèque Darks"},
    "menu_mosaic":      {"en": "Mosaic",               "fr": "Mosaïque"},

    # ── Settings page ─────────────────────────────────────────────────────────
    "settings_title":       {"en": "⚙️ Settings",              "fr": "⚙️ Paramètres"},
    "settings_app_info":    {"en": "ℹ️ Application Info",      "fr": "ℹ️ Infos Application"},
    "settings_version":     {"en": "Version",                  "fr": "Version"},
    "settings_lan_access":  {"en": "📡 LAN access",            "fr": "📡 Accès réseau"},
    "settings_lan_disabled":{"en": "📡 LAN access: disabled",  "fr": "📡 Accès réseau : désactivé"},
    "settings_language":    {"en": "🌐 Language",              "fr": "🌐 Langue"},
    "settings_dwarf_path":  {"en": "🔭 Dwarf Local Directory", "fr": "🔭 Répertoire Local Dwarf"},
    "settings_nova":        {"en": "🔭 NOVA Astrometry",       "fr": "🔭 NOVA Astrométrie"},
    "settings_mosaic":      {"en": "🔭 Mosaic & Stitch",       "fr": "🔭 Mosaïque & Assemblage"},
    "settings_export_pdf":  {"en": "📄 Export PDF Report",     "fr": "📄 Exporter Rapport PDF"},
    "settings_open_report": {"en": "📂 Open",                  "fr": "📂 Ouvrir"},

    # ── Backup Drive ──────────────────────────────────────────────────────────
    "backup_drive":         {"en": "Backup Drive",             "fr": "Disque de sauvegarde"},
    "backup_drive_saved":   {"en": "Backup drive saved.",      "fr": "Disque de sauvegarde enregistré."},
    "backup_drive_deleted": {"en": "BackupDrive deleted.",     "fr": "Disque de sauvegarde supprimé."},
    "backup_destination":   {"en": "Destination: Backup Drive","fr": "Destination : Disque de sauvegarde"},
    "select_destination":   {"en": "Select Destination",       "fr": "Sélectionner la destination"},
    "destination_dir":      {"en": "Destination Directory:",   "fr": "Répertoire de destination :"},

    # ── Dwarf device ──────────────────────────────────────────────────────────
    "dwarf_device":         {"en": "Dwarf Device",             "fr": "Appareil Dwarf"},
    "dwarf_connect":        {"en": "Dwarf Connect",            "fr": "Connexion Dwarf"},
    "dwarf_not_connected":  {"en": "Dwarf Device not connected","fr": "Appareil Dwarf non connecté"},
    "dwarf_deleted":        {"en": "Dwarf deleted.",           "fr": "Dwarf supprimé."},
    "add_dwarf":            {"en": "➕ Add New Dwarf",          "fr": "➕ Ajouter un Dwarf"},
    "dwarf_ip":             {"en": "Enter Dwarf IP Address:",  "fr": "Adresse IP du Dwarf :"},
    "detect_mtp":           {"en": "Detect MTP Dwarf",         "fr": "Détecter Dwarf MTP"},
    "mtp_devices":          {"en": "Connected MTP Devices:",   "fr": "Appareils MTP connectés :"},

    # ── Session / Explore ─────────────────────────────────────────────────────
    "session":              {"en": "Session",                  "fr": "Session"},
    "session_date":         {"en": "Date",                     "fr": "Date"},
    "session_dir":          {"en": "Directory",                "fr": "Répertoire"},
    "identify_target":      {"en": "🖼️ Identify Target",       "fr": "🖼️ Identifier la cible"},
    "show_details":         {"en": "Show Details",             "fr": "Afficher les détails"},
    "hide_details":         {"en": "Hide Details",             "fr": "Masquer les détails"},
    "show_gallery":         {"en": "🖼️ Show Gallery",          "fr": "🖼️ Afficher la galerie"},
    "show_fullscreen":      {"en": "Show fullscreen",          "fr": "Plein écran"},
    "open_folder":          {"en": "Open Folder",              "fr": "Ouvrir le dossier"},
    "view_session":         {"en": "🔭 View Session in Explore","fr": "🔭 Voir la session dans Explorer"},
    "no_stacked":           {"en": "(no stacked found on Dwarf)","fr": "(aucune image stackée trouvée)"},
    "no_thumbnail":         {"en": "(no thumbnail available)", "fr": "(aucune miniature disponible)"},
    "favorite_add":         {"en": "Click to Add to Favorites","fr": "Ajouter aux favoris"},
    "favorite_remove":      {"en": "Click to Remove from Favorites","fr": "Retirer des favoris"},

    # ── Transfer ──────────────────────────────────────────────────────────────
    "transfer":             {"en": "Transfer",                 "fr": "Transfert"},
    "transfer_mode":        {"en": "Transfer Mode",            "fr": "Mode de transfert"},
    "source_dir":           {"en": "Source Directory:",        "fr": "Répertoire source :"},
    "cancel_backup":        {"en": "Cancel Backup",            "fr": "Annuler la sauvegarde"},
    "cancel_import":        {"en": "Cancel Import",            "fr": "Annuler l'import"},
    "backup_session":       {"en": "Backup Session",           "fr": "Sauvegarder la session"},
    "check_integrity":      {"en": "Check Session Integrity",  "fr": "Vérifier l'intégrité"},
    "data_source":          {"en": "Data source:",             "fr": "Source de données :"},
    "before":               {"en": "Before",                   "fr": "Avant"},
    "after":                {"en": "After",                    "fr": "Après"},

    # ── Manual Session ────────────────────────────────────────────────────────
    "add_manual_session":   {"en": "Add Manual Session",       "fr": "Ajouter une session manuelle"},
    "edit_manual_session":  {"en": "Edit Manual Session",      "fr": "Modifier la session manuelle"},
    "import_files":         {"en": "Import Files",             "fr": "Importer les fichiers"},
    "update_session_files": {"en": "Update Session Files",     "fr": "Mettre à jour les fichiers"},
    "fits_files_list":      {"en": "Added FITS files list",    "fr": "Liste des fichiers FITS ajoutés"},
    "choose_failed":        {"en": "Choose Failed session",    "fr": "Choisir la session échouée"},
    "choose_new":           {"en": "Choose new session",       "fr": "Choisir une nouvelle session"},

    # ── DSO Catalog ───────────────────────────────────────────────────────────
    "catalog":              {"en": "Catalog",                  "fr": "Catalogue"},
    "assign_dso":           {"en": "Assign/Change DSO",        "fr": "Assigner/Changer le DSO"},
    "dso_assigned":         {"en": "DSO assigned/updated!",    "fr": "DSO assigné/mis à jour !"},
    "delete_unused":        {"en": "Delete Astro Objects not used anymore",
                             "fr": "Supprimer les objets astronomiques non utilisés"},
    "astro_purged":         {"en": "AstroObject data have been purged!",
                             "fr": "Les données AstroObject ont été supprimées !"},
    "export_csv":           {"en": "Export Associations to CSV",
                             "fr": "Exporter les associations en CSV"},
    "constellation_exact":  {"en": "Constellation (exact)",   "fr": "Constellation (exacte)"},
    "type_exact":           {"en": "Type (exact)",             "fr": "Type (exact)"},
    "custom_description":   {"en": "Edit or enter custom description",
                             "fr": "Modifier ou saisir une description"},
    "select_dso":           {"en": "Select DSO",               "fr": "Sélectionner un DSO"},
    "search_dso":           {"en": "Search (designation, name, constellation, type)",
                             "fr": "Rechercher (désignation, nom, constellation, type)"},

    # ── Session Notes ─────────────────────────────────────────────────────────
    "notes_title":          {"en": "🔭 Session Observations",  "fr": "🔭 Observations de session"},
    "notes_moon":           {"en": "Moon:",                    "fr": "Lune :"},
    "notes_seeing":         {"en": "Seeing:",                  "fr": "Seeing :"},
    "notes_location":       {"en": "📍 Observation site",      "fr": "📍 Lieu d'observation"},
    "notes_summary":        {"en": "Summary (shown directly)", "fr": "Résumé (affiché directement)"},
    "notes_summary_ph":     {"en": "e.g. Great night, light wind, good transparency",
                             "fr": "ex: Belle nuit, vent faible, bonne transparence"},
    "notes_detail":         {"en": "Detailed notes",           "fr": "Notes détaillées"},
    "notes_detail_ph":      {"en": "Conditions, equipment, observations...",
                             "fr": "Conditions, équipement, observations..."},
    "notes_add_btn":        {"en": "📋 Add observations",      "fr": "📋 Prendre des observations"},
    "notes_edit_tooltip":   {"en": "Edit observations",        "fr": "Modifier les observations"},
    "notes_saved":          {"en": "Observations saved ✓",     "fr": "Observations sauvegardées ✓"},
    "notes_after_import":   {"en": "Observations can be added after the session is imported.",
                             "fr": "Les observations pourront être ajoutées après l'import."},
    "notes_section":        {"en": "📋 Observations (optional)","fr": "📋 Observations (optionnel)"},

    # ── Moon phases ───────────────────────────────────────────────────────────
    "moon_new":             {"en": "New Moon",                 "fr": "Nouvelle Lune"},
    "moon_waxing_crescent": {"en": "Waxing Crescent",          "fr": "Croissant Croissant"},
    "moon_first_quarter":   {"en": "First Quarter",            "fr": "Premier Quartier"},
    "moon_waxing_gibbous":  {"en": "Waxing Gibbous",           "fr": "Gibbeuse Croissante"},
    "moon_full":            {"en": "Full Moon",                "fr": "Pleine Lune"},
    "moon_waning_gibbous":  {"en": "Waning Gibbous",           "fr": "Gibbeuse Décroissante"},
    "moon_last_quarter":    {"en": "Last Quarter",             "fr": "Dernier Quartier"},
    "moon_waning_crescent": {"en": "Waning Crescent",          "fr": "Croissant Décroissant"},

    # ── Dark Library ──────────────────────────────────────────────────────────
    "dark_library":         {"en": "Dark Library",             "fr": "Bibliothèque de darks"},
    "dark_inventory":       {"en": "Dark Inventory",           "fr": "Inventaire des darks"},
    "dark_deleted":         {"en": "Dark Library deleted.",    "fr": "Bibliothèque de darks supprimée."},

    # ── Notifications ─────────────────────────────────────────────────────────
    "notif_api_key_saved":  {"en": "API key saved successfully!",
                             "fr": "Clé API sauvegardée avec succès !"},
    "notif_backup_saved":   {"en": "Backup drive saved.",      "fr": "Disque de sauvegarde enregistré."},
    "notif_dwarf_deleted":  {"en": "Dwarf deleted.",           "fr": "Dwarf supprimé."},
    "notif_db_failed":      {"en": "DB removal failed.",       "fr": "Échec de la suppression en base."},
    "notif_backup_entries_deleted": {"en": "Backup entries and DwarfData deleted.",
                                     "fr": "Entrées de sauvegarde et DwarfData supprimées."},
    "notif_select_dso_first":{"en": "Please select a DSO first.",
                              "fr": "Veuillez d'abord sélectionner un DSO."},
    "notif_no_folder":      {"en": "No folder selected!",      "fr": "Aucun dossier sélectionné !"},
    "notif_cannot_remove_fits":{"en": "Cannot remove main FITS while others are present!",
                                "fr": "Impossible de supprimer le FITS principal tant que d'autres sont présents !"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_language() -> str:
    """Return the current language code ('en' or 'fr')."""
    try:
        lang = app.storage.general.get("language", DEFAULT_LANGUAGE)
        return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    except Exception:
        return DEFAULT_LANGUAGE


def set_language(lang: str):
    """Persist the language choice."""
    if lang in SUPPORTED_LANGUAGES:
        app.storage.general["language"] = lang


def t(key: str, **kwargs) -> str:
    """
    Translate a key to the current language.
    Falls back to English, then to the key itself if not found.
    Supports simple string formatting: t("hello", name="World")
    """
    lang = get_language()
    entry = _T.get(key)
    if entry is None:
        return key  # key not found — return as-is
    text = entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def t_list(keys: list) -> list:
    """Translate a list of keys."""
    return [t(k) for k in keys]

# ── Additional keys added during full migration ──────────────────────────────
_T.update({
    # Backup page
    "launch_backup":        {"en": "Launch Backup Dwarf Data...",   "fr": "Lancer la sauvegarde..."},
    "start_backup":         {"en": "Start Backup",                  "fr": "Démarrer la sauvegarde"},
    "cancel_backup":        {"en": "Cancel Backup",                 "fr": "Annuler la sauvegarde"},
    "backup_complete":      {"en": "✅ Backup completed successfully!", "fr": "✅ Sauvegarde terminée avec succès !"},
    "backup_verified":      {"en": "✅ Backup complete and verified!", "fr": "✅ Sauvegarde complète et vérifiée !"},
    "backup_incomplete":    {"en": "⚠️ Backup incomplete due to failures.", "fr": "⚠️ Sauvegarde incomplète (des erreurs se sont produites)."},
    "backup_cancelled":     {"en": "❌ Backup cancelled by user.",   "fr": "❌ Sauvegarde annulée par l'utilisateur."},
    "backup_drive_saved2":  {"en": "✅ Backup Drive saved!",        "fr": "✅ Disque de sauvegarde enregistré !"},
    "show_backup_data":     {"en": "🗂️ Show Backup Data",           "fr": "🗂️ Afficher les données sauvegardées"},
    "show_dwarf_data":      {"en": "🗂️ Show Dwarf Data",            "fr": "🗂️ Afficher les données Dwarf"},
    "backup_selected":      {"en": "📦 Backup Selected Sessions",   "fr": "📦 Sauvegarder les sessions sélectionnées"},
    "showing_backup":       {"en": "Showing Backup Data...",        "fr": "Affichage des données de sauvegarde..."},
    "no_backup_drive":      {"en": "No Backup Drive configured yet.", "fr": "Aucun disque de sauvegarde configuré."},
    "no_backup_selected":   {"en": "No Backup Drive selected.",     "fr": "Aucun disque de sauvegarde sélectionné."},
    "need_backup_drive":    {"en": "You need to add a Backup Drive before you can backup sessions.", "fr": "Ajoutez un disque de sauvegarde avant de sauvegarder des sessions."},
    "add_backup_drive":     {"en": "➕ Add New BackupDrive",        "fr": "➕ Ajouter un disque de sauvegarde"},
    "go_backup_settings":   {"en": "➕ Go to Backup Settings",      "fr": "➕ Aller aux paramètres de sauvegarde"},
    "save_update_drive":    {"en": "Save / Update Backup Drive",    "fr": "Enregistrer / Mettre à jour le disque"},
    "delete_backup_drive":  {"en": "🗑️ Delete Backup Drive",        "fr": "🗑️ Supprimer le disque de sauvegarde"},
    "delete_backup_entries":{"en": "🗑️ Delete Backup Entries",      "fr": "🗑️ Supprimer les entrées de sauvegarde"},
    "backup_entries_deleted":{"en": "Backup entries and DwarfData deleted.", "fr": "Entrées de sauvegarde et DwarfData supprimées."},
    "invalid_backup_drive": {"en": "Invalid backup Drive selection.", "fr": "Sélection de disque invalide."},
    "this_folder_registered":{"en": "This folder is already registered.", "fr": "Ce dossier est déjà enregistré."},
    "no_backup_drive_loc":  {"en": "No BackupDrive registered at this location.", "fr": "Aucun disque enregistré à cet emplacement."},
    "select_backup_session":{"en": "Select Backup Session:",        "fr": "Sélectionner une session de sauvegarde :"},
    "analyze_drive":        {"en": "🔍 Analyze Current Drive",      "fr": "🔍 Analyser le disque actuel"},
    "analyze_dwarf_drive":  {"en": "🔍 Analyze Dwarf Drive",        "fr": "🔍 Analyser le lecteur Dwarf"},

    # Dwarf device page
    "save_update_dwarf":    {"en": "Save / Update Dwarf",           "fr": "Enregistrer / Mettre à jour le Dwarf"},
    "delete_dwarf":         {"en": "🗑️ Delete Dwarf",               "fr": "🗑️ Supprimer le Dwarf"},
    "delete_dwarf_entries": {"en": "🗑️ Delete Dwarf Entries",       "fr": "🗑️ Supprimer les entrées Dwarf"},
    "add_dwarf2":           {"en": "➕ Add New Dwarf",               "fr": "➕ Ajouter un Dwarf"},
    "select_existing_dwarf":{"en": "Select Existing Dwarf",         "fr": "Sélectionner un Dwarf existant"},
    "fill_fields_save_dwarf":{"en": "Fill all fields and save a Dwarf first.", "fr": "Remplissez tous les champs et enregistrez d'abord un Dwarf."},
    "invalid_dwarf":        {"en": "Invalid dwarf selection",       "fr": "Sélection de Dwarf invalide"},
    "no_dwarf_selected":    {"en": "No Dwarf selected",             "fr": "Aucun Dwarf sélectionné"},
    "select_dwarf":         {"en": "Select Dwarf:",                 "fr": "Sélectionner un Dwarf :"},
    "first_run":            {"en": "First run detected. Connect your Dwarf via USB, then follow the Help panel to register it.", "fr": "Première utilisation détectée. Connectez votre Dwarf en USB, puis suivez le panneau d'aide pour l'enregistrer."},
    "first_setup":          {"en": "🚀 First Setup Required",       "fr": "🚀 Première configuration requise"},
    "dwarf_data_deleted":   {"en": "DwarfData entries deleted.",    "fr": "Entrées DwarfData supprimées."},

    # Transfer page
    "stop_transfer":        {"en": "🛑 Stop Transfer",              "fr": "🛑 Arrêter le transfert"},
    "transfer_running":     {"en": "🔄 Transfer running — you can browse other pages and come back.", "fr": "🔄 Transfert en cours — vous pouvez naviguer et revenir."},
    "transfer_warning":     {"en": "⚠️ Transfer in progress",       "fr": "⚠️ Transfert en cours"},
    "transfer_close_warn":  {"en": "⚠️ Transfer in progress — closing the app will stop the transfer.", "fr": "⚠️ Transfert en cours — fermer l'application l'arrêtera."},
    "transfer_reset":       {"en": "Transfer state reset — you can start a new transfer.", "fr": "État du transfert réinitialisé — vous pouvez démarrer un nouveau transfert."},
    "transfer_history":     {"en": "📋 Transfer History",           "fr": "📋 Historique des transferts"},
    "transfer_history_log": {"en": "📋 Transfer History Log",       "fr": "📋 Journal des transferts"},
    "transfer_mode":        {"en": "Transfer Mode",                 "fr": "Mode de transfert"},
    "source_directory":     {"en": "Source Directory:",             "fr": "Répertoire source :"},
    "select_source":        {"en": "Select Source",                 "fr": "Sélectionner la source"},
    "source_usb":           {"en": "Source: Dwarf USB Drive",       "fr": "Source : Lecteur USB Dwarf"},
    "no_source_dir":        {"en": "No source Directory selected.", "fr": "Aucun répertoire source sélectionné."},
    "no_dest_dir":          {"en": "No destination Directory selected.", "fr": "Aucun répertoire de destination sélectionné."},
    "cancel_transfer_warn": {"en": "⚠️ Closing the app will stop the transfer.", "fr": "⚠️ Fermer l'application arrêtera le transfert."},
    "transfer_cancellation":{"en": "🛑 Transfer cancellation requested...", "fr": "🛑 Annulation du transfert demandée..."},
    "no_usb_location":      {"en": "No USB location selected",      "fr": "Aucun emplacement USB sélectionné"},
    "usb_inaccessible":     {"en": "USB Directory is inaccessible.", "fr": "Le répertoire USB est inaccessible."},
    "select_usb_folder":    {"en": "Select USB Folder",             "fr": "Sélectionner le dossier USB"},
    "select_sub_folder":    {"en": "Select Sub Folder",             "fr": "Sélectionner un sous-dossier"},

    # Mosaic page
    "mosaic_result":        {"en": "🌅 Mosaic Result",              "fr": "🌅 Résultat de la mosaïque"},
    "create_mosaic":        {"en": "🖼️ Create Mosaic",              "fr": "🖼️ Créer la mosaïque"},
    "show_mosaic_gallery":  {"en": "🖼️ Show Mosaic Gallery",        "fr": "🖼️ Afficher la galerie mosaïque"},
    "mosaic_gallery":       {"en": "🧩 Mosaic Gallery",             "fr": "🧩 Galerie de mosaïque"},
    "new_stitch":           {"en": "✨ New Stitch",                  "fr": "✨ Nouveau Stitch"},
    "stitch_params":        {"en": "🔭 Stitch Parameters",          "fr": "🔭 Paramètres de Stitch"},
    "create_fits_close":    {"en": "🔭 Create FITS & Close",        "fr": "🔭 Créer le FITS & Fermer"},
    "stitching_failed":     {"en": "❌ Stitching Failed",            "fr": "❌ Échec du Stitch"},
    "stitching":            {"en": "⚙️ Stitching Mosaic...",         "fr": "⚙️ Assemblage de la mosaïque..."},
    "creating_fits":        {"en": "⚙️ Creating FITS Mosaic...",     "fr": "⚙️ Création du FITS mosaïque..."},
    "mosaic_accepted":      {"en": "✅ Mosaic accepted!",            "fr": "✅ Mosaïque acceptée !"},
    "mosaic_saved":         {"en": "✅ Mosaic saved to session!",    "fr": "✅ Mosaïque enregistrée dans la session !"},
    "mosaic_discarded":     {"en": "Mosaic discarded.",             "fr": "Mosaïque abandonnée."},
    "mosaic_discarded_restored":{"en": "Mosaic discarded — files restored.", "fr": "Mosaïque abandonnée — fichiers restaurés."},
    "mosaic_fits_created":  {"en": "✅ FITS mosaic created!",        "fr": "✅ Mosaïque FITS créée !"},
    "mosaic_in_error":      {"en": "🔴 Mosaic Sessions in Error",   "fr": "🔴 Sessions mosaïque en erreur"},
    "no_mosaic_dir":        {"en": "Directory does not contain MOSAIC", "fr": "Le répertoire ne contient pas de MOSAIC"},
    "primary_not_mosaic":   {"en": "⚠️ Primary does not contain MOSAIC.", "fr": "⚠️ La session principale ne contient pas de MOSAIC."},
    "mosaic_params":        {"en": "🔭 Mosaic & Stitch Parameters",  "fr": "🔭 Paramètres Mosaïque & Stitch"},
    "change_params":        {"en": "⚙️ Change Parameters",          "fr": "⚙️ Changer les paramètres"},
    "params_applied":       {"en": "✅ Parameters applied for this run", "fr": "✅ Paramètres appliqués pour cette exécution"},
    "stitch_params_saved":  {"en": "✅ Stitch parameters saved",    "fr": "✅ Paramètres de stitch enregistrés"},
    "reset_defaults":       {"en": "↺ Reset to defaults",           "fr": "↺ Réinitialiser par défaut"},
    "verify_orientation":   {"en": "Verify orientation before merge", "fr": "Vérifier l'orientation avant la fusion"},
    "start_merge":          {"en": "🔀 Start Merge",                "fr": "🔀 Démarrer la fusion"},
    "repair_transfer":      {"en": "🔧 Repair Transfer (Temp → Dwarf)", "fr": "🔧 Réparer le transfert (Temp → Dwarf)"},
    "merge_transfer":       {"en": "🔧 Merge Transfer (Temp → Dwarf)", "fr": "🔧 Fusionner le transfert (Temp → Dwarf)"},
    "repair_mosaic":        {"en": "Repair Mosaic Session",         "fr": "Réparer la session mosaïque"},
    "select_primary":       {"en": "📁 Select Primary Session",     "fr": "📁 Sélectionner la session principale"},
    "select_secondary":     {"en": "📁 Select Secondary Session",   "fr": "📁 Sélectionner la session secondaire"},
    "primary_session":      {"en": "📂 Primary Session (base mosaic)", "fr": "📂 Session principale (mosaïque de base)"},
    "secondary_session":    {"en": "📂 Secondary Session (Additional Data to Merge)", "fr": "📂 Session secondaire (données additionnelles)"},
    "no_primary":           {"en": "❌ Please select a Primary Session.", "fr": "❌ Veuillez sélectionner une session principale."},
    "no_secondary":         {"en": "❌ Please select a Secondary Session.", "fr": "❌ Veuillez sélectionner une session secondaire."},
    "sessions_different":   {"en": "⚠️ Primary and Secondary sessions must be different.", "fr": "⚠️ Les sessions principale et secondaire doivent être différentes."},
    "failed_session":       {"en": "Failed Session",                "fr": "Session échouée"},
    "choose_failed":        {"en": "Choose Failed session",         "fr": "Choisir la session échouée"},
    "choose_new":           {"en": "Choose new session",            "fr": "Choisir une nouvelle session"},
    "could_not_resolve":    {"en": "Could not resolve selected sessions", "fr": "Impossible de résoudre les sessions sélectionnées"},
    "sessions_merged":      {"en": "Sessions merged:",             "fr": "Sessions fusionnées :"},
    "merge_aborted":        {"en": "⚠️ Could not create backup — merge aborted.", "fr": "⚠️ Impossible de créer la sauvegarde — fusion annulée."},
    "no_sessions_selected": {"en": "No sessions selected",         "fr": "Aucune session sélectionnée"},
    "sessions_in_error":    {"en": "⚠️ Sessions with errors:",      "fr": "⚠️ Sessions avec erreurs :"},
    "no_sessions_error":    {"en": "✅ No Sessions in error.",       "fr": "✅ Aucune session en erreur."},
    "sessions_error_title": {"en": "Sessions in Error",            "fr": "Sessions en erreur"},

    # Explore / detail panel
    "press_esc":            {"en": "Press ESC to close the image",  "fr": "Appuyez sur ESC pour fermer l'image"},
    "show_fullscreen_img":  {"en": "Show Fullscreen Image",         "fr": "Afficher en plein écran"},
    "open_in_aladin":       {"en": "🌌 Open in Aladin",             "fr": "🌌 Ouvrir dans Aladin"},
    "open_in_explorer":     {"en": "🔎 Open in Explorer",           "fr": "🔎 Ouvrir dans l'Explorateur"},
    "open_folder":          {"en": "📂 Browse",                     "fr": "📂 Parcourir"},
    "original":             {"en": "📷 Original",                   "fr": "📷 Original"},
    "astro_gallery":        {"en": "⭐ Astro Gallery ⭐",            "fr": "⭐ Galerie Astro ⭐"},
    "favorites_gallery":    {"en": "⭐ My Favorite images ⭐",       "fr": "⭐ Mes images favorites ⭐"},
    "no_images_object":     {"en": "No images found for this object.", "fr": "Aucune image trouvée pour cet objet."},
    "no_images":            {"en": "No images found.",              "fr": "Aucune image trouvée."},
    "no_fav_images":        {"en": "No favorite images found.",     "fr": "Aucune image favorite trouvée."},
    "go_explore":           {"en": "🔭 Go to Explore",              "fr": "🔭 Aller vers Explorer"},
    "session_list":         {"en": "Session List",                  "fr": "Liste des sessions"},
    "no_session_selected":  {"en": "No session selected.",          "fr": "Aucune session sélectionnée."},
    "favorite_updated":     {"en": "Favorite updated.",             "fr": "Favori mis à jour."},
    "session_removed":      {"en": "Session removed from database.","fr": "Session supprimée de la base."},
    "session_not_found":    {"en": "Session not found",             "fr": "Session introuvable"},
    "session_not_found_db": {"en": "Session not found in database.","fr": "Session introuvable dans la base."},
    "delete_session":       {"en": "🗑️ Delete Session",             "fr": "🗑️ Supprimer la session"},
    "delete_manual_entries":{"en": "🗑️ Delete Manual Entries",      "fr": "🗑️ Supprimer les entrées manuelles"},
    "also_delete_manual":   {"en": "🗑️ Also delete ManualSession records?", "fr": "🗑️ Supprimer aussi les enregistrements ManualSession ?"},
    "no_linked_manual":     {"en": "No linked Manual session found.", "fr": "Aucune session manuelle liée trouvée."},
    "no_linked_dwarf":      {"en": "No linked Dwarf session for this import.", "fr": "Aucune session Dwarf liée pour cet import."},
    "session_registered":   {"en": "✅ Session registered in database.", "fr": "✅ Session enregistrée dans la base."},
    "resolution_complete":  {"en": "✅ Resolution completed",       "fr": "✅ Résolution terminée"},
    "analyzing_fits":       {"en": "🔍 Analysing Fits Image...",    "fr": "🔍 Analyse de l'image FITS..."},
    "no_fits_resolve":      {"en": "No FITS files to resolve.",     "fr": "Aucun fichier FITS à résoudre."},
    "no_info_fits":         {"en": "No info found in FITS file!",   "fr": "Aucune information trouvée dans le fichier FITS !"},
    "not_fits_url":         {"en": "Not a FITS file URL",           "fr": "Ce n'est pas une URL de fichier FITS"},
    "resolve_file":         {"en": "🪐 Resolve File",               "fr": "🪐 Résoudre le fichier"},
    "resolve_files":        {"en": "🪐 Resolve Files",              "fr": "🪐 Résoudre les fichiers"},
    "only_backed_up":       {"en": "Only show backed up sessions present on selected Dwarf", "fr": "Afficher uniquement les sessions sauvegardées présentes sur le Dwarf sélectionné"},
    "only_backed_not_dwarf":{"en": "Only show backed up sessions but deleted on selected Dwarf", "fr": "Afficher uniquement les sessions sauvegardées mais supprimées du Dwarf"},
    "only_duplicates":      {"en": "Only show duplicates backed up sessions", "fr": "Afficher uniquement les sessions sauvegardées en double"},
    "only_not_backed":      {"en": "Only show sessions not yet backed up on selected Dwarf", "fr": "Afficher uniquement les sessions non encore sauvegardées"},
    "only_already_backed":  {"en": "Only show sessions already backed up on selected Dwarf", "fr": "Afficher uniquement les sessions déjà sauvegardées"},

    # Dark Library
    "save_update_library":  {"en": "Save / Update Library",        "fr": "Enregistrer / Mettre à jour la bibliothèque"},
    "delete_library":       {"en": "🗑️ Delete Library",             "fr": "🗑️ Supprimer la bibliothèque"},
    "add_library":          {"en": "➕ Add New Library",             "fr": "➕ Ajouter une bibliothèque"},
    "select_existing_lib":  {"en": "Select Existing Dark Library",  "fr": "Sélectionner une bibliothèque existante"},
    "dark_lib_saved":       {"en": "✅ Dark Library saved.",         "fr": "✅ Bibliothèque de darks enregistrée."},
    "dark_lib_failed":      {"en": "❌ Failed to save library.",     "fr": "❌ Échec de l'enregistrement de la bibliothèque."},
    "scan_library":         {"en": "🔍 Scan Library",               "fr": "🔍 Scanner la bibliothèque"},
    "download_darks":       {"en": "📥 Download Darks",             "fr": "📥 Télécharger les darks"},
    "show_all_libraries":   {"en": "📋 Show All Libraries",         "fr": "📋 Afficher toutes les bibliothèques"},
    "no_library_selected":  {"en": "No library selected.",         "fr": "Aucune bibliothèque sélectionnée."},
    "no_dark_files":        {"en": "⚠️ No dark files found matching the naming convention.", "fr": "⚠️ Aucun fichier dark trouvé correspondant à la convention de nommage."},
    "set_cali_first":       {"en": "Please set a CALI_FRAME location first.", "fr": "Veuillez d'abord définir un emplacement CALI_FRAME."},
    "save_lib_first":       {"en": "Save the library first to set the CALI_FRAME location.", "fr": "Enregistrez d'abord la bibliothèque pour définir l'emplacement CALI_FRAME."},
    "no_subfolders":        {"en": "No subdirectories found in Astronomy folder.", "fr": "Aucun sous-dossier trouvé dans le dossier Astronomie."},

    # MTP Devices
    "unsupported_device":   {"en": "Unsupported Device",           "fr": "Appareil non pris en charge"},
    "unsupported_conn":     {"en": "Unsupported connection mode",  "fr": "Mode de connexion non pris en charge"},
    "mtp_unavailable":      {"en": "MTP functions are not available!", "fr": "Les fonctions MTP ne sont pas disponibles !"},
    "saved_mtp":            {"en": "Saved MTP Devices:",           "fr": "Appareils MTP enregistrés :"},

    # Settings / NOVA
    "nova_config":          {"en": "🔭 Configuration of NOVA Astrometry", "fr": "🔭 Configuration de NOVA Astrométrie"},
    "nova_online":          {"en": "🌐 Online mode (Astrometry.net)", "fr": "🌐 Mode en ligne (Astrometry.net)"},
    "nova_local":           {"en": "💻 Local Mode (solve-field)",   "fr": "💻 Mode local (solve-field)"},
    "nova_create_key":      {"en": "Create an API key on Astrometry.net", "fr": "Créer une clé API sur Astrometry.net"},
    "nova_install":         {"en": "Install solve-field localy",   "fr": "Installer solve-field localement"},
    "nova_no_key":          {"en": "⚠️ No Astrometry API key — NOVA astrometry resolution skipped.", "fr": "⚠️ Pas de clé API Astrométrie — résolution NOVA ignorée."},
    "nova_go_settings":     {"en": "Go to Settings to register a NOVA_ASTRO_API key.", "fr": "Allez dans les paramètres pour enregistrer une clé NOVA_ASTRO_API."},
    "solve_not_found":      {"en": "❌ solve-field not found.",     "fr": "❌ solve-field introuvable."},
    "solve_available":      {"en": "✅ solve-field is not available on this system.", "fr": "✅ solve-field n'est pas disponible sur ce système."},
    "install_not_supported":{"en": "Installation automatique non supportée pour ce système.", "fr": "Installation automatique non supportée pour ce système."},
    "dwarf_config":         {"en": "🔭 Configuration of Dwarf Local Parent directory", "fr": "🔭 Configuration du répertoire parent local Dwarf"},
    "select_dwarf_dir":     {"en": "Select a directory to store Dwarf data locally for offline use.", "fr": "Sélectionnez un répertoire pour stocker les données Dwarf localement."},
    "path_saved":           {"en": "Path saved successfully!",     "fr": "Chemin enregistré avec succès !"},

    # General UI
    "idle":                 {"en": "Idle...",                       "fr": "En attente..."},
    "starting":             {"en": "Starting...",                   "fr": "Démarrage..."},
    "starting_analysis":    {"en": "Starting Analysis ...",         "fr": "Démarrage de l'analyse..."},
    "starting_sync":        {"en": "Starting Local Sync ...",       "fr": "Démarrage de la synchronisation locale..."},
    "scanning_dwarf":       {"en": "🔍 Scanning Dwarf drive, please wait...", "fr": "🔍 Analyse du lecteur Dwarf, veuillez patienter..."},
    "restoring_fits":       {"en": "Restoring FITS files...",       "fr": "Restauration des fichiers FITS..."},
    "downloading_fits":     {"en": "⏳ Downloading FITS file...",   "fr": "⏳ Téléchargement du fichier FITS..."},
    "clean_fits":           {"en": "Clean Up FITS files...",        "fr": "Nettoyer les fichiers FITS..."},
    "next":                 {"en": "Next",                          "fr": "Suivant"},
    "next_arrow":           {"en": "Next ➡",                        "fr": "Suivant ➡"},
    "previous":             {"en": "Previous",                      "fr": "Précédent"},
    "previous_arrow":       {"en": "⬅ Previous",                   "fr": "⬅ Précédent"},
    "later":                {"en": "Later",                         "fr": "Plus tard"},
    "ignore":               {"en": "Ignore",                        "fr": "Ignorer"},
    "ignore_file":          {"en": "Ignore File",                   "fr": "Ignorer le fichier"},
    "stay_here":            {"en": "Stay here",                     "fr": "Rester ici"},
    "retry":                {"en": "🔄 Retry",                      "fr": "🔄 Réessayer"},
    "top":                  {"en": "↑ Top",                         "fr": "↑ Haut"},
    "help":                 {"en": "Help: ",                        "fr": "Aide : "},
    "tag":                  {"en": "Tag:",                          "fr": "Tag :"},
    "name_required":        {"en": "Name is required",             "fr": "Le nom est requis"},
    "new_session":          {"en": "New session",                   "fr": "Nouvelle session"},
    "session_name":         {"en": "Session:",                      "fr": "Session :"},
    "please_select":        {"en": "Please select",                 "fr": "Veuillez sélectionner"},
    "please_select_entry":  {"en": "Please select an entry first.", "fr": "Veuillez d'abord sélectionner une entrée."},
    "please_select_dir":    {"en": "Please select a valid directory.", "fr": "Veuillez sélectionner un répertoire valide."},
    "please_select_valid_dir":{"en": "Please select a valid existing directory.", "fr": "Veuillez sélectionner un répertoire existant valide."},
    "fill_location":        {"en": "Fill Location first.",          "fr": "Remplissez d'abord l'emplacement."},
    "please_session_name":  {"en": "Please provide or select a session name.", "fr": "Veuillez fournir ou sélectionner un nom de session."},
    "folder_not_found":     {"en": "Folder not found!",            "fr": "Dossier introuvable !"},
    "no_folder_selected":   {"en": "No folder selected!",          "fr": "Aucun dossier sélectionné !"},
    "no_session_error":     {"en": "No error session selected.",   "fr": "Aucune session en erreur sélectionnée."},
    "no_location":          {"en": "No location selected.",        "fr": "Aucun emplacement sélectionné."},
    "no_files_loaded":      {"en": "No files loaded",              "fr": "Aucun fichier chargé"},
    "no_manual_entries":    {"en": "No manual entries found for this drive.", "fr": "Aucune entrée manuelle trouvée pour ce disque."},
    "no_prev_actions":      {"en": "No previous actions found for this session.", "fr": "Aucune action précédente trouvée pour cette session."},
    "previous_actions":     {"en": "Previous actions found",       "fr": "Actions précédentes trouvées"},
    "no_report":            {"en": "No report generated yet",      "fr": "Aucun rapport généré pour l'instant"},
    "select_directory":     {"en": "Select Directory",             "fr": "Sélectionner un répertoire"},
    "select_folder":        {"en": "Select Folder",                "fr": "Sélectionner un dossier"},
    "select_output":        {"en": "📁 Select Output Folder",      "fr": "📁 Sélectionner le dossier de sortie"},
    "output_dir":           {"en": "📤 Output (Temporary) Directory", "fr": "📤 Répertoire de sortie (temporaire)"},
    "create_temp_folder":   {"en": "🗂️ Create Temp Folder",        "fr": "🗂️ Créer un dossier temporaire"},
    "no_output_dir":        {"en": "❌ Please select or create an Output directory.", "fr": "❌ Veuillez sélectionner ou créer un répertoire de sortie."},
    "db_removal_failed":    {"en": "DB removal failed.",           "fr": "Échec de la suppression en base."},
    "failed_update_object": {"en": "❌ Failed to update object",   "fr": "❌ Échec de la mise à jour de l'objet"},
    "delete_failed":        {"en": "❌ Delete failed.",             "fr": "❌ Échec de la suppression."},
    "entry_not_found":      {"en": "❌ Entry not found.",           "fr": "❌ Entrée introuvable."},
    "entry_removed":        {"en": "✅ Entry removed from history.", "fr": "✅ Entrée supprimée de l'historique."},
    "remove_history":       {"en": "Remove this entry from history?", "fr": "Supprimer cette entrée de l'historique ?"},
    "no_coords":            {"en": "❌ No coordinates available — link a session first or add an API key.", "fr": "❌ Aucune coordonnée disponible — liez d'abord une session ou ajoutez une clé API."},
    "no_nearby_dso":        {"en": "❌ No nearby DSO found in your catalog", "fr": "❌ Aucun DSO proche trouvé dans votre catalogue"},
    "target_known":         {"en": "⚠️ Target is already known: {target}", "fr": "⚠️ La cible est déjà connue : {target}"},
    "no_error_access":      {"en": "❌ Error accessing local Dwarf Directory", "fr": "❌ Erreur d'accès au répertoire Dwarf local"},
    "custom_description2":  {"en": "🔤 Enter a custom description", "fr": "🔤 Saisir une description personnalisée"},
    "accept_close":         {"en": "✅ Accept & Close",             "fr": "✅ Accepter & Fermer"},
    "apply":                {"en": "✅ Apply",                      "fr": "✅ Appliquer"},
    "save_continue":        {"en": "✅ Save and continue",          "fr": "✅ Enregistrer et continuer"},
    "close_x":              {"en": "✖️ Close",                      "fr": "✖️ Fermer"},
    "cancel_x":             {"en": "❌ Cancel",                     "fr": "❌ Annuler"},
    "discard":              {"en": "🗑️ Discard",                    "fr": "🗑️ Abandonner"},
    "empty_archive":        {"en": "🗑️ Empty Local Archive",        "fr": "🗑️ Vider l'archive locale"},
    "remove_all_files":     {"en": "🗑️ Remove all files",           "fr": "🗑️ Supprimer tous les fichiers"},
    "select_local_fits":    {"en": "Select Local FITS Files (optional)", "fr": "Sélectionner les fichiers FITS locaux (optionnel)"},
    "select_local_jpg":     {"en": "Select Local JPG Files (optional)", "fr": "Sélectionner les fichiers JPG locaux (optionnel)"},
    "select_local_png":     {"en": "Select Local PNG Files (optional)", "fr": "Sélectionner les fichiers PNG locaux (optionnel)"},
    "files_already_session":{"en": "Files already in session (edit mode)", "fr": "Fichiers déjà dans la session (mode édition)"},
    "primary_fits_deleted": {"en": "Primary FITS deleted — please upload a replacement.", "fr": "FITS principal supprimé — veuillez uploader un remplacement."},
    "db_saved_failed":      {"en": "⚠️ Files saved but database registration failed.", "fr": "⚠️ Fichiers enregistrés mais l'enregistrement en base a échoué."},
    "please_backup_dir":    {"en": "Please choose the main backup directory for your Dwarf astrophotography images or dark files.", "fr": "Choisissez le répertoire principal de sauvegarde pour vos images d'astrophotographie Dwarf ou fichiers darks."},
    "please_astro_dir":     {"en": "Please select the Astronomy directory within the mapped USB drive.", "fr": "Sélectionnez le répertoire Astronomie dans le lecteur USB mappé."},
    "select_astro_info":    {"en": "You can select a specific subfolder where your astrophotography session images are stored.", "fr": "Vous pouvez sélectionner un sous-dossier spécifique où sont stockées vos images de session d'astrophotographie."},
    "folder_not_in_loc":    {"en": "Selected folder is not inside the Location folder.", "fr": "Le dossier sélectionné n'est pas dans le dossier Location."},
    "fits_icon_clicked":    {"en": "FITS icon clicked",            "fr": "Icône FITS cliquée"},
    "jpg_icon_clicked":     {"en": "JPG icon clicked",             "fr": "Icône JPG cliquée"},
    "png_icon_clicked":     {"en": "PNG icon clicked",             "fr": "Icône PNG cliquée"},
    "ftp_disconnected":     {"en": "FTP disconnected",             "fr": "FTP déconnecté"},
    "no_restacked":         {"en": "No RESTACKED or STARTRAILS folder found on FTP or access failed", "fr": "Aucun dossier RESTACKED ou STARTRAILS trouvé sur FTP ou accès échoué"},
    "copy_fits_jpg":        {"en": "Copy Fits/JPG Session Files, Check it to do Megastack on Dwarf", "fr": "Copier les fichiers FITS/JPG de session, cochez pour faire un Megastack sur le Dwarf"},
    "select_backup_drive":  {"en": "Please select a Backup Drive.", "fr": "Veuillez sélectionner un disque de sauvegarde."},
    "select_existing_drive":{"en": "Select Existing BackupDrive",   "fr": "Sélectionner un disque de sauvegarde existant"},
    "dso_astro_assoc":      {"en": "🔭 AstroObject to DSO Association", "fr": "🔭 Association AstroObject vers DSO"},
    "back_btn":             {"en": "🔙 Back",                       "fr": "🔙 Retour"},
    "please_description":   {"en": "⚠️ Please enter a description", "fr": "⚠️ Veuillez entrer une description"},
    "save_key":             {"en": "💾 Save key",                   "fr": "💾 Enregistrer la clé"},
    "total_sessions_zero":  {"en": "Total matching sessions: 0",    "fr": "Total des sessions correspondantes : 0"},
    "no_error_session":     {"en": "No error session selected.",    "fr": "Aucune session en erreur sélectionnée."},
    "select_astro_dir":     {"en": "You can select a specific subfolder where your astrophotography session images are stored.", "fr": "Vous pouvez sélectionner un sous-dossier spécifique où sont stockées vos sessions d'astrophotographie."},
    "main_file_info":       {"en": "Main File Session Information (From First Fits file uploaded)", "fr": "Informations sur le fichier principal de session (à partir du premier fichier FITS uploadé)"},
    "select_this_session":  {"en": "☑ Select this session",        "fr": "☑ Sélectionner cette session"},
    "no_report_yet":        {"en": "No report generated yet",       "fr": "Aucun rapport généré pour l'instant"},
})

# ── Final remaining strings ───────────────────────────────────────────────────
_T.update({
    "target_known_short":   {"en": "⚠️ Target is already known: {target}", "fr": "⚠️ La cible est déjà connue : {target}"},
    "please_select_session":{"en": "Please select a session",      "fr": "Veuillez sélectionner une session"},
    "set_cali_loc":         {"en": "Please set a CALI_FRAME location.", "fr": "Veuillez définir un emplacement CALI_FRAME."},
    "dwarf_ip_long":        {"en": "Enter the Dwarf IP Address, you can find it on the My Device Page on the Dwarflab App.", "fr": "Entrez l'adresse IP du Dwarf, disponible sur la page Mon Appareil dans l'application Dwarflab."},
    "open_folder_icon":     {"en": "🗁 Open",                       "fr": "🗁 Ouvrir"},
    "mosaic_stitch_failed": {"en": "Mosaic stitching has failed!",  "fr": "L'assemblage de la mosaïque a échoué !"},
    "please_select_dwarf":  {"en": "Please select a Dwarf first",   "fr": "Veuillez d'abord sélectionner un Dwarf"},
    "no_backup_drive_sel2": {"en": "No backup drive selected",      "fr": "Aucun disque de sauvegarde sélectionné"},
    "destination_dir2":     {"en": "Destination Directory",         "fr": "Répertoire de destination"},
    "lang_label":           {"en": "🌐 Language / Langue :",        "fr": "🌐 Language / Langue :"},
    "error_astro_purge":    {"en": "Error occurs during AstroObject purge!", "fr": "Erreur lors de la suppression des AstroObjects !"},
    "backup_info_updated":  {"en": "BackupDrive info updated",      "fr": "Informations du disque mises à jour"},
    "astro_gallery2":       {"en": "🧩 Astro Gallery",              "fr": "🧩 Galerie Astro"},
    "no_sessions_error2":   {"en": "No Sessions in error.",         "fr": "Aucune session en erreur."},
})

# ── Form field labels ─────────────────────────────────────────────────────────
_T.update({
    "dwarf_name_label":     {"en": "Dwarf Name",               "fr": "Nom du Dwarf"},
    "description":          {"en": "Description",              "fr": "Description"},
    "type_label":           {"en": "Type",                     "fr": "Type"},
    "astronomy_dir":        {"en": "Astronomy Directory",      "fr": "Répertoire Astronomie"},
    "ip_sta_mode":          {"en": "Ip Address STA Mode",      "fr": "Adresse IP Mode STA"},
    "last_scan":            {"en": "Last Scan on:",            "fr": "Dernier scan le :"},
    "backup_drive_name":    {"en": "Backup Drive Name",        "fr": "Nom du disque de sauvegarde"},
    "backup_drive_loc":     {"en": "Backup Drive Location",    "fr": "Emplacement du disque"},
    "library_name":         {"en": "Library Name",             "fr": "Nom de la bibliothèque"},
    "library_location":     {"en": "Library Location",         "fr": "Emplacement de la bibliothèque"},
    "session_name_label":   {"en": "Session Name",             "fr": "Nom de la session"},
    "target_name":          {"en": "Target Name",              "fr": "Nom de la cible"},
    "object_name":          {"en": "Object Name",              "fr": "Nom de l'objet"},
    "ra_label":             {"en": "Right Ascension",          "fr": "Ascension droite"},
    "dec_label":            {"en": "Declination",              "fr": "Déclinaison"},
    "exposure_label":       {"en": "Exposure (s)",             "fr": "Exposition (s)"},
    "gain_label":           {"en": "Gain",                     "fr": "Gain"},
    "filter_label":         {"en": "Filter",                   "fr": "Filtre"},
    "date_label":           {"en": "Date",                     "fr": "Date"},
    "notes_label":          {"en": "Notes",                    "fr": "Notes"},
})

_T.update({
    "DWARF_LOCAL_PATH": {"en": "DWARF_LOCAL_PATH", "fr": "DWARF_LOCAL_PATH"},
    "api_key": {"en": "API key", "fr": "Clé API"},
    "select_a_folder": {"en": "Select a folder", "fr": "Sélectionner un dossier"},
    "drive_description": {"en": "Drive Description", "fr": "Description du disque"},
    "location_label": {"en": "Location", "fr": "Emplacement"},
    "cali_frame_location": {"en": "CALI_FRAME Location", "fr": "Emplacement CALI_FRAME"},
})

# ── Menu items ────────────────────────────────────────────────────────────────
_T.update({
    "menu_home":            {"en": "Home",              "fr": "Accueil"},
    "menu_dwarf_settings":  {"en": "Dwarfs Settings",  "fr": "Config. Dwarfs"},
    "menu_backup_settings": {"en": "Backup Setting",   "fr": "Config. Sauvegarde"},
    "menu_manual_sessions": {"en": "Manual Sessions",  "fr": "Sessions Manuelles"},
    "menu_add_session":     {"en": "Add Session",       "fr": "Ajouter Session"},
    "menu_mtp":             {"en": "MtpDevice",         "fr": "Appareil MTP"},
    "menu_dark_mode":       {"en": "🌙 Dark Mode",      "fr": "🌙 Mode Sombre"},
    "menu_light_mode":      {"en": "☀️ Light Mode",     "fr": "☀️ Mode Clair"},
    "menu_help":            {"en": "❓ Help",            "fr": "❓ Aide"},
    # Badge status
    "scanning":             {"en": "🔍 Scanning...",    "fr": "🔍 Analyse..."},
    "syncing_db":           {"en": "🔄 Syncing DB...",  "fr": "🔄 Sync DB..."},
    "transfer_done":        {"en": "✅ Transfer done",  "fr": "✅ Transfert terminé"},
    "transfer_error":       {"en": "❌ Transfer error", "fr": "❌ Erreur transfert"},
})

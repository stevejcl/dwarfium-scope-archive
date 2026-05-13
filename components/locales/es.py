# components/locales/es.py
"""
Dwarfium Scope Archive — Spanish translations.

This file was generated from the English source as a translation template.
Replace each value with the Spanish translation.
Lines marked # TODO have not been translated yet.
"""

TRANSLATIONS: dict[str, str] = {

    # ── Common actions ────────────────────────────────────────────────────────────
    "save":                         "💾 Save",  # TODO
    "cancel":                       "Cancel",  # TODO
    "confirm":                      "Confirm",  # TODO
    "close":                        "Close",  # TODO
    "delete":                       "🗑️ Delete",  # TODO
    "add":                          "Add",  # TODO
    "edit":                         "Edit",  # TODO
    "update":                       "Update",  # TODO
    "select":                       "Select",  # TODO
    "deselect_all":                 "Deselect All",  # TODO
    "select_all":                   "Select All",  # TODO
    "connect":                      "Connect",  # TODO
    "disconnect":                   "Disconnect",  # TODO
    "refresh":                      "Refresh",  # TODO
    "back":                         "← Back",  # TODO
    "search":                       "Search",  # TODO
    "filter":                       "Filter",  # TODO
    "export":                       "Export",  # TODO
    "import":                       "Import",  # TODO
    "yes":                          "Yes",  # TODO
    "no":                           "No",  # TODO
    "loading":                      "Loading...",  # TODO
    "error":                        "Error",  # TODO
    "success":                      "Success",  # TODO
    "warning":                      "Warning",  # TODO
    "next":                         "Next",  # TODO
    "next_arrow":                   "Next ➡",  # TODO
    "previous":                     "Previous",  # TODO
    "previous_arrow":               "⬅ Previous",  # TODO
    "later":                        "Later",  # TODO
    "ignore":                       "Ignore",  # TODO
    "ignore_file":                  "Ignore File",  # TODO
    "stay_here":                    "Stay here",  # TODO
    "retry":                        "🔄 Retry",  # TODO
    "top":                          "↑ Top",  # TODO
    "help":                         "Help: ",  # TODO
    "apply":                        "✅ Apply",  # TODO
    "accept_close":                 "✅ Accept & Close",  # TODO
    "save_continue":                "✅ Save and continue",  # TODO
    "close_x":                      "✖️ Close",  # TODO
    "cancel_x":                     "❌ Cancel",  # TODO
    "discard":                      "🗑️ Discard",  # TODO
    "name_required":                "Name is required",  # TODO
    "please_select":                "Please select",  # TODO
    "tag":                          "Tag:",  # TODO
    "on_label":                     "on",  # TODO
    "with_label":                   "with",  # TODO
    "size_label":                   "Size",  # TODO
    "no_data":                      "No data available",  # TODO
    "refresh_label":                "Refresh",  # TODO
    "back_btn":                     "Back",  # TODO

    # ── Navigation / Menu ─────────────────────────────────────────────────────────
    "menu_home":                    "Home",  # TODO
    "menu_explore":                 "Explore",  # TODO
    "menu_backup":                  "Backup",  # TODO
    "menu_transfer":                "Transfer",  # TODO
    "menu_settings":                "Settings",  # TODO
    "menu_catalog":                 "Catalog",  # TODO
    "menu_darks":                   "Dark Library",  # TODO
    "menu_mosaic":                  "Mosaic",  # TODO
    "menu_dwarf_settings":          "Dwarfs Settings",  # TODO
    "menu_backup_settings":         "Backup Setting",  # TODO
    "menu_manual_sessions":         "Manual Sessions",  # TODO
    "menu_add_session":             "Add Session",  # TODO
    "menu_mtp":                     "MtpDevice",  # TODO
    "menu_dark_mode":               "🌙 Dark Mode",  # TODO
    "menu_light_mode":              "☀️ Light Mode",  # TODO
    "menu_help":                    "❓ Help",  # TODO
    "scanning":                     "🔍 Scanning...",  # TODO
    "syncing_db":                   "Syncing database...",  # TODO
    "transfer_done":                "✅ Transfer done",  # TODO
    "transfer_error":               "❌ Transfer error",  # TODO

    # ── Page titles ───────────────────────────────────────────────────────────────
    "page_home":                    "Home",  # TODO
    "page_dwarf":                   "Dwarf Configuration",  # TODO
    "page_backup":                  "Backup Configuration",  # TODO
    "page_darks":                   "Dark Library",  # TODO
    "page_explore":                 "Explore",  # TODO
    "page_manual_explore":          "Explore Manual Session",  # TODO
    "page_manual_add":              "Add Manual Session",  # TODO
    "page_manual_exit":             "Edit Manual Session",  # TODO
    "page_transfer":                "Session Transfer",  # TODO
    "page_usb_transfer":            "Session USB Transfer",  # TODO
    "page_mosaic":                  "Mosaic Merge / Repair",  # TODO
    "page_mtp":                     "DWARF II MTP Device Manager",  # TODO
    "page_catalog":                 "Catalog Edition",  # TODO
    "page_settings":                "Settings",  # TODO

    # ── Status & UI feedback ──────────────────────────────────────────────────────
    "idle":                         "Idle...",  # TODO
    "starting":                     "Starting...",  # TODO
    "starting_analysis":            "Starting Analysis ...",  # TODO
    "starting_sync":                "Starting Local Sync ...",  # TODO
    "initializing_db":              "Initializing database...",  # TODO
    "ready":                        "Ready ✅",  # TODO
    "new_session":                  "New session",  # TODO
    "session_name":                 "Session:",  # TODO
    "please_select_entry":          "Please select an entry first.",  # TODO
    "please_select_dir":            "Please select a valid directory.",  # TODO
    "please_select_valid_dir":      "Please select a valid existing directory.",  # TODO
    "fill_location":                "Fill Location first.",  # TODO
    "please_session_name":          "Please provide or select a session name.",  # TODO
    "folder_not_found":             "Folder not found!",  # TODO
    "no_folder_selected":           "No folder selected!",  # TODO
    "no_session_error":             "No error session selected.",  # TODO
    "no_location":                  "No location selected.",  # TODO
    "no_files_loaded":              "No files loaded",  # TODO
    "no_manual_entries":            "No manual entries found for this drive.",  # TODO
    "no_prev_actions":              "No previous actions found for this session.",  # TODO
    "previous_actions":             "Previous actions found",  # TODO
    "no_report":                    "No report generated yet",  # TODO
    "select_directory":             "Select Directory",  # TODO
    "select_folder":                "Select Folder",  # TODO
    "select_output":                "📁 Select Output Folder",  # TODO
    "output_dir":                   "📤 Output (Temporary) Directory",  # TODO
    "create_temp_folder":           "🗂️ Create Temp Folder",  # TODO
    "no_output_dir":                "❌ Please select or create an Output directory.",  # TODO
    "db_removal_failed":            "DB removal failed.",  # TODO
    "failed_update_object":         "❌ Failed to update object",  # TODO
    "delete_failed":                "❌ Delete failed.",  # TODO
    "entry_not_found":              "❌ Entry not found.",  # TODO
    "entry_removed":                "✅ Entry removed from history.",  # TODO
    "remove_history":               "Remove this entry from history?",  # TODO
    "no_coords":                    "❌ No coordinates available — link a session first or add an API key.",  # TODO
    "no_nearby_dso":                "❌ No nearby DSO found in your catalog",  # TODO
    "target_known":                 "⚠️ Target is already known: {target}",  # TODO
    "target_known_short":           "⚠️ Target is already known: {target}",  # TODO
    "no_error_access":              "❌ Error accessing local Dwarf Directory",  # TODO
    "custom_description2":          "🔤 Enter a custom description",  # TODO
    "please_description":           "⚠️ Please enter a description",  # TODO
    "total_sessions_zero":          "Total matching sessions: 0",  # TODO
    "no_error_session":             "No error session selected.",  # TODO
    "no_report_yet":                "No report generated yet",  # TODO
    "select_astro_dir":             "You can select a specific subfolder where your astrophotography session images are stored.",  # TODO
    "main_file_info":               "Main File Session Information (From First Fits file uploaded)",  # TODO
    "select_this_session":          "☑ Select this session",  # TODO
    "local_data_size":              "Local Data size:",  # TODO
    "local_archive_size":           "Local Archive size:",  # TODO
    "restoring_fits":               "Restoring FITS files...",  # TODO
    "downloading_fits":             "⏳ Downloading FITS file...",  # TODO
    "clean_fits":                   "Clean Up FITS files...",  # TODO
    "no_filter":                    "No filter",  # TODO
    "temp_label":                   "Temp",  # TODO
    "list_objects":                 "List Objects",  # TODO
    "all_sessions_display":         "[ALL SESSIONS]",  # TODO

    # ── Form field labels ─────────────────────────────────────────────────────────
    "dwarf_name_label":             "Dwarf Name",  # TODO
    "description":                  "Description",  # TODO
    "type_label":                   "Type",  # TODO
    "astronomy_dir":                "Astronomy Directory",  # TODO
    "ip_sta_mode":                  "IP Address STA Mode",  # TODO
    "last_scan":                    "Last Scan on:",  # TODO
    "backup_drive_name":            "Backup Drive Name",  # TODO
    "backup_drive_loc":             "Backup Drive Location",  # TODO
    "library_name":                 "Library Name",  # TODO
    "library_location":             "Library Location",  # TODO
    "session_name_label":           "Session Name",  # TODO
    "target_name":                  "Target Name",  # TODO
    "object_name":                  "Object Name",  # TODO
    "ra_label":                     "Right Ascension",  # TODO
    "dec_label":                    "Declination",  # TODO
    "exposure_label":               "Exposure (s)",  # TODO
    "gain_label":                   "Gain",  # TODO
    "filter_label":                 "Filter",  # TODO
    "date_label":                   "Date",  # TODO
    "notes_label":                  "Notes",  # TODO
    "cali_frame_location":          "CALI_FRAME Location",  # TODO
    "drive_description":            "Drive Description",  # TODO
    "location_label":               "Location",  # TODO
    "select_a_folder":              "Select a folder",  # TODO
    "api_key":                      "API key",  # TODO
    "DWARF_LOCAL_PATH":             "DWARF_LOCAL_PATH",  # TODO
    "session_date":                 "Date",  # TODO
    "session":                      "Session",  # TODO
    "target_label":                 "Target",  # TODO
    "lens_label":                   "Lens",  # TODO
    "folder_label":                 "Folder",  # TODO
    "drive_label":                  "Drive",  # TODO
    "dwarf_label":                  "Dwarf",  # TODO
    "session_label":                "Session",  # TODO

    # ── Settings ──────────────────────────────────────────────────────────────────
    "settings_title":               "⚙️ Settings",  # TODO
    "settings_app_info":            "ℹ️ Application Info",  # TODO
    "settings_version":             "Version",  # TODO
    "settings_lan_access":          "📡 LAN access",  # TODO
    "settings_lan_disabled":        "📡 LAN access: disabled",  # TODO
    "settings_language":            "🌐 Language",  # TODO
    "settings_dwarf_path":          "🔭 Dwarf Local Directory",  # TODO
    "settings_nova":                "🔭 NOVA Astrometry",  # TODO
    "settings_mosaic":              "🔭 Mosaic & Stitch",  # TODO
    "settings_export_pdf":          "📄 Export PDF Report",  # TODO
    "settings_open_report":         "📂 Open",  # TODO
    "lang_label":                   "🌐 Language / Langue :",  # TODO
    "path_saved":                   "Path saved successfully!",  # TODO
    "nova_config":                  "🔭 Configuration of NOVA Astrometry",  # TODO
    "nova_online":                  "🌐 Online mode (Astrometry.net)",  # TODO
    "nova_local":                   "💻 Local Mode (solve-field)",  # TODO
    "nova_create_key":              "Create an API key on Astrometry.net",  # TODO
    "nova_install":                 "Install solve-field localy",  # TODO
    "nova_no_key":                  "⚠️ No Astrometry API key — NOVA astrometry resolution skipped.",  # TODO
    "nova_go_settings":             "Go to Settings to register a NOVA_ASTRO_API key.",  # TODO
    "solve_not_found":              "❌ solve-field not found.",  # TODO
    "solve_available":              "✅ solve-field is not available on this system.",  # TODO
    "install_not_supported":        "Automatic installation not supported for this system.",  # TODO
    "dwarf_config":                 "🔭 Configuration of Dwarf Local Parent directory",  # TODO
    "select_dwarf_dir":             "Select a directory to store Dwarf data locally for offline use.",  # TODO
    "save_key":                     "💾 Save key",  # TODO
    "dwarf_local_disk":             "⚠️ This folder stores a local index of your sessions\n— stacked results only (FITS, PNG, JPG) not the individual raw frames.\nDepending on the number of sessions this can still reach 10 GB or more.\nChoose a drive with enough free space.",  # TODO
    "astap_path":                   "✅ ASTAP found: {path}",  # TODO
    "astap_path_not_found":         "⚠️ ASTAP not found.",  # TODO
    "astap_download_link":          "Download ASTAP (fast local solver, recommended for Windows)",  # TODO
    "astap_db_label":               "narrow FOV (<5°)",  # TODO
    "astap_wide_db_label":          "wide FOV (>5°)",  # TODO
    # ── Dwarf device ──────────────────────────────────────────────────────────────
    "dwarf_device":                 "Dwarf Device",  # TODO
    "dwarf_connect":                "Dwarf Connect",  # TODO
    "dwarf_not_connected":          "Dwarf Device not connected",  # TODO
    "dwarf_deleted":                "Dwarf deleted.",  # TODO
    "add_dwarf":                    "➕ Add New Dwarf",  # TODO
    "add_dwarf2":                   "➕ Add New Dwarf",  # TODO
    "dwarf_ip":                     "Enter Dwarf IP Address:",  # TODO
    "dwarf_ip_long":                "Enter the Dwarf IP Address, you can find it on the My Device Page on the Dwarflab App.",  # TODO
    "detect_mtp":                   "Detect MTP Dwarf",  # TODO
    "mtp_devices":                  "Connected MTP Devices:",  # TODO
    "mtp_device":                   "MTP Device",  # TODO
    "save_update_dwarf":            "Save / Update Dwarf",  # TODO
    "delete_dwarf":                 "🗑️ Delete Dwarf",  # TODO
    "delete_dwarf_entries":         "🗑️ Delete Dwarf Entries",  # TODO
    "select_existing_dwarf":        "Select Existing Dwarf",  # TODO
    "fill_fields_save_dwarf":       "Fill all fields and save a Dwarf first.",  # TODO
    "invalid_dwarf":                "Invalid dwarf selection",  # TODO
    "no_dwarf_selected":            "No Dwarf selected",  # TODO
    "select_dwarf":                 "Select Dwarf:",  # TODO
    "select_dwarf_label":           "Select Dwarf",  # TODO
    "first_run":                    "First run detected. Connect your Dwarf via USB, then follow the Help panel to register it.",  # TODO
    "first_setup":                  "🚀 First Setup Required",  # TODO
    "dwarf_data_deleted":           "DwarfData entries deleted.",  # TODO
    "cannot_delete_dwarf":          "Cannot delete: this Dwarf is still linked to one or more backup entries.",  # TODO
    "dwarf_target":                 "Dwarf Target",  # TODO

    # ── MTP Devices ───────────────────────────────────────────────────────────────
    "unsupported_device":           "Unsupported Device",  # TODO
    "unsupported_conn":             "Unsupported connection mode",  # TODO
    "mtp_unavailable":              "MTP functions are not available!",  # TODO
    "saved_mtp":                    "Saved MTP Devices:",  # TODO

    # ── Backup Drive configuration ────────────────────────────────────────────────
    "backup_drive":                 "Backup Drive",  # TODO
    "backup_drive_saved":           "Backup drive saved.",  # TODO
    "backup_drive_deleted":         "BackupDrive deleted.",  # TODO
    "backup_destination":           "Destination: Backup Drive",  # TODO
    "select_destination":           "Select Destination",  # TODO
    "destination_dir":              "Destination Directory:",  # TODO
    "destination_dir2":             "Destination Directory",  # TODO
    "add_backup_drive":             "➕ Add New BackupDrive",  # TODO
    "go_backup_settings":           "➕ Go to Backup Settings",  # TODO
    "save_update_drive":            "Save / Update Backup Drive",  # TODO
    "delete_backup_drive":          "🗑️ Delete Backup Drive",  # TODO
    "delete_backup_entries":        "🗑️ Delete Backup Entries",  # TODO
    "backup_entries_deleted":       "Backup entries and DwarfData deleted.",  # TODO
    "invalid_backup_drive":         "Invalid backup Drive selection.",  # TODO
    "this_folder_registered":       "This folder is already registered.",  # TODO
    "no_backup_drive_loc":          "No BackupDrive registered at this location.",  # TODO
    "no_backup_drive":              "No Backup Drive configured yet.",  # TODO
    "no_backup_selected":           "No Backup Drive selected.",  # TODO
    "need_backup_drive":            "You need to add a Backup Drive before you can backup sessions.",  # TODO
    "backup_drive_saved2":          "✅ Backup Drive saved!",  # TODO
    "select_backup_drive":          "Please select a Backup Drive.",  # TODO
    "select_existing_drive":        "Select Existing BackupDrive",  # TODO
    "select_backup_session":        "Select Backup Session:",  # TODO
    "analyze_drive":                "🔍 Analyze Current Drive",  # TODO
    "analyze_dwarf_drive":          "🔍 Analyze Dwarf Drive",  # TODO
    "drive_in_use_backup":          "This Backup Drive is still in use by one or more backup entries. Please delete them first.",  # TODO
    "drive_in_use_manual":          "This Backup Drive is still in use by one or more manual entries. Please delete them first.",  # TODO
    "backup_info_updated":          "BackupDrive info updated",  # TODO
    "no_backup_drive_sel":          "No backup drive selected.",  # TODO
    "dest_already_exists":          "The destination:\n'{dest_path}' already exists.\nAre you sure you want to continue?",  # TODO
    "notify_dest_already_exists":   "The destination: '{dest_path}' already exists!}",  # TODO
    "please_backup_dir":            "Please choose the main backup directory for your Dwarf astrophotography images or dark files.",  # TODO
    "please_astro_dir":             "Please select the Astronomy directory within the mapped USB drive.",  # TODO
    "select_astro_info":            "You can select a specific subfolder where your astrophotography session images are stored.",  # TODO
    "scanning_backup_location":     "🔍 Scanning: {location}, please wait...",  # TODO
    "button_end_analysis_errors":   "Close and Show Results",  # TODO

    # ── Backup operations ─────────────────────────────────────────────────────────
    "launch_backup":                "Launch Backup Dwarf Data...",  # TODO
    "start_backup":                 "Start Backup",  # TODO
    "cancel_backup":                "Cancel Backup",  # TODO
    "backup_complete":              "✅ Backup completed successfully!",  # TODO
    "backup_verified":              "✅ Backup complete and verified!",  # TODO
    "backup_incomplete":            "⚠️ Backup incomplete due to failures.",  # TODO
    "backup_cancelled":             "❌ Backup cancelled by user.",  # TODO
    "show_backup_data":             "🗂️ Show Backup Data",  # TODO
    "show_dwarf_data":              "🗂️ Show Dwarf Data",  # TODO
    "backup_selected":              "📦 Backup Selected Sessions",  # TODO
    "showing_backup":               "Showing Backup Data...",  # TODO
    "restore_selected":             "📦 Restore Selected Sessions",  # TODO
    "go_explore_backup":            "Would you like to go to Explore now to back up your Dwarf sessions?",  # TODO
    "delete_entries_sessions":      "Delete entries AND sessions",  # TODO
    "delete_entries_only":          "Delete entries only",  # TODO
    "manual_session_info":          "ManualSession records hold the metadata (RA/Dec, description, file paths).",  # TODO
    "select_session_for":           "Select a session for",  # TODO
    "select_a_session":             "Select a session",  # TODO
    "backup_available_on":          "Backup Available on:",  # TODO
    "all_backups":                  "(All Backups)",  # TODO
    "all_dwarfs":                   "(All Dwarfs)",  # TODO
    "all_sessions":                 "[ALL SESSIONS]",  # TODO
    "total_matching":               "Total matching sessions:",  # TODO
    "sessions_found":               "sessions were found, totaling",  # TODO
    "session_found":                "session was found, totaling",  # TODO
    "stacks_exp":                   "stacks and a total exposure time of",  # TODO
    "stack_exp":                    "stack and a total exposure time of",  # TODO
    "no_session_found":             "No Session found.",  # TODO

    # ── Transfer ──────────────────────────────────────────────────────────────────
    "transfer":                     "Transfer",  # TODO
    "transfer_mode":                "Transfer Mode",  # TODO
    "source_dir":                   "Source Directory:",  # TODO
    "source_directory":             "Source Directory:",  # TODO
    "select_source":                "Select Source",  # TODO
    "source_usb":                   "Source: Dwarf USB Drive",  # TODO
    "stop_transfer":                "🛑 Stop Transfer",  # TODO
    "transfer_running":             "🔄 Transfer running — you can browse other pages and come back.",  # TODO
    "transfer_warning":             "⚠️ Transfer in progress",  # TODO
    "transfer_close_warn":          "⚠️ Transfer in progress — closing the app will stop the transfer.",  # TODO
    "transfer_reset":               "Transfer state reset — you can start a new transfer.",  # TODO
    "transfer_history":             "📋 Transfer History",  # TODO
    "transfer_history_log":         "📋 Transfer History Log",  # TODO
    "cancel_import":                "Cancel Import",  # TODO
    "cancel_restore":               "Cancel Restore",  # TODO
    "cancel_transfer":              "Cancel Transfer",  # TODO
    "backup_session":               "Backup Session",  # TODO
    "check_integrity":              "Check Session Integrity",  # TODO
    "data_source":                  "Data source:",  # TODO
    "before":                       "Before",  # TODO
    "after":                        "After",  # TODO
    "no_source_dir":                "No source Directory selected.",  # TODO
    "no_dest_dir":                  "No destination Directory selected.",  # TODO
    "cancel_transfer_warn":         "⚠️ Closing the app will stop the transfer.",  # TODO
    "transfer_cancellation":        "🛑 Transfer cancellation requested...",  # TODO
    "no_usb_location":              "No USB location selected",  # TODO
    "usb_inaccessible":             "USB Directory is inaccessible.",  # TODO
    "select_usb_folder":            "Select USB Folder",  # TODO
    "select_sub_folder":            "Select Sub Folder",  # TODO
    "wait_complete":                "Please wait for it to complete before starting a new one.",  # TODO
    "select_src_dir":               "Select a Source Directory",  # TODO
    "select_dst_dir":               "Select a Destination Directory",  # TODO
    "start_restore":                "Start Restore",  # TODO
    "start_repair_transfer":        "Start Repair Mosaic Transfer",  # TODO
    "start_merge_transfer":         "Start Merge Mosaic Transfer",  # TODO
    "transfer_background":          "💡 Transfer runs in the background — you can navigate to other pages and return. Closing the app will stop the transfer.",  # TODO
    "copy_complete":                "Copy complete ({copied}/{total} files)",  # TODO
    "db_sync_progress":             "Database sync in progress.",  # TODO
    "ftp_read_only":                "FTP is read-only: Restore not allowed.",  # TODO
    "transferring":                 "Transferring",  # TODO
    "syncing_session_files":        "🔄 Syncing session files...",  # TODO
    "transfer_complete":            "Transfer complete: {copied}/{total} files copied successfully",  # TODO
    "transfer_cancelled":           "Transfer cancelled after {copied}/{total} files",  # TODO
    "transfer_error_msg":           "Error after {copied}/{total}: {error}",  # TODO
    "last_transfer_ok":             "Last transfer OK — {mode} | {dwarf} → {backup} | {session} ({copied}/{total} files) at {ts}",  # TODO
    "last_transfer_interrupted":    "Last transfer interrupted — {mode} | {dwarf} → {backup} | {session} ({copied}/{total} files) at {ts}",  # TODO
    "transfer_already_running":     "A transfer is already running ({copied}/{total} files copied).",  # TODO
    "transfer_interrupted":         "⚠️ Last transfer was interrupted: {copied}/{total} files copied from {src}. You can restart the transfer to complete it.",  # TODO
    "disk_full_msg":                "❌ Disk full — transfer stopped after {verified}/{total} files.",  # TODO
    "sessions_indexed":             "✅ {copied}/{total} files — {dwarf} dwarf + {backup} backup sessions indexed",  # TODO
    "force_reset_transfer":         "⚠️ Force Reset Transfer State",  # TODO
    "no_connection_available":      "No connection available",  # TODO
    "source_dwarf_ftp":             "Source: Dwarf Drive (FTP)",  # TODO
    "source_dwarf":                 "Source: Dwarf Drive",  # TODO
    "source_cali_ftp":              "Source: Dwarf CALI_FRAME (FTP)",  # TODO
    "source_cali":                  "Source: Dwarf CALI_FRAME",  # TODO
    "source_repaired_mosaic":       "Source: Repaired Mosaic Temp Directory",  # TODO
    "source_merged_mosaic":         "Source: Merged Mosaic Temp Directory",  # TODO
    "source_backup_drive":          "Source: Backup Drive",  # TODO
    "dest_backup_drive":            "Destination: Backup Drive",  # TODO
    "dest_dwarf_ftp":               "Destination: Dwarf Drive (FTP)",  # TODO
    "dest_dwarf":                   "Destination: Dwarf Drive",  # TODO
    "the_dwarf_dir":                "the Dwarf directory!",  # TODO
    "the_backup_dir":               "the backup directory!",  # TODO
    "scanning_backup_drive":        "🔍 Scanning Backup drive, please wait...",  # TODO
    "scanning_dwarf_drive":         "🔍 Scanning Dwarf drive, please wait...",  # TODO
    "end_scanning_backup":          "End of Scanning Backup drive",  # TODO
    "end_scanning_dwarf":           "End of Scanning Dwarf drive",  # TODO
    "scanning_dwarf":               "🔍 Scanning Dwarf drive, please wait...",  # TODO
    "analysing_backup_drive":       "🔍 Analysing backup drive...",  # TODO
    "no_local_dwarf_dir":           "No local Dwarf directory",  # TODO
    "archive_mode":                 "Archive",  # TODO
    "restore_mode":                 "Restore",  # TODO
    "ftp_not_connected":            "❌ FTP Error: not connected",  # TODO
    "ftp_disconnected":             "FTP disconnected",  # TODO
    "no_restacked":                 "No RESTACKED or STARTRAILS folder found on FTP or access failed",  # TODO

    # ── Explore / Sessions ────────────────────────────────────────────────────────
    "session_dir":                  "Directory",  # TODO
    "identify_target":              "🖼️ Identify Target",  # TODO
    "show_details":                 "Show Details",  # TODO
    "hide_details":                 "Hide Details",  # TODO
    "show_gallery":                 "🖼️ Show Gallery",  # TODO
    "show_fullscreen":              "Show fullscreen",  # TODO
    "open_folder":                  "📂 Browse",  # TODO
    "open_folder_icon":             "🗁 Open",  # TODO
    "open_folder_btn":              "🗁 Open",  # TODO
    "view_session":                 "🔭 View Session in Explore",  # TODO
    "no_stacked":                   "(no stacked found on Dwarf)",  # TODO
    "no_thumbnail":                 "(no thumbnail available)",  # TODO
    "favorite_add":                 "Click to Add to Favorites",  # TODO
    "favorite_remove":              "Click to Remove from Favorites",  # TODO
    "confirm_favorite_remove":      "Are you sure you want to remove this image from your favorites?",  # TODO
    "press_esc":                    "Press ESC to close the image",  # TODO
    "show_fullscreen_img":          "Show Fullscreen Image",  # TODO
    "show_fullscreen_btn":          "Show fullscreen",  # TODO
    "open_in_aladin":               "🌌 Open in Aladin",  # TODO
    "open_in_explorer":             "🔎 Open in Explorer",  # TODO
    "original":                     "📷 Original",  # TODO
    "astro_gallery":                "⭐ Astro Gallery ⭐",  # TODO
    "astro_gallery2":               "🧩 Astro Gallery",  # TODO
    "favorites_gallery":            "⭐ My Favorite images ⭐",  # TODO
    "no_images_object":             "No images found for this object.",  # TODO
    "no_images":                    "No images found.",  # TODO
    "no_fav_images":                "No favorite images found.",  # TODO
    "go_explore":                   "🔭 Go to Explore",  # TODO
    "session_list":                 "Session List",  # TODO
    "no_session_selected":          "No session selected.",  # TODO
    "favorite_updated":             "Favorite updated.",  # TODO
    "session_removed":              "Session removed from database.",  # TODO
    "session_not_found":            "Session not found",  # TODO
    "session_not_found_db":         "Session not found in database.",  # TODO
    "delete_session":               "🗑️ Delete Session",  # TODO
    "delete_session_btn":           "🗑️ Delete session",  # TODO
    "delete_manual_entries":        "🗑️ Delete Manual Entries",  # TODO
    "also_delete_manual":           "🗑️ Also delete ManualSession records?",  # TODO
    "no_linked_manual":             "No linked Manual session found.",  # TODO
    "no_linked_dwarf":              "No linked Dwarf session for this import.",  # TODO
    "session_registered":           "✅ Session registered in database.",  # TODO
    "resolution_complete":          "✅ Resolution completed",  # TODO
    "analyzing_fits":               "🔍 Analysing Fits Image...",  # TODO
    "no_fits_resolve":              "No FITS files to resolve.",  # TODO
    "no_info_fits":                 "No info found in FITS file!",  # TODO
    "not_fits_url":                 "Not a FITS file URL",  # TODO
    "resolve_file":                 "🪐 Resolve File",  # TODO
    "resolve_files":                "🪐 Resolve Files",  # TODO
    "only_backed_up":               "Only show backed up sessions present on selected Dwarf",  # TODO
    "only_backed_not_dwarf":        "Only show backed up sessions but deleted on selected Dwarf",  # TODO
    "only_duplicates":              "Only show duplicates backed up sessions",  # TODO
    "only_not_backed":              "Only show sessions not yet backed up on selected Dwarf",  # TODO
    "only_already_backed":          "Only show sessions already backed up on selected Dwarf",  # TODO
    "prepare_siril":                "📡 Prepare for Siril",  # TODO
    "filter_objects":               "🔍 Filter objects...",  # TODO
    "view_linked_manual":           "🔗 View linked Manual session",  # TODO
    "show_panels":                  "🧩 Show Current Panels",  # TODO
    "manual_sessions_found":        "manual sessions found.",  # TODO
    "last_scan_label":              "Last Scan on:",  # TODO
    "taken":                        "Taken",  # TODO
    "restack":                      "Restack",  # TODO
    "stacked_shots":                "stacked shots for a total exposure time of",  # TODO
    "stacked_shots_one":            "stacked shot for a total exposure time of",  # TODO
    "classified_as":                "Classified as:",  # TODO
    "directory_size":               "Directory Size",  # TODO
    "filename":                     "Filename",  # TODO
    "panels_found":                 "panel(s) found",  # TODO
    "images_found":                 "images found",  # TODO
    "fits_files_in_folder":         "FITS file(s) in session folder",  # TODO
    "no_fits_on_disk":              "No sub-exposure fits files were found on the disk",  # TODO
    "folder_not_exist":             "Folder does not exist:\n{path}",  # TODO
    "folder_deleted":               "Folder deleted:\n{path}",  # TODO
    "error_deleting_folder":        "Error deleting folder:\n{e}",  # TODO
    "fits_cleanup_confirm_title":   "Confirm FITS Cleanup on Dwarf",  # TODO
    "fits_cleanup_confirm_msg":     "⚠️ Are you sure you want to clean up FITS files on the Dwarf for this session?\n\nAll raw FITS files will be permanently removed.\nThe final stacked FITS file will be kept.\n\n",  # TODO
    "image_quality":                "Images quality: ",  # TODO

    # ── Manual Session ────────────────────────────────────────────────────────────
    "add_manual_session":           "Add Manual Session",  # TODO
    "edit_manual_session":          "Edit Manual Session",  # TODO
    "import_files":                 "Import Files",  # TODO
    "update_session_files":         "Update Session Files",  # TODO
    "fits_files_list":              "Added FITS files list",  # TODO
    "choose_failed":                "Choose Failed session",  # TODO
    "choose_new":                   "Choose new session",  # TODO
    "edit_session":                 "✏️ Edit session",  # TODO
    "view_linked_dwarf":            "🔗 View linked Dwarf session",  # TODO
    "identify_target_btn":          "🖼️ Identify target",  # TODO
    "select_local_fits":            "Select Local FITS Files (optional)",  # TODO
    "select_local_jpg":             "Select Local JPG Files (optional)",  # TODO
    "select_local_png":             "Select Local PNG Files (optional)",  # TODO
    "files_already_session":        "Files already in session (edit mode)",  # TODO
    "primary_fits_deleted":         "Primary FITS deleted — please upload a replacement.",  # TODO
    "db_saved_failed":              "⚠️ Files saved but database registration failed.",  # TODO
    "tag_optional":                 "Help: Tag is Optional. Leave empty for a single version.\nUse a tag (e.g. 'v2', 'Siril') to keep multiple imports of the same session side by side.\n",  # TODO
    "folder_not_in_loc":            "Selected folder is not inside the Location folder.",  # TODO
    "fits_icon_clicked":            "FITS icon clicked",  # TODO
    "jpg_icon_clicked":             "JPG icon clicked",  # TODO
    "png_icon_clicked":             "PNG icon clicked",  # TODO
    "copy_fits_jpg":                "Copy Fits/JPG Session Files, Check it to do Megastack on Dwarf",  # TODO
    "please_select_session":        "Please select a session",  # TODO
    "set_cali_loc":                 "Please set a CALI_FRAME location.",  # TODO
    "please_select_dwarf":          "Please select a Dwarf first",  # TODO
    "empty_archive":                "🗑️ Empty Local Archive",  # TODO
    "remove_all_files":             "🗑️ Remove all files",  # TODO

    # ── DSO Catalog ───────────────────────────────────────────────────────────────
    "catalog":                      "Catalog",  # TODO
    "assign_dso":                   "Assign/Change DSO",  # TODO
    "dso_assigned":                 "DSO assigned/updated!",  # TODO
    "delete_unused":                "Delete Astro Objects not used anymore",  # TODO
    "astro_purged":                 "AstroObject data have been purged!",  # TODO
    "export_csv":                   "Export Associations to CSV",  # TODO
    "constellation_exact":          "Constellation (exact)",  # TODO
    "type_exact":                   "Type (exact)",  # TODO
    "custom_description":           "Edit or enter custom description",  # TODO
    "select_dso":                   "Select DSO",  # TODO
    "search_dso":                   "Search (designation, name, constellation, type)",  # TODO
    "dso_astro_assoc":              "🔭 AstroObject to DSO Association",  # TODO
    "error_astro_purge":            "Error occurs during AstroObject purge!",  # TODO

    # ── Session Notes ─────────────────────────────────────────────────────────────
    "notes_title":                  "🔭 Session Observations",  # TODO
    "notes_moon":                   "Moon:",  # TODO
    "notes_seeing":                 "Seeing:",  # TODO
    "notes_location":               "📍 Observation site",  # TODO
    "notes_summary":                "Summary (shown directly)",  # TODO
    "notes_summary_ph":             "e.g. Great night, light wind, good transparency",  # TODO
    "notes_detail":                 "Detailed notes",  # TODO
    "notes_detail_ph":              "Conditions, equipment, observations...",  # TODO
    "notes_add_btn":                "📋 Add observations",  # TODO
    "notes_edit_tooltip":           "Edit observations",  # TODO
    "notes_saved":                  "Observations saved ✓",  # TODO
    "notes_after_import":           "Observations can be added after the session is imported.",  # TODO
    "notes_section":                "📋 Observations (optional)",  # TODO

    # ── Moon phases ───────────────────────────────────────────────────────────────
    "moon_new":                     "New Moon",  # TODO
    "moon_waxing_crescent":         "Waxing Crescent",  # TODO
    "moon_first_quarter":           "First Quarter",  # TODO
    "moon_waxing_gibbous":          "Waxing Gibbous",  # TODO
    "moon_full":                    "Full Moon",  # TODO
    "moon_waning_gibbous":          "Waning Gibbous",  # TODO
    "moon_last_quarter":            "Last Quarter",  # TODO
    "moon_waning_crescent":         "Waning Crescent",  # TODO

    # ── Dark Library ──────────────────────────────────────────────────────────────
    "dark_library":                 "Dark Library",  # TODO
    "dark_inventory":               "Dark Inventory",  # TODO
    "dark_library_deleted":         "Dark Library deleted.",  # TODO
    "save_update_library":          "Save / Update Library",  # TODO
    "delete_library":               "🗑️ Delete Library",  # TODO
    "add_library":                  "➕ Add New Library",  # TODO
    "select_existing_lib":          "Select Existing Dark Library",  # TODO
    "dark_lib_saved":               "✅ Dark Library saved.",  # TODO
    "dark_lib_failed":              "❌ Failed to save library.",  # TODO
    "scan_library":                 "🔍 Scan Library",  # TODO
    "download_darks":               "📥 Download Darks",  # TODO
    "show_all_libraries":           "📋 Show All Libraries",  # TODO
    "no_library_selected":          "No library selected.",  # TODO
    "no_dark_files":                "⚠️ No dark files found matching the naming convention.",  # TODO
    "set_cali_first":               "Please set a CALI_FRAME location first.",  # TODO
    "save_lib_first":               "Save the library first to set the CALI_FRAME location.",  # TODO
    "no_subfolders":                "No subdirectories found in Astronomy folder.",  # TODO
    "darks_matched_range":          "dark(s) matched (temp in range)",  # TODO
    "darks_matched_closest":        "dark(s) matched (closest temp)",  # TODO
    "no_darks_found":               "❌ No matching darks found",  # TODO
    "min_temp":                     "MinTemp",  # TODO
    "max_temp":                     "MaxTemp",  # TODO
    "found_one_fits":               "Found one fits image on the disk",  # TODO
    "found_fits_images":            "fits images on the disk",  # TODO
    "found_failed_images":          "failed images on the disk",  # TODO

    # ── Mosaic ────────────────────────────────────────────────────────────────────
    "mosaic_result":                "🌅 Mosaic Result",  # TODO
    "create_mosaic":                "🖼️ Create Mosaic",  # TODO
    "show_mosaic_gallery":          "🖼️ Show Mosaic Gallery",  # TODO
    "mosaic_gallery":               "🧩 Mosaic Gallery",  # TODO
    "new_stitch":                   "✨ New Stitch",  # TODO
    "stitch_params":                "🔭 Stitch Parameters",  # TODO
    "create_fits_close":            "🔭 Create FITS & Close",  # TODO
    "stitching_failed":             "❌ Stitching Failed",  # TODO
    "stitching":                    "⚙️ Stitching Mosaic...",  # TODO
    "creating_fits":                "⚙️ Creating FITS Mosaic...",  # TODO
    "mosaic_accepted":              "✅ Mosaic accepted!",  # TODO
    "mosaic_saved":                 "✅ Mosaic saved to session!",  # TODO
    "mosaic_discarded":             "Mosaic discarded.",  # TODO
    "mosaic_discarded_restored":    "Mosaic discarded — files restored.",  # TODO
    "mosaic_fits_created":          "✅ FITS mosaic created!",  # TODO
    "mosaic_in_error":              "🔴 Mosaic Sessions in Error",  # TODO
    "no_mosaic_dir":                "Directory does not contain MOSAIC",  # TODO
    "primary_not_mosaic":           "⚠️ Primary does not contain MOSAIC.",  # TODO
    "mosaic_params":                "🔭 Mosaic & Stitch Parameters",  # TODO
    "change_params":                "⚙️ Change Parameters",  # TODO
    "params_applied":               "✅ Parameters applied for this run",  # TODO
    "stitch_params_saved":          "✅ Stitch parameters saved",  # TODO
    "reset_defaults":               "↺ Reset to defaults",  # TODO
    "verify_orientation":           "Verify orientation before merge",  # TODO
    "start_merge":                  "🔀 Start Merge",  # TODO
    "repair_transfer":              "🔧 Repair Transfer (Temp → Dwarf)",  # TODO
    "merge_transfer":               "🔧 Merge Transfer (Temp → Dwarf)",  # TODO
    "repair_mosaic":                "Repair Mosaic Session",  # TODO
    "select_primary":               "📁 Select Primary Session",  # TODO
    "select_secondary":             "📁 Select Secondary Session",  # TODO
    "primary_session":              "📂 Primary Session (base mosaic)",  # TODO
    "secondary_session":            "📂 Secondary Session (Additional Data to Merge)",  # TODO
    "no_primary":                   "❌ Please select a Primary Session.",  # TODO
    "no_secondary":                 "❌ Please select a Secondary Session.",  # TODO
    "sessions_different":           "⚠️ Primary and Secondary sessions must be different.",  # TODO
    "failed_session":               "Failed Session",  # TODO
    "could_not_resolve":            "Could not resolve selected sessions",  # TODO
    "sessions_merged":              "Sessions merged:",  # TODO
    "merge_aborted":                "⚠️ Could not create backup — merge aborted.",  # TODO
    "no_sessions_selected":         "No sessions selected",  # TODO
    "sessions_in_error":            "⚠️ Sessions in Error",  # TODO
    "no_sessions_error":            "✅ No Sessions in error.",  # TODO
    "sessions_error_title":         "Sessions in Error",  # TODO
    "merge_mode":                   "Merge",  # TODO
    "repair_mode":                  "Repair",  # TODO
    "mosaic_merge_desc":            "Primary = base mosaic. Secondary = session whose data will be merged into it. Result goes to the work directory.",  # TODO
    "mosaic_repair_desc":           "Primary = reference mosaic (small but correct). Secondary = session to repair. Result goes to the work directory.",  # TODO
    "primary_session_dir":          "Primary Session Directory:",  # TODO
    "secondary_session_dir":        "Secondary Session Directory:",  # TODO
    "path_detected":                "✅ Path detected.",  # TODO
    "path_not_detected":            "❌ Path not detected.",  # TODO
    "primary_session_repair":       "📂 Primary Session (reference — correct mosaic)",  # TODO
    "secondary_session_repair":     "📂 Secondary Session (session to repair)",  # TODO
    "confirm_continue":             "Confirm and continue",  # TODO
    "no_thumbnail_check":           "No thumbnail available — check orientation manually",  # TODO
    "output_directory":             "Output Directory:",  # TODO
    "select_session_repair":        "Select a session to repair:",  # TODO
    "copy_to_dwarf":                "📁 Copy to Dwarf now",  # TODO
    "use_as_secondary":             "🔧 Use as Secondary Session",  # TODO
    "mosaic_stitch_failed":         "Mosaic stitching has failed!",  # TODO
    "no_sessions_error2":           "No Sessions in error.",  # TODO

    # ── SkyBot / Comet search ─────────────────────────────────────────────────────
    "comet_expansion_title":        "☄️ Nearby comets & asteroids (SkyBot / IMCCE)",  # TODO
    "col_type":                     "Type",  # TODO
    "col_mag":                      "Mag (V)",  # TODO
    "searching_comets":             "⏳ Searching comets…",  # TODO
    "no_session_date_skybot":       "⚠️ No session date available — cannot query SkyBot.",  # TODO
    "comet_error":                  "☄️ Unexpected error:",  # TODO
    "comets_found_searching":       "comet(s) found — searching asteroids…",  # TODO
    "no_comets_searching":          "⏳ No comets found — searching asteroids…",  # TODO
    "no_comets_asteroids":          "✅ No comets or asteroids found within 4° at the time of this session.",  # TODO
    "comet_copied":                 "copied to description — click 💾 Save to confirm.",  # TODO
    "max_magnitude":                "Max magnitude",  # TODO
    "apply_filter":                 "Apply filter",  # TODO
    "objects_shown":                "object(s) shown",  # TODO
    "click_to_use":                 "click ➕ to use as description",  # TODO
    "objects_fainter":              "object(s) found but all fainter than mag {limit:.1f} — try increasing the limit.",  # TODO
    "mag_tooltip":                  "Objects fainter than this value are excluded (Dwarf II ≈ mag 13–15)",  # TODO

    # ── Notifications ─────────────────────────────────────────────────────────────
    "notif_api_key_saved":          "API key saved successfully!",  # TODO
    "notif_backup_saved":           "Backup drive saved.",  # TODO
    "notif_dwarf_deleted":          "Dwarf deleted.",  # TODO
    "notif_db_failed":              "DB removal failed.",  # TODO
    "notif_backup_entries_deleted": "Backup entries and DwarfData deleted.",  # TODO
    "notif_select_dso_first":       "Please select a DSO first.",  # TODO
    "notif_no_folder":              "No folder selected!",  # TODO
    "notif_cannot_remove_fits":     "Cannot remove main FITS while others are present!",  # TODO
    # ── Observation Locations ─────────────────────────────────────────────────
    "loc_title":                    'Observation Locations',  # TODO
    "loc_add":                      '➕ Add Location',  # TODO
    "loc_edit":                     'Edit Location',  # TODO
    "loc_name":                     'Name',  # TODO
    "loc_latitude":                 'Latitude',  # TODO
    "loc_longitude":                'Longitude',  # TODO
    "loc_address":                  'Address',  # TODO
    "loc_comment":                  'Comment',  # TODO
    "loc_set_default":              '⭐ Set as default',  # TODO
    "loc_is_default":               '⭐ Default',  # TODO
    "loc_open_map":                 '🗺️ Map',  # TODO
    "loc_no_locations":             'No observation locations yet.',  # TODO
    "loc_confirm_delete":           'Delete this location?',  # TODO
    "loc_saved":                    'Location saved.',  # TODO
    "loc_deleted":                  'Location deleted.',  # TODO
    "loc_name_required":            'Name is required.',  # TODO
    "loc_apply_session":            '📍 Apply to session',  # TODO
    "loc_manage":                   'Manage locations',  # TODO
    "loc_none":                     '(no location)',  # TODO

    "loc_detect":                   'Detect my location',  # TODO
    "loc_detecting":                'Detecting...',  # TODO
    "loc_detect_failed":            'Location detection failed.',  # TODO

    # ── Sky Position Search ─────────────────────────────────────────────────────
    "sky_search_title":             'Find sessions near an object',  # TODO
    "sky_search_catalog":           'DSO Catalog',  # TODO
    "sky_search_online":            'Search online (Simbad)',  # TODO
    "sky_search_constellation":     'Constellation',  # TODO
    "sky_search_type":              'Type',  # TODO
    "sky_search_name":              'Object name...',  # TODO
    "sky_search_simbad_ph":         'e.g. Betelgeuse, HD 12345...',  # TODO
    "sky_search_not_found":         'Object not found in Simbad.',  # TODO
    "sky_search_radius":            'Radius',  # TODO
    "sky_search_found":             'Found {n} object(s) within {r:.1f}° of {label}',  # TODO
    "sky_search_none":              'No sessions within {r:.1f}° of {label}',  # TODO
    "sky_search_show":              'Show sessions',  # TODO
    # ── FITS / Restore / Mosaic notifications ─────────────────────────────────
    "fits_cleanup_running":         "Running cleanup on Dwarf Dir: '{path}'",  # TODO
    "fits_deleted_count":           '{count} FITS files on Dwarf have been deleted.',  # TODO
    "fits_deleted_one":             'One FITS file on Dwarf has been deleted.',  # TODO
    "fits_deleted_none":            'No FITS files on Dwarf have been deleted.',  # TODO
    "fits_cleanup_error":           'Error cleanup folder:\n{error}',  # TODO
    "fits_creation_failed":         'FITS creation failed: {error}',  # TODO
    "fits_json_error":              '❌ Failed to generate JSON: {error}',  # TODO
    "restore_cancelled":            'Restore cancelled at {restored} restored on {total} total files, {skipped} skipped',  # TODO
    "restore_completed":            'Restore completed ✅ {restored} restored on {total} total files, {skipped} skipped',  # TODO
    "restore_error":                'Error restoring files:\n{error}',  # TODO
    "mosaic_failed":                'Mosaic failed: {error}',  # TODO
    "save_failed":                  '❌ Save failed: {error}',  # TODO
    "save_ok":                      '✅ Saved: {name}',  # TODO
    "launching_restore":            'Launching restore for {count} session(s)...',  # TODO
    "launching_backup":             'Launching backup for {count} session(s)...',  # TODO
    "folder_delete_error":          'Error deleting folder:\n{error}',  # TODO

    # ── Extra notification keys ────────────────────────────────────────────────
    "item_deleted":                 '🗑️ Deleted: {name}',  # TODO
    "auto_install_unsupported":     'Automatic installation not supported on this system.',  # TODO

    # ── Notifications — file, scan, dwarf, mosaic, transfer ──────────────────
    "file_delete_error":            'Could not delete {name}: {error}',  # TODO
    "file_not_found_disk":          'File not found on disk: {name}',  # TODO
    "file_open_error":              'Cannot open file: {error}',  # TODO
    "file_upload_ok":               '✅ Uploaded {name}',  # TODO
    "folder_selected":              '✅ Selected Folder: {path}',  # TODO
    "folder_delete_error":          'Error deleting folder:\n{error}',  # TODO    "temp_file_deleted":            '🧹 Deleted temp file: {path}',  # TODO
    "temp_file_delete_error":       'Error deleting temp file: {error}',  # TODO
    "temp_folder_created":          '✅ Temp folder created: {path}',  # TODO
    "output_folder_selected":       '✅ Output folder: {path}',  # TODO
    "access_denied_outside":        '❌ Access denied: You cannot navigate outside {path}',  # TODO
    "access_denied_source":         '❌ Access denied: source must be inside the backup directory ({path})',  # TODO
    "edit_mode_loaded":             "✏️ Edit mode: session '{name}' loaded.",  # TODO
    "fits_read_error":              'Error reading FITS: {error}',  # TODO
    "scanning_location":            '🔍 Scanning: {location}',  # TODO
    "analysis_complete":            '✅ Analysis Complete: {total} new sessions found, {deleted} sessions deleted.',  # TODO
    "analysis_complete_backup":     '✅ Analysis Complete: {total} new sessions found on backup.',  # TODO
    "analysis_complete_dwarf":      '✅ Analysis Complete: {total} new sessions found on dwarf.',  # TODO
    "analysis_errors_found":        '✅ Analysis Complete: {count} sessions with errors found.',  # TODO
    "dwarf_updated":                "Dwarf '{name}' updated.",  # TODO
    "dwarf_created":                "Dwarf '{name}' created with ID {id}",  # TODO
    "dwarf_local_path_saved":       'Dwarf Local Parent path saved: {path}',  # TODO
    "dwarf_local_dir_error":        '❌ Error accessing local Dwarf Directory: {path}',  # TODO
    "dwarf_local_dir_create_error": "❌ Error: can't create Local Dwarf Directory",  # TODO
    "primary_session_set":          '✅ Primary session: {name}',  # TODO
    "secondary_session_set":        '✅ Secondary session: {name}',  # TODO
    "primary_source_set":           '✅ Primary source → {source}: {path}',  # TODO
    "secondary_source_set":         '✅ Secondary source → {source}: {path}',  # TODO
    "no_dir_available":             '⚠️ No {label} directory available.',  # TODO
    "manual_sessions_relinked":     '🔗 {count} manual session(s) re-linked.',  # TODO
    "manual_sessions_unmatched":    '⚠️ {count} manual session(s) could not be matched.',  # TODO
    "error_generic":                '❌ Error: {error}',  # TODO
    "report_saved":                 'Report saved: {name}',  # TODO
    "export_failed":                'Export failed: {error}',  # TODO

    # ── Quality filter ──────────────────────────────────────────────────────────
    "quality_filter_label":         'Quality:',  # TODO
    "quality_filter_tooltip":       'Filter by quality score — 🌐 all · 🟢 good (≥65) · 🟡 fair (≥40)\nUnscored sessions always shown',  # TODO

    # ── Quality scoring ─────────────────────────────────────────────────────────
    "score_session_btn":            '🌟 Score', # TODO
    "score_no_sessions":            'No sessions to score for this object.', # TODO
    "score_running":                'Scoring {count} session(s)...', # TODO
    "score_done":                   '✅ {count} session(s) scored.', # TODO

    # ── DSO Catalog ─────────────────────────────────────────────────────────────
    "confirm_delete_astro":         'Delete this object? Sessions linked to it will lose their object assignment.', # TODO
    "astro_deleted":                '✅ Object deleted.', # TODO

    "confirm_clear_dso":            'Remove the DSO association from this object?', # TODO
    "dso_cleared":                  '✅ DSO association removed.', # TODO
    "clear":                        'Clear', # TODO

    "no_unused_astro":              'No unused objects to delete.', # TODO
    "confirm_delete_unused_astro":  '{count} unused object(s) will be permanently deleted. Continue?', # TODO

    # ── Transfer / Mosaic / MTP status messages ────────────────────────────────
    "ftp_readonly":                 'FTP is read-only.',  # TODO
    "transfer_canceled":            'Backup canceled.',  # TODO
    "no_files_to_copy":             'No files to copy.',  # TODO
    "starting_copy":                'Starting copying {total} files...',  # TODO
    "full_backup_starting":         'Full Backup, Starting copying {total} files...',  # TODO
    "end_of_backup":                'End of Backup',  # TODO
    "backup_interrupted":           'Backup interrupted!',  # TODO
    "status_idle":                  'Idle...',  # TODO
    "status_checking":              'Check Files...',  # TODO
    "status_starting":              'Starting...',  # TODO
    "status_copying":               'Copy...',  # TODO
    "status_end":                   'End...',  # TODO
    "copied_files":                 'Copied {copied}/{total} files',  # TODO
    "select_dest_dir":              'Select a destination Directory.',  # TODO
    "select_src_dir_msg":           'Select a source directory.',  # TODO
    "dest_backup_drive_label":      'Destination: Backup Drive',  # TODO
    "view_session_explore":         '🔭 View Session in Explore',  # TODO
    "backup_session_label":         'Backup Session',  # TODO
    "restore_session_label":        'Restore Session',  # TODO
    "mosaic_copying":               '📋 Copying primary session to work directory…',  # TODO
    "mosaic_copy_failed":           '❌ Copy failed.',  # TODO
    "mosaic_running":               '🚀 Running Mosaic process on work directory…',  # TODO
    "mosaic_complete":              '✅ Process complete.',  # TODO
    "mosaic_failed_cancelled":      '❌ Process failed or was cancelled.',  # TODO
    "transfer_successful":          '✅ {mode} successful!',  # TODO

    # ── Sky Map Features ───────────────────────────────────────────────────────
    "sky_map_menu":                 "Sky Map", # TODO
    "sky_map_title":                "Sky Map — Solved Sessions", # TODO
    "sky_map_open_browser":         "Open the Sky Map web page", # TODO
    "sky_map_open_hint":            "Opens the interactive sky map in your web browser", # TODO
    "sky_map_min_quality":          "Min quality:", # TODO
    "sky_map_sessions_ready":       "{n} sessions ready • ASTAP: {astap} • Nova: {nova}", # TODO
    "sky_map_col_dwarf":            "Dwarf", # TODO
    "sky_map_col_total":            "Total", # TODO
    "sky_map_col_solved":           "Solved", # TODO
    "sky_map_col_pending":          "Pending", # TODO
    "sky_map_col_no_score":         "No score", # TODO
    "sky_map_btn_scan":             "Scan", # TODO
    "sky_map_mosaic_centers":       "Mosaic centers", # TODO

    # ── Video export ────────────────────────────────────────────────────────────
    "export_video":                 'Export Video', # TODO
    "signature_name":               'Your name', # TODO
    "your_name":                    'e.g. John Doe', # TODO
    "signature_text":               'Custom text (optional)', # TODO
    "optional_text":                'e.g. My astrophotography gallery', # TODO
    "font_choice":                  'Font', # TODO
    "font_size":                    'Font size', # TODO
    "duration_per_photo":           'Duration per photo (sec)', # TODO
    "video_resolution":             'Resolution', # TODO
    "video_extra_info":             'Add Imaging Session Details', # TODO
    "video_resolution":             'Résolution', # TODO
    "video_generating":             'Generating video...', # TODO
    "video_saved":                  'Video saved', # TODO
    "generate":                     'Generate', # TODO

    "filter_favorites_only":        'Show favorites only', # TODO

    # ── Video music ─────────────────────────────────────────────────────────────
    "background_music":             'Background music', # TODO
    "no_music":                     'No music', # TODO
    "my_music":                     'My music', # TODO
    "music_file_path":              'Music file path', # TODO
    "browse_music":                 'Browse...', # TODO
    "music_copyright_warning":      'Make sure you have the rights to use this music for sharing', # TODO

    # ── FFmpeg ──────────────────────────────────────────────────────────────────
    "ffmpeg_config":                'FFmpeg (Video/Audio)', # TODO
    "ffmpeg_used_for_music":        'Used for adding background music to exported videos.', # TODO
    "ffmpeg_needed_for_music":      'Install ffmpeg to add background music to your videos.', # TODO
    "ffmpeg_install_hint":          '→ Extract and place ffmpeg.exe in extern/windows/', # TODO

    "music_folder":                'Music folder', # TODO
    "upload_music":                'Upload music file', # TODO
    "music_uploaded":              'added to music folder', # TODO
}
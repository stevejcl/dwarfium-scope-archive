# Changelog

## [V3.1.6_RC4] - 2026-05-07

### Add
    DB v11 migration, DbPageMixin and UI/tool fixes
    Bump DB to v11 and add migration to enforce UNIQUE on SessionQuality.backup_entry_id (rebuilds table when needed). 

    Open SQLite connections with check_same_thread=False and update tools to use connect_db.
    Add api helpers (get_backupDrive_id_from_backupEntry, count_unused_astro_objects, load_catalog_data) and update catalog UI to use them.
    Introduce components/db_page_mixin.DbPageMixin to auto-close page DB connections on client disconnect and apply it across multiple pages.
    Add Windows exe logging in dwarfium_scope_archive
    
### BugFix#
    Improve Transfer/App UI robustness (async JS calls, manual_update_dir, session naming, journal restore)

## [V3.1.6_RC3] - 2026-05-07

### BugFix#
    Ensure the tools directory is packaged for Windows builds: add tools to extra_data, copy tools/*.py into dist/tools, and create a tools/__init__.py at build time

## [V3.1.6_RC2] - 2026-05-06

### BugFix#
    Add Tools directory for Windows build

## [V3.1.6_RC] - 2026-05-06

### BugFix#
    import time error

## [V3.1.6] - 2026-05-06

### Add
    Improve object handling, quality filter & i18n
    Improve SQL and DB API: tighten object-match logic
    Localization: replace many hard-coded UI labels in help_locales (de/en/es/fr) with tokenized {t:...} keys and add documentation 
    add optional min_quality filtering
    add new DB helpers clear_astro_object and delete_astro_object
    add documentation for scoring / quality-related controls.

### BugFix#
     Code fix: correct column indices for astro_object_id/astro_group_id mapping

## [V3.1.5c] - 2026-05-05

### Add 
    Introduce session quality and sky-search features
    new tools (quality_scan, skybot_scan)
    Add missing Description in DSO Catalog

## [V3.1.5b] - 2026-05-01

### Add 
    Include locale files in dist and robust loaders

## [V3.1.5] - 2026-05-01

### BugFix#
    Load Translation in Windows exe

## [V3.1.4c] - 2026-04-30

### Add 
    Add SessionNotes Managment
    Add robust file copy for Session Transfer
    Begin of Multi Language
    Add Comets/Asteroid detector fot setting Target
    Add localized help content and loader
    Add ObservationLocation support & UI

### BugFix#
    ALL_SESSION Filter translat every where
    NOTES Widgedt appearance
    Error Version Comit

## [V3.1.3] - 2026-04-28

### Add 
    Add Report and DB tools, DSO assign UI and mobile fixes
    Cmd Line DB Tools add on

### BugFix# 
    Resolve UI threading/UX issues when assigning DSOs
    UI improvment in the app on mobile.

## [V3.1.2] - 2026-04-27
**Test version (published to test branches)**

### Add 
    Add DwarfSessionsError schema, migration (v7) and DB API to record mosaic sessions missing a final stacked file.
    Integrate detection into the backup scanner: register sessions with shotsInfo.json but no stacked image
    ignore MERGE/REPAIR bases, and mark sessions REPAIRED when repair completes.

    Enhance mosaic/repair logic to write repairInfo.json (MERGE/REPAIR)
    copy repaired artifacts back to the Dwarf, and update error status.
    Add UI elements across Dwarf, Explore and Mosaic pages to surface error sessions
    let users browse/open them, and pre-fill secondary session for repair.
    
    Provide mobile-responsive layout and navigation tweaks
     
    Extract app version from CHANGELOG in build scrip
    Add LAN CLI flags and safe shutdown/storage write improvements

### BugFix# 
    Avoid duplicating data in DB when using MERGE/REPAIR functionnality and MOSAIC creation
    Exclude session-origin fields from rescan updates to avoid overwriting original session metadata.
    Small fixes in mosaic algorithms (transform save path, temp extraction, FITS loading) and JSON merging of min/max temps.
    Fix some missing include and varaible typo

## [V3.1.1] - 2026-04-25
**Test version (published to test branches)**

### Add 
    Add UI improvements for background transfers
    update DB API to support editing ManualSession entries
    App lifecycle: robust storage shutdown cleanup with atomic write and removal of transient transfer keys to avoid corruption on shutdown.
    RA/DEC as fallback when FITS lacks coordinates, surface update_manual_session in edit mode to avoid duplicate rows.
    UI: harmonize button sizing across pages, center transfer progress badge in menu, add visible Stop Transfer warning banner with cancel action
    Add transfer history panel (reads transfer_journal.json) in backup UI
    Add fallback preview image scanning in manual explore.

### BugFix# 
    Adjust file utilities (files_are_different default, extract_core_name session remove .zip handling)
    small help text fixes
    - Misc: small help text fixes,
    - Change link to Astrometry open in a new tab

## [V3.1.0] - 2026-04-21
**Test version (published to test branches)**

### Add 
    Background transfers and persistent progress

### BugFix# 
    Dark Library better management

## [V3.0.9] - 2026-04-19

### Add 
    Refactor UI spinners, async flows and menu

### BugFix# 
    Improve UI responsiveness and async behavior across the app:
    Modify Help

## [V3.0.8] - 2026-04-19

### Add 
    Informs the User for the DWARF LOCAL directory : warning about size
    Add a No Backup Button to redirect the User to Backup Page
    Then add a Dialog to go the Dwarf Explore Page with the option selected to Backup a session
    Remove All DWARFS / ALL BACKUPS if only one choice to see the checbox directly.
    Correction for The Back URL corruption : using URL Encode the BACKURL to avoid problem
    Use ui.context.client.layout for Dialog with long process to avoid User Interraction before the dialog is shown
    Add Alert Message in Transfert Page to avoid closing the Transfert Page

### BugFix# 
    Fresh DB Install forgets Settings table
    Fresh DB Install runs Migration => corrected by bypass and set to Last Version
    Error When selecting a Dwarf Local Directory, Default was used
    Error 404 to Backup a session in no Backup exists
    Error In Explore Page BAD index For AUTO SELECTION For Manual Session Back URL

## [V3.0.7] - 2026-04-18

### Add 
    Add DarkLibrary Management
    Add API functions to list/create/delete DarkLibrary entries, scan CALI_FRAME folders
    Find matching darks (by exp/gain/bin/temp), locate bias/flat files, for Explore Page
    Generate Siril_session.json payloads that include matched calibration files.
    This json can be used with Dwarfium Archive Selector script in Siril
    Refactor manual session code paths: 
    Add Manual Sessions Favorite Image to Home Page

## [V3.0.6] - 2026-04-17

### Add 
    Rebuild ManualSessionEntry if need
    Add Optional Delete Manual Session
    UI Improvement for Dwarf and Backup Page
    Add some spinning cursor when loading data

### BugFix# 
    Secure Database Migration

## [V3.0.5] - 2026-04-16

### Add 
    Add Tag for ManualSession to permit multiple version of same session
	Manual Session Explore Page OK
	Add Linked to Manual Session on Explore Page

### BugFix# 
    Database migration correction, lost of Auto Increment during Migration
    Improve DB migration routine recreate current Tables
    Add rule to prevent deletion of data if Manual Session use it


## [V3.0.4] - 2026-04-13

### Add 
    Add DB request for Manual Session management
    Add Manual Session pages : Add and Explore Pages

## [V3.0.3] - 2026-04-12

### BugFix# 
    Improve mosaic repair/merge robustness & UI

### Add 
    Multi Selection in Explore Page To Transfert Sessions to Dwarf or Backup from Dwarf
    Add Support for importing StarTrails Sessions
    Improve Merge Functions - Add Image Result and Choice to Merge or Discard
    Add Params Page for Stiching Mosaic
    Improve Stiching Mosaic Algo    

## [V3.0.2] - 2026-03-28

### BugFix# 
   Improve mosaic repair/merge robustness & UI
   
   long_path used for Mosaic functions
   
### Add 
    Mosaic Page add Backup Drive Selection
	Merge Dwarf and Backup selection
	Avoid uploading Mosaic on Dwarf
   
## [V3.0.1] - 2026-03-27

### BugFix# 
   Copilot correction

## [V3.0.0] - 2026-03-26

### BugFix# 
 Many Corrections in DB function and Interface
 Filter on Explorer has been improved
 
### Add 
 Help Sytem Page : To Be continued
 Setting Pages
 Add Gallery in explorer Page
 MOSAIC Correction / Megastack pages
 Stellar Studio Page:
    File saving is working
    Database not ready for the moment

## [V2.2.8] - 2025-12-12

### Compatibility with MacOs 14+

## [V2.2.7] - 2025-10-30

### BugFix# 
 Correction for Full FTP transfer

## [V2.2.6] - 2025-09-12

### Compatibility with MacOs 13+

## [V2.2.5] - 2025-09-09

### Add Init Python Script for Mac, Linux

### BugFix# 
 Path separator comparible for Linux, Mac

## [V2.2.4] - 2025-08-28

### Add Delete Session Function

### Test new fits viewer

## [V2.2.3] - 2025-07-22

### BugFix
- Home Page correction for URL folder preview
- Use Name build from description if exists

## [V2.2.2] - 2025-07-21

### BugFix
- Remove UTF 8 char in print function for PyInstaller errors in Runtime

## [V2.2.1] - 2025-07-20

### BugFix
- Import Requests
- Change for PyInstaller errors in Runtime

## [V2.2] - 2025-07-20

### Setup Database Patch
- Better database upgrade 

### Add First Database Patch to differentiate Unknown Targets

### Add Target identification Function
- Add Dso Identification from Catalog in Explore Page
- Add multiple entries for Unknow Target so each can be identified

### Using a Local Dwarf Copy
- Show Dwarf Session Image without connection
- Better Synchonization

### Add Backup button available in Explore Page
    when the filter not yet Backed up is active

### Add Restore button available in Explore Page
    when the filter deleted on Dwarf is active

## [V2.1.1] - 2025-07-05

### Better management of Mosaic session
- Improve Display panel and use fullscree view

### BugFix
- Correction for invalid character in console

## [V2.1.0] - 2025-07-02

### This release contains pre-built zip archives for:
 - Windows
 - macOS
 - Linux

 - Added support for automatic mosaic panel detection
 - Improved file structure under dist/
 - Included release automation via GitHub Actions


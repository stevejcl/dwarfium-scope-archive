# Changelog

## [V3.0.9c] - 2026-04-24

### Add 
    Improve help, onboarding, and UI behaviors
    Guide the user to configure the UI at initial Startup
    Add Sample Image to Favorite page when none exist

### BugFix# 
    Home page: wait for client connection
    Modify Help
    Dark Library page : link between location db value improve
    First Launch: Correction in Setting Page

## [V3.0.9b] - 2026-04-19

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


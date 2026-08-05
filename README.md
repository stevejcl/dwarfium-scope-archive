# Dwarfium Scope Archive

A desktop application to **back up, organise, explore and process** your [DWARF telescope](https://www.dwarflab.com/) astrophotography sessions.

> **Current version:** V3.1.x (evolution-test branch) — actively developed.

---

## Table of Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Installation](#installation)
- [Usage](#usage)
- [Pages overview](#pages-overview)
  - [Home](#home)
  - [Dwarf Configuration](#dwarf-configuration)
  - [Backup Drive](#backup-drive)
  - [Explore](#explore)
  - [Manual Sessions](#manual-sessions)
  - [Dark Library](#dark-library)
  - [Siril Integration](#siril-integration)
  - [Transfer](#transfer)
  - [Storage Report](#storage-report)
  - [Sky Map](#sky-map)
  - [Mosaic](#mosaic)
  - [Catalog](#catalog)
  - [MTP Device](#mtp-device)
  - [Settings](#settings)
- [Tools](#tools)
- [Platform support](#platform-support)
- [Contributing](#contributing)
- [License](#license)

---

## Features

| Category | What it does |
|---|---|
| **Backup & Archive** | Scan Dwarf USB / FTP drives, index sessions into a local SQLite database, copy to a backup drive |
| **Explore** | Browse all sessions by object, filter by Dwarf or backup drive, view stacked images (JPG / PNG / FITS) |
| **Manual Sessions** | Import stacked images from Siril, GraXpert, Stellar Studio or any other tool |
| **Dark Library** | Manage `CALI_FRAME` folders, inventory darks by exposure / gain / binning / temperature
| **Siril Integration** | export a `siril_session.json` for the [Dwarfium Archive Selector] Siril script |
| **Transfer** | Copy sessions between the Dwarf and a backup drive via USB or FTP, with background transfer (navigate freely while copying) |
| **Mosaic** | Stitch multi-panel mosaics, repair partially transferred mosaics, merge panels from different sessions |
| **Storage Report** | View session sizes by backup drive or Dwarf, identify large sessions, trigger size calculation and Clean/Restore FITS directly |
| **Image Quality Score** | Automatically score sessions 0–100 based on metadata (stack rate, exposure, darks) and image analysis (dynamic range, contrast, entropy) |
| **Sky Map** | Visualise all sessions on an interactive Aladin Lite sky map, with WCS footprints, overlap detection and per-panel mosaic display |
| **Astrometry** | Resolve session RA/Dec via ASTAP (local) or Nova astrometry.net API (online fallback), storing WCS data for sky map display |
| **Session Notes** | Record observation conditions per session: moon phase, seeing, location, free-text summary and detailed notes |
| **DSO Catalog** | Match session targets to a built-in DSO catalog (NGC / IC / Messier), identify targets from RA/Dec coordinates, open in Aladin |
| **SkyBot** | Query the IMCCE SkyBot service to detect comets and asteroids visible in the field at the time of the session |
| **Video Export** | Generate a timelapse-style video slideshow from your favourite or filtered sessions with customisable captions and transitions |
| **Disk Space** | Live disk space widgets on Dwarf, Backup and Report pages with colour-coded fill bar; cached values shown when the drive is offline |
| **Dwarf Type Detection** | Auto-detect Dwarf model (Dwarf 2 / 3 / Mini) from stacked JPEG dimensions before any scan — warns if the configured type does not match |
| **DB Backup** | Automatic `.bak` on startup and `.last` on shutdown; manual backup to any folder from Settings |
| **Multi-language** | English and French UI, extensible to other languages via locale files |
| **PDF Report** | Export a summary report of your archive |
| **MTP** | Connect to Dwarf 2 via MTP (Windows) to browse and transfer without USB drive access |
| **LAN access** | Optionally expose the web UI on your local network |
| **DB Tools** | Command-line tools for diagnostics, deduplication and PDF report generation |

---

## Screenshots

### Home — favourite images slideshow
![Home page](https://github.com/user-attachments/assets/8d4f60fe-27a2-462e-a834-7c98972c011a)

### Explore — session detail with dark match badge
![Explore page](https://github.com/user-attachments/assets/eb3858c6-a241-4418-b27f-d900134a5543)

### Explore — backup and restore actions
![Explore backup](https://github.com/user-attachments/assets/e097e8f0-8b3e-4377-a9b5-87d018019524)

### Explore — identify target / Aladin view
![Identify target](https://github.com/user-attachments/assets/d760ea70-1e80-430a-b963-950daa5afaae)
![Aladin](https://github.com/user-attachments/assets/8497283d-7cd5-4896-b270-5a6e760d6c4c)

### Explore — mosaic panels
![Mosaic](https://github.com/user-attachments/assets/2e83d8a8-8a1a-432d-85f0-2f13997d1159)
![Panels](https://github.com/user-attachments/assets/8ee96ed0-018f-41bd-898c-803b9afcea91)

### Backup Drive configuration
![Backup page](https://github.com/user-attachments/assets/2c73c433-e4fb-40d2-887e-bb748ebe40ef)

### DSO Catalog — assign target
![Catalog](https://github.com/user-attachments/assets/b566b572-6575-4741-aeb1-dad76df3cd02)

---

## Installation

### Prerequisites

- **Python 3.10+**
- Windows, macOS 13+ or Linux

### 1 — Clone the repository

```bash
git clone https://github.com/stevejcl/dwarfium-scope-archive.git
cd dwarfium-scope-archive
```

### 2 — Create a virtual environment (recommended)

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3 — Install dependencies

```bash
# All platforms
pip install -r requirements.txt

# Windows only (adds MTP / Windows-specific libraries)
pip install -r requirements-windows.txt
```

### Pre-built executable (Windows)

A standalone `DwarfiumScopeArchive.exe` is available on the
[Releases](https://github.com/stevejcl/dwarfium-scope-archive/releases) page —
no Python installation required.

---

## Usage

```bash
python dwarfium_scope_archive.py
```

The application opens in your default browser at `http://localhost:8080`.

### Optional flags

| Flag | Effect |
|---|---|
| `--lan` | Expose the UI on your local network (all interfaces) |
| `--port <N>` | Change the port (default 8080) |

### Database

A SQLite database `dwarf_backup.db` is created automatically on first run in the
project directory. It is upgraded automatically on each new version — no manual
migration needed.

---

## Pages overview

### Home

Displays a **slideshow of your favourite images** — mark any session image as a
favourite from the Explore page to have it appear here.

---

### Dwarf Configuration

Register the Dwarf telescopes you own. Each entry stores:

- A name and description
- The **Astronomy directory** path when connected by USB (e.g. `I:\Astronomy`)
- The **IP address in STA Mode** for FTP / WiFi transfer
- The device type (Dwarf 2, Dwarf 3, Dwarf Mini)

**Actions available:**

- **Analyze Dwarf Drive** — scan the USB/FTP directory and index all sessions; before scanning, the app automatically checks that the configured device type matches the actual sessions by sampling stacked JPEG dimensions — warns and blocks if a mismatch is detected
- **Show Dwarf Data** — open Explore filtered to this Dwarf's sessions
- **Sessions with Errors** — list mosaic sessions without a final stacked file

A **disk space card** shows Local Data Size / Local Archive Size / Local Free Space colour-coded. A USB disk widget shows the real Dwarf disk space when connected.

> **Dwarf 2 note:** direct USB drive access is not available on Dwarf 2. Use FTP (STA Mode) or MTP (Windows only — see [MTP Device](#mtp-device)).
>
> **Dwarf 3 / Mini note:** both models share the same FTP path and cannot be distinguished via FTP alone — the configured type is trusted in that case.

---

### Backup Drive

Configure the drives where your sessions are stored. Each backup drive is linked
to one Dwarf.

**Actions available:**

- **Analyze Current Drive** — scan the backup drive and index sessions; shows a
  transfer history log with date, session name and status
- **Check Session Integrity** — compare the FITS file count on disk with the
  database record
- **Show All Backup Data** — open Explore filtered to this drive's sessions
- **Transfer History** — view the log of all past transfers with status

---

### Explore

The main session browser. Sessions are grouped by target object in the left panel.

**Filters:**

- Backup drive / Dwarf / target name / image quality score
- *Only on Dwarf* / *Only on backup* / *Not yet backed up* / *Already backed up* / *Duplicates* checkboxes

**Session gallery:**

When multiple sessions exist for the same object, a **Show Gallery** button appears. The gallery opens immediately with the first image and loads the rest in the background — navigate with Previous / Next or jump directly to a session.

**Session detail panel shows:**

- Target, RA/Dec, classification, constellation
- Date, exposure, gain, filter, temperature, lens
- Stacked shots count, total exposure time and **image quality score** (0–100, ⭐ to ⭐⭐⭐⭐⭐)
- **🎯 Dark match badge** — green (temperature in range) / orange (closest temperature) / red (no match)
- Mosaic panels preview and panorama generation
- Folder size (updated automatically when viewing a session)

**Image Quality Score** is computed in two passes:
- **Pass A (metadata)** — stack rate, total exposure, dark calibration, sensor type
- **Pass B (image analysis)** — dynamic range, contrast and entropy of the stacked JPEG

**Actions:**

- Open session folder in Explorer / Finder
- View stacked image full-screen
- **Clean FITS** — remove raw FITS files to reclaim disk space (stacked files are kept)
- **Restore FITS** — copy raw FITS files back from the backup drive
- Backup or Restore the session between Dwarf and backup drive
- Identify target — match RA/Dec against the DSO catalog, open in Aladin
- Detect nearby **comets and asteroids** via SkyBot (IMCCE)
- Score session image quality
- Add / remove from favourites
- Add / edit **Session Notes**
- View linked Manual Session
- Delete session

> **RESTACKED** and **STARTRAILS** sessions (created by the Dwarf from multi-panel or long-exposure captures) are shown alongside regular sessions. The Restore FITS button is hidden for RESTACKED sessions as they contain no raw frames.

---

### Manual Sessions

Import stacked images produced outside the Dwarf — from **Siril**, **GraXpert**,
**Stellar Studio** or any other processing tool.

Each import creates a session folder on a backup drive and registers it in the
database. Supported inputs:

| Input | Saved as |
|---|---|
| JPG preview | `stacked.jpg` |
| PNG stack | `stacked-16_{session}.png` |
| FITS stack | `stacked-16_{session}.fits` |
| Additional FITS | original filename preserved |
| Stellar Studio URL | downloaded with Auto / Denoise / Starless suffix |

**Tags** allow multiple variants of the same session to coexist (e.g. `Siril`,
`GraXpert`, `v2`).

Manual sessions appear in their own **Manual Explore** page and can be linked
back to the original raw Dwarf session.

---

### Dark Library

Manage calibration dark frame libraries for **Siril** processing.

Each library points to a `CALI_FRAME` folder on a backup drive. Dark files must
follow the naming convention:

```
dark_exp_15.0_gain_80_bin_1_14C.fits
```

**Actions:**

- **Scan Library** — inventory `CALI_FRAME/dark/` by camera, exposure, gain,
  binning and temperature
- **Download Darks** — open the Transfer page pre-configured to copy
  `CALI_FRAME` from the Dwarf to the backup drive

The 🎯 badge in Explore shows the dark match status for every session.

---
 
## Siril Integration
 
[#siril-integration](#siril-integration)
 
Dwarfium Scope Archive prepares your sessions for stacking in
[**Siril**](https://siril.org/), and can drive the process end-to-end via the
companion **Dwarfium Archive Selector** Siril Python script made by Stephan Schmidt-Bilkenroth

> An up-to-date version of the script is available in the `extern` directory
> of this project. 

Two workflows are available from **Explore**:
 
| Workflow | Use case |
| --- | --- |
| **Prepare for Siril** (single session) | Stack one session — matches darks from the Dark Library, generates `siril_session.json` |
| **Prepare for Siril** (multi-session) | Combine several sessions of the same target (same or different filters) into one deeper image |
 
### Single session
 
Selecting **Prepare for Siril** on a session copies its lights (and matching
darks, if a 🎯 match was found in the [Dark Library](#dark-library)) to a
processing folder and writes a `siril_session.json`. Run it through the
Dwarfium Archive Selector script inside Siril to calibrate, register and stack.
 
### Prepare for Siril (multi-session)
 
Selecting several sessions of the same object and clicking **🧩 Prepare for
Siril (Megastack)** opens a picker where you choose which sessions to include,
then generates a `siril_megastack.json`:
 
- **Single filter** → a straightforward deeper stack of all selected sessions.
- **Multiple filters** (e.g. Duo-Band + L, or separate Ha / OIII sessions) →
  each filter is stacked independently, then combined automatically
  (HaRGB / HOO / LRGB, based on the filters present).
- **Mosaic sessions** are supported: panels are pulled from each session's
  panel sub-folders and combined into the group for that filter.

#### Stacking mode
 
When at least one selected session is a mosaic, you can choose how its panels
are stacked:
 
| Mode | What it does | Darks |
| --- | --- | --- |
| **Raw files** (default) | Collects the raw light frames from every panel and stacks them normally | Looked up from the Dark Library as usual |
| **Already-stacked panels** | Uses each panel's own `stacked-16` FITS directly (the Dwarf already stacked it in-camera) instead of the raw sub-exposures | Skipped — already applied when the panel was stacked in-camera |
 
"Already-stacked panels" also applies to regular (non-mosaic) sessions that
only have a single `stacked-16` file of their own (e.g. a session you've
already restacked) — in that case its one stacked FITS is used as-is.
 
When the already-stacked panels come from **mosaic** sessions (different
pointings covering a wider field), the Dwarfium Archive Selector script
automatically switches to an **astrometric mosaic assembly**:
 
1. Each panel is plate-solved (local Gaia DR3 catalogue via ASTAP/Siril).
2. Panels are registered with **max framing**, so the final canvas grows to
   cover every panel instead of being cropped down to their overlap.
3. The panels are integrated with overlap normalisation, output normalisation,
   RGB equalisation, and optional edge feathering (same feather setting used
   by the [Mosaic](#mosaic) page).
This mirrors the dedicated **🧩 Build Mosaic (RESTACKED)** button, which does
the same astrometric assembly directly for `RESTACKED_` sessions (see below) —
Megastack now applies it automatically whenever the selected sessions call
for it.
 
> Requires Siril **1.4.0+** for the astrometric mosaic path (`seqplatesolve` /
> `seqapplyreg -framing=max`); the plain raw or already-stacked-panels paths
> (non-mosaic) only require Siril **1.2.0+**.
 
#### Mixing `RESTACKED_` sessions
 
`RESTACKED_` sessions (see [Explore](#explore)) are already fully processed
(calibrated, debayered, stacked) and are always treated as "already-stacked" —
you don't need to change the stacking mode for them specifically.
 
- If **every** other selected session for a given filter is *also*
  already-stacked (either `RESTACKED_` or using "Already-stacked panels"
  mode), they're all combined together in the astrometric mosaic / plain
  integration pipeline described above.
- If you mix a `RESTACKED_` session with sessions that still have **raw**
  lights, the raw pipeline (calibrate + debayer) runs for that filter group —
  and the already-processed `RESTACKED_` file is automatically **excluded**
  from it (a warning is logged) rather than being run through calibration a
  second time and corrupted. Process the `RESTACKED_` session separately, or
  switch the raw sessions to "Already-stacked panels" mode too if they also
  have per-panel stacks available.

---

### Transfer

Copy sessions between the Dwarf and a backup drive.

| Mode | Direction |
|---|---|
| **Archive** | Dwarf → Backup Drive |
| **Restore** | Backup Drive → Dwarf |

| Connection | Speed |
|---|---|
| **USB** | Fast — Dwarf connected by cable |
| **FTP** | Slower — Dwarf on the same WiFi network |

**Background transfer:** once started, you can navigate to any other page and
come back — the transfer continues in the background. A badge in the menu shows
live progress. Closing the application will stop the transfer.

A **Transfer History** log is maintained in `transfer_journal.json`.

---

### Storage Report

Identify which sessions take the most disk space on a backup drive or Dwarf.

- **Drive selector** — switch between Backup and Dwarf mode; disk space widget shows free / total with colour-coded bar (cached when offline)
- **Session table** — Date / Object / Backup size / Dwarf total / Dwarf −FITS / Quality / Explore link
- **Sorting** — Biggest (by size) or Latest (by date); limit to 20 / 50 / 100 / All
- **Calculate sizes** — measures folder sizes for sessions not yet calculated; a ⟳ icon forces recalculation of all sessions on the drive
- **Calculate Dwarf sizes** — measures both the total size and the size after a Clean FITS operation (the *−FITS* column shows what would be reclaimed)
- **Explore link** — opens the session directly in Explore with the back button returning to the same Report view
- **Dwarf type check** — warns before any calculation if the configured Dwarf type does not match the detected type

---

### Sky Map

Visualise your sessions on an interactive sky map powered by **Aladin Lite v3** (opens in an external browser window).

- Sessions are resolved via **ASTAP** (local solver) or the **Nova astrometry.net API** (online fallback)
- WCS footprints are drawn for each resolved session; mosaic panels are shown individually
- **Overlap detection** highlights sessions covering the same sky area
- Per-Dwarf catalogs; multi-session highlight overlay; zoom / rotate preview
- Configure ASTAP path and database (D50 for narrow FOV, G05 for wide FOV ≥ 5°) in Settings

---

### Mosaic

Process multi-panel mosaics captured with the Dwarf.

**Modes:**

- **Stitch** — assemble selected panels into a wide-field image using WCS
  coordinates from FITS headers
- **Merge** — combine panels from two different sessions (Primary = base,
  Secondary = additional data)
- **Repair** — fix a mosaic where the transfer was interrupted (Primary =
  small correct reference, Secondary = session to repair)

Sessions missing a final stacked file (e.g. aborted captures) are tracked in the
database and surfaced in the **Sessions with Errors** view.

---

### Catalog

Browse the built-in DSO catalog (NGC / IC / Messier). Search by name, type or
constellation. Assign or change the DSO associated with any session directly from
this page.

---

### MTP Device

Connect to a **Dwarf 2** via MTP (Media Transfer Protocol) on Windows when USB
drive mode is not available. Browse the device file system and select sessions to
transfer.

---

### Settings

- **Language** — switch between English and French (more languages can be added via `components/locales/`)
- **Theme** — light / dark mode
- **Database Backup** — shows date of last startup backup (`.bak`) and last shutdown backup (`.last`); choose a folder and click **Backup now** to save a timestamped copy anywhere
- **Dwarf Local Directory** — path to a local copy of Dwarf data for offline use
- **NOVA Astrometry** — API key for online (astrometry.net) resolution; ASTAP path and databases (D50 / G05) for local solving
- **Mosaic & Stitch parameters** — default stitch settings
- **PDF Report** — generate and open an archive summary report
- **LAN access** — enable / disable network exposure

---

## Tools

Command-line tools in the `tools/` directory, run from the project root:

```bash
python tools/db_diagnostic.py          # diagnose the database
python tools/db_cleanup_dupes.py       # remove duplicate entries
python tools/db_report_pdf.py          # generate a PDF report

python tools/quality_scan.py           # batch-score session image quality
python tools/skybot_scan.py            # batch-query SkyBot for solar system objects
python tools/astrometry_scan.py        # batch-resolve session WCS via ASTAP / Nova
python tools/video_export.py           # export a video slideshow from your sessions

python tools/check_i18n.py             # audit UI translation files
python tools/check_help.py             # audit help content translation files
```

---

## Platform support

| Platform | Status |
|---|---|
| Windows 10/11 | ✅ Full support (USB, FTP, MTP) |
| macOS 13+ | ✅ Supported (USB, FTP) |
| Linux | ✅ Supported (USB, FTP) |

> MTP support is Windows-only.

---

## Contributing

Contributions are welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Open a pull request

For bugs or feature requests, please [open an issue](https://github.com/stevejcl/dwarfium-scope-archive/issues).

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

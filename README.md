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
  - [Transfer](#transfer)
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
| **Dark Library** | Manage `CALI_FRAME` folders, inventory darks by exposure / gain / binning / temperature, export a `siril_session.json` for the [Dwarfium Archive Selector](https://github.com/stevejcl/dwarfium-siril) Siril script |
| **Transfer** | Copy sessions between the Dwarf and a backup drive via USB or FTP, with background transfer (navigate freely while copying) |
| **Mosaic** | Stitch multi-panel mosaics, repair partially transferred mosaics, merge panels from different sessions |
| **Session Notes** | Record observation conditions per session: moon phase, seeing, location, free-text summary and detailed notes |
| **DSO Catalog** | Match session targets to a built-in DSO catalog (NGC / IC / Messier), identify targets from RA/Dec coordinates, open in Aladin |
| **SkyBot** | Query the IMCCE SkyBot service to detect comets and asteroids visible in the field at the time of the session |
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

- **Analyze Dwarf Drive** — scan the USB directory and index all sessions
- **Show Dwarf Data** — open Explore filtered to this Dwarf's sessions
- **Sessions with Errors** — list mosaic sessions without a final stacked file

> **Dwarf 2 note:** direct USB drive access is not available on Dwarf 2. Use
> FTP (STA Mode) or MTP (Windows only — see [MTP Device](#mtp-device)).

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

The main session browser. Sessions are grouped by target object in the left
panel.

**Filters:**

- Backup drive / Dwarf / target name
- *Only on Dwarf* / *Only on backup* / *Not yet backed up* / *Already backed up*
  / *Duplicates* checkboxes to quickly find what needs attention

**Session detail panel shows:**

- Target, RA/Dec, classification, constellation
- Date, exposure, gain, filter, temperature, lens
- Stacked shots count and total exposure time
- **🎯 Dark match badge** — green (temperature in range) / orange (closest
  temperature) / red (no match)
- Mosaic panels preview

**Actions:**

- Open session folder in Explorer / Finder
- View stacked image full-screen
- Backup or Restore the session
- Identify target — match RA/Dec against the DSO catalog, open in Aladin
- Detect nearby **comets and asteroids** via SkyBot (IMCCE) at the time of the session
- Add / remove from favourites
- Add / edit **Session Notes** (observation conditions, location, seeing, moon phase)
- View linked Manual Session
- Delete session (from backup drive or from Dwarf)

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
- **Siril integration** — a `siril_session.json` file is generated for each
  session containing matched calibration files, ready for the
  [Dwarfium Archive Selector](https://github.com/stevejcl/dwarfium-siril) Siril script

The 🎯 badge in Explore shows the dark match status for every session.

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

- **Language** — switch between English and French (more languages can be added
  via `components/locales/`)
- **Theme** — light / dark mode
- **Dwarf Local Directory** — path to a local copy of Dwarf data for offline use
- **NOVA Astrometry** — configure an online (astrometry.net) or local
  (`solve-field`) key for automatic target resolution
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

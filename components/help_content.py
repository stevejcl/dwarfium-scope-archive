from nicegui import ui, app

help_content = {
    '/': {
        'title': 'Home — Dwarfium Scope Archive',
        'content': '''
## Welcome

Dwarfium Scope Archive helps you back up, organise and explore your Dwarf telescope sessions.

## Main features

- **Dwarf** — configure your Dwarf devices (USB path, IP address, type)
- **Backup** — configure your backup drives and scan for new sessions
- **Explore** — browse and search all backed-up sessions
- **Manual Sessions** — import custom stacked FITS/PNG/JPG files from any tool
- **Dark Library** — manage calibration frames (darks) for Siril processing
- **Transfer** — copy sessions between the Dwarf and a backup drive

## Typical workflow

1. Configure your Dwarf on the **Dwarf** page
2. Configure your backup drive on the **Backup** page
3. Use the **Transfer** page to copy sessions from the Dwarf to your backup
4. Use **Analyze Current Drive** on the Backup page to index the sessions
5. Browse everything on the **Explore** page
'''
    },

    '/Dwarf': {
        'title': 'Dwarf Configuration',
        'content': '''
## Purpose

Configure the Dwarf telescopes you own. Each Dwarf entry stores its USB path,
IP address (for FTP/WiFi transfer), and type (Dwarf2, Dwarf3, Dwarf Mini).

## Adding a new Dwarf

1. Click **➕ Add New Dwarf**
2. Enter a name (e.g. `Dwarf Mini New`)
3. Set the **Astronomy Directory** — the full path to the `Astronomy` folder on
   the Dwarf's SD card when connected by USB (e.g. `I:\\Astronomy`)
4. Set the **IP Address STA Mode** if you want WiFi/FTP transfer
5. Click **Save / Update Dwarf**

## Analyze Dwarf Drive

Scans the Dwarf's USB directory and indexes all sessions into the database.
Run this after connecting the Dwarf by USB.

## Tips

- The USB path must be accessible when you click **Analyze Dwarf Drive**
- FTP requires the Dwarf to be on the same WiFi network as your computer
- You can have multiple Dwarfs — each has its own entry

## Delete Dwarf Entries

Removes all indexed session data for this Dwarf from the database.
The files on disk are **not** deleted.
'''
    },

    '/Backup': {
        'title': 'Backup Drive Configuration',
        'content': '''
## Purpose

Configure the backup drives where your Dwarf sessions are stored.
Each backup drive is linked to one Dwarf.

## Adding a new Backup Drive

1. Click **➕ Add New BackupDrive**
2. Enter a name (e.g. `DWARF_MINI_NEW`)
3. Click **Select Folder** to choose the root folder of the backup drive
4. Optionally set an **Astronomy Directory** subdirectory
5. Select the **Dwarf** this drive belongs to
6. Click **Save / Update Backup Drive**

## Analyze Current Drive

Scans the backup drive and indexes all sessions into the database.
Run this after copying new sessions from the Dwarf.

## Check Session Integrity

Verifies that all indexed sessions still exist on disk.

## Delete Backup Entries

Removes all indexed session data for this drive from the database.
The files on disk are **not** deleted. After deleting, run
**Analyze Current Drive** to re-index.

## Delete Manual Entries

Removes ManualSessionEntry links for this drive.
The ManualSession metadata is kept so sessions can be re-linked
automatically from `shotsInfo.json` files when you re-analyze.

## Tips

- You can have multiple backup drives per Dwarf
- The backup drive does not need to be connected to save its configuration
'''
    },

    '/Explore/': {
        'title': 'Explore Sessions',
        'content': '''
## Purpose

Browse and search all sessions indexed from your backup drives and Dwarfs.

## Filters

- **Backup Drive** — filter by backup drive (or show all)
- **Dwarf** — filter by Dwarf device
- **Filter objects** — search by target name

## Session detail

Click a target in the left panel, then select a session from the
**Session list** dropdown to see:

- Target, RA/Dec, classification
- Exposure, gain, filter, temperature
- Stacked shots and total exposure time
- **🎯 Dark match** — how many calibration darks are available for this session

## Actions

- **Open** — open the session folder in Windows Explorer
- **Show Fullscreen** — view the stacked image fullscreen
- **View linked Manual Session** — jump to any Manual Session linked to this entry
- **Add/Remove Favorite** — mark sessions you want to process
- **Show Details / Hide Details** — toggle file stats and directory info

## Tips

- Use the **Only on Dwarf** / **Only on Backup** checkboxes to find sessions
  that exist in one place but not the other
- The 🎯 badge shows dark match status — green = temp in range, orange = closest temp, red = no match
'''
    },

    '/ManualExplore/': {
        'title': 'Explore Manual Sessions',
        'content': '''
## Purpose

Browse sessions imported manually — stacked images from Stellar Studio,
Siril, GraXpert or any other processing tool.

## Filters

- **Backup Drive** — filter by drive
- **Dwarf** — filter by Dwarf device
- **Session list** — select a specific session to view

## Session detail

Selecting a session shows:

- Target, RA/Dec, classification
- Date, session type, exposure, filter, temperature
- Number of FITS files in the session folder
- Stacked image preview

## Actions

- **Open** — open the session folder in Explorer
- **Show Fullscreen** — view the stacked image fullscreen
- **View linked Dwarf session** — jump to the original raw session in Explore
- **Add Favorite / Remove Favorite** — mark for processing
- **Edit Session** — update metadata or add more files
- **Delete Session** — remove files and database entry

## Tips

- Sessions are grouped by target object in the left panel
- The **manual** group contains sessions without a recognised DSO target
- Use **Edit Session** to add Starless or Denoise variants after processing
'''
    },

    '/AddManualSession/': {
        'title': 'Import Manual Session',
        'content': '''
## Purpose

Import stacked images produced outside the Dwarf — from Stellar Studio,
Siril, GraXpert, or any other tool — into the archive.

## Workflow

### 1. Select destination

Choose a **Backup Drive** and set the **Destination Directory** where the
session folder will be created.

### 2. Name the session

Enter a **Session Name** (e.g. `Cave_Nebula_Duo-Band_20260409`).
Optionally add a **Tag** (e.g. `Siril`) to distinguish variants.

### 3. Upload files

- **JPG** — preview image → saved as `stacked.jpg`
- **PNG** — stacked PNG → saved as `stacked-16_{session}.png` (first file)
- **FITS** — stacked FITS → first file saved as `stacked-16_{session}.fits`,
  additional files keep their original filename

### 4. Stellar Studio URL

Paste a URL to a FITS file hosted online. Choose a **Type** suffix:
- **Auto** → `stacked-16_{session}__Auto.fits`
- **Denoise** → `stacked-16_{session}__Denoise.fits`
- **Starless** → `stacked-16_{session}__Starless.fits`

### 5. Import

Click **Import Files** to copy all files to the destination folder and
register the session in the database.

After a successful import, click **🔭 View Session in Explore** to jump
directly to the session in Manual Explore.

## Tips

- The first FITS file provides session metadata (RA, Dec, exposure, filter)
- Additional FITS files with meaningful names (e.g. `Cave_Nebula_Starless.fits`)
  keep their original names — no rename needed
- You can edit an existing session to add more files later
'''
    },

    '/DarkLibrary': {
        'title': 'Dark Library',
        'content': '''
## Purpose

Manage calibration dark frame libraries for Siril processing.
Each library points to a `CALI_FRAME` folder on a backup drive.

## Dark file naming convention

Dark files must follow this format for matching to work:
```
dark_exp_15.0_gain_80_bin_1_14C.fits
```
Where: `exp` = exposure in seconds, `gain` = gain value,
`bin` = binning (1 or 2), temperature in °C.

## Adding a library

1. Click **➕ Add New Library**
2. Select the **Dwarf** and **Backup Drive**
3. Click **Select Folder** to choose the `CALI_FRAME` folder
   (the dialog opens at the backup drive root — navigate one level down)
4. Click **Save / Update Library**

## Scan Library

Reads the `CALI_FRAME/dark/` directory and shows an inventory grouped
by camera (cam_0 = Tele, cam_1 = Wide) and by exposure/gain/binning.

## Download Darks

Opens the **Transfer** page with:
- Source pre-set to the Dwarf's `CALI_FRAME` folder
- Destination starting at the backup drive root

Navigate to your destination `CALI_FRAME` folder and start the transfer.
The `CALI_FRAME` directory structure (`dark/`, `bias/`, `flat/`) is
created automatically.

## Tips

- Dark libraries are matched in Explore using exposure, gain, binning and
  temperature — the 🎯 badge shows how many darks match each session
- One library per backup drive is typical, but you can have multiple
- The Dwarf2 has no temperature sensor — temperature matching will be
  added in a future version
'''
    },

    '/Transfer': {
        'title': 'Transfer',
        'content': '''
## Purpose

Copy sessions between the Dwarf and a backup drive.

## Modes

- **Archive** — copy from Dwarf → Backup Drive (normal backup)
- **Restore** — copy from Backup Drive → Dwarf (put sessions back)

## Transfer modes

- **USB** — Dwarf connected by USB cable (fastest)
- **FTP** — Dwarf connected by WiFi (slower, Dwarf must be on same network)

## Workflow

1. Select the **Dwarf** and **Backup Drive**
2. Choose **USB** or **FTP** in the Transfer Mode selector
3. Set the **Source Directory** (or use Select Source)
4. Set the **Destination Directory** (or use Select Destination)
5. Click **Start Backup** / **Start Restore**

## Tips

- After a transfer, the Backup page will automatically re-analyze the drive
  to index any new sessions
- You can transfer a single session by selecting its folder as the source
- Multi-session transfer: the source dropdown shows all sessions — select
  multiple by navigating through them
- **Dark download mode** (from Dark Library page): source is pre-set to
  `CALI_FRAME` and destination starts at the backup drive root
'''
    },

    '/Settings': {
        'title': 'Settings',
        'content': '''
## Purpose

Configure global application settings.

## Options

- **Theme** — switch between light and dark mode
- **Storage paths** — configure where local session data is cached
- **API Keys** — set astrometry.net key for automatic target resolution

## Tips

- Dark mode and light mode can also be toggled quickly from the menu
- Settings are saved per user in browser storage
'''
    },

    '/Mosaic': {
        'title': 'Mosaic',
        'content': '''
## Purpose

Manage and process mosaic sessions captured with the Dwarf telescope.
Mosaics are multi-panel images where the Dwarf captures several adjacent
fields that are stitched together into a single wide-field image.

## Workflow

1. Select a **Dwarf** and **Backup Drive**
2. Browse the list of mosaic sessions detected on the drive
3. Select panels to include in the stitch
4. Click **Generate Panorama** to stitch the panels together

## Actions

- **Show Panel** — preview an individual mosaic panel
- **Generate Panorama** — stitch selected panels into a wide-field image
- **Repair Transfer** — fix a mosaic that was partially transferred
- **Merge Transfer** — merge panels from multiple sessions

## Tips

- Mosaic sessions are stored in `RESTACKED_DWARF_RAW_*_MOSAIC_*` folders
- The stitching uses WCS coordinates from FITS headers for alignment
- Large mosaics with many panels may take several minutes to process
'''
    },

    '/MtpDevice': {
        'title': 'MTP Device',
        'content': '''
## Purpose

Connect to a Dwarf telescope via MTP (Media Transfer Protocol) —
useful when the Dwarf appears as a camera/phone device rather than
a USB drive.

## Workflow

1. Connect the Dwarf by USB
2. On this page, click **Scan for MTP Devices**
3. Select the detected Dwarf from the list
4. Use **Browse** to navigate the device file system
5. Select sessions to transfer

## Tips

- MTP is slower than direct USB drive access
- If the Dwarf appears as a normal USB drive, use the **Transfer** page instead
- Windows may require the device to be set to "File Transfer" mode
  in the Dwarf's USB connection settings
'''
    },

    '/Catalog': {
        'title': 'Catalog',
        'content': '''
## Purpose

Browse the built-in astronomical object catalog used for automatic
target identification and session classification.

## Features

- Search by object name, type, or constellation
- View RA/Dec coordinates, size, and magnitude
- See which sessions in your archive match each object

## Object types

- **Galaxy** — external galaxies (M31, NGC 891...)
- **Nebula** — emission, reflection, planetary nebulae
- **Cluster** — open and globular clusters
- **HII Region** — ionised hydrogen regions

## Tips

- The catalog is used automatically when you analyze a backup drive —
  session targets are matched and classified
- Use **Identify Target** on any unresolved session in Explore to
  manually link it to a catalog object
- The catalog is based on standard DSO databases (NGC, IC, Messier)
'''
    },

    '/Settings': {
        'title': 'Settings',
        'content': '''
## Purpose

Configure global application settings.

## Options

- **Theme** — switch between light and dark mode
- **Storage paths** — configure where local session data is cached
- **API Keys** — set astrometry.net key for automatic target resolution

## Tips

- Dark mode and light mode can also be toggled quickly from the menu
- Settings are saved per user in browser storage
'''
    },
}
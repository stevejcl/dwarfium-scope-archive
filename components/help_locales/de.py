# components/help_locales/de.py
"""
Dwarfium Scope Archive — German help content.

Generated from English as a translation template.
Translate each 'title' and 'content' value.
Remove the # TODO comment once a section is translated.
"""

HELP: dict[str, dict[str, str]] = {

    '/': {  # TODO
        'title': 'Home — Dwarfium Scope Archive',
        'content': '''
## Welcome

Dwarfium Scope Archive helps you back up, organise and explore your Dwarf telescope sessions.

## Main features

- **{t:dwarf_label}** — configure your Dwarf devices (USB path, IP address, type)
- **{t:menu_backup}** — configure your backup drives and scan for new sessions
- **{t:page_explore}** — browse and search all backed-up sessions
- **{t:menu_manual_sessions}** — import custom stacked FITS/PNG/JPG files from any tool
- **{t:page_darks}** — manage calibration frames (darks) for Siril processing
- **{t:transfer}** — copy sessions between the Dwarf and a backup drive

## Typical workflow

1. Configure your Dwarf on the **{t:dwarf_label}** page
2. Use **{t:analyze_dwarf_drive}** to index the sessions on your Dwarf
2. Configure your backup drive on the **{t:menu_backup}** page
3. Use **{t:analyze_drive}** on the **{t:page_backup}** page to index the sessions
4. Use the **{t:transfer}** page to copy sessions from the Dwarf to your backup
5. Browse everything on the **{t:page_explore}** page
6. The **{t:page_explore}** page allows also to Backup directly a selected session
''',
    },

    '/Dwarf': {  # TODO
        'title': 'Dwarf Configuration',
        'content': '''
## Purpose

Configure the Dwarf telescopes you own. Each Dwarf entry stores its USB path,
IP address (for FTP/WiFi transfer), and type (Dwarf2, Dwarf3, Dwarf Mini).

## Adding a new Dwarf

1. Click **{t:add_dwarf}**
2. Enter a name (e.g. `Dwarf Mini New`)
3. Set the **{t:astronomy_dir}** — the full path to the `Astronomy` folder on
   the Dwarf's Disk when connected by USB (e.g. `I:\\Astronomy`)
4. If you are using the Dwarf 2, a direct USB connection is not available.
   You should use one of the following methods:
   1. FTP Connection: Setup the Dwarf in STA Mode with the DwarfLab Mobile App
      1. Find the IP address of the Dwarf and enter it on this page
      2. You can then use all the function available on this page.
   2. MTP Mode, this mode is specific to Windows
      But you can still register your Dwarf in the Settings
      1. Connect the Dwarf 2 by USB
      2. Turn on the Dwarf 2 and connect to it using the Dwarflab mobile app
      3. In the app, go to to **Advanced Settings** to enable MTP
      4. On this page, click **Scan for MTP Devices**
      5. You can then register your Dwarf, but the scan function will not be available
      6. To transfer a session, you must use the MTP Page
5. Set the **{t:ip_sta_mode}** if you want WiFi/FTP transfer
6. Click **{t:save_update_dwarf}**

## Analyze Dwarf Drive

Scans the Dwarf's USB directory and indexes all sessions into the database.
Run this after connecting the Dwarf by USB.

## Show Dwarf Data

Opens the **{t:page_explore}** page to view data stored on your Dwarf.
You can then import it into your backup.
Enable **{t:only_backed_not_dwarf}** 
This will display pending sessions and show the Backup button.
Run this after running : **{t:analyze_dwarf_drive}**.

## Sessions with Errors

Opens sessions without a final stacked file.

**Possible reasons:**

    1. No frames recorded → Normal (session stopped early)
    2. Mosaic session → Frames exist but no final stack
       → Repair it from the Mosaic page

## Tips

- The USB path must be accessible when you click **{t:analyze_dwarf_drive}**
- FTP requires the Dwarf to be on the same WiFi network as your computer
- You can have multiple Dwarfs — each has its own entry

## Delete Dwarf Entries

Removes all indexed session data for this Dwarf from the database.
The files on disk are **not** deleted.
''',
    },

    '/Backup': {  # TODO
        'title': 'Backup Drive Configuration',
        'content': '''
## Purpose

Configure the backup drives where your Dwarf sessions are stored.
Each backup drive is linked to one Dwarf.

## Adding a new Backup Drive

1. Click **{t:add_backup_drive}**
2. Enter a name (e.g. `DWARF_MINI_NEW`)
3. Click **{t:select_folder}** to choose the root folder of the backup drive
4. Optionally set an **{t:astronomy_dir}** subdirectory
5. Select the **{t:dwarf_label}** this drive belongs to
6. Click **{t:save_update_drive}**

## Analyze Current Drive

Scans the backup drive and indexes all sessions into the database.
Run this after copying new sessions from the Dwarf.

Show the History of Session Transfer with date, session and status.
## Check Session Integrity

Compare the number of FITS files present to those registered in the session.
The counts may differ if bad frames were removed on the Dwarf.

## Show All Current Backup Data

Opens the **{t:page_explore}** page to view data stored on your drive.
You can then restore them to your dwarf.
Enable **{t:only_backed_not_dwarf}** 
to list deleted sessions and display the Restore button..

## Delete Backup Entries

Removes all indexed session data for this drive from the database.
The files on disk are **not** deleted. After deleting, run
**{t:analyze_drive}** to re-index.

## Delete Manual Entries

Removes ManualSessionEntry links for this drive.
The ManualSession metadata is kept so sessions can be re-linked
automatically from `shotsInfo.json` files when you re-analyze.

## Tips

- You can have multiple backup drives per Dwarf
- The backup drive does not need to be connected to save its configuration
''',
    },

    '/Explore/': {  # TODO
        'title': 'Explore Sessions',
        'content': '''
## Purpose

Browse and search all sessions indexed from your backup drives.
To view sessions currently stored on your Dwarf, go to the **{t:page_dwarf}** page
 and click the "Show Dwarf Data" button.

## Filters

- **{t:backup_drive}** — filter by backup drive (or show all)
- **{t:dwarf_label}** — filter by Dwarf device
- **{t:filter_objects}** — search by target name

## Session detail

Click a target in the left panel, then select a session from the
**{t:session_list}** dropdown to see:

- Target, RA/Dec, classification
- Exposure, gain, filter, temperature
- Stacked shots and total exposure time
- **🎯 Dark match** — how many calibration darks are available for this session

## Actions

- **{t:open_folder_btn}** — open the session folder in Windows Explorer
- **{t:show_fullscreen_btn}** — view the stacked image fullscreen
- **Backup/Restore** — Allows you to perform actions on the selected session.
- **Availability** — Depends on the selected checkboxes. See tips for more details.
- **{t:delete_session}** — Permanently removes all session data from the backup drive.
- **{t:delete_session}** — Available only if a backup exists.
    Access it via the **{t:show_dwarf_data}** button in the Dwarf Settings page.
- **{t:view_linked_manual}** — jump to any Manual Session linked to this entry
- **Add/Remove Favorite** — Toggle the session title to show or hide it on the home page
- **{t:show_details}** — toggle file stats and directory info

## Tips

- Use the **Only Show Sessonon Dwarf** / **Only on Backup** checkboxes to find sessions
  that exist in one place but not the other
- Use the **Only on Dwarf** / **Only on Backup** checkboxes to find sessions
  that exist in one place but not the other
- The 🎯 badge shows dark match status — green = temp in range, orange = closest temp, red = no match
''',
    },

    '/ManualExplore/': {  # TODO
        'title': 'Explore Manual Sessions',
        'content': '''
## Purpose

Browse sessions imported manually — stacked images from Stellar Studio,
Siril, GraXpert or any other processing tool.

## Filters

- **{t:backup_drive}** — filter by drive
- **{t:dwarf_label}** — filter by Dwarf device
- **{t:session_list}** — select a specific session to view

## Session detail

Selecting a session shows:

- Target, RA/Dec, classification
- Date, session type, exposure, filter, temperature
- Number of FITS files in the session folder
- Stacked image preview

## Actions

- **{t:open_folder_btn}** — open the session folder in Explorer
- **{t:show_fullscreen_btn}** — view the stacked image fullscreen
- **{t:view_linked_dwarf}** — jump to the original raw session in Explore
- **Add Favorite / Remove Favorite** — mark for processing
- **{t:edit_session}** — update metadata or add more files
- **{t:delete_session_btn}** — remove files and database entry

## Tips

- To Backup a Dwarf session, selct the 
- Sessions are grouped by target object in the left panel
- The **manual** group contains sessions without a recognised DSO target
- Use **{t:edit_session}** to add Starless or Denoise variants after processing
''',
    },

    '/AddManualSession/': {  # TODO
        'title': 'Import Manual Session',
        'content': '''
## Purpose

Import stacked images produced outside the Dwarf — from Stellar Studio,
Siril, GraXpert, or any other tool — into the archive.

## Workflow

### 1. Select destination

Choose a **{t:backup_drive}** and set the **{t:destination_dir2}** where the
session folder will be created.

### 2. Name the session

Enter a **{t:session_name_label}** (e.g. `Cave_Nebula_Duo-Band_20260409`).
Optionally add a **{t:tag}** (e.g. `Siril`) to distinguish variants.

### 3. Upload files

- **JPG** — preview image → saved as `stacked.jpg`
- **PNG** — stacked PNG → saved as `stacked-16_{session}.png` (first file)
- **FITS** — stacked FITS → first file saved as `stacked-16_{session}.fits`,
  additional files keep their original filename

### 4. Stellar Studio URL

Paste a URL to a FITS file hosted online. Choose a **{t:sky_search_type}** suffix:
- **Auto** → `stacked-16_{session}__Auto.fits`
- **Denoise** → `stacked-16_{session}__Denoise.fits`
- **Starless** → `stacked-16_{session}__Starless.fits`

### 5. Import

Click **{t:import_files}** to copy all files to the destination folder and
register the session in the database.

After a successful import, click **{t:view_session}** to jump
directly to the session in Manual Explore.

## Tips

- The first FITS file provides session metadata (RA, Dec, exposure, filter)
- Additional FITS files with meaningful names (e.g. `Cave_Nebula_Starless.fits`)
  keep their original names — no rename needed
- You can edit an existing session to add more files later
''',
    },

    '/DarkLibrary': {  # TODO
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

1. Click **{t:add_library}**
2. Select the **{t:dwarf_label}** and **{t:backup_drive}**
3. Click **{t:select_folder}** to choose the `CALI_FRAME` folder
   (the dialog opens at the backup drive root — navigate one level down)
4. Click **{t:save_update_library}**

## Scan Library

Reads the `CALI_FRAME/dark/` directory and shows an inventory grouped
by camera (cam_0 = Tele, cam_1 = Wide) and by exposure/gain/binning.

## Download Darks

Opens the **{t:transfer}** page with:
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
''',
    },

    '/Transfer': {  # TODO
        'title': 'Transfer',
        'content': '''
## Purpose

Copy sessions between the Dwarf and a backup drive.

## Modes

- **{t:archive_mode}** — copy from Dwarf → Backup Drive (normal backup)
- **{t:restore_mode}** — copy from Backup Drive → Dwarf (put sessions back)

## Transfer modes

- **USB** — Dwarf connected by USB cable (fastest)
- **FTP** — Dwarf connected by WiFi (slower, Dwarf must be on same network)

## Workflow

1. Select the **{t:dwarf_label}** and **{t:backup_drive}**
2. Choose **USB** or **FTP** in the Transfer Mode selector
3. Set the **{t:source_directory}** (or use Select Source)
4. Set the **{t:destination_dir2}** (or use Select Destination)
5. Click **{t:start_backup}** / **{t:start_restore}**

## Tips

- After a transfer, the **{t:page_backup}** page will automatically re-analyze the drive
  to index any new sessions
- You can transfer a single session by selecting its folder as the source
- Multi-session transfer: the source dropdown shows all sessions — select
  multiple by navigating through them
- **Dark download mode** (from Dark Library page): source is pre-set to
  `CALI_FRAME` and destination starts at the backup drive root
''',
    },

    '/Settings': {  # TODO
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
''',
    },

    '/Mosaic': {  # TODO
        'title': 'Mosaic',
        'content': '''
## Purpose

Manage and process mosaic sessions captured with the Dwarf telescope.
Mosaics are multi-panel images where the Dwarf captures several adjacent
fields that are stitched together into a single wide-field image.

## Workflow

1. Select a **{t:dwarf_label}** and **{t:backup_drive}**
2. Browse the list of mosaic sessions detected on the drive
3. Select panels to include in the stitch
4. Click **Generate Panorama** to stitch the panels together

## Actions

- **Show Panel** — preview an individual mosaic panel
- **Generate Panorama** — stitch selected panels into a wide-field image
- **{t:repair_transfer}** — fix a mosaic that was partially transferred
- **{t:merge_transfer}** — merge panels from multiple sessions

## Tips

- Mosaic sessions are stored in `RESTACKED_DWARF_RAW_*_MOSAIC_*` folders
- The stitching uses WCS coordinates from FITS headers for alignment
- Large mosaics with many panels may take several minutes to process
''',
    },

    '/MtpDevice': {  # TODO
        'title': 'MTP Device',
        'content': '''
## Purpose

Connect to a Dwarf 2 telescope via MTP (Media Transfer Protocol) —

## Workflow

1. Connect the Dwarf 2 by USB
2. Turn on the Dwarf2 and connect to it using the Dwarflab mobile app
3 .In the app, go to to **Advanced Settings** to enable MTP
2. On this page, click **Scan for MTP Devices**
3. Select the detected Dwarf from the list
4. Use **{t:open_folder}** to navigate the device file system
5. Select sessions to transfer

## Tips

- MTP is slower than direct USB drive access
- If the Dwarf appears as a normal USB drive, use the **{t:transfer}** page instead
- Windows may require the device to be set to "File Transfer" mode
  in the Dwarf's USB connection settings
''',
    },

    '/Catalog': {  # TODO
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
- Use **{t:identify_target_btn}** on any unresolved session in Explore to
  manually link it to a catalog object
- The catalog is based on standard DSO databases (NGC, IC, Messier)
''',
    },

}

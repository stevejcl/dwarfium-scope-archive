# components/help_locales/en.py
"""
Dwarfium Scope Archive — English help content.

Each key is a route string. Each value has 'title' and 'content' (Markdown).
Routes not present here fall back to English at runtime.

Placeholders like {t:add_dwarf} are resolved at display time
using the active language's translation strings — no duplication needed.
"""

HELP: dict[str, dict[str, str]] = {

    '/': {
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
- **{t:menu_report}** — view session sizes and disk usage by drive

## Home slideshow

The home page displays a slideshow of your favourite sessions.
The first image appears immediately; the remaining favourites load in the background.
Use ⭐ to remove a session from your favourites.

## Typical workflow

1. Configure your Dwarf on the **{t:dwarf_label}** page
2. Use **{t:analyze_dwarf_drive}** to index the sessions on your Dwarf
3. Configure your backup drive on the **{t:menu_backup}** page
4. Use **{t:analyze_drive}** on the **{t:page_backup}** page to index the sessions
5. Use the **{t:transfer}** page to copy sessions from the Dwarf to your backup
6. Browse everything on the **{t:page_explore}** page
7. Use **{t:menu_report}** to identify large sessions and free up space
''',
    },
    '/AnalyzeAll': {
        'title': 'Analyze everything',
        'content': '''
## Purpose

Analyzes, one after the other, the local copy of every Dwarf and every backup drive of the database -
what **{t:analyze_dwarf_drive}** and **{t:analyze_drive}** do, for all of them. The database then
matches the files again.

## When

- Another Scope Archive installation (e.g. the executable and a source run, each with its own
  database) shares the same Dwarf_Local and backup drives, and imported, transferred or deleted
  sessions there.
- A session folder was moved or removed by hand.

## How

- **For a Dwarf**, its local copy (`Dwarf_Local/DWARF_<id>`) is analyzed: the Dwarf itself needs not
  be connected, nothing is read from it.
- A folder not reachable (drive unplugged) can't be ticked.
- Untick what you don't want analyzed, then **{t:analyze_all_start}**: each line shows its result
  (+ new sessions, - entries removed) and the log follows the analyses.
- The log is also written to a file, `logs/analyze_all_<date>.log` in the application's folder (the
  last 20 kept), each line with its time: **{t:analyze_all_open_log}** opens it, for a close look.
''',
    },
    '/RecommendTonight': {
        'title': "Tonight's Targets",
        'content': '''
## Purpose

This page suggests deep-sky targets worth shooting tonight, based on your observation
location, the selected date, and your session history.

## Location and date

- **{t:tonight_location}** — pick from your saved observation locations
- **{t:tonight_date}** — the night to analyze (calendar icon)
- **{t:tonight_refresh}** — recompute recommendations for the selected location/date

## Categories

- ✨ **{t:tonight_new_targets}** — objects you've never captured before
- 🔧 **{t:tonight_incomplete_targets}** — objects with some sessions, but not enough
  total integration time (or, for mosaics, at least one panel still under-exposed)
- ✅ **{t:tonight_well_covered_targets}** — objects already well covered, hidden by default

## Filters

- **{t:tonight_max_magnitude}** — hides objects too faint for your equipment
- **{t:tonight_type}** — narrows the list to nebulae, galaxies, or clusters
- **{t:tonight_hide_covered}** — keeps the list focused on targets that still need work

## How targets are ranked

Targets are scored by how long and how high they stay above the horizon tonight, with
a bonus for new or incomplete targets. A penalty applies when a target sits close to a
bright Moon — stronger for faint nebulae, which are more affected by sky glow than
galaxies or clusters.

## Combinable targets

When two catalog objects are close enough on sky to fit in a single wide-field frame,
a note appears on the higher-scoring one.

## Aladin link

The <i class="q-icon material-icons text-primary" style="font-size:1.2em;vertical-align:-0.2em">travel_explore</i> button on each card opens the target in Aladin Lite (external browser) to
preview the field before observing.

## Plan on the Dwarf

The <i class="q-icon material-icons text-primary" style="font-size:1.2em;vertical-align:-0.2em">event</i> button on each card offers two choices:

- **Plan this target tonight** — opens Astro Dwarf Session's planning page (external
  browser) with the target and its window tonight (above 25°).
- **Add to tonight's plan** — adds it to a list of targets (5 at most by default, see
  Settings › Session), shown at the bottom
  of the window with each target's window: ✕ removes one, **Clear** empties it, and
  **Plan these targets** opens the planning page with all of them, chained over the
  night. When the list is full, adding a target offers to replace one of them. The ⌄ button
  folds the list into one small line (a click opens it again). The
  list belongs to one night and site, and is kept when you change page.

On the planning page, pick the Dwarf, programs or a native schedule, the exposure and
filter (and adjust the slots), then send. Astro Dwarf Session (3.2.3 and later) must be
running with this app's address in its Settings: it says hello every 30 s, which is how
this app knows where it is.

## Session matching

Your integration history is matched to catalog objects using, in order: an existing
manual link, a name match, or the nearest catalog object by coordinates. Sessions that
don't match anything (too far from any catalog object, or missing coordinates) aren't
counted here.

## Tips

- The first computation after changing location/date can take a few seconds
  (astronomical calculation per catalog object)
- The reference catalog can be expanded if recurring targets aren't in it yet
''',
    },
    '/Dwarf': {
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
   Under it, ✅ / ❌ says whether that folder is there now (the Dwarf
   connected by USB); ⟳ checks again once it is plugged in.
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
   **{t:session_ip}** (optional): a second FTP IP for this Dwarf, kept on this PC only (not in the
   database) - e.g. its IP on a remote site reached through Tailscale (a subnet route on the computer
   there). The FTP functions (this page, **{t:transfer}**, Import Session) use whichever of the two IPs
   answers. A link from Dwarfium Lite giving the Dwarf's IP fills it in.
6. Fill in the **{t:dwarf_ble_id}**: the last 6 characters of the MAC address printed on the
   Dwarf (the whole address can be pasted), which also end its Bluetooth name (`DWARF3_A1B2C3`).
   Dwarf on and on the network: **{t:dwarf_ble_id_read}** asks the Dwarf at its IP.
   Dwarfium-Hub uses it to link this Dwarf to the same Dwarf in Dwarfium Lite.
   Several Dwarfs on: **{t:dwarf_identify}** flashes the ring light of the Dwarf at this IP
   (through Dwarfium Lite, running; never during a capture).
7. Click **{t:save_update_dwarf}**

## Analyze Dwarf Drive

Scans the Dwarf's USB directory and indexes all sessions into the database.
Run this after connecting the Dwarf by USB.

Before the scan, Scope Archive checks that the Dwarf connected is the one chosen:
- its model, from its images;
- over FTP, its identifier: the Dwarf answering at the IP must have the **{t:dwarf_ble_id}** saved;
- its sessions: when those on the drive are already archived under another Dwarf and none under the
  chosen one, it is the other Dwarf's drive - even between two Dwarfs of the same model.

A warning then offers to choose the right Dwarf, or to continue anyway.

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

    '/Backup': {
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

## Disk Space

When a backup drive is selected, a disk space indicator shows free / total space
with a colour-coded bar (green → yellow → orange → red as free space decreases).
The last-known values are cached in `db/diskinfo.json` and displayed even when
the drive is offline.

## Analyze Current Drive

Scans the backup drive and indexes all sessions into the database.
Run this after copying new sessions from the Dwarf.
A progress bar shows the current folder being scanned and the overall count.

## Transfer History

Shows the history of session transfers with date, session name and status.

## Check Session Integrity

Compare the number of FITS files present to those registered in the session.
The counts may differ if bad frames were removed on the Dwarf.

## Show All Current Backup Data

Opens the **{t:page_explore}** page to view data stored on your drive.
Enable **{t:only_backed_not_dwarf}** to list deleted sessions and show the Restore button.

## Delete Backup Entries

Removes all indexed session data for this drive from the database.
The files on disk are **not** deleted. After deleting, run
**{t:analyze_drive}** to re-index.

## Tips

- You can have multiple backup drives per Dwarf
- The backup drive does not need to be connected to save its configuration
- Use **{t:menu_report}** to see session sizes and identify large sessions
''',
    },

    '/Explore/': {
        'title': 'Explore Sessions',
        'content': '''
## Purpose

Browse and search all sessions indexed from your backup drives.
To view sessions currently stored on your Dwarf, go to the **{t:page_dwarf}** page
and click the "Show Dwarf Data" button.

## Filters

- **{t:backup_drive}** — filter by backup drive (or show all). A disk space indicator
  shows free / total space for the selected drive, with cached values when offline.
- **{t:dwarf_label}** — filter by Dwarf device
- **{t:filter_objects}** — search by target name
- **{t:quality_filter_label}** — filter sessions by image quality score
- **{t:sky_search_title}** — find sessions within a sky radius around a DSO
- **{t:fits_filter_label}** (Dwarf mode) — the sessions whose raw FITS are still on the Dwarf, or not,
  from the Storage Report's measure (**{t:report_calc_dwarf_sizes}**); a session never measured is in neither

## Gallery

When multiple sessions exist for an object, a **{t:show_gallery}** button appears.
The gallery opens immediately with the first image and loads the rest in the background.
Use Previous / Next to browse, or Select to jump directly to that session.
The mouse wheel goes through them too - a notch a session, spun faster several (their small thumbnail
meanwhile, the full image once it stops); the automatic slideshow pauses while it turns. The position
(12 / 240) is shown under the image.

## Session detail

Click a target in the left panel, then select a session from the
**{t:session_list}** dropdown to see:

- Target, RA/Dec, classification
- Exposure, gain, filter, temperature
- Stacked shots and total exposure time with **quality score** (⭐⭐⭐⭐ 78.2)
- **🎯 Dark match** — how many calibration darks are available for this session

## Image Quality Score

Each session can be scored on a scale of 0–100 based on two passes:

- **Pass A (metadata)** — stack rate, total exposure time, dark calibration, sensor type
- **Pass B (image analysis)** — dynamic range, contrast and entropy of the stacked JPEG

Score thresholds: ⭐⭐⭐⭐⭐ Excellent (≥ 80) · ⭐⭐⭐⭐ Good (≥ 65) · ⭐⭐⭐ Average (≥ 50) · ⭐⭐ Fair (≥ 35) · ⭐ Poor (< 35)

## Actions

Under the actions, two tabs: **{t:explore_tab_infos}** (the session's details) and **{t:explore_tab_image}** (its stacked image; click it for fullscreen). They slide into each other; on a phone or tablet, swipe to switch.

The actions are shown as icons: hover one for its name (on a phone or tablet, the name is under the icon).

- **{t:open_folder_btn}** — open the session folder in Windows Explorer
- **{t:show_fullscreen_btn}** — view the stacked image fullscreen
- **{t:score_session_btn}** — score all sessions for the selected object
- **{t:explore_plan_tonight}** — tonight's window of the selected object at the default location (computed on the click), then plan it on a Dwarf in Astro Dwarf Session or add it to tonight's plan (see the Recommended tonight help)
- **{t:backup_session}** / **{t:restore_mode}** — copy sessions between Dwarf and backup drive
- **{t:delete_session}** — permanently removes all session data from the backup drive
- **{t:view_linked_manual}** — jump to any Manual Session linked to this entry
- **{t:favorite_add}** / **{t:favorite_remove}** — toggle the session on the home page slideshow
- **{t:megastack_title_short}** (Dwarf mode) — see below
- **{t:frames_title}** — see below
- **{t:wcs_mosaic_btn}** (Backup mode, a mosaic tile's session) — the Mosaic page's **{t:milky_way_mode}** tab on that tile's mosaic
- Under the details, the line saying the session is also on the Dwarf (Backup mode) or on a backup drive
  (Dwarf mode): **{t:explore_view_copy}** opens it there in Explore
- Next to the quality score: ⌫ **{t:score_clear}** (it then reads "no score"; **{t:score_session_btn}**
  scores it again), and for a solved session **{t:sky_map_hide}** / **{t:sky_map_unhide}**

## Megastack on the Dwarf

The Dwarf stacks several of its own sessions of a target together - or restacks a single one - into
`Astronomy/RESTACKED/`, like the official app's megastack. Dwarfium Lite (Astro Dwarf Session 3.2.6+)
talks to the Dwarf and follows it.

1. Dwarf mode, a Dwarf and an object selected: click **{t:megastack_title_short}**.
2. The window shows the object's sessions that can be stacked, grouped by target, with their thumbnail,
   date, images stacked, exposure and filter. Not offered: megastack results, and sessions whose raw FITS
   are known to be gone (cleaned by Clean Fits) - read on the Dwarf plugged in USB, else from the Storage
   Report's measure. Hover a thumbnail for the session's folder name.
3. Click the sessions to stack: one target only, single captures or mosaics (not mixed). Filters can be
   mixed (Duo-Band with Astro).
4. **{t:megastack_start}**: Dwarfium Lite must be running and the Dwarf connected in it. It checks the FITS
   again, then the Dwarf checks the rest itself (binning, dark frames) - a refusal is shown with its reason.

Follow it on the Dwarf's page in Dwarfium Lite (images stacked so far, the stack growing in the Tele view);
the Dwarf does nothing else meanwhile (about 1 h for 600 images). The result then appears in the Dwarf's
sessions (`RESTACKED_…`), its total exposure read from its FITS.

## Session frames

The Dwarf writes a JPG of each frame in the session's `Thumbnail` folder, named like its FITS; the frames
it rejected while stacking carry a `failed_` prefix, both. **{t:frames_title}** shows them: a click enlarges
one (arrows or the mouse wheel: previous / next - spun faster, it goes faster; space: mark it). Mark the bad ones (clouds, trails, rotation) and
**Delete the ticked frames** - their FITS and JPG go, so a megastack or a restack takes only the good ones;
**Delete the rejected frames** takes all the `failed_` ones at once. The session's sizes are measured again.

Where they go:
- **On the Dwarf** (plugged in USB - its local copy isn't the Dwarf, its FTP is read-only): deleted for
  good from it. A session backed up has them moved into its backup copy's trash at the same time (its drive
  connected); one not backed up loses them - said before.
- **On a backup drive**: into the session's trash (a `.trash` folder, in each panel for a mosaic). The Dwarf
  plugged in USB with the session still on it, a box (unticked) deletes them from the Dwarf too, for good -
  else a later backup of the session brings them back.

**The trash**: under the session's FITS in Explore, "N frames in the trash" with **{t:trash_view}** and
**{t:trash_empty_btn}**. View shows them: mark each one **{t:trash_restore}** (back into the session) or
**{t:trash_delete}**, done when you leave or with **{t:trash_apply}**. The Dwarf plugged in USB with the
session on it, the frames restored can be copied back onto it too; else the session's own restore
(Restore FITS, Transfer) puts them back later. The trash is never copied onto the Dwarf, nor seen as a
session or counted in the FITS.

## Tips

- Use **{t:only_not_backed}** / **{t:only_already_backed}** checkboxes to find sessions in one place only
- The 🎯 badge shows dark match status — green = temp in range, orange = closest, red = no match
- Use **{t:menu_report}** to view session sizes and identify sessions to clean or delete
''',
    },

    '/ManualExplore/': {
        'title': 'Explore Manual Sessions',
        'content': '''
## Purpose

Browse sessions imported manually — stacked images from Stellar Studio,
Siril, GraXpert or any other processing tool.

## Filters

- **{t:backup_drive}** — filter by drive
- **{t:dwarf_label}** — filter by Dwarf device
- **{t:session_list}** — select a specific session to view

## Gallery

When multiple sessions exist for an object, a **{t:show_gallery}** button appears
in the action bar. The gallery shows one image per session and lets you browse
and jump directly to any session. A separate **{t:show_gallery}** button inside
the session detail shows all images found within that single session.

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
- **{t:favorite_add}** / **{t:favorite_remove}** — mark for processing
- **{t:edit_session}** — update metadata or add more files
- **{t:delete_session_btn}** — remove files and database entry

## Tips

- Sessions are grouped by target object in the left panel
- The **manual** group contains sessions without a recognised DSO target
- Use **{t:edit_session}** to add Starless or Denoise variants after processing
''',
    },

    '/AddManualSession/': {
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

1. Click **{t:add_library}**
2. Select the **{t:dwarf_label}** and **{t:backup_drive}**
3. Click **{t:select_folder}** to choose the `CALI_FRAME` folder
   (the dialog opens at the backup drive root — navigate one level down)
4. Click **{t:save_update_library}**

## Scan Library

Reads the `CALI_FRAME/dark/` directory and shows an inventory grouped
by camera (cam_0 = Tele, cam_1 = Wide) and by exposure/gain/binning.

Each dark session of the Dwarf leaves its raw frames in `DWARF_DARK` (next to
`CALI_FRAME`), in a dated folder of its own (`wide_exp_15_gain_60_bin_1_2026-10-20-...`,
the temperature at the end of each file name), and the master built from them in
`CALI_FRAME` on firmwares that make one (one master per setting and temperature,
replaced by a new session at the same temperature; a newer firmware makes none).
Each master is shown with its raw frames (count, date); the raw sets without a
master (all of them on a firmware making none, an older session at a temperature
redone since, a master deleted, undated folders) are listed below them.

For a session, the darks are chosen among the `CALI_FRAME` masters and those raw
sets alike: same gain, binning, exposure and camera; then the darks of the
session's firmware (the `FIRMWARE` header of its FITS and of the raw darks, a
master taking its raws') - a firmware update can change the raw frames; when
the firmware is unknown on either side, the darks of the session's era instead,
dated within 3 months of it, before or after (a sensor gains hot pixels over
time); all of them when none is. Then the temperature closest to the session's
(±1 °C); then the most frames (a master's `_stack_N`: a session's frames at
that temperature - a master of 1 frame is as noisy as a raw frame); then the
date closest to the session's (the date of the master's dark session, the
folder's date); the master on a tie. Siril's dark optimisation makes up for a
remaining temperature gap. With `DWARF_DARK` raw frames, Siril builds the master from them;
the 🎯 badge says so.

## Download Darks

Opens the **{t:transfer}** page with:
- Source pre-set to the Dwarf's `CALI_FRAME` folder
- Destination starting at the backup drive root

Navigate to your destination `CALI_FRAME` folder and start the transfer.
The `CALI_FRAME` directory structure (`dark/`, `bias/`, `flat/`) is
created automatically.

The Dwarf's `DWARF_DARK` folder (the raw frames of its dark sessions) is copied
at the same time, next to `CALI_FRAME`.

## Tips

- Dark libraries are matched in Explore using exposure, gain, binning and
  temperature — the 🎯 badge shows how many darks match each session
- One library per backup drive is typical, but you can have multiple
- The Dwarf2 has no temperature sensor — temperature matching will be
  added in a future version
''',
    },

    '/Transfer': {
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

    '/Settings': {
        'title': 'Settings',
        'content': '''
## Purpose

Configure global application settings including language, local storage path,
astrometry solvers, and mosaic parameters.

## Language

Switch between English and French. The UI reloads immediately.

## Local Storage Path

The folder where processed session data (FITS, PNG, JPG) is cached locally.
Choose a drive with enough free space — this can exceed 10 GB with many sessions.

## Nova API Key (online solver)

[Astrometry.net](https://nova.astrometry.net) is a free online plate solver.
Create an account, generate an API key, and paste it here.
Nova is used as a fallback when ASTAP fails.

## ASTAP (local solver)

ASTAP is a fast, offline astrometry solver that runs locally on your machine.
It is strongly recommended for Windows users — no internet required.

**Download:** [https://www.hnsky.org/astap.htm](https://www.hnsky.org/astap.htm)

### Star databases

ASTAP requires a star database installed alongside the executable:

| Database | Size | Best for |
|----------|------|----------|
| **D50** | ~5 GB | General use — recommended default |
| **D20** | ~2 GB | Faster, slightly less accurate |
| **D80** | ~8 GB | Long focal length, narrow fields (<1°) |
| **G05** | ~1 GB | Wide fields >5° (Dwarf in WIDE mode) |

- **Narrow FOV** (< 5°) — use D50 or D20
- **Wide FOV** (> 5°, e.g. 24 mm lens) — use G05

The application automatically switches to G05 when the estimated field of
view exceeds 5°. Both databases can be installed simultaneously.

### Solving workflow

1. ASTAP attempts to solve the image locally (fast, ~1–5 s)
2. If ASTAP fails, Nova is used as an online fallback
3. Results are stored in the database and displayed on the Sky Map

## Session

- **{t:settings_max_sessions}** — how many targets tonight's plan holds at most (1–10, default 5),
  each one a session on the Dwarf
- **{t:settings_day_change_hour}** — before this hour, "tonight" is still the night in progress
  (default 08:00: at 2 am, last evening's night; at 10 am, the coming one). Used for the default
  date of Recommended tonight and for tonight's plan (Recommended tonight, Explore)

## Mosaic Parameters

Configure stitching parameters for mosaic sessions.
See the **Mosaic** page help for details.
''',
    },

    '/Mosaic': {
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

- **{t:show_panel}** — preview an individual mosaic panel
- **{t:generate_panorama}** — stitch selected panels into a wide-field image
- **{t:repair_transfer}** — fix a mosaic that was partially transferred
- **{t:merge_transfer}** — merge panels from multiple sessions

## {t:milky_way_mode} tab: mosaic by astrometry

A mosaic planned tile by tile (Astro Dwarf Session's Milky Way planner: "MW Tile R1C1", "MW Tile R1C2"...)
gives one session per tile. Choose the **{t:backup_drive}**: **{t:wcs_mosaic_found}** lists its mosaics - the
sessions whose names have R<row>C<col>, grouped by name and night (newest first) - or **{t:wcs_mosaic_add_folder}**
takes the FITS of a folder (its own, and the stacked FITS of its subfolders). Untick the tiles to leave out, then
**{t:wcs_mosaic_run}**:
- each tile goes where its sky is: its WCS, else it is plate solved (ASTAP, solve-field or Nova, like the
  astrometry scan), then refit on the bright stars with the lens distortion;
- the foreground (roof, trees) is left out, each tile's brightness and colour levelled to its neighbours, and
  in the overlaps the tile seen nearer its centre wins (sharper stars);
- the result, in a `MOSAIC_WCS` folder next to the sessions: a linear FITS with its WCS - to process in Siril
  (background extraction, photometric colour calibration, stretch) - and a stretched preview.

Parts of the sky no tile covers stay black. About 2 minutes and 1 GB of memory for 5 tiles.
In Explore, **{t:wcs_mosaic_btn}** on a tile's session opens this tab on its mosaic.

## Tips

- Mosaic sessions are stored in `RESTACKED_DWARF_RAW_*_MOSAIC_*` folders
- The stitching uses WCS coordinates from FITS headers for alignment
- Large mosaics with many panels may take several minutes to process
''',
    },

    '/MtpDevice': {
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

    '/Catalog': {
        'title': 'Catalog Edition',
        'content': '''
## Purpose

Link the **objects** of your archive (one per target name found in the
session folders, plus the groups = sub-folders) to the built-in **DSO
catalog** (Messier, NGC, IC, Caldwell...), and keep the archive consistent:
sessions linked to the wrong DSO, sessions filed in the wrong group.

## The list

- **{t:catalog_filter_all}** / **{t:catalog_filter_objects}** /
  **{t:catalog_filter_groups}**: show every row, only objects, or only groups
  (the default groups Unknown / MOSAIC_Unknown / Manual are listed with the
  groups). The choice is remembered.
- Per row:
  - **Assign/Change DSO**: search the catalog (name, constellation, type),
    pick the DSO, and optionally set your own description
  - **{t:move_sessions_btn}**: the archive sessions of this object or group
    (see below)
  - 🗑️: removes the **DSO link** of the object (the object itself is kept)

## Buttons

- **{t:dso_wizard_open}**: one by one, each object without DSO. The
  nearest catalog object to one of its sessions is proposed, with the
  session's stacked image to check: **{t:dso_wizard_yes}**,
  **{t:dso_wizard_no}**, another nearby candidate, or
  **{t:dso_wizard_manual}**. The plate-solved centre of the session is used
  when available, else its goto position.
- **{t:dso_check_open}**, two checks:
  - **{t:dso_check_mode_objects}**: objects having sessions further than the
    chosen distance (twice for a mosaic) from their DSO, with the DSO
    detected at each session's position — **{t:dso_check_relink}** fixes it
    (kept by the next rescan)
  - **{t:dso_check_mode_groups}**: every group at once, listing only the
    sessions far from their group (its DSO, or the position of most of its
    sessions)
- **{t:export_csv}**: the object ↔ DSO links as a CSV file.
- **{t:delete_unused}**: objects no session uses anymore.

## Sessions of an object or group

The archive sessions, newest first, with Dwarf, archive, sub-folder and
object. For each one:
- 🖼️ the stacked image, larger (with an Aladin link), to check a wide or
  mosaic field when several catalog objects are close
- 🔍 open it in Explore (e.g. to identify its target again) — the back button
  returns here with this list open
- **{t:move_button}**: moves the session folder within the archives of its
  Dwarf — to the **{t:move_root}**, an **{t:move_existing}** (sub-folders
  already holding this object are suggested) or a **{t:move_new}**, in the
  same or another archive. The folder is never renamed; only that folder is
  rescanned, and its notes, scores and plate solving follow it.

**{t:dso_check_open}** in this list only annotates it: catalog object
detected at each session's position, sessions too far from the object or
group. Nothing is changed.

## Tips

- An object's name comes from the session folder name and is never changed
  here: fix a wrong match by linking the object to the right DSO.
- Unknown / MOSAIC_Unknown / Manual objects are created one per position by
  the scan, so each can be linked to its own DSO.
- Run the groups check from time to time after adding sessions to
  sub-folders.
''',
    },

    '/Report': {
        'title': 'Storage Report',
        'content': '''
## Purpose

The Storage Report helps you identify which sessions take the most space
and decide what to clean or delete — especially useful when a Dwarf disk
or backup drive is nearly full.

## Drive selector

Choose between **Backup** and **Dwarf** mode, then select a specific drive.
A disk space indicator shows free / total space with a colour-coded bar.
Values are cached in `db/diskinfo.json` and displayed even when the drive is offline.

## Session table

Each row shows:

- **Date** — session date
- **Object** — target name (hover the session dir for the full path)
- **{t:report_size}** — size of the session's folder on the backup drive; **{t:report_backup_missing}**
  (orange) when the drive is connected but the folder isn't on it any more (moved, or put back on another
  drive) - analyze the drive again
- **{t:report_dwarf_size}** — its size on the Dwarf (plugged in USB, else its local copy)
- **{t:report_dwarf_no_fits}** — the same without its raw FITS (what Clean Fits would leave); written to
  every backup copy of the session
- **Quality** — image quality score (colour-coded)
- **Explore** — opens the session directly in the Explore page

## Sorting and filtering

- **{t:report_biggest}** — sort by backup size, largest first
- **{t:report_latest}** — sort by date, most recent first
- **{t:report_show}** — limit to 20 / 50 / 100 sessions, or **{t:report_all}**

## Calculating sizes

- **{t:report_calc_sizes}** — measures the backup folders not measured yet (column **{t:report_size}**).
- **{t:report_calc_dwarf_sizes}** — measures the sessions on the Dwarf not measured yet, with and without
  their raw FITS (columns **{t:report_dwarf_size}** / **{t:report_dwarf_no_fits}**) - it also feeds
  Explore's **{t:fits_filter_label}** filter and the megastack's window.
- ⟳ next to each button — **{t:report_calc_sizes_force}** (after a Clean Fits, for instance).

## Tips

- Sessions showing `—` for size have not been measured yet — click **{t:report_calc_sizes}**
- **{t:report_dwarf_no_fits}** = size that would remain after **Clean Fits** — compare to
  **{t:report_dwarf_size}** to see how much space you would reclaim without losing the stacked result
- Click **Explore** to open the session and run Clean Fits or delete it directly
- The back button in Explore returns to this report with the same filters active
''',
    },

    '/SkyMap': {
        'title': 'Sky Map',
        'content': '''
## Purpose

The Sky Map displays all your astrometry-resolved sessions on an interactive
celestial map powered by Aladin Lite. Each coloured rectangle represents one
observation session, colour-coded by quality score.

## Quality colours

- 🟢 **Green** — score ≥ 80 (excellent)
- 🟡 **Orange** — score 65–79 (good)
- 🔴 **Red** — score < 65 (low)
- ⬜ **Grey** — no score

## Scanning sessions

Each Dwarf has its own row in the table showing:
- **Total** — all sessions in the database
- **Solved** — sessions with astrometry resolved
- **Pending** — unsolved sessions above the quality threshold
- **No score** — sessions without a quality score

Use the **Min quality** slider to adjust which sessions are eligible for scanning.
Click **{t:sky_map_btn_scan}** to launch the astrometry solver for that Dwarf.

## Opening the map

Click **{t:sky_map_open_browser}** to open the interactive Aladin Lite map in
your browser.

## Navigating the map

- **Click** a footprint to see session details and a preview image
- **Rotate** the preview with the ↻ button
- **Zoom** the preview with + / −
- Each Dwarf has its own **layer** in Aladin — toggle visibility from the
  layer control panel (top-left of the map)
- If several sessions overlap, a list lets you choose which one to open
- **{t:sky_map_best_only}** (toolbar) — only the best-scored session of each object
  (the newest on a tie): 10 sessions of the same nebula, one on the map
- **{t:sky_map_hide}** (a session's popup) — the session leaves the map; it stays solved, so the next
  scan doesn't solve it again. **{t:sky_map_show_hidden}** shows the hidden ones greyed, their popup
  has **{t:sky_map_unhide}**. Both boxes are remembered by the browser.

## Mosaic sessions

Mosaic sessions show a bounding box covering all resolved panels.
If the mosaic was re-stitched, the global WCS is used instead of individual panels.
''',
    },

}
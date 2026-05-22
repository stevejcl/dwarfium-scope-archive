# Dwarfium Scope Archive — Test Plan v3.1.9

---

## Level 1 — Basic Installation & First Use

> **Goal:** Verify a fresh install works end-to-end for a new user.
> **Prerequisites:** Clean DB (no existing data), Dwarf connected via USB.

### 1.1 Installation
- [ ] App launches without errors
- [ ] UI displays in the selected language (FR / EN)
- [ ] Menu and navigation work on all pages
- [ ] Help buttons open the correct help page for each route

### 1.2 Add a Dwarf
- [ ] Go to **Dwarf Settings** page
- [ ] Click **Add a Dwarf**
- [ ] Enter name (e.g. `Dwarf3`)
- [ ] Select type: **Dwarf 3**
- [ ] Click **Select USB Folder** → select `I:\Astronomy` (or equivalent)
- [ ] Verify **Path detected** appears
- [ ] Save — Dwarf appears in the selector
- [ ] Verify Local Data Size / Archive Size / Free Space shown in info card
- [ ] Verify USB disk widget shows correct free space

### 1.3 Scan the Dwarf USB
- [ ] With Dwarf connected, click **Analyze USB Drive**
- [ ] **Type detection check fires** — verify no mismatch warning (correct type configured)
- [ ] Progress bar advances, log fills with scanned sessions
- [ ] Scan completes — total sessions shown
- [ ] Verify session count in DB matches expected (check via Explore)

### 1.4 Add a Backup Drive
- [ ] Go to **Backup** page
- [ ] Click **Add Backup Drive**
- [ ] Enter name (e.g. `DATA4`)
- [ ] Select root folder
- [ ] Set `Astronomy Dir` if applicable
- [ ] Link to the Dwarf created above
- [ ] Save — drive appears in selector with disk space widget

### 1.5 Transfer: Dwarf → Backup
- [ ] Go to **Transfer** page
- [ ] Select source Dwarf and destination Backup Drive
- [ ] Select a session (or all new sessions)
- [ ] Click **Transfer**
- [ ] Progress bar shows folder count and session count
- [ ] Transfer completes — success notification
- [ ] Session appears in **Explore** page under the correct object

### 1.6 Explore — Basic Navigation
- [ ] Open **Explore**, select the backup drive
- [ ] Object list loads on the left
- [ ] Select an object — session dropdown populates
- [ ] Select a session — detail panel shows:
  - Date, exposure, gain, filter, temperature
  - Number of stacked shots
  - Stacked image preview
- [ ] **Open Folder** button works
- [ ] **Full Screen** image view works
- [ ] Add to Favorites — session appears on Home page slideshow

### 1.7 Home Page
- [ ] First image loads immediately (sample or first favorite)
- [ ] Slideshow advances automatically every 10 seconds
- [ ] Favorites loaded in background (no blocking)
- [ ] Navigate away and back — no slot-deleted errors in console

---

## Level 2 — Intermediate Features

> **Goal:** Test core daily-use features, multi-Dwarf setups, quality scoring, galleries.

### 2.1 FTP Connection (Dwarf 3 / Mini)
- [ ] Enter IP address in **IP STA Mode** field
- [ ] Click **Check FTP** — status shows `✅ Connected to FTP`
- [ ] Verify `❌ MTP not Connected` shown correctly when MTP not available
- [ ] Scan via FTP — same flow as USB
- [ ] **Type detection check fires on FTP** — verify no mismatch warning

### 2.2 Dwarf Type Mismatch Detection
- [ ] Configure a Dwarf as **Dwarf Mini** but use a Dwarf 3 USB disk
- [ ] Click **Analyze USB Drive**
- [ ] Verify warning appears: `⚠️ [name]: configured as Dwarf Mini but sessions detected as Dwarf3`
- [ ] Verify scan does NOT start after warning
- [ ] Correct the type → scan starts normally

### 2.3 Image Quality Scoring
- [ ] In **Explore**, select an object with multiple sessions
- [ ] Click **Score Sessions** (⭐ button)
- [ ] Progress indicator appears
- [ ] Sessions show quality scores with star rating (0–100)
- [ ] Quality filter (🌐 / 🟢 / 🟡) works correctly
- [ ] Score persists after page reload

### 2.4 Gallery (Explore)
- [ ] With 2+ sessions for an object, **Show Gallery** button appears
- [ ] Gallery opens — first image displayed immediately
- [ ] Slideshow advances every 10 seconds
- [ ] Prev / Next buttons work (reset 10s countdown)
- [ ] **Select** button closes gallery and selects the session
- [ ] Single session → Gallery button hidden

### 2.5 Manual Sessions (ManualExplore)
- [ ] Go to **Manual Explore**
- [ ] Add a manual session pointing to a processed FITS/PNG/JPG
- [ ] Session appears in the list under the correct object
- [ ] Gallery available when 2+ sessions
- [ ] Session gallery available when 2+ images in a session
- [ ] **View linked Dwarf session** link works

### 2.6 Storage Report
- [ ] Open **Report** page
- [ ] Select a Backup drive — table loads (biggest sessions first)
- [ ] Switch to Latest — sort by date
- [ ] Change limit (20 / 50 / 100 / All)
- [ ] **Calculate sizes** — new sessions get their `folder_size_bytes` filled
- [ ] Switch to Dwarf mode — USB status indicator shown (🟢 / 🔴)
- [ ] **Calculate Dwarf sizes** — type check fires before scan
- [ ] **Force recalculate** icon button — confirmation dialog appears
- [ ] Confirm — all sessions on the drive recalculated
- [ ] **Explore** button in table → opens correct session in Explore with back button
- [ ] Back button returns to Report with same filters active

### 2.7 Dark Library
- [ ] Open **Dark Library** page
- [ ] Add darks for a known session temperature
- [ ] In **Explore**, dark match badge (🎯) shown on matching sessions
- [ ] Green = exact temp range, orange = nearest, red = no match

### 2.8 Disk Space Widget
- [ ] Disconnect backup drive → widget shows cached values (offline mode)
- [ ] Reconnect → widget updates with live values
- [ ] Color-coding: green (>15% free), yellow (5–15%), orange (<5%), red (<2%)
- [ ] Dwarf page: 3-column card shows Local Data / Archive / Free space

### 2.9 Backup Analyze & Progress
- [ ] Go to **Backup** page, select a drive
- [ ] Click **Analyze Drive**
- [ ] Progress bar shows `[done/total] 🔍 folder_name`
- [ ] New sessions added to DB, deleted sessions removed
- [ ] Folder sizes calculated automatically for new sessions

---

## Level 3 — Advanced Features

> **Goal:** Test complex workflows: mosaics, stitching, repair, astrometry.

### 3.1 Clean FITS / Restore FITS
- [ ] In **Explore** (Dwarf mode, `only_already_backed` checked), select a non-RESTACKED session
- [ ] Verify **Restore FITS** button hidden for RESTACKED sessions
- [ ] Click **Clean FITS** on a regular session
- [ ] Confirm dialog — FITS files deleted, notification shows count
- [ ] Session detail shows 0 FITS files
- [ ] Report → Dwarf sizes updated automatically after clean
- [ ] Click **Restore FITS** — files restored from backup
- [ ] Restore count matches original count
- [ ] Report → sizes updated after restore
- [ ] **Mosaic session**: Clean FITS works (long path support, `\\?\` prefix)
- [ ] **Mosaic session**: Restore FITS works and files appear on disk

### 3.2 Mosaic Stitching
- [ ] In **Explore**, select a MOSAIC session with multiple panels
- [ ] Verify panel count shown
- [ ] Click **Show Mosaic Gallery** — panels displayed
- [ ] Click **Create Mosaic** / **Generate Panorama**
- [ ] Stitching completes — result image visible
- [ ] RESTACKED session created in DB
- [ ] RESTACKED session appears in **Explore** with correct object name
- [ ] Restore FITS button hidden on RESTACKED session

### 3.3 Astrometry (ASTAP + Nova)
- [ ] Go to **Sky Map** page
- [ ] Configure ASTAP path and database in Settings
- [ ] Launch scan on a session — WCS data stored in `SessionWCS`
- [ ] Session appears on Sky Map with footprint
- [ ] Mosaic: individual panels resolved, panel 0 from bbox center
- [ ] Nova API fallback works when ASTAP fails
- [ ] Lock file prevents concurrent CLI + UI scans

### 3.4 Sky Map Visualization
- [ ] Sky Map loads in external browser (pywebview CDN restriction)
- [ ] Sessions from multiple Dwarfs shown as separate catalogs
- [ ] Overlap detection highlights overlapping sessions
- [ ] Zoom / rotate preview works
- [ ] Click session marker → highlight in session list
- [ ] Search for object → map centers correctly

### 3.5 Transfer with FTP
- [ ] Configure FTP connection (Dwarf 3 / Mini via IP)
- [ ] Transfer session from Dwarf (FTP) → Backup Drive
- [ ] Progress bar works (FTP mode)
- [ ] Session indexed in DB after transfer
- [ ] Size calculated in `SessionQuality` after transfer

### 3.6 Session Error Management
- [ ] Sessions with missing stacked files shown in **⚠️ Sessions in Error** panel
- [ ] `repairInfo.json` with `type=REPAIR` → session marked as repaired, ignored in next scan
- [ ] `repairInfo.json` with `type=MERGE` → session ignored entirely
- [ ] Repair workflow completes without duplicating DB entries

### 3.7 Multi-Dwarf Workflow
- [ ] Two Dwarfs configured (e.g. Dwarf3 + Dwarf Mini)
- [ ] Each Dwarf scanned independently
- [ ] Explore filter by Dwarf works correctly
- [ ] Report shows correct sizes per Dwarf
- [ ] Same USB drive connected to different Dwarfs → type detection warns on mismatch

### 3.8 Database Migrations
- [ ] Fresh install creates DB at current version (v14+)
- [ ] Upgrading from older DB triggers all pending migrations
- [ ] `SessionQuality` table has all expected columns after upgrade:
  `folder_size_bytes`, `folder_sized_at`, `dwarf_size_bytes`, `dwarf_size_no_fits_bytes`, `dwarf_sized_at`
- [ ] No data loss during migration

### 3.9 Build & Packaging
- [ ] `buildDwarfiumScopeArchive.py` completes without encoding errors
- [ ] Packaged app launches in pywebview native mode
- [ ] All CDN resources blocked by pywebview served locally
- [ ] Aladin Lite loads via local HTTP route `/skymap_view`

---

## Regression Checklist

> Run after any significant change.

- [ ] Home slideshow: no `parent slot deleted` errors when navigating away quickly
- [ ] Gallery dialogs: no slot errors when opening/closing rapidly
- [ ] Timer cleanup: no leaked timers after page navigation
- [ ] `on_change` guard: no double `load_objects` on init
- [ ] Long paths (Windows > 260 chars): Clean/Restore FITS work on mosaic sessions
- [ ] RA wrap-around: sessions near 359°/0° (NGC 7822 area) appear correctly on Sky Map
- [ ] Mosaic stacked file deduplication: only one stacked file per folder in DB
- [ ] `ON CONFLICT DO UPDATE`: rescan does not overwrite `shotsToTake`/`shotsTaken` metadata

---

## Known Limitations / Out of Scope

- MTP backup transfer not fully tested (Windows MTP driver dependent)
- Nova Astrometry API requires internet access and valid API key
- FTP scan speed depends on Dwarf WiFi signal quality
- Dwarf 3 / Mini indistinguishable via FTP path detection (by design)

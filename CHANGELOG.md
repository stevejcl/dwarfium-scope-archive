# Changelog

## [V3.4.6] - 2026-10-17

### Add
    Load Dwarfium JSON, photometry: with the session's lights and the green images of an earlier run already in the
    working directory (a run stopped at image 95 of 509, Oct 2026), it offers to resume without copying again - the
    copy deleted process/ first, so the plate solve couldn't be resumed.
    Siril script: an unexpected Python error no longer kills it - PyQt6's default (qFatal) closed it without a word
    (user-reported Oct 2026: a 509-image run stopped at image 95, Windows reporting python.exe / Qt6Core.dll, c0000409
    code 7); now written to Siril's log, build_sessions.log and a message. The plate solve loop leaves out an image on
    any error, stopping after 5 in a row.
    Photometry script, resumed after a stop (user-reported Oct 2026: Siril closed at image 95 of 509, after 15 minutes
    of calibration and green channel): with the green images of an earlier run all in process/, it offers to start at
    the plate solve, which skips the images already solved; Siril's image closed every 25 plate solves.
    Photometry script: its intermediate images now really deleted - its cleanup lines were taken by the stacking
    scripts' PYTHON_CLEANUP (paths, globs), which found nothing to delete (user's 509-image run, Oct 2026); now
    PYTHON_CLEANUP_SEQ, handled first.
    Backup drive given to another Dwarf: its sessions (backup and manual entries) move with it (user-reported Oct 2026:
    they stayed on the first Dwarf, an analysis only adding new ones) - one the new Dwarf already had merged into it,
    how many said; the "still in use" messages of a drive's deletion translated.
    Photometry script, long sessions (after Naztronomy's Smart Telescope script, user-shared Oct 2026: 509 images
    took about 40 GB): the lights linked (Siril's link) instead of converted - not copied once more -, and each step's
    intermediate images deleted once the next one is made (light_ after the calibration, pp_light_ after the green
    channel; their .seq kept) - only the green images left, the space freed in build_sessions.log.
    Analyze: a drive (or a Dwarf's local copy) read through with no session left has its entries removed from the
    database (user-reported Oct 2026: the only session of a test drive deleted, it stayed in the database, the analysis
    ending with "False" - nothing was removed when none was found); and a session's data kept while the Dwarf's copy
    or a backup still uses it (only one table was checked: the foreign key stopped the whole cleanup).
    Build Sessions: each Siril command run in the background, the script's window kept alive - the command and its
    elapsed time shown, the long ones' in build_sessions.log (user-reported Oct 2026: on 509 images, calibrate ran for
    minutes with the window frozen, Windows calling it not responding - it looked crashed); Siril no longer answering
    reported as a failed command instead of stopping the script.
    Photometry and Check exposure: a session without a target (manual pointing, "Unknown", RA = DEC = 0 in the FITS
    header - a user's DY Peg data, Oct 2026) plate solved from the star's coordinates (VSX), Siril starting from the
    header's; a warning when neither is known.
    Check exposure, VSX: requests when Siril's Python has it, else urllib with a User-Agent and certifi's
    certificates; the reason shown and logged when it fails (user-reported Oct 2026: "Not found in VSX" for DY Peg
    from Siril, found by Astro Dwarf Session).
    Photometry, sessions put together: the drives not plugged in named in one line (a user's database knew 10).
    Prepare for Siril (one session and Megastack): the frames the Dwarf rejected (failed_*.fits) left out of the
    lights (user-asked Oct 2026), as the frame counts, the foreground repair and the mosaics do.
    Photometry: the target's name without SIMBAD's prefix ("V* DY Peg" -> "DY Peg", "* ", "NAME "), findcompstars
    writing SIMBAD's identifier - the star was archived as _PHOTOMETRY/V_DY_Peg/, its sessions under another name not
    put together (user's DY Peg test, Oct 2026).
    Check exposure (user's DY Peg test at full Moon in clouds, Oct 2026): the amplitude asked is VSX's by default (an
    eclipse depth or a pulsation's range - DY Peg 0.67 mag, 1.00 before for every star) with its type in the report;
    the Moon's phase and distance from the star, a warning when more than half lit within 60 degrees; a failed plate
    solve says why it likely failed (no or too few stars: clouds, mist, the focus) instead of Siril's "Generic error".
    Photometry archive: a result file open in another program (Excel, an image viewer: WinError 32, user-reported Oct
    2026) is named in the summary and left as it was, the others archived and the sessions still put together - it
    stopped the archive, then said the session folder wasn't reachable.
    Photometry, a star's sessions put together across the backup drives (user-requested Oct 2026: one DWARF, one
    drive): siril_session.json "photometry_roots" lists every drive's Astronomy root, the sessions of the star found on
    the drives plugged in are combined (a session on two drives once, its newer copy), the result written in the star's
    folder of each, the drives not reachable named in the summary, combined_sessions.csv giving each session's drive.
    Photometry, a star's sessions put together (user-requested Oct 2026): after each run, in _PHOTOMETRY/<star>/,
    combined_light_curve.csv / .png and combined_sessions.csv - each session shifted to the one with most points by
    the comparison stars both measured, matched by position (findcompstars numbers them differently each time), 3-sigma
    clipped. Explore's Photometry tab shows it first. The user's two DWARF 3 on HD 216964 at once: offset -0.003 from
    38 stars in common. The light curve CSV gives the target's x, y in each image too.
    Photometry results by star (user-requested Oct 2026: a star's sessions side by side, to be put together):
    _PHOTOMETRY/<star>/<session folder>/ instead of _PHOTOMETRY/<session folder>/. Analyze all moves the earlier
    ones (each star's files to its folder, build_sessions.log to every one); Explore finds both until then.
    Explore, Photometry tab read again on each click and a Refresh button (user-reported Oct 2026: a run of the Siril
    script after the session was selected kept showing the previous plots).
    Photometry: saturation level of the DWARF's 12-bit data 3300 ADU instead of 3700 (user's HD 216964 test, Oct
    2026: the target 0.04 mag fainter with its peak at 3300 - 3700 ADU than under 3000 - not linear). Also the level
    of the exposure check.
    Photometry: a comparison star with another catalogue star (or the target) within twice the aperture is left out
    (user's HD 216964 test, Oct 2026: two V 12.20 stars 4 px apart each measured 0.7 mag brighter, in the zero point).
    Light curve plot: the mean magnitudes of the target and the check star (weighted) as dashed lines, with their
    catalogue V, and the target's points, mean, std and range plus the check star's std under the title (user-requested
    Oct 2026).
    Photometry CSV ready for several sessions of a star (user-requested Oct 2026): header lines "# key: value" with
    the session, instrument (TELESCOP, CAMERA), filter, exposure, gain, site, target and check star (name, RA, Dec,
    V), and an airmass column (Pickering 2002) - the site is the session's location in the archive, else the default
    one (siril_session.json "site", the DWARF's FITS has none). Columns before it unchanged.
    _FIXED_FOREGROUND, _PHOTOMETRY and _WCS_MOSAIC (were FIXED_FOREGROUND, PHOTOMETRY, MOSAIC_WCS: a leading _ not to
    meet a user's folder, not _MOSAIC_WCS - "_MOSAIC_" makes a mosaic session) at the root of the archive - the backup's Astronomy folder (BackupDrive location +
    astronomy_dir), the level of RESTACKED - instead of next to the session (user-requested Oct 2026: two copies of a
    session in different sub-folders then share the same results, and a result from several sessions has one place).
    Found from the session's path (api/archive_paths.py: the backup whose Astronomy folder holds it, else its parent -
    the grandparent under RESTACKED / STARTRAILS / Archive); siril_session.json gives it to the Siril script
    ("astronomy_root"). Analyze all moves the ones made before next to the sessions (old names) to the root first, renamed, merged with
    those there (same file once, a different one kept as _1; each move logged; api/archive_paths.migrate_results);
    the analyses and session moves skip these folders.
    Explore, "Photometry" tab (user-requested Oct 2026: the light curve kept with the session in the archive): the
    Siril script's photometry results are archived in _PHOTOMETRY/<session folder>/ at the root of the archive, as
    _FIXED_FOREGROUND - light_curve_<star>.csv/.png, stars_variability_<star>.csv/.png, comparison_stars_<star>.csv,
    the .ssf script and build_sessions.log, several stars of one session side by side. The session's Photometry tab
    shows the plots (a click opens one in the system's viewer), opens the CSV and the folder; hidden when the session
    has none (api/photometry_results.py).
    Photometry, variability survey of the field (user-requested Oct 2026: the stars found in a session measured too):
    every comparison star measured in each image from the zero point of the others (leave-one-out); a scatter twice
    that of the stars within 0.5 mag and twice its own errors (chi2) makes it a candidate variable. stars_variability.csv
    (coordinates, V, magnitude, scatter, chi2, ratio) and stars_variability.png (scatter against magnitude), the top 5
    in the summary. On 60 frames built from a real DWARF 3 frame, a comparison star made variable (0.3 mag) is the
    only candidate found.
    Dwarfium Archive Selector: build_sessions.log in Siril's working directory, each command written and flushed
    before it runs (user-reported Oct 2026: Siril closed on a 141-image photometry session, its log gone with it) -
    its last line is where it stopped. The photometry logs its progress every 10 images, moves the progress bar,
    keeps the window alive and reads the images as float32.
    The photometry's plate solve runs image by image from Python (platesolve -noflip, saved), not seqplatesolve: on a
    141-image session the script's window stayed frozen through its minutes and the session looked stopped. The
    progress is shown between images (Siril's log, build_sessions.log, the progress bar); an image that can't be
    solved is left out, findcompstars runs on the first solved one.
    Dwarfium Archive Selector (Siril script), "📈 Photometry" option (user-requested Oct 2026: measure variable
    stars - eclipsing binary minima planned with Astro Dwarf Session - in Siril). Ticked, a single siril_session.json
    gives 01_photometry_<star>.ssf instead of stacking, run with Build Sessions: master dark, green channel (AAVSO TG
    band), registration without stacking, plate solve of the first frame made the reference (DWARF II tele focal
    length / pixel size passed: not in its FITS), comparison stars (findcompstars, APASS) and light_curve -
    process/light_curve.dat and its plot. The DWARF writes DATE-OBS as the end of the exposure ("Time end of
    exposure"), Siril reads it as the start: moved back by EXPTIME in the copied lights. The raw FITS hold 12-bit data
    (saturated at 4095) while Siril's photometry counts a star as saturated above 60000 ADU: setphot -max_val=3700 for
    the run (a DWARF 3 V1.5.3.9 sub). Siril 1.4.0+, Internet.
    light_curve without -autoring, its background annulus set to 10-15 px with setphot (FWHM 2 - 2.5 px) and Siril's
    defaults put back: in Siril 1.4.0 - 1.4.2 -autoring clears the reference image it measured, and the target star is
    then looked for in an image without its plate solve ("There was a problem finding the target star", real test).
    setphot -min_val=-1000: Siril rejects a star when a pixel of its aperture or annulus is <= min_val (0 by default),
    and after the dark the background is a few ADU - every comparison star was rejected. -dyn_ratio=4.0 given with it:
    a setphot without it fixes the aperture to 10 px.
    platesolve -noflip on the reference: platesolve turns an image it finds upside down the right way up, the reference
    was saved mirrored against the other registered frames and light_curve found no star in them.
    A script stopped on a failed command left Siril in process/ with its sequence open: the next Load Dwarfium JSON
    failed on Windows deleting process/ (os.rmdir). Siril now closes its image / sequence and goes back to the working
    directory before the copy deletes its folders, and after a failed Build Sessions.
    The photometry no longer uses Siril's light_curve, which failed on real DWARF images one way after another in
    Siril 1.4.0 - 1.4.2 (fixes above): seqplatesolve of every image, then the script measures the target and the
    comparison stars at their coordinates in each image (as Check exposure), a zero point per image from the
    comparison stars, the target's magnitude and error - process/light_curve_<sequence>.csv, with the mid-exposure
    time as JD UTC, HJD UTC and BJD TDB. No registration (the dithering doesn't matter), no setphot. A real DWARF 3
    frame of HD 216999 (V 9.36): 9.384 +/- 0.046 from 20 comparison stars.
    The same comparison stars in every image (those measured in at least 90 % of them): 19 to 23 from one image to the
    next made the zero point jump (first real light curve).
    The DWARF writes its local time in DATE-OBS, not UTC (user-checked: on the same DWARF 3 the last frame of a session
    read 04:10, the next session started at 04:22 French summer time): the script asks for its UTC offset - this PC's
    at the session's date by default, daylight saving included - and the CSV's JD / HJD / BJD are UTC-based.
    A check star - the comparison star closest to the target's magnitude, left out of the zero point (as HD 218587 in V.
    Lecomte's DY Peg procedure) - in the CSV, and light_curve_<sequence>.png: the target and the check star against HJD,
    error bars, magnitudes growing downwards, means of 3 points beyond 15 images (matplotlib, installed if missing).
    Same script, "🔆 Check exposure" (user-requested Oct 2026: set the exposure and gain from a few test frames): for
    each test frame, its green channel plate solved, the variable star and its comparison stars (findcompstars)
    measured with Siril's PSF - the star's peak against the 3700 ADU saturation level, its S/N, the longest exposure
    at that gain (peak at 80 % of it; 15 s at most on a DWARF II), the S/N at the minimum for the eclipse depth given, the comparison stars
    saturated. Shown, logged and saved in exposure_check/exposure_check.txt. The plate solved green image is saved and read
    with astropy (installed in Siril's Python if missing), each star measured at its coordinates: its peak the
    brightest pixel near it - Siril's fitted Gaussian was a third lower on these sharp stars -, a lone hot pixel
    rejected, the S/N from an aperture and its background annulus (first real tests, Oct 2026: Siril's own star
    list left the comparison stars out and gave no S/N, its selection coordinates didn't match radec2pix's).
    The script's buttons overlapped (one row needing ~1500 px in a 750 px window): two rows now - the stacking
    buttons, then the mosaic options and the variable star tools -, the window at least 1000 x 640.
    Explore, "Image Fix" tab (user-requested Oct 2026): a session whose foreground was fixed shows the fixed preview
    next to Infos / Image, with its folder - opened by itself when a repair ends with its dialog open. The image
    opens in the system's viewer (a click on it, or Open the image), and Open the folder shows the fixed FITS
    selected (Explorer, Finder - user-asked).
    Explore, "Fix the foreground" on a wide session (user-requested Oct 2026: before DWARF 3 V1.5.3.9 / DWARF mini
    V1.1.4.4 - DWARFLAB's "fixed foreground" beta - the Dwarf stacked on the stars and the trees, the roof came out
    smeared, the ground turning 15 deg an hour against the sky). From the session's raw frames (40 at most, spread
    over it): plate solved once on the catalogue, each frame registered on the stars (dithering); the foreground
    stacked on itself - where each frame saw a bit of ground computed from the sidereal time elapsed (EQ tracking:
    the ground turns about the celestial pole) - median; its mask on that sharp stack (darker than the sky,
    vignetting divided out); the sky stacked on the stars, each frame only where its own foreground wasn't,
    sigma-clipped (a satellite trail gone); both blended in the first frame's geometry. Into FIXED_FOREGROUND next
    to the sessions - the session untouched: a linear FITS with its WCS, a preview, the sky alone and the foreground
    alone as 16-bit TIFFs with transparency. Shown on Backup drives only, for wide sessions with raw frames shot
    before those firmwares (FIRMWARE / TELESCOP read in a frame). Runs
    for the app, as the Milky Way mosaic: the dialog shows it running, its steps and its result. A Mini session of
    22 frames: 90 s, 0.9 GB.
    Mosaic page, new "Milky Way" tab: mosaic by astrometry (user-requested Oct 2026: a Milky Way mosaic of
    wide-angle tiles - Affinity kept the roof and the trees, bent the 70 deg of sky and left the tiles uneven). It
    lists the mosaics found on the backup drive - sessions whose names have R<row>C<col> (Astro Dwarf Session's
    Milky Way planner: "MW Tile R1C2"), grouped by name and night - or takes the FITS of a folder chosen by hand,
    and assembles the tiles ticked: each one where its sky is - its WCS, else plate solved (ASTAP / solve-field /
    Nova, as the astrometry scan) -, refit on the Bright Star Catalogue with a distortion of order 4 (a wide-angle
    solution is off by 20-100 px at the edges without it, stars doubled in the overlaps), its foreground (roof,
    trees: no stars, or darker than the sky) left out, its brightness and colour levelled to its neighbours,
    blended where the tile seen nearer its centre wins (sharper stars). Output in MOSAIC_WCS next to the sessions:
    a linear 32-bit FITS with its WCS (Siril: background extraction, photometric colour calibration, stretch) and
    a stretched preview. 5 tiles: ~2 min, ~1 GB. In Explore, "Mosaic (astrometry)" on a tile's session opens the
    tab on its mosaic.
    The assembly belongs to the app, not to the page (user-asked: it takes minutes, one goes elsewhere meanwhile):
    coming back to the tab shows it - a banner that stays while it runs ("Mosaic being assembled, please wait...",
    the time and the current step), its steps (plate solving, catalogue stars and residual, sky kept, levelling...),
    then its result and preview; Assemble is off meanwhile (one at a time), and every open page of the app is told
    when it ends.
    Explore, the sessions' gallery: the mouse wheel goes through the sessions (user-requested: All sessions, hundreds)
    - a notch one, spun faster several, their small stacked_thumbnail.jpg meanwhile (the next ones loaded ahead)
    and the full image once it stops; the automatic slideshow pauses while it turns, and stops when the gallery is
    closed (it went on behind it). The position (12 / 240) shown.
    Explore: a View button on the line saying the session is also on the Dwarf (Backup mode) or on a backup drive
    (Dwarf mode) - opens that copy of the session in Explore, in the other mode (user-requested).
    Explore: a session's frames (user-requested) - the Dwarf's JPG of each frame (its Thumbnail folder, named like
    the FITS) in a gallery, enlarged with previous / next (arrows, or the mouse wheel - spun faster, it goes faster;
    its place shown, e.g. 12 / 240; space marks); the bad ones marked go, their FITS and JPG, so a megastack or
    restack takes only the good ones. "Delete the rejected frames" takes the failed_ ones (rejected by the Dwarf)
    at once. On the Dwarf plugged in USB (its local copy reads "plug the Dwarf in USB"):
    deleted for good there - said before for a session not backed up -, and moved into the trash of its backup copy
    (its drive connected). On a backup drive: into the session's trash (.trash, in each panel for a mosaic) - the
    Dwarf plugged in USB with the session on it, a box (unticked) deletes them from it too, for good. Under
    the session's FITS, "N frames in the trash": View (each one Restore or Delete for good, done when leaving or
    with Apply; restored ones copied back onto the Dwarf plugged in USB when asked) and Empty the trash. The trash
    is left out of the drive analysis, the FITS counts, Restore FITS and the transfers. The session's sizes are
    measured again.
    Sky Map (user-requested: "10 sessions of the Lion Nebula, only the best one on the map"): "Best session per
    object" in its toolbar - only the best-scored session of each object, the newest on a tie; "Hide from the Sky
    Map" in a session's popup - it stays solved, so the next scan doesn't solve it again; "Show hidden" shows them
    greyed, to show one again. Both boxes remembered by the browser. Explore, next to a session's quality score: an
    icon to clear it (then "no score", Score scores it again - the Storage Report's sizes are kept), and for a
    solved session one to hide it from the Sky Map / show it again. Several sessions overlapping where the map is
    clicked: the list to choose one shows again (it never did).
    Explore, Dwarf mode: a "FITS on the Dwarf" filter (All / With / Without) - the sessions whose raw FITS are still
    on the Dwarf (a megastack needs them), from the Storage Report's measure (Measure the Dwarf): one query, no folder
    read; a session never measured, or not backed up yet, is in neither.
    Storage Report: a session listed on a connected drive but whose folder is no longer there (moved, or put back on
    another drive) reads "not found" in orange instead of "—" - its tooltip says to analyze the drive again, which
    removes the old entry. The Dwarf sizes (total / without FITS) are now written to every backup copy of the
    session: a copy kept an old measure from before its FITS were cleaned (user-seen).
    Its labels say what is measured: the buttons Measure the backup / Measure the Dwarf (a tooltip each: which
    folder, which columns, only the sessions not measured yet), the columns Backup / On the Dwarf / Dwarf without
    FITS (were Size / Dwarf total / Dwarf -FITS, and "Calculate sizes" / "Calculate Dwarf sizes").
    Explore, Dwarf mode, a session without its FITS shown from the Dwarf's local copy (Dwarf_Local - the Dwarf not
    plugged in USB): the Restore FITS icon now reads "plug the Dwarf in USB" (grey, a USB icon) and explains on a
    click - the FITS would only go back into the copy, not onto the Dwarf (a megastack needs them there), and the
    Dwarf's FTP is read-only (writing over the network: Dwarf 2 only, SFTP).
    Explore: the session's EQ mode (EQ: yes / no), from the "eq" field of its shotsInfo.json - written by
    recent Dwarf firmwares only: nothing shown when the file or the field is missing.
    Explore, Dwarf mode, a Dwarf and an object selected: Megastack on the Dwarf - the Dwarf stacks sessions of a
    target together (a single one: restacked) into Astronomy/RESTACKED/, like the official app's megastack, asked to
    Dwarfium Lite (3.2.6+), which runs and follows it (its device page: images stacked so far and the stack growing;
    then its Results tab). Its button opens a picker, like Dwarfium Lite's Explorer: the object's sessions that can
    be megastacked, grouped by target with their thumbnails (date, images stacked, exposure, filter - the Dwarf
    takes mixed filters, e.g. Duo-Band with Astro) - not a megastack result, nor one whose FITS are gone (read on
    the Dwarf plugged in USB, a mosaic's in its panels' subfolders, else the Storage Report's measure; offered when
    not known - Dwarfium Lite checks them again; its name, a mosaic's too, in the tile's tooltip) - a click selects
    one (one target, single captures or mosaics - not mixed), the images counted below, then Start: Dwarfium Lite
    must be running and the Dwarf connected in it (found by its Dwarf ID, else its IP). The Dwarf checks the rest
    itself (binning, dark frames) - its refusal shown with the reason.
    Mosaic page, Milky Way tab: the sky alone, stretched, as a 16-bit TIFF with the foreground transparent
    (user-requested Oct 2026: blend it over a foreground shot - a panorama at blue hour - in Affinity), next to
    the FITS and the preview (_sky.tif): the parts where no tile kept sky (roof, trees, outside the tiles) are
    transparent, fading in like the tiles' own edges - laid over the foreground, no cutting out by hand.
    The Mosaic page's title names its new tab: "Mosaic Merge / Repair / Milky Way".
    Mosaic page, Milky Way tab: plate solving on the app's own catalogue first (user-requested Oct 2026: the
    Dwarf's FITS have no WCS, and the tools reading mosaics need one) - near the pointing the Dwarf records (RA /
    DEC) at the scale of its optics, the tile's brightest stars (by their light, not their peak: a stretched stack
    saturates them all) matched to the Bright Star Catalogue's by their triangles, any orientation, then refit with
    the lens distortion: offline, 20-50 s a tile (D3 and Mini wide, 178-263 stars, 0.35-0.46 px on 7 tiles), made
    for these 46 deg fields where ASTAP and solve-field struggle; ASTAP / solve-field / Nova after it. A solution is
    written next to its tile as <name>.wcs (a header-only FITS with a CD matrix, as ASTAP and astrometry.net do -
    the tile itself untouched), read back by the next assembly before any solve. "Open the folder" next to the
    output FITS and with the result opens MOSAIC_WCS.

### BugFix
    Explore, Fix the foreground: on a session with little foreground (user-found Oct 2026), a starless disc of sky
    in the middle of the result - the darker half of the sky's own gradient passed for foreground and got the
    foreground stack. A dark patch where the first frames (stars still sharp) show stars over most of it is now sky -
    its starless part kept if it comes in from the frame's edge -, and foreground away from the edge is sky unless
    large. Each frame's offset and turn are in the steps.
    Fix the foreground refused a session whose stars turned 0.3 deg over 44 min (user-found Oct 2026) as alt-az -
    an EQ mount's polar alignment error. No session is refused for its tracking any more (nor for EQMODE): each
    frame's registration on the stars carries its turn, and the ground is placed through it, so the geometry holds
    for EQ and alt-az alike. The session's plate-solve is written next to its first raw frame (<name>.wcs) and
    read back by the next repair (a solve saved: 113 -> 87 s on a Mini session).
    Fix the foreground's preview showed a pale grey sky (user-found Oct 2026): one stretch over the whole frame took
    the trees' black as the sky's. Sky and foreground are now stretched each on its own pixels - the preview's black
    at the sky's background, the foreground kept darker -, and _ground.tif no longer has its trees clipped to black.
    Its stretch made gentler too (asinh 2 for the preview, 4 for the TIFFs, from 10 - user-asked).
    Fix the foreground left the trees smeared in star trails (user-found Oct 2026, NGC 6871 session under a bright
    sky): 0% foreground found - the check keeping only pixels the frames saw well (over 90% of the median) dropped
    the trees, darker than that. Now 30%: 36% foreground found, sharp silhouettes. The foreground is grown by 3 px
    so the sky's halo at its edge doesn't show, the preview is stretched once on the sky (no grey band around the
    trees), and the steps list a frame's offset only when it's large (over 30 px or 0.2 deg).
    Mosaic page, Milky Way tab: small square holes in an open sky (user-found Oct 2026) - a patch of sky where a
    few less stars happened to be detected passed for foreground. Foreground comes into a tile from its edge (trees,
    a roof): a patch of it in the middle of the sky is now kept as sky, unless it's large (over 2% of the tile).
    Mosaic page, Milky Way tab: a tile mostly roof (user-found: the old R3C1, a lit roof with a wedge of sky) kept
    patches of the roof full of holes - its noise passed for stars, the star density being judged against the tile's
    median, the roof's own. The sky is now judged against the tile's starriest part: the roof is left out whole.
    Dark Library: DWARF_DARK is not an older firmware's leftover (user-found: three dark sessions at three
    temperatures) - each dark session of the Dwarf leaves its raw frames there, in a dated folder, and, on firmwares
    that make one (a newer one doesn't), the master built from them in CALI_FRAME (one per setting and temperature,
    replaced by a new session at the same temperature). Each master is now shown with its raw frames (count, date)
    and dated by its dark session (its file date is the copy's) when a session's darks are chosen; the raw sets
    without a master (all of them on a firmware making none, an older session at a temperature redone since, a master
    deleted, undated folders) are listed apart and offered as well, Siril building their master - the same darks
    were offered twice. "Download the darks" copies DWARF_DARK alone when the Dwarf has no CALI_FRAME (it was given
    as the source anyway). Texts and help no longer say "older firmware".
    A session's darks: the temperature now comes before the date (darks at 6, 9 and 12 °C, a session at 8-10 °C took
    the 12 °C ones - all three within its range ±2 °C, then the closest date won), but only among the darks of the
    session's era: dated within 3 months of it (a sensor gains hot pixels over time, a firmware update can change the
    raw frames - no other era's dark corrects that, while Siril's dark optimisation makes up for a temperature gap);
    all of them when none is. Then the closest date, the master on a tie.
    Better still, the session's firmware when known: the FIRMWARE header of its FITS and of the raw darks (a master,
    whose header carries none, takes its raws') - the darks of that firmware first, the 3 months window only when the
    firmware is unknown on either side. One master per temperature met during a dark session (its frames grouped by
    the temperature in their names: 7 frames at 23 °C and 1 at 24 °C gave ..._23C_stack_7 and ..._24C_stack_1): the
    raw sets are split the same way, each master paired with its own frames, and among temperatures 1 °C apart the
    most frames win (_stack_N) - a master of 1 frame is as noisy as a raw frame. The Dark Library page shows each set's
    firmware.
    Transfer, several sessions backed up over FTP (Explore's Backup Selected): only the first one was copied - its
    folder was taken for the source's main folder, so the transfer was seen as a single one. Over USB it worked. "Select
    the source" then listed one path made of all the sessions: it lists each of them now.
    Sessions never scored automatically: after a backup drive's analysis only the sessions without any quality row
    were scored, but a size measured first (Storage Report, Clean Fits, restored FITS, the Dwarf's sizes written to
    every copy) creates that row without a score - the session then stayed "no score" (no colour on the Sky Map,
    not proposed to its scan). Scored now when its score is empty, except one cleared on purpose (Explore's ⌫) -
    database V17: SessionQuality.score_cleared and the SkyMapHidden table, nothing to do by hand.
    Explore: a message showed its key "no_backup_drive_sel2" instead of "No backup drive selected." (a typo in the
    key).
    Storage Report: confirming "Measure again all the sessions" of the Dwarf (⟳ next to Measure the Dwarf) did
    nothing - "coroutine was never awaited" in the console.
    Import of a session from Dwarfium Lite (Archive in Scope Archive): a session not on the Dwarf's USB drive is
    now read by FTP - a megastack made while the Dwarf was plugged in by USB isn't shown on the drive until it is
    plugged again ("Session not found on the Dwarf", user-seen); the Transfer page that follows then copies it by
    FTP too.

## [V3.4.5] - 2026-10-14

### Add
    A new icon: a Dwarf pointing at the sky and archived pictures, on the green disc - the same family as Dwarfium
    Lite's and Dwarfium-Hub's icons (the name no longer written in it, unreadable at small sizes).
    The logo also shows on the "What to shoot tonight" page, before its title (instead of 🔭), next to the title of
    its help, and before "Tonight's Targets" in the menu. Its help shows the cards' own Aladin and plan buttons
    (it still showed the former 🔭 and 📅).
    And before the "AstroObject to DSO Association" title of the Catalog page (instead of 🔭).
    Analyze everything (menu, tools/full_rescan.py): the local copy of every Dwarf (the Dwarf needs not be
    connected) and every backup drive of the database analyzed one after the other, the ticked ones only (a folder
    not reachable can't be ticked) - a line per folder with its result (+ new sessions, - removed) and the log. The
    database matches the files again after another installation sharing the same folders changed them, or a
    folder moved by hand.
    Its log also written to logs/analyze_all_<date>.log (the folders chosen, each line timed, each folder's result;
    the last 20 kept), with buttons to open the file and its folder (the folder through explorer, the log selected).
    The page always back to its idle state at the end (a failure reading the new dates left the spinner and
    "Analyzing 9/9" after the analyses were over); the dates read on their own connection, a failure shown.
    The cause: reopening a page's database connection closed by a disconnect during a long operation raised
    "name 'connect_db' is not defined" (components/db_page_mixin.py) - also for Explore and What to shoot tonight.
    Its log reaches the screen in batches, twice a second (at most 50 lines each, all of them in the file): each line
    sent from the analysis thread meant thousands of messages a minute to every browser open, and a phone open at the
    same time kept losing its connection.
    The same for the Dwarf page's analysis and the Backup page's analysis and integrity check
    (components/batched_log.py).

### BugFix#
    Explore and Manual Explore, a shorter session panel: the image info on fewer lines (directory size with the
    files found, file name with its size), tighter lines; on a phone, a line that wraps ("Identify target", the
    temperatures, "Score") no longer leaves a large gap, and the empty "classified as" line takes no room. Manual
    Explore gets the Infos / Image tabs of Explore.
    Explore, a mosaic's line (panels found, layout and scale, "Show mosaic gallery", "Create mosaic"): on a phone it
    wraps instead of squeezing its labels and buttons letter by letter. Manual Explore's gallery line (images found,
    "Show gallery") alike.
    Explore and Manual Explore, the objects list condensed when it holds more than 10 objects: about 30px per object
    instead of 48 - nearly twice as many in view. The sessions list (its dropdown) likewise, beyond 14 sessions: 32px
    per session instead of 48; and the sessions listed under it (all sessions of an object, or several sessions):
    normal spacing up to 14, condensed beyond.
    Manual Explore: a session whose image can't be found raised "'List' object has no attribute 'append'"; it now
    says so in the details and in the Image tab, without trying to show the image.
    Add Manual Session, on a phone: no wider than the screen - the mode / Dwarf / drive selection and the JPG / PNG
    / FITS uploads one under the other (the uploads overlapped), the session, tag and destination fields full width.
    Catalog page, on a phone: its buttons each take a full line.
    Dwarf page, on a phone: the local data / archive / free space card goes under "Empty local archive" instead of
    being squeezed to a letter per line next to it.
    Add Manual Session and Mosaic pages: no more browser error "Cannot read properties of null (reading
    'startsWith')" on opening - their thumbnails were created with no image (None) before a session is chosen.
    Folder picker (in a browser - Transfer, Dark Library...): wider (up to 1000px), a long folder name wraps beside
    its icon - the Dwarf's session folders overlapped one another.
    What to shoot tonight: reloaded (or left and reopened) while its target images were still loading, the page stayed
    blank, its spinner turning - the images' downloads filled the threads the page's own computation needed. They now
    load on their own threads, and those of a page left are dropped; no more "The client this element belongs to has
    been deleted" in the log either.
    What to shoot tonight: no more "'NoneType' object has no attribute 'execute'" when the page is left, reloaded or
    briefly disconnected during the targets' computation (its database connection is closed then).
    What to shoot tonight: a section closed (new, incomplete, well covered targets) stays closed when the images are
    turned on or a filter changes, and loads no images until it is opened - they all reopened and loaded everything.
    German and Spanish help (components/help_locales/de.py, es.py): the translation templates brought up to date
    with the English help - the 8 pages changed since and the 3 missing (What to shoot tonight, Report, Sky map);
    each page still marked # TODO until translated.
    German and Spanish interface texts (components/locales/de.py, es.py): already complete; 3 outdated values
    aligned with English (the local plate solving label, "solve-field is available" that said "not available", a
    stray "}" in "destination already exists").
    Dwarf Configuration help: the Session IP (a second FTP IP kept on this PC, for a Dwarf on a remote site reached
    through Tailscale - the FTP functions use the IP that answers) and the path detected / not detected line with
    its refresh button, which it didn't mention.
    Analysis log: "add astro object" also printed when an existing astro object was reused (now "use astro object"),
    and in the sessions grouped under their parent folder it named the parent folder instead of the object actually
    created or reused.
    Last analysis date (Dwarf, Backup and Analyze everything pages): set by every full analysis, also when it finds
    nothing new - it only moved when sessions were added or removed, so a database checked yesterday could show a
    date months old. A single session imported still sets it only when something changed.
    Dwarf page: no empty line under the STA mode IP and the Session IP (the space kept for a validation message) -
    the message still shows when an IP is invalid.

## [V3.4.4] - 2026-10-13

### Add
    Older firmware darks: the Dark Library also reads DWARF_DARK (next to CALI_FRAME), one folder of raw darks per
    setting - tele/wide_exp_<s>_gain_<g>_bin_<b>, dated or not; their temperature read from the frames' names when
    they carry it. "Scan the library" lists them per camera (exposure, gain, binning, frames, temperature or ?, date).
    A session's darks are chosen among the CALI_FRAME masters and the DWARF_DARK folders alike - same gain / binning
    / exposure within 2% and the session's camera (now also for the CALI_FRAME masters), then the temperature in the
    session's range ±2 °C, else the closest, then the date closest to the session's, before or after (the folder's date,
    the master's file date; the most recent when the session has none), the current firmware's master on a tie -
    one master or one folder, in Explore's 🎯 badge ("older firmware") and in the session sent to Siril, which builds
    the master from DWARF_DARK raw frames. "Download the darks" copies the Dwarf's DWARF_DARK too, next to
    CALI_FRAME, when it has one. Help updated.

### BugFix#
    Dwarf page, identifier: "Read from the Dwarf" and "Identify" are compact icons with a small caption (shown at every
    size), on the field's line, together as wide as the buttons of the other lines and aligned with them; on a phone,
    like the other lines, the field and the buttons each take a full line. They took a line of their own before, "Identify" easy to miss.

## [V3.4.3] - 2026-10-13

### Add
    App info: GET /api/app-info answers {"app": "dwarfium_scope_archive", "name", "version"}: Dwarfium-Hub tells this
    app from another program on the same port, and learns the version of an installation it didn't install.
    Dwarf identifier: the Dwarf page has the Dwarf's identifier, the last 6 characters of the MAC address printed on it
    (the whole address can be pasted), which also end its Bluetooth name (DWARF3_A1B2C3). "Read from the Dwarf" asks
    the Dwarf at its IP (POST :8082/deviceInfo: only its name and model are kept, the passwords in that answer are
    never kept nor logged) and warns when it isn't the Dwarf the identifier said, or of another type. Stored in
    Dwarf.ble_id (database V16); a Dwarf whose description is its Bluetooth name (DWARF3_3C2E2A, DWARF_mini_19A608)
    gets its identifier from it at the migration. Only exact forms are taken (6 hex digits after the name's last "_",
    the 6 digits, or a whole MAC address), nothing is guessed. Dwarfium-Hub uses it to link a Dwarf for sure to the
    same Dwarf of Dwarfium Lite.
    Help updated.
    The Dwarf connected is the one chosen: before "Analyze the Dwarf drive", next to the type check (which can't tell
    two Dwarfs of the same model apart), over FTP the Dwarf answering at the IP must have the chosen Dwarf's
    identifier, and on any drive the sessions found must not be archived under another Dwarf only (a session folder
    name is unique to a device: 2 of them under another Dwarf and none under the chosen one is that other Dwarf's
    drive). A warning lists what doesn't match and offers to continue anyway. Help updated.
    Identify a Dwarf: "Identify" on the Dwarf page flashes the ring light of the Dwarf at its IP, to see which one it is
    when several are on - asked to Dwarfium Lite (Astro Dwarf Session 3.2.4+, running: its address is the one it says
    hello with), which refuses during a capture. Each case said (not running, older version, busy, no answer, held by
    another app). Help updated.

## [V3.4.2] - 2026-10-11

### Add
    Astro Dwarf Session presence: Astro Dwarf Session (3.2.3 and later) says hello every 30 s at /api/peer/hello, so
    this app knows its address (the request's IP and the port it gives) and whether it is running (heard from in the
    last 75 s), for actions done in Astro Dwarf Session. Answered at once, kept in memory only. /api/peer/status
    shows it.
    Recommended tonight: plan a target on a Dwarf. A 📅 button on each target opens Astro Dwarf Session's "Plan a target"
    page (external browser) with the target and its best slot tonight (the stretch above 25° around its best time, now
    computed with its visibility): the Dwarf, a program or a native schedule and the settings are chosen there. Needs
    Astro Dwarf Session 3.2.3 or later, running (else said so). Help updated.
    Tonight's plan (components/tonight_plan.py, reusable by other pages): the 📅 button now offers "Plan this target
    tonight" or "Add to tonight's plan", a list of targets (5 by default, see Settings) with their windows, floating
    at the bottom of the window (remove one, clear, "Plan these targets": Astro Dwarf Session chains them over the
    night). When full, adding offers to replace one. Kept by the app for one night and site (survives a page
    change). The floating list folds into one small line ("📅 Tonight's plan (n/5)", a click opens it), remembered
    on every page.
    Explore: "Plan tonight" button once an object is selected (with all sessions, once a session is chosen: its
    object), usable when it has coordinates (mean of its sessions' RA/Dec - the center of a mosaic -, else its object
    record, else the DSO catalog by name): its window tonight at the default location is computed on the click (in
    the background, the night cached per site and date, so later clicks are instant) and shown with its maximum
    altitude, or "not above 25° tonight"; then plan it alone or add it to tonight's plan, shared with Recommended
    tonight.
    Settings: new "Session" card before the mosaic parameters - sessions per night (targets in tonight's plan at most,
    1-10, default 5) and day change hour (before it, "tonight" is still the night in progress; default 08:00), used for
    Recommended tonight's default date and tonight's plan (Recommended tonight, Explore).

    Explore / Manual sessions: the action buttons are now large icons, grouped (view, process, plan, archive, then
    delete apart in red), their name in a tooltip; on a phone or tablet the name is shown under the icon
    (components/action_icon.py).

    Explore: the session's details and its image are two tabs (Infos / Image) sliding into each other - swipe on a
    touch screen - instead of the image under the details. Without an image, the Image tab says why: no session
    chosen, the session has no image, or its path was not found (in the Dwarf mode: "Dwarf not connected?").

### BugFix#
    Explore / Manual sessions: with a long session label, the right column grew past the window and its buttons were
    cut off. The column now stays within the window: the label is shortened (…) and the buttons wrap.

## [V3.4.1] - 2026-10-08

### Add
    Session IP: a second FTP IP per Dwarf, next to the configured one, kept on this PC only (not in the database) - e.g.
    the Dwarf's IP on a remote site reached through Tailscale, the configured one staying the local site's. The Dwarf
    Configuration, Transfer and import pages use whichever IP answers. Astro Dwarf Session's links give the IP it reaches
    the Dwarf at (DwarfIp): tried first by the import and the Transfer page that follows; on the Dwarf Configuration
    page, when it's neither IP, a dialog offers to save it as FTP IP, use it as session IP, or ignore it.

### BugFix#
    Open in the app's window right after the app started: the request no longer reloads the window (the pywebview
    calls that blocked it) while its page hasn't reported itself yet - it waits for it and lets a page connected less
    than 3 s ago settle before navigating it. The home page also says when it is built: a request while it is still
    starting waits for it, 4 s at most, then is answered {"opened": false, "busy": true} instead of touching the
    window (Astro Dwarf Session then asks to try again).
    Import one session (USB / mapped folder): a RESTACKED session was copied to RESTACKED\RESTACKED\<session>, so the
    import ended with "Session not found on the Dwarf" although its files were copied. It now goes to
    RESTACKED\<session>, as with FTP. The Transfer page's single-session sync keeps RESTACKED\<session>, and now puts a
    STARTRAILS session in STARTRAILS\<session> where its scan looks for it (it went to the top of the Dwarf folder).
    Page opened from Astro Dwarf Session in the app's window: it looked frozen until a click (the window was brought to
    front with an Alt key press, whose release put it in menu mode). Brought to front without a key press now.

## [V3.4.0] - 2026-10-06

### Add
    Import one session: /ImportSession?DwarfId=<id>&session=<session folder>, opened from Astro Dwarf Session's "Archive
    in Dwarfium Scope Archive" button. It first says if the session is already backed up (same rule as the Explore page),
    listing its drives and whether the folder is still on each, with "See it in the backups" or "Import and transfer
    anyway". Then the same two steps as the Dwarf Configuration page's analysis, for this session only: its stacked /
    shotsInfo files are synced from the Dwarf (USB when its astronomy folder is reachable, else FTP) and scanned into the
    database, and the Transfer page opens with it preselected (Archive mode) - choosing the backup drive and starting the
    copy stay with the user. The log and progress bar appear once the import starts; on failure the log stays shown,
    with a link to the Transfer page.
    Open in the app's window: GET /api/open-in-app?path=<page of this app>. The page shown in the app's window goes
    through a small relay page (/Init) that then opens the requested page itself (opening it directly froze the
    interface), and the window is brought to front on Windows (Win32); {"opened": false} when there's
    no app window (browser / server mode), so the caller opens a browser tab instead. Only this app's own pages are
    accepted. Used by Astro Dwarf Session for "Archive" and its "Config / Sessions on the Dwarf / Backed-up sessions" links.

### BugFix#
    Catalog Edition help: rewritten for what the page does now (DSO links, the association wizard, the objects / groups
    consistency checks, sessions of an object or group with Move); it still described an older catalog browser.
    Transfer page in a web browser: the folder buttons did nothing - they open the system dialog of the app's own window,
    out of sight from a browser. In a browser they now show a folder picker in the page (folders of this PC, from the
    start folder, never above the allowed root - backup drive or source); the app's window keeps the system dialog.

## [V3.3.2] - 2026-10-04

### BugFix#
    Port detection: launched one after the other, this app and Astro Dwarf Session could pick the same port on Windows
    (a free test bind on 127.0.0.1 doesn't see a server listening on 0.0.0.0). A port is now free only when nothing answers on
    it and it binds on 127.0.0.1 and 0.0.0.0 (exclusive bind on Windows).

## [V3.3.1] - 2026-10-04

### Add
    DSO catalog add-on: objects kept in Astro Dwarf Session (targets sent from its /catalog page with "Keep these targets
    in the catalog" ticked) are written to db/catalog_add_on.json and imported after dso_catalog.json, which is never modified
    and wins when both have the same designation. They can then be linked to sessions like any other catalog object
    ("Identify the target", Catalog page, association wizards).
    The catalog is refreshed before each session import (Dwarf / Backup pages, CLI) and when the manual session page opens,
    so objects added while the app is running can be linked to the new sessions without a restart.

### BugFix#
    The DSO catalog was re-imported at every start as soon as the table and dso_catalog.json didn't have the same number of
    objects: it is now imported only when an object of the JSON files is missing from the table. Catalog rows are never deleted
    (sessions are linked to them).
    Re-importing the catalog no longer resets the catalog objects' favorite flag.
    The catalog used to match sessions to objects (dso_sky_search_catalog.json) was built once and never updated: it is now
    rebuilt when dso_catalog.json or catalog_add_on.json changes, and only the new or changed objects are converted (much faster).

## [V3.3.0] - 2026-10-02

### Add
    Local plate solving: ASTAP is now found on Linux and macOS too (astap_cli, /opt/astap, ~/astap, ASTAP.app, /usr/local/opt/astap),
    with its star database located separately (next to the executable or in the installer folders).
    Astrometry: wide-angle sessions use the real lens optics (header FOCALLEN, falling back to 7 mm / 2.9 µm instead of a hard-coded 24 mm),
    so ASTAP gets the right field of view and Nova the right plate scale; W08 added to the wide database selector,
    D05 switches to the wide database for fields > 5°.
    UI languages are discovered from the locale files (LANGUAGE_NAME / ENABLED flag): a translator can add or test a language
    in the packaged app without overwriting en.py or fr.py. The Settings selector and Help follow the available languages.
    Settings: on Windows and macOS the local solver card shows ASTAP only ("Local Mode (ASTAP)"), unless solve-field is really reachable.
    CI: the 3-OS build also runs on pull requests to evolution-main.

### BugFix#
    ASTAP solves always failed (frequent fallback to Nova): wrong -s/-D options for the database, -fov computed from the image width
    instead of its height, stale .ini/.wcs from a previous run. Unknown FOV now uses -fov 0 (auto).
    solve-field: the WCS result is now returned and copied next to the image (<name>.wcs.fits); RA/Dec hints, scale range and CPU limit
    are passed, with Nova as fallback when an API key is set. Linux installer fixed (terminal for sudo, Tycho-2 index files);
    the broken Windows solve-field .bat is removed.
    Astrometry scan no longer leaks temp files (FITS copies and ASTAP results) in the temp folder.
    Astrometry scan skips star-trail sessions (STARTRAILS folder / *_startrails_* images): they cannot be solved and were queued
    first (high quality score), each one costing an ASTAP try and a Nova upload. Manual sessions already solved are no longer re-queued.
    Dwarf type mismatch detection: D2 / D3 decided by the source (D3 4K firmware outputs 3840x2160), mosaic roots skipped,
    D3 bin2 (1920x1080) no longer reported as a DWARF Mini, unreadable or ambiguous images no longer vote DWARF3.

## [V3.2.9] - 2026-09-28
### BugFix#
    correction for FTP Transfert crash

## [V3.2.8] - 2026-09-19

### Add
    Add a new api/wiki_images.py to lookup representative free-licensed images from Wikimedia Commons (with license/artist metadata), and cache outcomes in DsoImageCache.
    Integrates into pages/recommend_tonight.py: adds a 'Show images' toggle, lazy/background fetching per card, credit rendering, and size display.
    Adds translation keys (en/de/es/fr)
    Add a README license badge, plus an MIT LICENSE file.

### BugFix#
    Misc: small UI improvements (notification timeouts/close buttons), debug flags for mismatch dialogs to ignore the notification, and async adjustments in config/report pages.

## [V3.2.7] - 2026-08-26

### Add
    Add a centralized DSO matching catalog helper and reuse it across the app, including the new sky-search catalog loading path.
    This commit also introduces the new /RecommendTonight page, which scores observable deep-sky targets for a selected date/location using session history, mosaic coverage, and sky visibility.
    
    It includes localized help strings and menu entries, plus the skyfield dependency needed for night-altitude calculations and target ranking.

### BugFix#
    Correction for __init__.py, remove non ASCII character.


## [V3.2.6] - 2026-08-09

### BugFix#
    Correction Dwarf Type Detection for Wide Mode

## [V3.2.5] - 2026-08-05

### Add
    Add Siril integration docs and UI preview support; update selector logic

    - README: add a detailed "Siril Integration" section and link to the bundled extern script.
    - pages/dwarf_backup_ui_explore.py: make the Siril session picker async, add thumbnail preview modal, helper to resolve backup thumbnails, and improved checkbox handling (clickable labels + select/deselect).
    - extern/Dwarfium_archive_selector.py: bump version to 1.0.0 and fix pre_stacked/mosaic detection logic so groups made entirely of RESTACKED_ sessions are treated correctly.

    In Explore UI import load_mosaic_info and show mosaic layout/scale from shotsInfo.json;
    In Mosaic page, notify that the mosaic was repaired on the Dwarf

## [V3.2.4] - 2026-07-28

### Add
    In Explore UI import load_mosaic_info and show mosaic layout/scale from shotsInfo.json;
    In Mosaic page, notify that the mosaic was repaired on the Dwarf

### BugFix#
    Correction for Long Source FileName in Tranfer Page
    Correction to Add Trace and Notification for File Transfer Error.
    Add mosaic-related translation keys across de/en/es/fr.
    Adjust dialog and scroll area sizing.
    In Mosaic page make notify_me accept a type and mount its refreshable container

## [V3.2.3] - 2026-07-19

### BugFix#
    Fix astropy, astroquery and pyvo version to resolve build exe errors
    Correction for Bad variable name
    Add await for load_selected_backupDrive

## [V3.2.2] - 2026-07-17

### Add
    Add 'stacked_panels' mode to Siril Megastack
    Introduce a stack_mode option (default "raw") to generate_siril_megastack_json so megastack generation can use already-stacked FITS per mosaic panel or per-session ("stacked_panels").
    When using stacked_panels, raw lights are replaced with stacked*.fits, dark-matching is skipped, and missing panel stacks are logged.
    Expose a radio in the Explore UI to select the mode and pass it to the API; include the chosen mode in the generated JSON and show a small tag in the notification.
    Add translation keys (en/fr/es/de) for labels and hints.

## [V3.2.1] - 2026-07-16

### Add
    Implement multi-session Siril JSON generation for combining observations across filters (HaRGB, HOO, etc).
    Add functions to reconstruct missing mosaic ZIPs from panel FITS files when compression didn't complete on Dwarf.
    Improve connection resilience for long-running operations
    Support both backup and manual sessions in megastack mode.

### BugFix#
    fix ftp availability in Transfer Page
    fix sizing sort in Report Page
    fix row indexing in session JSON export, and add path accessibility tracking.
    

## [V3.2.0] - 2026-05-22

### Add
    Official Release 

## [V3.1.9_RC2] - 2026-05-21

### Add
    Add DB backup
    Added api/db_backup.py for automatic startup (.bak)/shutdown (.last) and manual timestamped DB backups.
    Add Dwarf type detection & session size tracking
    Introduce automatic Dwarf device detection (by stacked image resolution + binning) and checks for type mismatches (USB and FTP).
    Added test_plan_dwarfium_scop_archive.md
    Miscellaneous fixes and translation additions to support these features.

### BugFix#
   Add missings Translations
   FTP sync improvements: include STARTRAILS/RESTACKED handling and correction for path conversion
   buildDwarfiumScopeArchive now copies assets/music into dist.

## [V3.1.9_RC1] - 2026-05-20

### Add
    Scan/sync functions (local and FTP) now accept optional progress_callback and report per-folder progress.
    Add main Gallery for Manual Session
    Add disk-space cache, widget and report
    Persist and display disk usage and add support for storage reporting.
    Add a persistent diskinfo.json cache and disk space widget
    that shows live or cached values when drives are offline.
    Database schema bumped to v14
    Help/locales updated
    Report page scaffold added

## [V3.1.8_RC3] - 2026-05-14

### BugFix#
   Remove print_log been replaced by claude in Mosaic stiching
   Ignore wcs.fits files when replace fits

## [V3.1.8_RC2] - 2026-05-14

### BugFix#
    Refactor empty_local_archive_dwarf_dir to accept a local directory path.
    Use storage-based help drawer state when toggling help
    run MTP availability check off the main thread for responsiveness
    Add correct notify_archive_cleaned translation to send that notification.
    Correct button namings to avoid errors

## [V3.1.8_RC1] - 2026-05-13

### Add
    Add video export & slideshow / music strings and assets
    FFmpeg status UI and helper tool integration;
    add astrometry_scan.bat and a new tools/video_export.py. Introduce path utility helpers (h) and adjust session path handling across manual session code to store/use relative DB paths. Extend DB queries and manual session API to include ManualSessionDrive fields and update related insert/update call signature.
    Improve robustness (date parsing fallback),
    UI tweaks (thin global scrollbar, layout/scroll behavior, favorite-filter button)
    
### BugFix#
    Various locale files updated with new translations and minor bugfixes (date index fix in Explore listing). 
    get_relative_file_path, get_basefolder_from_db_path correction
       
## [V3.1.7_RC1] - 2026-05-11

### Add
    Introduce local ASTAP integration and a Sky Map WCS feature.

    - Add ASTAP discovery, configuration and solve functions
    - enhance auto_resolve to prefer ASTAP, then solve-field, then Nova API.
    - Improve online upload by sending plate-scale hints extracted from FITS headers to Nova (scale_lower/scale_upper).
    - Add SessionWCS DB table, unique index and migration to DB version 12
    - Add sky map UI: new component components/sky_map_wcs.py

    - Add integrity check for stacked FITS size in backup functions to detect corrupted stacked FITS.

### BugFix#
    Improve UI in Explore / Manual Explore
    Corrected Missing Translations

## [V3.1.6_RC5] - 2026-05-07

### Add
    Add more translations
    
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


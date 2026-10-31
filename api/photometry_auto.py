"""Automatic photometry of a session from Scope Archive (user-asked Oct 2026:
"Photometry (auto)" in Explore - no Siril window to open, no script to load).

Siril runs in the background, without its window (siril-cli in pipe mode,
driven through pySiril - user-tested with Siril 1.4.4: started in 3 s, a
Dwarf 3 image plate solved in 0.7 s against the local Gaia DR3). The work is
the Siril script's own (extern/Dwarfium_archive_selector.py, imported without
sirilpy nor Qt): photometry_script() writes the same .ssf as its
"📈 Photometry" option, ScriptRunner runs it - Siril's commands sent to
siril-cli, the photometry done here in Python. The results land where the
script puts them: _PHOTOMETRY/<star>/<session>/ at the archive's root.

In a working folder of this PC (user-asked: the archive's drive may be slow):
<work folder>/<session folder>/ - lights, darks and flat copied there, the
session read once. An earlier run stopped there is resumed (its green
images kept, its plate solved images skipped). Deleted once the run
succeeded (user-chosen), kept when it failed - for the next run to resume.
The session's earlier results in _PHOTOMETRY are moved to previous/.

The choices (user-chosen, Oct 2026): the AAVSO sequence by default, the
other comparison stars when the star has none (not exportable then); the
target's saturated images left out unless asked; the star's last list of
comparison stars reused unless a new one is asked."""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

PHOTOMETRY_WORK_SUBDIR = "DwarfiumPhotometry"
_FITS = (".fits", ".fit", ".fts")
_LOCK = threading.Lock()     # one Siril at a time: pySiril's pipes have fixed names


# ----------------------------------------------------------------------------
# The Siril script, imported without Siril


def _extern_dir() -> Path:
    if getattr(sys, "frozen", False):        # next to the .exe (buildDwarfiumScopeArchive.py)
        return Path(sys.executable).parent / "extern"
    return Path(__file__).resolve().parent.parent / "extern"


_selector = None


def selector():
    """The Siril script as a module (HEADLESS: its functions, ScriptRunner)."""
    global _selector
    if _selector is None:
        path = _extern_dir() / "Dwarfium_archive_selector.py"
        spec = importlib.util.spec_from_file_location("dwarfium_archive_selector", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _selector = module
    return _selector


def _bundle_hint():   # pragma: no cover - never called
    """The modules the Siril script imports, named here for PyInstaller (it
    can't see inside the script, loaded from extern/ at run time)."""
    import astropy.units  # noqa: F401
    import certifi  # noqa: F401
    import matplotlib.pyplot  # noqa: F401
    import numpy  # noqa: F401
    import pysiril.siril  # noqa: F401
    if sys.platform.startswith("win"):   # pySiril's named pipes (pywin32)
        import win32file  # noqa: F401
        import win32pipe  # noqa: F401
    import requests  # noqa: F401
    from astropy.coordinates import EarthLocation, SkyCoord  # noqa: F401
    from astropy.io import fits  # noqa: F401
    from astropy.time import Time  # noqa: F401
    from astropy.utils import iers  # noqa: F401
    from astropy.wcs import WCS  # noqa: F401
    from astropy.wcs.utils import proj_plane_pixel_scales  # noqa: F401


# ----------------------------------------------------------------------------
# siril-cli


def siril_candidates() -> list[str]:
    if sys.platform.startswith("win"):
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")]
        return [os.path.join(r, name, "bin", "siril-cli.exe") for r in roots if r for name in ("Siril", "SiriL")]
    if sys.platform == "darwin":
        return ["/Applications/Siril.app/Contents/MacOS/siril-cli",
                "/Applications/Siril.app/Contents/Resources/bin/siril-cli",
                "/Applications/Siril.app/Contents/Resources/bin/Siril-cli"]
    return [p for p in (shutil.which("siril-cli"), "/usr/bin/siril-cli", "/usr/local/bin/siril-cli",
                        shutil.which("siril"), "/usr/bin/siril") if p]


def find_siril(configured: str = "") -> str | None:
    """siril-cli: the one set in Scope Archive, else the usual places."""
    for path in ([configured] if configured else []) + siril_candidates():
        if path and os.path.isfile(path):
            return path
    return None


def pysiril_available() -> bool:
    return importlib.util.find_spec("pysiril") is not None


_PYSIRIL_MODULES = ("changelog", "LogMsg", "PipeReader", "PipeWriter", "ThreadSiril", "tools", "cpipe")


def _import_pysiril():
    """(Siril, LogMsg, ThreadSiril) of pySiril. Its lib/ modules are imported
    by their bare names ("import tools"): its folder put first on sys.path
    meanwhile - Scope Archive has a tools/ package of its own, which pySiril
    took instead (its translation then never set up)."""
    import builtins
    spec = importlib.util.find_spec("pysiril")
    if spec is None or not spec.origin:
        raise RuntimeError("pySiril not installed")
    lib = os.path.join(os.path.dirname(spec.origin), "lib")
    ours = {name: sys.modules.pop(name) for name in _PYSIRIL_MODULES if name in sys.modules
            and not os.path.normcase(str(getattr(sys.modules[name], "__file__", ""))).startswith(os.path.normcase(lib))}
    sys.path.insert(0, lib)
    try:
        from pysiril.siril import Siril
        log_msg, thread_siril = sys.modules["LogMsg"], sys.modules["ThreadSiril"]
    except (ImportError, KeyError) as e:
        raise RuntimeError(f"pySiril not usable ({e})") from e
    finally:
        if lib in sys.path:
            sys.path.remove(lib)
        sys.modules.update(ours)        # Scope Archive's own tools package back
    if not hasattr(builtins, "_"):      # pySiril's translation function
        builtins._ = lambda text: text
    return Siril, log_msg, thread_siril


def _pipe_sirils():
    """The siril-cli running in pipe mode ("-p") on this PC: only this
    automatic photometry starts them (Siril's own window is siril.exe)."""
    try:
        import psutil
    except ImportError:
        return []
    found = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmdline = proc.info.get("cmdline") or []
        except (psutil.Error, OSError):
            continue
        if name.startswith("siril-cli") and "-p" in cmdline[1:]:
            found.append(proc)
    return found


def stop_pipe_sirils(log=None) -> int:
    """siril-cli left in pipe mode by an earlier run stopped (user-reported
    Nov 2026: one left hanging, the next run talked to it through the same
    named pipe). Returns how many."""
    procs = _pipe_sirils()
    for proc in procs:
        try:
            proc.kill()
            if log:
                log(f"siril-cli left by an earlier run stopped (pid {proc.pid})")
        except Exception:
            pass
    if procs:
        time.sleep(1)
    return len(procs)


class SirilPipe:
    """siril-cli in pipe mode through pySiril, as the Siril script's
    self.siril: cmd(*args) raises the script's s.CommandError (refused) or
    s.SirilConnectionError (Siril gone); log(text, color) to our log."""

    def __init__(self, siril_exe: str, log):
        self._log = log
        self._errors = selector().s
        Siril, LogMsg, ThreadSiril = _import_pysiril()
        stop_pipe_sirils(log)
        # pySiril prints everything: to our log instead (no console in the .exe)
        LogMsg.trace.WriteRaw = lambda _self, buffer: self._pysiril_line(buffer)
        if sys.platform.startswith("win"):
            # siril-cli is a console program: no console window opened for it
            import subprocess as _subprocess
            import types

            def _popen(*args, **kwargs):
                kwargs.setdefault("creationflags", getattr(_subprocess, "CREATE_NO_WINDOW", 0))
                return _subprocess.Popen(*args, **kwargs)
            ThreadSiril.subprocess = types.SimpleNamespace(**{**vars(_subprocess), "Popen": _popen})
        try:
            self.app = Siril(siril_exe, delai_start=30)
        except (Exception, SystemExit) as e:   # pySiril exits on a version it refuses
            raise RuntimeError(f"siril-cli not usable ({siril_exe}): {e or type(e).__name__}") from e
        self.version = self.app.version
        if not self.app.Open():
            raise RuntimeError("Siril did not start in pipe mode (siril-cli -p)")

    def _pysiril_line(self, buffer):
        for line in str(buffer).splitlines():
            line = line.rstrip()
            # Siril's own log lines ("> command", ": log: ..."): what the user needs
            if line.startswith(("> ", ": log:", "ERROR", "WARNING")):
                self._log("    " + line)

    def _drain(self):
        """Statuses left in pySiril's queue: not this command's."""
        import queue
        while True:
            try:
                self.app.qStatus.get_nowait()
            except queue.Empty:
                return

    def _own_status(self, name):
        """True / False: this command's own "status: success|error <name>"
        line from Siril, waited for while Siril runs (None when it stopped).
        pySiril takes the first status in its queue as the command's: one
        left over from the command before (user-reported Nov 2026: Scope
        Archive's run stuck after a seqplatesolve that ended in error) would
        stand for this one, and this one's for the next."""
        import re
        pattern = re.compile(r"^status: (success|error) " + re.escape(name) + r"\b")
        while True:
            for line in list(self.app.GetData()):
                m = pattern.match(line.strip())
                if m:
                    time.sleep(0.05)      # its queued status too, then dropped
                    self._drain()
                    return m[1] == "success"
            if not self.app.thSiril.IsRunning():
                return None
            time.sleep(0.05)

    def cmd(self, *args):
        command = " ".join(str(a) for a in args)
        name = command.split()[0] if command.split() else ""
        self._drain()
        self.app.GetData().clear()
        self.app.Execute(command)
        ok = self._own_status(name)
        if ok:
            return
        answer = [line for line in self.app.GetData() if line.strip()]
        if ok is None or not self.app.thSiril.IsRunning():
            raise self._errors.SirilConnectionError(f"Siril stopped during '{command}'")
        why = next((line[len("log:"):].strip() for line in reversed(answer) if line.startswith("log:")), "")
        raise self._errors.CommandError(f"'{command}' failed" + (f": {why}" if why else ""))

    def log(self, text, color=None):
        self._log(str(text))

    def close(self):
        try:
            self.app.Close()
        except Exception:
            pass
        stop_pipe_sirils()       # none left behind, whatever happened


# ----------------------------------------------------------------------------
# The run


def default_work_root() -> str:
    """A folder of this PC (the archive's drive may be slow - user-asked)."""
    return str(Path.home() / PHOTOMETRY_WORK_SUBDIR)


def _session_name(data: dict) -> str:
    folder = os.path.basename(os.path.normpath(data.get("session", {}).get("session_dir") or "")) or "session"
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in folder)


def _fits_in(folder) -> list[str]:
    try:
        return sorted(f for f in os.listdir(folder) if f.lower().endswith(_FITS))
    except OSError:
        return []


def earlier_run(work: str, n_lights: int) -> bool:
    """The working folder holds this session's lights and their green images:
    a run stopped there, to resume."""
    proc = os.path.join(work, "process")
    green = [f for f in _fits_in(proc) if f.startswith("Green_")]
    return n_lights > 0 and len(_fits_in(os.path.join(work, "lights"))) >= n_lights and len(green) >= n_lights


def _copy_session(data: dict, work: str, log, progress, stopped=lambda: False):
    """lights/, darks/, flat/ of the working folder, as the Siril script's
    Load Dwarfium JSON (the bias isn't used by the photometry)."""
    lights = data.get("lights") or []
    if len({os.path.dirname(f) for f in lights}) > 1:
        raise ValueError("a mosaic session can't be measured")
    if os.path.isdir(work):
        shutil.rmtree(work)
    pairs = [(f, "lights") for f in lights]
    pairs += [(f, "darks") for f in (data.get("darks") or {}).get("files", [])]
    flat_file, flat_dir = data.get("flat_file"), data.get("flat_dir")
    if flat_file and os.path.isfile(flat_file):
        pairs.append((flat_file, "flat"))
    elif flat_dir and os.path.isdir(flat_dir):
        pairs += [(os.path.join(flat_dir, f), "flat") for f in _fits_in(flat_dir)]
    for sub in ("lights", "darks", "flat"):
        os.makedirs(os.path.join(work, sub), exist_ok=True)
    for i, (src, sub) in enumerate(pairs, 1):
        if stopped():
            raise RuntimeError("stopped")
        shutil.copy2(src, os.path.join(work, sub, os.path.basename(src)))
        progress(i, len(pairs), "copy")
    log(f"{len(lights)} light(s), {sum(1 for _, s in pairs if s == 'darks')} dark(s), "
        f"{sum(1 for _, s in pairs if s == 'flat')} flat(s) copied to {work}")


class AutoPhotometry:
    """One run, in a thread (start()): its log lines, progress and outcome
    read by the page. stop(): at the next Siril command or image."""

    def __init__(self, data: dict, star: str, work_root: str, siril_exe: str, aavso: bool = True,
                 keep_saturated: bool = False, new_comparison_list: bool = False, start_again: bool = False):
        self.data, self.star = data, " ".join(star.split())
        self.work = os.path.join(work_root or default_work_root(), _session_name(data))
        self.siril_exe, self.aavso, self.keep_saturated = siril_exe, aavso, keep_saturated
        self.new_comparison_list, self.start_again = new_comparison_list, start_again
        self.lines: list[str] = []
        self.step, self.done, self.total = "", 0, 0
        self.finished, self.ok, self.summary, self.error = False, False, [], ""
        self.runner = None
        self._stop = False

    # what the page reads
    def log(self, text):
        line = f"{datetime.now():%H:%M:%S} {text}"
        self.lines.append(line)
        del self.lines[:-400]

    def progress(self, done, total, step=""):
        self.done, self.total, self.step = done, total, step or self.step

    def stop(self):
        self._stop = True
        if self.runner is not None:
            self.runner.stop_requested = True

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="auto-photometry").start()

    def _run(self):
        if not _LOCK.acquire(blocking=False):
            self.error = "another automatic photometry is running"
            self.finished = True
            return
        self._siril = None
        try:
            self._run_locked()
        except Exception as e:
            import traceback
            self.error = f"{type(e).__name__}: {e}"
            self.log(f"failed: {self.error} - the working folder is kept: the next run resumes there")
            try:   # in build_sessions.log too (user-reported Nov 2026: the log just stopped)
                with open(os.path.join(self.work, "build_sessions.log"), "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now():%H:%M:%S} failed: {self.error}\n{traceback.format_exc()}")
            except OSError:
                pass
        finally:
            if self._siril is not None:
                self._siril.close()
                self._siril = None
            _LOCK.release()
            self.finished = True

    def _run_locked(self):
        sel = selector()
        data, star = self.data, self.star
        lights = data.get("lights") or []
        if not lights:
            raise ValueError("no light FITS for this session (folder not reachable?)")
        os.makedirs(self.work, exist_ok=True)
        resume = not self.start_again and earlier_run(self.work, len(lights))
        self.log(f"=== Automatic photometry of {star}, {len(lights)} image(s) - "
                 + ("earlier run resumed" if resume else "new run"))
        if not resume:
            self.step = "copy"
            _copy_session(data, self.work, self.log, self.progress, stopped=lambda: self._stop)
        if self._stop:
            raise RuntimeError("stopped")
        # The DWARF's local time in DATE-OBS: this PC's offset at that date
        first = {k: v for _, k, v, _ in sel.read_fits_cards(os.path.join(self.work, "lights",
                                                                          _fits_in(os.path.join(self.work, "lights"))[0]))}
        utc_offset = sel.local_utc_offset_hours(first.get("DATE-OBS", ""))
        ssf_path, lines = sel.photometry_script(
            data, self.work, star, utc_offset, log=self.log, warn=lambda t: self.log(f"⚠️ {t}"),
            resume=resume, keep_saturated=self.keep_saturated, aavso=self.aavso)
        self.log(f"script: {ssf_path} (UTC{utc_offset:+g} h)")

        self.step = "siril"
        self.log(f"starting Siril: {self.siril_exe}")
        siril = self._siril = SirilPipe(self.siril_exe, self.log)
        self.log(f"{siril.version} started (no window)")
        log_path = os.path.join(self.work, "build_sessions.log")

        def build_log(text, new=False):
            self.log(text)
            try:
                with open(log_path, "w" if new else "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now():%H:%M:%S} {text}\n")
            except OSError:
                pass

        build_log(f"=== Automatic photometry (Scope Archive) {datetime.now():%Y-%m-%d %H:%M:%S}", new=True)
        self.runner = sel.ScriptRunner(siril, self.work, build_log, progress=self.progress,
                                       log_path=log_path, aavso_fallback=True)
        self.runner.stop_requested = self._stop
        # A new list of comparison stars, not the star's last one
        self.runner.reuse_compstars = not self.new_comparison_list
        self.runner.keep_previous = True     # the session's earlier results moved to previous/
        start = time.monotonic()
        self.ok = self.runner.run_script(ssf_path, lines)
        self.summary = self.runner.summary or []
        elapsed = int(time.monotonic() - start)
        if not self.ok:
            self.error = "stopped" if self._stop else "a step failed - see the log"
            self.log(f"not finished ({self.error}); the working folder is kept: the next run resumes there")
            return
        self.log(f"done in {elapsed // 60} min {elapsed % 60:02d} s")
        siril.close()
        self._siril = None
        try:
            shutil.rmtree(self.work)
            self.log(f"working folder deleted: {self.work}")
        except OSError as e:
            self.log(f"working folder not deleted ({e}): {self.work}")

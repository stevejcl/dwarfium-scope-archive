"""
tools/video_export.py — Slideshow video generator for Dwarfium Scope Archive.

Generates an MP4 slideshow from favorite session images with:
- Fade in/out transitions between photos
- Signature banner at the bottom (name + free text + metadata)
- Configurable font, duration, resolution

Usage (standalone):
    python tools/video_export.py --help

Called from home.py UI with VideoExportConfig dataclass.
"""

from __future__ import annotations
import os
import sys
import glob
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── Config ────────────────────────────────────────────────────────────────────

FONT_PRESETS = {
    "Sans-serif":  ["Arial", "LiberationSans-Regular", "DejaVuSans", "FreeSans"],
    "Serif":       ["Georgia", "LiberationSerif-Regular", "DejaVuSerif", "FreeSerif"],
    "Monospace":   ["Consolas", "LiberationMono-Regular", "DejaVuSansMono", "FreeMono"],
    "Elegant":     ["Palatino Linotype", "GFSBaskerville", "LiberationSerif-BoldItalic"],
}

VIDEO_RESOLUTIONS = {
    "4K (3840×2160)":  (3840, 2160),
    "FHD (1920×1080)": (1920, 1080),
    "HD (1280×720)":   (1280, 720),
}

FONT_SIZES = {"Small": 28, "Medium": 36, "Large": 48}

BANNER_HEIGHT_RATIO = 0.10  # 10% of image height


@dataclass
class VideoExportConfig:
    images: list[dict]          # list of {file_path, object_name, dwarf_name, session_date}
    output_path: str            # destination MP4 path
    user_name: str = ""         # signature name
    free_text: str = ""         # optional custom text
    font_preset: str = "Sans-serif"
    font_size_label: str = "Medium"
    duration_per_image: float = 8.0   # seconds per photo
    fade_duration: float = 1.0         # seconds for fade in/out
    resolution: str = "FHD (1920×1080)"
    fps: int = 30
    extra_info: bool = False        # show exp/gain/filter/total exposure on 2nd line
    music_path: str = ""            # path to audio file (MP3/WAV/OGG)
    music_fade_in: float = 2.0      # fade in duration in seconds
    music_fade_out: float = 3.0     # fade out duration in seconds
    progress_callback: Callable[[int, int, str], None] | None = None


# ── Font loading ──────────────────────────────────────────────────────────────

def _find_font(names: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try each font name, return first found or fallback to default."""
    font_dirs = []
    if platform.system() == "Windows":
        font_dirs += [
            "C:/Windows/Fonts",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft/Windows/Fonts"),
        ]
    else:
        font_dirs += [
            "/usr/share/fonts", "/usr/local/share/fonts",
            os.path.expanduser("~/.fonts"),
        ]

    for name in names:
        # Try direct name match
        for d in font_dirs:
            for ext in ["ttf", "otf", "TTF", "OTF"]:
                candidates = glob.glob(f"{d}/**/{name}.{ext}", recursive=True) + \
                             glob.glob(f"{d}/{name}.{ext}")
                if candidates:
                    try:
                        return ImageFont.truetype(candidates[0], size)
                    except Exception:
                        pass
    # Fallback
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def get_fonts(config: VideoExportConfig) -> tuple:
    """Return (font_main, font_small) for the banner."""
    size_main  = FONT_SIZES.get(config.font_size_label, 36)
    size_small = max(18, size_main - 10)
    names = FONT_PRESETS.get(config.font_preset, FONT_PRESETS["Sans-serif"])
    return _find_font(names, size_main), _find_font(names, size_small)


# ── Image processing ──────────────────────────────────────────────────────────

def _load_image(path: str, target_w: int, target_h: int) -> np.ndarray:
    """Load image with PIL, fit to target resolution (letterbox), return BGR numpy."""
    img = Image.open(path).convert("RGB")
    img_w, img_h = img.size

    # Fit inside target keeping aspect ratio
    scale = min(target_w / img_w, target_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Center on black background
    canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    x = (target_w - new_w) // 2
    y = (target_h - new_h) // 2
    canvas.paste(img, (x, y))

    return cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2BGR)


def _draw_banner(frame: np.ndarray, meta: dict, config: VideoExportConfig,
                 font_main: ImageFont.FreeTypeFont,
                 font_small: ImageFont.FreeTypeFont) -> np.ndarray:
    """Draw signature banner at the bottom of the frame."""
    h, w = frame.shape[:2]
    banner_h = max(60, int(h * BANNER_HEIGHT_RATIO))

    # Convert to PIL for text rendering
    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil, "RGBA")

    # Semi-transparent black banner
    banner_y = h - banner_h
    #draw.rectangle([(0, banner_y), (w, h)], fill=(0, 0, 0, 180))
    banner_y = 0
    draw.rectangle([(0, 0), (w, banner_h)], fill=(0, 0, 0, 180))

    # Left side: object name + date + device
    pad = 16
   # Strip any emoji prefixes that might come from favorites (🛰️, 🔭, 🖼️, 📷, ⭐, ☆)
    import re
    def _strip_emoji_prefix(s: str) -> str:
        return re.sub(r'^[\U00010000-\U0010ffff\u2600-\u27BF\u2B00-\u2BFF\u1F300-\u1FAFF\u26A0-\u26FF☆⭐\s]+', '', s).strip()

    obj_name = _strip_emoji_prefix(meta.get("object_name", ""))
    dwarf    = _strip_emoji_prefix(meta.get("dwarf_name", ""))
    date_str = _strip_emoji_prefix(meta.get("session_date", ""))
    meta_text = f"{obj_name}  ·  {dwarf}  ·  {date_str}"
    draw.text((pad, banner_y + 8), meta_text, font=font_main, fill=(255, 255, 255, 230))

    # Second line: exp / gain / filter / total exposure
    if config.extra_info:
        exp     = meta.get("exp_time", "")
        gain    = meta.get("gain", "")
        filt    = meta.get("filter", "")
        total   = meta.get("total_exposure", "")
        parts2  = [p for p in [
            f"Exp {exp}s" if exp else "",
            f"Gain {gain}" if gain else "",
            filt,
            f"Total {total}" if total else "",
        ] if p]
        if parts2:
            line2 = "  ·  ".join(parts2)
            draw.text((pad, banner_y + int(banner_h * 0.55)), line2,
                      font=font_small, fill=(180, 220, 255, 200))

    # Right side: user name + free text
    sig_parts = []
    if config.user_name.strip():
        sig_parts.append(config.user_name.strip())
    if config.free_text.strip():
        sig_parts.append(config.free_text.strip())
    sig_text = "  ·  ".join(sig_parts) if sig_parts else ""

    if sig_text:
        bbox = draw.textbbox((0, 0), sig_text, font=font_small)
        sig_w = bbox[2] - bbox[0]
        draw.text((w - sig_w - pad, banner_y + 12), sig_text,
                  font=font_small, fill=(200, 200, 200, 200))

    # Dwarfium watermark (very subtle)
    wm = "Dwarfium Scope Archive"
    wm_bbox = draw.textbbox((0, 0), wm, font=font_small)
    wm_w = wm_bbox[2] - wm_bbox[0]
    draw.text((w - wm_w - pad, banner_y + banner_h - 28), wm,
              font=font_small, fill=(120, 120, 120, 160))

    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


# ── Fade helpers ──────────────────────────────────────────────────────────────

def _fade_frames(from_frame: np.ndarray, to_frame: np.ndarray,
                 n_frames: int) -> list[np.ndarray]:
    """Generate crossfade frames from from_frame to to_frame."""
    frames = []
    for i in range(n_frames):
        alpha = i / max(n_frames - 1, 1)
        blended = cv2.addWeighted(from_frame, 1 - alpha, to_frame, alpha, 0)
        frames.append(blended)
    return frames


def _black_frame(w: int, h: int) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


# ── Main export ───────────────────────────────────────────────────────────────

def find_ffmpeg() -> str | None:
    """Find ffmpeg executable — checks PATH, repo extern/, then common locations."""
    import shutil as _shutil
    # 1. PATH
    found = _shutil.which("ffmpeg") or _shutil.which("ffmpeg.exe")
    if found:
        return found
    # 2. Bundled in repo extern/
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in [
        repo_root / "extern" / "windows" / "ffmpeg.exe",
        repo_root / "extern" / "ffmpeg" / "ffmpeg.exe",
        repo_root / "extern" / "ffmpeg.exe",
    ]:
        if candidate.exists():
            return str(candidate)
    # 3. Common Windows install locations
    import platform
    if platform.system() == "Windows":
        for p in [
            "C:/ffmpeg/bin/ffmpeg.exe",
            "C:/Program Files/ffmpeg/bin/ffmpeg.exe",
            "C:/Program Files (x86)/ffmpeg/bin/ffmpeg.exe",
        ]:
            if Path(p).exists():
                return p
    return None


def has_ffmpeg() -> bool:
    return find_ffmpeg() is not None


def mix_audio(video_path: str, music_path: str, output_path: str,
              fade_in: float = 2.0, fade_out: float = 3.0) -> str:
    """
    Mix audio into video using ffmpeg.
    - Loops music if shorter than video
    - Applies fade in / fade out
    - Returns output path
    """
    import subprocess, tempfile

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found. Install ffmpeg to add music.")

    # Get video duration
    probe = subprocess.run(
        [ffmpeg, "-i", video_path],
        capture_output=True, text=True
    )
    duration = None
    for line in probe.stderr.splitlines():
        if "Duration" in line:
            parts = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = parts.split(":")
            duration = int(h) * 3600 + int(m) * 60 + float(s)
            break

    # Build audio filter: loop + fade in/out
    audio_filter = f"aloop=loop=-1:size=2e+09,atrim=duration={duration}"
    if fade_in > 0:
        audio_filter += f",afade=t=in:d={fade_in}"
    if fade_out > 0 and duration:
        fade_start = max(0, duration - fade_out)
        audio_filter += f",afade=t=out:st={fade_start:.2f}:d={fade_out}"

    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-i", music_path,
        "-filter_complex", f"[1:a]{audio_filter}[a]",
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio mix failed: {result.stderr[-500:]}")
    return output_path


def get_music_files(music_dir: str = None) -> list[dict]:
    """
    List available music files from assets/music/ directory.
    Returns list of {name, path} dicts.
    """
    import glob as _glob

    if music_dir is None:
        # Default: assets/music/ relative to this file's parent
        music_dir = str(Path(__file__).resolve().parent.parent / "assets" / "music")

    files = []
    for ext in ["mp3", "wav", "ogg", "m4a", "MP3", "WAV", "OGG"]:
        files += _glob.glob(f"{music_dir}/*.{ext}")

    return [{"name": Path(p).stem.replace("_", " ").title(), "path": p}
            for p in sorted(files)]


def export_video(config: VideoExportConfig) -> str:
    """
    Generate the slideshow MP4.
    Returns the output path on success, raises on error.
    """
    if not config.images:
        raise ValueError("No images to export")

    target_w, target_h = VIDEO_RESOLUTIONS.get(config.resolution, (1920, 1080))
    fps = config.fps
    fade_frames_n  = max(1, int(config.fade_duration * fps))
    hold_frames_n  = max(1, int((config.duration_per_image - 2 * config.fade_duration) * fps))

    font_main, font_small = get_fonts(config)

    # Ensure output directory exists
    Path(config.output_path).parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(config.output_path, fourcc, fps, (target_w, target_h))

    if not writer.isOpened():
        raise RuntimeError(f"Cannot open video writer for: {config.output_path}")

    total = len(config.images)
    black = _black_frame(target_w, target_h)

    prev_frame = None

    for idx, meta in enumerate(config.images):
        path = meta.get("file_path", "")
        if not path or not os.path.exists(path):
            continue

        if config.progress_callback:
            config.progress_callback(idx + 1, total, meta.get("object_name", path))

        # Load and add banner
        try:
            raw = _load_image(path, target_w, target_h)
        except Exception as e:
            print(f"[VideoExport] Skipping {path}: {e}")
            continue

        frame_with_banner = _draw_banner(raw, meta, config, font_main, font_small)

        # Fade in
        fade_in_from = prev_frame if prev_frame is not None else black
        for f in _fade_frames(fade_in_from, frame_with_banner, fade_frames_n):
            writer.write(f)

        # Hold
        for _ in range(hold_frames_n):
            writer.write(frame_with_banner)

        prev_frame = frame_with_banner

    # Final fade out to black
    if prev_frame is not None:
        for f in _fade_frames(prev_frame, black, fade_frames_n):
            writer.write(f)

    writer.release()

    # Mix audio if provided
    if config.music_path and Path(config.music_path).exists():
        if config.progress_callback:
            config.progress_callback(len(config.images), len(config.images), "🎵 Adding music...")
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            # Output with audio alongside original
            audio_output = config.output_path.replace(".mp4", "_music.mp4")
            try:
                mix_audio(
                    config.output_path,
                    config.music_path,
                    audio_output,
                    fade_in=config.music_fade_in,
                    fade_out=config.music_fade_out,
                )
                # Replace original with audio version
                os.replace(audio_output, config.output_path)
            except Exception as e:
                print(f"[VideoExport] Audio mix failed: {e} — video saved without music")
        else:
            print("[VideoExport] ffmpeg not found — video saved without music")

    return config.output_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def list_fonts() -> list[str]:
    """Return available font preset names."""
    return list(FONT_PRESETS.keys())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Dwarfium Slideshow Video Generator")
    parser.add_argument("images", nargs="+", help="Image file paths")
    parser.add_argument("--output",   default="DwarfiumGallery.mp4", help="Output MP4 path")
    parser.add_argument("--name",     default="",    help="Signature name")
    parser.add_argument("--text",     default="",    help="Free text")
    parser.add_argument("--font",     default="Sans-serif", choices=list(FONT_PRESETS.keys()))
    parser.add_argument("--fontsize", default="Medium", choices=list(FONT_SIZES.keys()))
    parser.add_argument("--duration", type=float, default=8.0, help="Seconds per image")
    parser.add_argument("--fade",     type=float, default=1.0,  help="Fade duration")
    parser.add_argument("--resolution", default="FHD (1920×1080)", choices=list(VIDEO_RESOLUTIONS.keys()))
    args = parser.parse_args()

    images = [{"file_path": p, "object_name": Path(p).stem,
               "dwarf_name": "", "session_date": ""} for p in args.images]

    def progress(i, total, name):
        print(f"  [{i}/{total}] {name}")

    config = VideoExportConfig(
        images=images,
        output_path=args.output,
        user_name=args.name,
        free_text=args.text,
        font_preset=args.font,
        font_size_label=args.fontsize,
        duration_per_image=args.duration,
        fade_duration=args.fade,
        resolution=args.resolution,
        progress_callback=progress,
    )

    print(f"Generating {len(images)} image(s) → {args.output}")
    out = export_video(config)
    print(f"✅ Done: {out}")

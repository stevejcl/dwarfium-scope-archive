import shutil
import subprocess
import zipfile
from pathlib import Path
import os
import platform

# correction for Pyinstaller Error
import astroquery
from pathlib import Path
astroquery_dir = Path(astroquery.__file__).parent
citation_path = astroquery_dir / "CITATION"

sep = os.pathsep  # Cross-platform separator: ; on Windows, : on Unix/macOS

extra_data = [
    f"{citation_path}{sep}astroquery",
    f"astroquery/simbad/data/query_criteria_fields.json{sep}astroquery/simbad/data"
]
   
APP_NAME = "DwarfiumScopeArchive"
ICON_NAME = "DwarfiumScopeArchive.ico"
SOURCE_FILE = "dwarfium_scope_archive.py"
DIST_DIR = Path("dist")
BUILD_DIR = Path("build")
IMAGE_DIR = Path("image")
DIST_IMAGE_DIR = DIST_DIR / "image"
DIST_DB_DIR = DIST_DIR / "db"

print("Current working directory:", os.getcwd())

# Step 1 – Clean old build folders
for folder in [DIST_DIR, BUILD_DIR]:
    if folder.exists():
        print(f"Removing {folder}...")
        shutil.rmtree(folder)

# Step 1b – Extract version from CHANGELOG.md and write version.py
import re
version_str = "Unknown"
try:
    with open("CHANGELOG.md", "r", encoding="utf-8") as f:
        for line in f:
            m = re.search(r"\[V?([\d.]+[a-z]?)\]", line)
            if m:
                version_str = m.group(1)
                break
except Exception:
    pass

with open("version.py", "w", encoding="utf-8") as f:
    f.write(f'APP_VERSION = "{version_str}"\n')
print(f"Version extracted: {version_str}")

# Step 2 – Run nicegui-pack
print("Building executable...")

subprocess.run([
    "nicegui-pack",
    "--onefile",
    "--windowed",
    "--icon", ICON_NAME,
    "--name", APP_NAME,
    *[arg for data in extra_data for arg in ["--add-data", data]],
    SOURCE_FILE
], check=True)

# Step 3 – Copy additional files into dist
print("Copying extra files into dist...")

# Create the folders dist/image and dist/db if they don't exist
DIST_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
DIST_DB_DIR.mkdir(parents=True, exist_ok=True)

# Copy all .png files from the current folder to dist/image
for png_file in IMAGE_DIR.glob("*.png"):
    dest = DIST_IMAGE_DIR / png_file.name
    print(f"Copying {png_file} to {dest}")
    shutil.copy2(png_file, dest)

# Copy all .jpg files from the current folder to dist/image
for jpg_file in IMAGE_DIR.glob("*.jpg"):
    dest = DIST_IMAGE_DIR / jpg_file.name
    print(f"Copying {jpg_file} to {dest}")
    shutil.copy2(jpg_file, dest)

# Copy the dso_catalog.json file into dist/db
src_json = Path("db") / "dso_catalog.json"
dest_json = DIST_DB_DIR / "dso_catalog.json"

if src_json.exists():
    print(f"Copying {src_json} to {dest_json}")
    shutil.copy2(src_json, dest_json)
else:
    print(f"Warning: {src_json} does not exist, skipping.")

# Step 4 – Zip everything in dist
import platform
suffix = os.environ.get("RUNNER_OS", "unknown")  # Windows, Linux, macOS
zip_path = Path(f"{APP_NAME}-{suffix}.zip")
print(f"Creating archive {zip_path}...")

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
    for path in DIST_DIR.rglob("*"):
        arcname = path.relative_to(DIST_DIR)
        zipf.write(path, arcname)

print("Build and packaging complete.")
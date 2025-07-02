import shutil
import subprocess
import zipfile
from pathlib import Path

APP_NAME = "DwarfiumScopeArchive"
ICON_NAME = "DwarfiumScopeArchive.ico"
SOURCE_FILE = "dwarfium_scope_archive.py"
DIST_DIR = Path("dist")
BUILD_DIR = Path("build")
IMAGE_DIR = Path("image")
DIST_IMAGE_DIR = DIST_DIR / "image"
DIST_DB_DIR = DIST_DIR / "db"

import os
print("Current working directory:", os.getcwd())

# Step 1 – Clean old build folders
for folder in [DIST_DIR, BUILD_DIR]:
    if folder.exists():
        print(f"Removing {folder}...")
        shutil.rmtree(folder)

# Step 2 – Run nicegui-pack
print("Building executable...")
subprocess.run([
    "nicegui-pack",
    "--onefile",
    "--windowed",
    "--icon", ICON_NAME,
    "--name", APP_NAME,
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
suffix = platform.system().lower()  # 'windows', 'linux', 'darwin'
zip_path = Path(f"{APP_NAME}-{suffix}.zip")
print(f"Creating archive {zip_path}...")

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
    for path in DIST_DIR.rglob("*"):
        arcname = path.relative_to(DIST_DIR)
        zipf.write(path, arcname)

print("Build and packaging complete.")

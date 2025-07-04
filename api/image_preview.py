# image_preview.py

import os
from urllib.parse import quote
from fastapi import HTTPException
from fastapi.responses import FileResponse
# Encoding changed to UTF-8
BASE_FOLDER = None  # This should be set in your app

def set_base_folder(path: str):
    global BASE_FOLDER
    BASE_FOLDER = path

def build_preview_url(file_path: str) -> str:
    """Builds a URL-safe preview URL for an image."""
    return f'/preview/{quote(file_path.replace("\\", "/"))}'

def serve_preview(file_path: str):
    """Securely serves an image from the base folder."""
    global BASE_FOLDER
    if BASE_FOLDER is None:
        raise HTTPException(status_code=400, detail="Base folder not set")

    full_path = os.path.abspath(os.path.join(BASE_FOLDER, file_path.replace("\\", "/")))
    if not full_path.startswith(os.path.abspath(BASE_FOLDER)):
        raise HTTPException(status_code=403, detail="Access denied")

    if os.path.exists(full_path) and os.path.isfile(full_path):
        return FileResponse(full_path)
    else:
        raise HTTPException(status_code=404, detail="File not found")

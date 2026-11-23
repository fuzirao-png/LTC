"""File upload validation, save, and cleanup utilities."""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4


ALLOWED_AUDIO_EXTENSIONS: set[str] = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".wma", ".aac"}
ALLOWED_VIDEO_EXTENSIONS: set[str] = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_MEDIA_EXTENSIONS: set[str] = ALLOWED_AUDIO_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS


def is_audio_file(filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    return suffix in ALLOWED_AUDIO_EXTENSIONS


def is_video_file(filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    return suffix in ALLOWED_VIDEO_EXTENSIONS


def is_allowed_media_file(filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    return suffix in ALLOWED_MEDIA_EXTENSIONS


async def save_upload_file(upload_file: object, target_dir: str) -> str:
    """Save a FastAPI `UploadFile` to `target_dir` with a UUID-based filename.

    Returns the full path to the saved file.
    """
    dest = Path(target_dir)
    dest.mkdir(parents=True, exist_ok=True)
    # Access attributes dynamically so we don't add a hard FastAPI dependency.
    original_name: str = getattr(upload_file, "filename", "upload.bin")
    ext = Path(original_name).suffix or ".bin"
    file_path = dest / f"{uuid4().hex}{ext}"
    file_obj = getattr(upload_file, "file", None)
    if file_obj is None:
        raise RuntimeError("UploadFile has no .file attribute")
    with open(file_path, "wb") as out:
        shutil.copyfileobj(file_obj, out)
    return str(file_path)


def cleanup_file(file_path: str) -> None:
    """Remove a single file if it exists."""
    p = Path(file_path)
    if p.is_file():
        p.unlink()


def cleanup_files(*paths: str) -> None:
    """Remove all given files; ignores missing files."""
    for path in paths:
        cleanup_file(path)

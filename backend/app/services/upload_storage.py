from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.services.storage import storage_service

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx"}
UPLOAD_CHUNK_SIZE = 1024 * 1024
WINDOWS_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class SavedUploadFile:
    original_filename: str
    saved_filename: str
    storage_path: Path
    content_type: str | None
    size_bytes: int
    checksum_sha256: str


def sanitize_filename(filename: str | None) -> str:
    if not filename:
        return "upload"

    base_name = Path(filename.replace("\\", "/")).name.strip()
    safe_name = WINDOWS_UNSAFE_FILENAME_CHARS.sub("_", base_name)
    safe_name = safe_name.strip(" .")
    return safe_name or "upload"


def get_upload_extension(filename: str | None) -> str:
    return Path(sanitize_filename(filename)).suffix.lower()


def is_allowed_upload_filename(filename: str | None) -> bool:
    return get_upload_extension(filename) in ALLOWED_UPLOAD_EXTENSIONS


def build_saved_filename(original_filename: str | None) -> str:
    extension = get_upload_extension(original_filename)
    safe_stem = Path(sanitize_filename(original_filename)).stem[:80] or "upload"
    return f"{uuid4().hex}_{safe_stem}{extension}"


async def save_upload_file(upload_batch_id: UUID, upload_file: UploadFile) -> SavedUploadFile:
    original_filename = sanitize_filename(upload_file.filename)
    saved_filename = build_saved_filename(original_filename)
    batch_dir = storage_service.uploads_dir / str(upload_batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)
    storage_path = batch_dir / saved_filename

    checksum = hashlib.sha256()
    size_bytes = 0

    try:
        with storage_path.open("wb") as destination:
            while chunk := await upload_file.read(UPLOAD_CHUNK_SIZE):
                size_bytes += len(chunk)
                checksum.update(chunk)
                destination.write(chunk)
    except OSError:
        storage_path.unlink(missing_ok=True)
        raise
    finally:
        await upload_file.close()

    return SavedUploadFile(
        original_filename=original_filename,
        saved_filename=saved_filename,
        storage_path=storage_path,
        content_type=upload_file.content_type,
        size_bytes=size_bytes,
        checksum_sha256=checksum.hexdigest(),
    )

from pathlib import Path

from app.core.config import get_settings


class LocalStorageService:
    def __init__(self, storage_root: Path | None = None) -> None:
        self._storage_root = storage_root

    @property
    def storage_root(self) -> Path:
        return self._storage_root or get_settings().resolved_storage_root

    @property
    def uploads_dir(self) -> Path:
        return self.storage_root / "uploads"

    @property
    def exports_dir(self) -> Path:
        return self.storage_root / "exports"

    def ensure_storage_dirs(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)


storage_service = LocalStorageService()

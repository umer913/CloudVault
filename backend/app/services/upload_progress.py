from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass
class UploadProgress:
    user_id: int
    loaded: int = 0
    total: int = 0
    phase: str = "preparing"
    complete: bool = False


_lock = Lock()
_uploads: dict[str, UploadProgress] = {}


def start_upload(upload_id: str, user_id: int) -> None:
    with _lock:
        _uploads[upload_id] = UploadProgress(user_id=user_id)


def update_upload(upload_id: str, *, loaded: int, total: int, phase: str) -> None:
    with _lock:
        progress = _uploads.get(upload_id)
        if progress is not None:
            progress.loaded = loaded
            progress.total = total
            progress.phase = phase


def finish_upload(upload_id: str, *, complete: bool) -> None:
    with _lock:
        progress = _uploads.get(upload_id)
        if progress is not None:
            progress.complete = complete
            progress.phase = "complete" if complete else "failed"


def get_upload(upload_id: str, user_id: int) -> UploadProgress | None:
    with _lock:
        progress = _uploads.get(upload_id)
        if progress is None or progress.user_id != user_id:
            return None
        return UploadProgress(
            user_id=progress.user_id,
            loaded=progress.loaded,
            total=progress.total,
            phase=progress.phase,
            complete=progress.complete,
        )

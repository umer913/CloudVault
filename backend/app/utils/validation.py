from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import BinaryIO

import filetype

from app.errors import AppError


MAX_FILENAME_LENGTH = 255
MAX_SNIFF_BYTES = 8192
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class ValidatedUpload:
    original_name: str
    extension: str
    mime_type: str


_TEXT_MIME_BY_EXTENSION = {
    "txt": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
}
_GENERIC_MIME_TYPE = "application/octet-stream"


def sanitize_filename(name: str) -> str:
    name = name.replace("\\", "/")
    name = PurePath(name).name
    name = _CONTROL_CHARACTERS.sub("", name).strip()

    if not name or name in {".", ".."}:
        raise AppError(422, "INVALID_FILENAME", "A valid filename is required.")
    if len(name) > MAX_FILENAME_LENGTH:
        raise AppError(
            422,
            "INVALID_FILENAME",
            "The filename must be at most 255 characters.",
        )
    return name


def validate_upload(
    name: str,
    content: BinaryIO,
    *,
    size: int | None = None,
) -> ValidatedUpload:
    filename = sanitize_filename(name)
    extension = file_extension(filename)

    position = content.tell()
    head = content.read(MAX_SNIFF_BYTES)
    content.seek(position)

    mime_type = _detect_mime_type(extension, head)
    if size is not None and size < 0:
        raise ValueError("File size cannot be negative.")

    return ValidatedUpload(filename, extension, mime_type)


def validate_upload_header(name: str, head: bytes) -> ValidatedUpload:
    filename = sanitize_filename(name)
    extension = file_extension(filename)
    return ValidatedUpload(filename, extension, _detect_mime_type(extension, head))


def file_extension(filename: str) -> str:
    if "." not in filename or filename.endswith("."):
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _detect_mime_type(extension: str, head: bytes) -> str:
    if extension in _TEXT_MIME_BY_EXTENSION and _valid_utf8_text(head):
        return _TEXT_MIME_BY_EXTENSION[extension]
    kind = filetype.guess(head)
    return kind.mime if kind is not None else _GENERIC_MIME_TYPE


def _valid_utf8_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True

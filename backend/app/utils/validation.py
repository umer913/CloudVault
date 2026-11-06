from __future__ import annotations

import json
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


_MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "zip": "application/zip",
    "csv": "text/csv",
    "json": "application/json",
}


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
    extension = _extension(filename)
    if extension not in _MIME_BY_EXTENSION:
        raise AppError(
            422,
            "UNSUPPORTED_TYPE",
            "This file type is not supported.",
        )

    position = content.tell()
    head = content.read(MAX_SNIFF_BYTES)
    content.seek(position)

    mime_type = _validate_content(extension, head, content)
    if size is not None and size < 0:
        raise ValueError("File size cannot be negative.")

    return ValidatedUpload(filename, extension, mime_type)


def validate_upload_header(name: str, head: bytes) -> ValidatedUpload:
    filename = sanitize_filename(name)
    extension = _extension(filename)
    if extension not in _MIME_BY_EXTENSION:
        raise AppError(
            422,
            "UNSUPPORTED_TYPE",
            "This file type is not supported.",
        )

    expected = _MIME_BY_EXTENSION[extension]
    if extension == "pdf":
        valid = head.startswith(b"%PDF-")
    elif extension == "png":
        valid = head.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension in {"jpg", "jpeg"}:
        valid = head.startswith(b"\xff\xd8\xff")
    elif extension == "zip":
        valid = _is_zip(head)
    elif extension in {"txt", "csv", "json"}:
        valid = _valid_utf8_text(head)
    elif extension == "docx":
        kind = filetype.guess(head)
        valid = kind is not None and kind.extension == "docx"
    else:
        valid = False

    if not valid:
        raise AppError(
            422,
            "UNSUPPORTED_TYPE",
            "The file content does not match its extension.",
        )
    return ValidatedUpload(filename, extension, expected)


def _extension(filename: str) -> str:
    if "." not in filename or filename.endswith("."):
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _validate_content(extension: str, head: bytes, content: BinaryIO) -> str:
    expected = _MIME_BY_EXTENSION[extension]

    if extension == "pdf":
        valid = head.startswith(b"%PDF-")
    elif extension == "png":
        valid = head.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension in {"jpg", "jpeg"}:
        valid = head.startswith(b"\xff\xd8\xff")
    elif extension == "txt":
        valid = _valid_utf8_text(head)
    elif extension in {"csv", "json"}:
        valid = _valid_utf8_text(head)
        if valid and extension == "json":
            valid = _valid_json(content)
    elif extension == "zip":
        valid = _is_zip(head)
    elif extension == "docx":
        valid = _is_docx(content)
    else:
        valid = False

    if not valid:
        raise AppError(
            422,
            "UNSUPPORTED_TYPE",
            "The file content does not match its extension.",
        )

    return expected


def _valid_utf8_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _is_zip(head: bytes) -> bool:
    return head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))


def _is_docx(content: BinaryIO) -> bool:
    position = content.tell()
    content.seek(0)
    kind = filetype.guess(content.read(MAX_SNIFF_BYTES))
    content.seek(position)
    return kind is not None and kind.extension == "docx"


def _valid_json(content: BinaryIO) -> bool:
    position = content.tell()
    content.seek(0)
    try:
        json.load(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    finally:
        content.seek(position)
    return True

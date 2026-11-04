from io import BytesIO

import pytest

from app.errors import AppError
from app.utils.validation import sanitize_filename, validate_upload


@pytest.mark.parametrize(
    ("name", "content", "mime_type"),
    [
        ("report.pdf", b"%PDF-1.7", "application/pdf"),
        ("image.png", b"\x89PNG\r\n\x1a\n", "image/png"),
        ("image.jpg", b"\xff\xd8\xff\xe0", "image/jpeg"),
        ("notes.txt", b"hello", "text/plain"),
        ("data.csv", b"name,value\nAlice,1\n", "text/csv"),
        ("data.json", b'{"ok": true}', "application/json"),
        ("archive.zip", b"PK\x03\x04", "application/zip"),
    ],
)
def test_supported_uploads(name: str, content: bytes, mime_type: str) -> None:
    result = validate_upload(name, BytesIO(content))
    assert result.mime_type == mime_type


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("program.exe", b"MZ"),
        ("fake.pdf", b"MZ"),
        ("bad.txt", b"\x00not text"),
        ("bad.png", b"not png"),
    ],
)
def test_invalid_uploads_are_rejected(name: str, content: bytes) -> None:
    with pytest.raises(AppError) as error:
        validate_upload(name, BytesIO(content))
    assert error.value.status == 422
    assert error.value.code == "UNSUPPORTED_TYPE"


def test_filename_path_parts_are_removed() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"


def test_empty_filename_is_rejected() -> None:
    with pytest.raises(AppError) as error:
        sanitize_filename("   ")
    assert error.value.code == "INVALID_FILENAME"

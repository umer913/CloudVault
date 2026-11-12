from io import BytesIO

import pytest

from app.errors import AppError
from app.utils.validation import (
    file_extension,
    sanitize_filename,
    validate_upload,
    validate_upload_header,
)


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
def test_uploads_detect_known_mime_types(
    name: str,
    content: bytes,
    mime_type: str,
) -> None:
    result = validate_upload(name, BytesIO(content))
    assert result.mime_type == mime_type


@pytest.mark.parametrize(
    ("name", "content", "mime_type"),
    [
        (
            "Counter-Strike 2.app",
            b"application bundle data",
            "application/octet-stream",
        ),
        ("program.exe", b"MZ", "application/x-msdownload"),
        ("fake.pdf", b"MZ", "application/x-msdownload"),
        ("bad.txt", b"\x00not text", "application/octet-stream"),
        ("bad.png", b"not png", "application/octet-stream"),
        ("no-extension", b"unknown bytes", "application/octet-stream"),
        ("long." + "x" * 200, b"unknown bytes", "application/octet-stream"),
    ],
)
def test_arbitrary_extensions_and_content_are_accepted(
    name: str,
    content: bytes,
    mime_type: str,
) -> None:
    result = validate_upload(name, BytesIO(content))
    assert result.original_name == name
    assert result.mime_type == mime_type


def test_direct_upload_header_accepts_arbitrary_extension() -> None:
    result = validate_upload_header("Counter-Strike 2.app", b"application bundle data")
    assert result.extension == "app"
    assert result.mime_type == "application/octet-stream"


def test_file_extension_is_not_truncated() -> None:
    extension = "x" * 200
    result = validate_upload(f"file.{extension}", BytesIO(b"unknown bytes"))

    assert file_extension(result.original_name) == extension
    assert result.extension == extension


def test_filename_path_parts_are_removed() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"


def test_empty_filename_is_rejected() -> None:
    with pytest.raises(AppError) as error:
        sanitize_filename("   ")
    assert error.value.code == "INVALID_FILENAME"

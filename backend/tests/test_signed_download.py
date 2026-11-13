from urllib.parse import parse_qs, urlsplit

import httpx

from app.services.b2_storage_service import B2Storage
from app.services.supabase_storage_service import SupabaseStorage


_STORAGE_KEY = "7/" + "a" * 32 + ".bin"


def test_supabase_signed_download_url_sets_download_filename() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "signedURL": (
                    "https://storage.example/object/sign/cloudvault/file?token=secret"
                )
            },
        )

    client = httpx.Client(
        base_url="https://supabase.example/storage/v1",
        transport=httpx.MockTransport(respond),
    )
    storage = SupabaseStorage(bucket="cloudvault", client=client)
    try:
        url = storage.create_signed_url(
            _STORAGE_KEY,
            expires_in=300,
            download_filename="Quarterly report.pdf",
        )
    finally:
        client.close()

    assert parse_qs(urlsplit(url).query) == {
        "token": ["secret"],
        "download": ["Quarterly report.pdf"],
    }


def test_b2_signed_download_url_sets_attachment_content_disposition() -> None:
    class FakeClient:
        params: dict[str, str] | None = None

        def generate_presigned_url(self, _operation, *, Params, ExpiresIn):
            self.params = Params
            return "https://storage.example/file"

    storage = B2Storage.__new__(B2Storage)
    storage.bucket = "cloudvault"
    storage._client = FakeClient()

    url = storage.create_signed_url(
        _STORAGE_KEY,
        expires_in=300,
        download_filename="Quarterly report.pdf",
    )

    assert url == "https://storage.example/file"
    assert storage._client.params == {
        "Bucket": "cloudvault",
        "Key": _STORAGE_KEY,
        "ResponseContentDisposition": (
            "attachment; filename*=UTF-8''Quarterly%20report.pdf"
        ),
    }


def test_b2_preview_signed_url_does_not_force_attachment() -> None:
    class FakeClient:
        params: dict[str, str] | None = None

        def generate_presigned_url(self, _operation, *, Params, ExpiresIn):
            self.params = Params
            return "https://storage.example/file"

    storage = B2Storage.__new__(B2Storage)
    storage.bucket = "cloudvault"
    storage._client = FakeClient()

    storage.create_signed_url(_STORAGE_KEY, expires_in=300)

    assert storage._client.params == {
        "Bucket": "cloudvault",
        "Key": _STORAGE_KEY,
    }

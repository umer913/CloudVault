from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, BinaryIO

import httpx

from app.config import settings


_OBJECT_KEY_PATTERN = re.compile(r"^[0-9]+/[0-9a-f]{32}\.bin$")


class StorageError(Exception):
    """Raised when Supabase Storage cannot complete an operation."""


@dataclass(frozen=True)
class StorageObject:
    content: bytes
    content_type: str | None


class SupabaseStorage:
    def __init__(
        self,
        *,
        bucket: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.bucket = bucket or settings.SUPABASE_BUCKET
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=settings.SUPABASE_URL.rstrip("/") + "/storage/v1",
            headers=self._headers(),
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> SupabaseStorage:
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()

    @staticmethod
    def _headers() -> dict[str, str]:
        key = settings.SUPABASE_SERVICE_ROLE_KEY
        return {
            "Authorization": f"Bearer {key}",
            "apikey": key,
        }

    @staticmethod
    def validate_key(key: str) -> str:
        if not _OBJECT_KEY_PATTERN.fullmatch(key):
            raise StorageError("Invalid storage object key.")
        return key

    def upload(
        self,
        key: str,
        content: BinaryIO,
        *,
        content_type: str,
        size: int,
    ) -> None:
        key = self.validate_key(key)
        if size < 0:
            raise ValueError("Object size cannot be negative.")

        try:
            response = self._client.post(
                f"/object/{self.bucket}/{key}",
                content=content,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(size),
                    "x-upsert": "false",
                },
            )
            self._raise_for_storage(response)
        except (httpx.HTTPError, StorageError) as exc:
            if isinstance(exc, StorageError):
                raise
            raise StorageError("Storage upload failed.") from exc

    def download(self, key: str) -> StorageObject:
        key = self.validate_key(key)

        try:
            response = self._client.get(f"/object/{self.bucket}/{key}")
            self._raise_for_storage(response)
        except (httpx.HTTPError, StorageError) as exc:
            if isinstance(exc, StorageError):
                raise
            raise StorageError("Storage download failed.") from exc

        return StorageObject(
            content=response.content,
            content_type=response.headers.get("content-type"),
        )

    def iter_download(self, key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        key = self.validate_key(key)

        try:
            with self._client.stream("GET", f"/object/{self.bucket}/{key}") as response:
                self._raise_for_storage(response)
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    if chunk:
                        yield chunk
        except (httpx.HTTPError, StorageError) as exc:
            if isinstance(exc, StorageError):
                raise
            raise StorageError("Storage download failed.") from exc

    def delete(self, key: str) -> None:
        key = self.validate_key(key)

        try:
            response = self._client.post(
                f"/object/remove/{self.bucket}",
                json={"prefixes": [key]},
            )
            self._raise_for_storage(response)
        except (httpx.HTTPError, StorageError) as exc:
            if isinstance(exc, StorageError):
                raise
            raise StorageError("Storage deletion failed.") from exc

    def exists(self, key: str) -> bool:
        key = self.validate_key(key)

        try:
            response = self._client.get(f"/object/{self.bucket}/{key}")
        except httpx.HTTPError as exc:
            raise StorageError("Storage availability check failed.") from exc

        if response.status_code == 404:
            return False
        self._raise_for_storage(response)
        return True

    def create_signed_url(self, key: str, *, expires_in: int) -> str:
        key = self.validate_key(key)
        if not 1 <= expires_in <= 3600:
            raise ValueError("Signed URL lifetime must be between 1 and 3600 seconds.")

        try:
            response = self._client.post(
                f"/object/sign/{self.bucket}/{key}",
                json={"expiresIn": expires_in},
            )
            self._raise_for_storage(response)
        except (httpx.HTTPError, StorageError) as exc:
            if isinstance(exc, StorageError):
                raise
            raise StorageError("Signed URL creation failed.") from exc

        payload = response.json()
        signed_url = payload.get("signedURL")
        if not isinstance(signed_url, str) or not signed_url:
            raise StorageError("Storage returned an invalid signed URL.")
        return signed_url

    def list_objects(
        self,
        *,
        prefix: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("Invalid object listing pagination.")

        try:
            response = self._client.post(
                f"/object/list/{self.bucket}",
                json={
                    "prefix": prefix,
                    "limit": limit,
                    "offset": offset,
                    "sortBy": {"column": "created_at", "order": "asc"},
                },
            )
            self._raise_for_storage(response)
        except (httpx.HTTPError, StorageError) as exc:
            if isinstance(exc, StorageError):
                raise
            raise StorageError("Storage listing failed.") from exc

        payload = response.json()
        if not isinstance(payload, list):
            raise StorageError("Storage returned an invalid object listing.")
        return payload

    @staticmethod
    def _raise_for_storage(response: httpx.Response) -> None:
        if response.is_success:
            return
        if response.status_code == 404:
            raise StorageError("Storage object was not found.")
        raise StorageError(f"Storage request failed with status {response.status_code}.")
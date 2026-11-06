from __future__ import annotations

from collections.abc import Iterator
from typing import Any, BinaryIO, Callable

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from boto3.s3.transfer import TransferConfig

from app.config import settings
from app.services.supabase_storage_service import StorageError, _OBJECT_KEY_PATTERN


class B2Storage:
    def __init__(self) -> None:
        self.bucket = settings.B2_BUCKET
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.B2_ENDPOINT,
            region_name=settings.B2_REGION,
            aws_access_key_id=settings.B2_KEY_ID,
            aws_secret_access_key=settings.B2_APPLICATION_KEY,
            config=Config(signature_version="s3v4"),
        )
        self._transfer = TransferConfig(
            multipart_threshold=settings.B2_MULTIPART_THRESHOLD_BYTES,
            multipart_chunksize=settings.B2_MULTIPART_CHUNK_BYTES,
            max_concurrency=settings.B2_MAX_CONCURRENCY,
            use_threads=True,
        )

    def close(self) -> None:
        return None

    def __enter__(self) -> B2Storage:
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()

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
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> None:
        self.validate_key(key)
        if size < 0:
            raise ValueError("Object size cannot be negative.")
        try:
            self._client.upload_fileobj(
                content,
                self.bucket,
                key,
                ExtraArgs={"ContentType": content_type},
                Config=self._transfer,
                Callback=(
                    lambda transferred: progress_callback(transferred, size, "storing")
                    if progress_callback
                    else None
                ),
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("B2 upload failed.") from exc

    def iter_download(self, key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        self.validate_key(key)
        try:
            body = self._client.get_object(Bucket=self.bucket, Key=key)["Body"]
            while chunk := body.read(chunk_size):
                yield chunk
            body.close()
        except (BotoCoreError, ClientError, KeyError) as exc:
            raise StorageError("B2 download failed.") from exc

    def delete(self, key: str) -> None:
        self.validate_key(key)
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("B2 deletion failed.") from exc

    def exists(self, key: str) -> bool:
        self.validate_key(key)
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
                return False
            raise StorageError("B2 availability check failed.") from exc
        except BotoCoreError as exc:
            raise StorageError("B2 availability check failed.") from exc
        return True

    def create_signed_url(self, key: str, *, expires_in: int) -> str:
        self.validate_key(key)
        if not 1 <= expires_in <= 3600:
            raise ValueError("Signed URL lifetime must be between 1 and 3600 seconds.")
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("B2 signed URL creation failed.") from exc

    def create_multipart_upload(self, key: str, *, content_type: str) -> str:
        self.validate_key(key)
        try:
            response = self._client.create_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                ContentType=content_type,
            )
            upload_id = response.get("UploadId")
            if not isinstance(upload_id, str) or not upload_id:
                raise StorageError("B2 returned an invalid multipart upload ID.")
            return upload_id
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("B2 multipart upload creation failed.") from exc

    def create_part_url(
        self,
        key: str,
        *,
        upload_id: str,
        part_number: int,
        expires_in: int = 3600,
    ) -> str:
        self.validate_key(key)
        if not 1 <= part_number <= 10_000:
            raise ValueError("Multipart part number must be between 1 and 10000.")
        try:
            return self._client.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=expires_in,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("B2 multipart URL creation failed.") from exc

    def complete_multipart_upload(
        self,
        key: str,
        *,
        upload_id: str,
        parts: list[dict[str, Any]],
    ) -> None:
        self.validate_key(key)
        if not parts:
            raise ValueError("At least one multipart part is required.")
        try:
            self._client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("B2 multipart upload completion failed.") from exc

    def abort_multipart_upload(self, key: str, *, upload_id: str) -> None:
        self.validate_key(key)
        try:
            self._client.abort_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("B2 multipart upload cancellation failed.") from exc

    def list_multipart_uploads(self) -> list[dict[str, str]]:
        try:
            response = self._client.list_multipart_uploads(Bucket=self.bucket)
            uploads = []
            for item in response.get("Uploads", []):
                key = item.get("Key")
                upload_id = item.get("UploadId")
                initiated = item.get("Initiated")
                if isinstance(key, str) and isinstance(upload_id, str):
                    uploads.append(
                        {
                            "key": key,
                            "upload_id": upload_id,
                            "initiated": initiated.isoformat()
                            if hasattr(initiated, "isoformat")
                            else "",
                        }
                    )
            return uploads
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("B2 multipart upload listing failed.") from exc

    def list_objects(
        self, *, prefix: str = "", limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("Invalid object listing pagination.")
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            objects: list[dict[str, str]] = []
            skipped = 0
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for item in page.get("Contents", []):
                    key = item.get("Key")
                    if not isinstance(key, str):
                        continue
                    if skipped < offset:
                        skipped += 1
                        continue
                    objects.append({"name": key.removeprefix(prefix)})
                    if len(objects) == limit:
                        return objects
            return objects
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("B2 listing failed.") from exc

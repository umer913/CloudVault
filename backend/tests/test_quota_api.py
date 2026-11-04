from io import BytesIO

from sqlalchemy import update

from app.models import User
from app.services.supabase_storage_service import StorageError


class TrackingStorage:
    uploads = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def upload(self, *_args, **_kwargs):
        type(self).uploads += 1


class FailingStorage(TrackingStorage):
    def upload(self, *_args, **_kwargs):
        raise StorageError("storage unavailable")


def _set_quota(test_engine, user_id: int, quota: int) -> None:
    with test_engine.begin() as connection:
        connection.execute(
            update(User)
            .where(User.id == user_id)
            .values(storage_quota=quota)
        )


def test_upload_at_quota_boundary_succeeds_and_next_upload_is_rejected(
    client, make_user, monkeypatch, test_engine
):
    headers, user = make_user()
    _set_quota(test_engine, user["id"], 5)

    storage = TrackingStorage()
    monkeypatch.setattr("app.routers.files.SupabaseStorage", lambda: storage)

    first = client.post(
        "/api/files/upload",
        files={"file": ("first.txt", BytesIO(b"hello"), "text/plain")},
        headers=headers,
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/files/upload",
        files={"file": ("second.txt", BytesIO(b"!"), "text/plain")},
        headers=headers,
    )
    assert second.status_code == 413
    assert second.json()["code"] == "QUOTA_EXCEEDED"
    assert storage.uploads == 1

    usage = client.get("/api/storage/usage", headers=headers)
    assert usage.json()["used_bytes"] == 5


def test_storage_failure_does_not_consume_quota(
    client, make_user, monkeypatch, test_engine
):
    headers, user = make_user()
    _set_quota(test_engine, user["id"], 100)
    monkeypatch.setattr(
        "app.routers.files.SupabaseStorage",
        FailingStorage,
    )

    response = client.post(
        "/api/files/upload",
        files={"file": ("failed.txt", BytesIO(b"hello"), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 502
    assert response.json()["code"] == "STORAGE_UNAVAILABLE"

    usage = client.get("/api/storage/usage", headers=headers)
    assert usage.status_code == 200
    assert usage.json()["used_bytes"] == 0

from datetime import datetime, timedelta, timezone
from io import BytesIO


class FakeStorage:
    objects: dict[str, bytes] = {}

    def __init__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self):
        return None

    def upload(self, key, content, **_kwargs):
        self.objects[key] = content.read()

    def exists(self, key):
        return key in self.objects

    def iter_download(self, key):
        yield self.objects[key]


def _upload_text(client, headers, monkeypatch, name="notes.txt"):
    monkeypatch.setattr("app.routers.files.SupabaseStorage", FakeStorage)
    monkeypatch.setattr("app.routers.public.SupabaseStorage", FakeStorage)
    response = client.post(
        "/api/files/upload",
        files={"file": (name, BytesIO(b"shared content"), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_share(client, headers, file_id, **overrides):
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    payload = {
        "file_id": file_id,
        "permission": "download",
        "expires_at": expires_at.isoformat(),
    }
    payload.update(overrides)
    response = client.post("/api/shares", json=payload, headers=headers)
    return response


def test_share_can_be_read_publicly_and_downloaded(
    client, make_user, monkeypatch
):
    headers, _ = make_user()
    uploaded = _upload_text(client, headers, monkeypatch)

    created = _create_share(client, headers, uploaded["id"])
    assert created.status_code == 201, created.text
    token = created.json()["token"]

    metadata = client.get(f"/api/public/share/{token}")
    assert metadata.status_code == 200
    assert metadata.json()["original_name"] == "notes.txt"

    content = client.get(f"/api/public/share/{token}/content")
    assert content.status_code == 200
    assert content.content == b"shared content"
    assert "attachment" in content.headers["content-disposition"]


def test_password_protected_share_requires_valid_password(
    client, make_user, monkeypatch
):
    headers, _ = make_user()
    uploaded = _upload_text(client, headers, monkeypatch)
    created = _create_share(
        client,
        headers,
        uploaded["id"],
        password="share-password",
    )
    token = created.json()["token"]

    missing = client.get(f"/api/public/share/{token}")
    assert missing.status_code == 401
    assert missing.json()["code"] == "PASSWORD_REQUIRED"

    valid = client.get(
        f"/api/public/share/{token}",
        headers={"X-Share-Password": "share-password"},
    )
    assert valid.status_code == 200
    assert valid.json()["password_required"] is True


def test_revoked_share_is_not_publicly_available(client, make_user, monkeypatch):
    headers, _ = make_user()
    uploaded = _upload_text(client, headers, monkeypatch)
    created = _create_share(client, headers, uploaded["id"])
    share = created.json()

    revoked = client.delete(f"/api/shares/{share['id']}", headers=headers)
    assert revoked.status_code == 204

    public = client.get(f"/api/public/share/{share['token']}")
    assert public.status_code == 404
    assert public.json()["code"] == "SHARE_NOT_FOUND"

    listed = client.get("/api/shares", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == []


def test_share_expiry_must_be_future_and_within_thirty_days(
    client, make_user, monkeypatch
):
    headers, _ = make_user()
    uploaded = _upload_text(client, headers, monkeypatch)

    expired = _create_share(
        client,
        headers,
        uploaded["id"],
        expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    )
    assert expired.status_code == 422
    assert expired.json()["code"] == "INVALID_EXPIRY"

    too_far = _create_share(
        client,
        headers,
        uploaded["id"],
        expires_at=(datetime.now(timezone.utc) + timedelta(days=31)).isoformat(),
    )
    assert too_far.status_code == 422
    assert too_far.json()["code"] == "INVALID_EXPIRY"


def test_view_share_rejects_zip_files(client, make_user, monkeypatch):
    headers, _ = make_user()
    monkeypatch.setattr("app.routers.files.SupabaseStorage", FakeStorage)
    monkeypatch.setattr("app.routers.public.SupabaseStorage", FakeStorage)
    uploaded = client.post(
        "/api/files/upload",
        files={"file": ("archive.zip", BytesIO(b"PK\x03\x04archive"), "application/zip")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text

    response = _create_share(
        client,
        headers,
        uploaded.json()["id"],
        permission="view",
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PREVIEW_NOT_SUPPORTED"


def test_user_cannot_create_or_revoke_another_users_share(
    client, make_user, monkeypatch
):
    owner_headers, _ = make_user("owner@example.com")
    uploaded = _upload_text(client, owner_headers, monkeypatch)
    share = _create_share(client, owner_headers, uploaded["id"]).json()

    other_headers, _ = make_user("other@example.com")
    create = _create_share(client, other_headers, uploaded["id"])
    assert create.status_code == 404
    assert create.json()["code"] == "FILE_NOT_FOUND"

    revoke = client.delete(f"/api/shares/{share['id']}", headers=other_headers)
    assert revoke.status_code == 404
    assert revoke.json()["code"] == "SHARE_NOT_FOUND"

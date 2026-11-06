from io import BytesIO


def test_folder_creation_and_nested_contents(client, make_user):
    headers, _ = make_user()

    parent_response = client.post(
        "/api/folders",
        json={"name": "Documents"},
        headers=headers,
    )
    assert parent_response.status_code == 201
    parent = parent_response.json()

    child_response = client.post(
        "/api/folders",
        json={"name": "Reports", "parent_id": parent["id"]},
        headers=headers,
    )
    assert child_response.status_code == 201
    assert child_response.json()["parent_id"] == parent["id"]

    contents = client.get(
        f"/api/folders/{parent['id']}",
        headers=headers,
    )
    assert contents.status_code == 200
    assert contents.json()["folders"][0]["name"] == "Reports"


def test_foreign_folder_is_not_accessible(client, make_user):
    owner_headers, _ = make_user("owner@example.com")
    owner_folder = client.post(
        "/api/folders",
        json={"name": "Private"},
        headers=owner_headers,
    ).json()

    other_headers, _ = make_user("other@example.com")
    response = client.post(
        "/api/folders",
        json={"name": "Attack", "parent_id": owner_folder["id"]},
        headers=other_headers,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "FOLDER_NOT_FOUND"


def test_duplicate_folder_name_is_rejected(client, make_user):
    headers, _ = make_user()
    payload = {"name": "Documents"}

    assert client.post("/api/folders", json=payload, headers=headers).status_code == 201
    duplicate = client.post("/api/folders", json=payload, headers=headers)

    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "DUPLICATE_NAME"


def test_storage_usage_is_updated_after_upload(client, make_user, monkeypatch):
    headers, _ = make_user()

    class FakeStorage:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def upload(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        "app.routers.files.SupabaseStorage",
        lambda: FakeStorage(),
    )

    response = client.post(
        "/api/files/upload",
        files={"file": ("notes.txt", BytesIO(b"hello"), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201, response.text

    usage = client.get("/api/storage/usage", headers=headers)
    assert usage.status_code == 200
    assert usage.json()["used_bytes"] == 5


def test_file_is_not_accessible_to_another_user(client, make_user, monkeypatch):
    owner_headers, _ = make_user("owner@example.com")

    class FakeStorage:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def upload(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        "app.routers.files.SupabaseStorage",
        lambda: FakeStorage(),
    )
    uploaded = client.post(
        "/api/files/upload",
        files={"file": ("notes.txt", BytesIO(b"hello"), "text/plain")},
        headers=owner_headers,
    )
    file_id = uploaded.json()["id"]

    other_headers, _ = make_user("other@example.com")
    response = client.get(f"/api/files/{file_id}", headers=other_headers)
    assert response.status_code == 404
    assert response.json()["code"] == "FILE_NOT_FOUND"


def test_root_file_list_excludes_files_inside_folders(client, make_user, monkeypatch):
    headers, _ = make_user()

    class FakeStorage:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def upload(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        "app.routers.files.SupabaseStorage",
        lambda: FakeStorage(),
    )
    folder = client.post(
        "/api/folders",
        json={"name": "Books"},
        headers=headers,
    ).json()

    root_file = client.post(
        "/api/files/upload",
        files={"file": ("root.txt", BytesIO(b"root"), "text/plain")},
        headers=headers,
    )
    nested_file = client.post(
        "/api/files/upload",
        data={"folder_id": str(folder["id"])},
        files={"file": ("nested.txt", BytesIO(b"nested"), "text/plain")},
        headers=headers,
    )
    assert root_file.status_code == 201
    assert nested_file.status_code == 201

    root_listing = client.get("/api/files", headers=headers)
    assert root_listing.status_code == 200
    assert [item["original_name"] for item in root_listing.json()["items"]] == [
        "root.txt"
    ]

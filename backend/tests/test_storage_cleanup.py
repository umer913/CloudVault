from sqlalchemy import text

from app.services.storage_cleanup_service import cleanup_orphan_objects


class FakeStorage:
    def __init__(self, objects):
        self.objects = objects
        self.deleted = []

    def list_objects(self, *, prefix, limit, offset):
        assert limit == 1000
        assert offset == 0
        return [
            {"name": name.removeprefix(prefix)}
            for name in self.objects
            if name.startswith(prefix)
        ]

    @staticmethod
    def validate_key(key):
        if not key.endswith(".bin") or "/" not in key:
            raise ValueError("invalid key")
        return key

    def delete(self, key):
        self.deleted.append(key)


def test_cleanup_deletes_only_unreferenced_managed_objects(test_engine, client):
    with test_engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (name, email, password_hash) "
            "VALUES ('Alice', 'cleanup@example.com', 'hash')"
        )

    with test_engine.connect() as connection:
        user_id = connection.exec_driver_sql(
            "SELECT id FROM users WHERE email = 'cleanup@example.com'"
        ).scalar_one()

    known_key = f"{user_id}/" + "a" * 32 + ".bin"
    orphan_key = f"{user_id}/" + "b" * 32 + ".bin"
    with test_engine.begin() as connection:
        connection.execute(
            text(
            "INSERT INTO files "
            "(user_id, original_name, extension, storage_key, size, mime_type, checksum) "
            "VALUES (:user_id, 'known.txt', 'txt', :storage_key, 1, "
            "'text/plain', :checksum)",
            ),
            {
                "user_id": user_id,
                "storage_key": known_key,
                "checksum": "c" * 64,
            },
        )

    from sqlalchemy.orm import Session

    storage = FakeStorage([known_key, orphan_key])
    with Session(test_engine) as db:
        report = cleanup_orphan_objects(db, storage, dry_run=False)

    assert report.scanned == 2
    assert report.orphaned == 1
    assert report.deleted == 1
    assert storage.deleted == [orphan_key]

from types import SimpleNamespace

from scripts import cleanup_orphan_objects


def test_cleanup_command_requires_explicit_confirmation(capsys):
    result = cleanup_orphan_objects.run_cleanup(
        apply=True,
        confirmation=None,
        page_size=1000,
    )

    assert result == 2
    assert "requires --confirm DELETE-ORPHANS" in capsys.readouterr().err


def test_cleanup_command_rejects_confirmation_without_apply(capsys):
    result = cleanup_orphan_objects.run_cleanup(
        apply=False,
        confirmation="DELETE-ORPHANS",
        page_size=1000,
    )

    assert result == 2
    assert "--confirm can only be used with --apply" in capsys.readouterr().err


def test_cleanup_command_defaults_to_dry_run(monkeypatch, capsys):
    report = SimpleNamespace(scanned=4, orphaned=2, deleted=0)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class FakeStorage(FakeSession):
        pass

    monkeypatch.setattr(cleanup_orphan_objects, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(cleanup_orphan_objects, "SupabaseStorage", FakeStorage)
    monkeypatch.setattr(
        cleanup_orphan_objects,
        "cleanup_orphan_objects",
        lambda db, storage, *, dry_run, page_size: (
            report if dry_run and page_size == 1000 else None
        ),
    )

    assert cleanup_orphan_objects.run_cleanup(
        apply=False,
        confirmation=None,
        page_size=1000,
    ) == 0
    assert "would delete: 2" in capsys.readouterr().out

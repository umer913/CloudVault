from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.services.active_storage import create_storage
from app.services.b2_storage_service import B2Storage
from app.services.supabase_storage_service import StorageError
from app.services.upload_session_cleanup_service import cleanup_upload_sessions

logger = logging.getLogger(__name__)
_CONFIRMATION = "EXPIRE-UPLOADS"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find and expire abandoned direct B2 upload sessions."
    )
    parser.add_argument("--apply", action="store_true", help="Expire sessions.")
    parser.add_argument("--confirm", help=f"Required with --apply: {_CONFIRMATION}")
    return parser


def run_cleanup(*, apply: bool, confirmation: str | None) -> int:
    if apply and confirmation != _CONFIRMATION:
        print(f"--apply requires --confirm {_CONFIRMATION}", file=sys.stderr)
        return 2
    if not apply and confirmation is not None:
        print("--confirm can only be used with --apply", file=sys.stderr)
        return 2

    try:
        with SessionLocal() as db, create_storage() as storage:
            if not isinstance(storage, B2Storage):
                print(
                    "Upload-session cleanup requires STORAGE_PROVIDER=b2.",
                    file=sys.stderr,
                )
                return 2
            report = cleanup_upload_sessions(db, storage, dry_run=not apply)
    except (SQLAlchemyError, StorageError):
        logger.exception("Upload-session cleanup failed.")
        return 1

    action = "expired" if apply else "would expire"
    print(
        f"Scanned: {report.scanned}; expired: {report.expired}; "
        f"{action}: {report.aborted}; failed: {report.failed}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_cleanup(apply=args.apply, confirmation=args.confirm)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.services.storage_cleanup_service import cleanup_orphan_objects
from app.services.supabase_storage_service import StorageError, SupabaseStorage

logger = logging.getLogger(__name__)
_CONFIRMATION = "DELETE-ORPHANS"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find and optionally delete orphaned CloudVault objects."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete confirmed orphan objects instead of performing a dry run.",
    )
    parser.add_argument(
        "--confirm",
        help=f"Required with --apply: {_CONFIRMATION}",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        choices=range(1, 1001),
        metavar="N",
        help="Storage listing page size (default: 1000).",
    )
    return parser


def run_cleanup(*, apply: bool, confirmation: str | None, page_size: int) -> int:
    if apply and confirmation != _CONFIRMATION:
        print(
            f"--apply requires --confirm {_CONFIRMATION}",
            file=sys.stderr,
        )
        return 2
    if not apply and confirmation is not None:
        print("--confirm can only be used with --apply", file=sys.stderr)
        return 2

    try:
        with SessionLocal() as db, SupabaseStorage() as storage:
            report = cleanup_orphan_objects(
                db,
                storage,
                dry_run=not apply,
                page_size=page_size,
            )
    except (SQLAlchemyError, StorageError):
        logger.exception("Orphan object cleanup failed.")
        return 1

    mode = "deleted" if apply else "would delete"
    print(
        f"Scanned: {report.scanned}; orphaned: {report.orphaned}; "
        f"{mode}: {report.deleted if apply else report.orphaned}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_cleanup(
        apply=args.apply,
        confirmation=args.confirm,
        page_size=args.page_size,
    )


if __name__ == "__main__":
    raise SystemExit(main())

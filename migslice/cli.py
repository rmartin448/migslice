"""Command-line entry point for migslice."""
from __future__ import annotations

import argparse
import sys
from typing import IO, List, Optional

from .parser import extract, extract_range, iter_duplicate_ids, list_ids


def _open_input(path: Optional[str]) -> IO[str]:
    if path is None or path == "-":
        return sys.stdin
    return open(path, "r", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migslice",
        description="Pull one migration's SQL out of a concatenated migration stream.",
    )
    parser.add_argument(
        "id",
        nargs="?",
        help="id of the migration to extract (the value after '-- migrate:')",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="path to the migration stream (defaults to stdin)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list migration ids found in the stream instead of extracting one",
    )
    parser.add_argument(
        "--check-duplicates",
        action="store_true",
        help=(
            "scan the stream for marker ids that appear more than once, "
            "instead of extracting one"
        ),
    )
    parser.add_argument(
        "--from",
        dest="from_id",
        metavar="ID",
        help="start of an inclusive id range; with no --to, runs through the end of the stream",
    )
    parser.add_argument(
        "--to",
        dest="to_id",
        metavar="ID",
        help="end of an inclusive id range; with no --from, starts at the first migration",
    )

    args = parser.parse_args(argv)

    if (
        not args.list
        and not args.check_duplicates
        and not args.id
        and not args.from_id
        and not args.to_id
    ):
        parser.error(
            "an id, or --from/--to, is required unless --list or "
            "--check-duplicates is given"
        )
    if args.id and (args.from_id or args.to_id):
        parser.error("id is not used together with --from/--to")

    source = _open_input(args.file)
    try:
        if args.list:
            for migration_id in list_ids(source):
                print(migration_id)
            return 0

        if args.check_duplicates:
            seen = set()
            duplicates = []
            for migration_id in iter_duplicate_ids(source):
                if migration_id not in seen:
                    seen.add(migration_id)
                    duplicates.append(migration_id)
            for migration_id in duplicates:
                print(f"migslice: duplicate migration id {migration_id!r}", file=sys.stderr)
            return 1 if duplicates else 0

        if args.from_id or args.to_id:
            lines = extract_range(source, args.from_id, args.to_id)
            if lines is None:
                bounds = " ".join(
                    part
                    for part in (
                        f"--from {args.from_id!r}" if args.from_id else "",
                        f"--to {args.to_id!r}" if args.to_id else "",
                    )
                    if part
                )
                print(f"migslice: could not find requested range ({bounds})", file=sys.stderr)
                return 1
            sys.stdout.writelines(lines)
            return 0

        lines = extract(source, args.id)
        if lines is None:
            print(f"migslice: no migration with id {args.id!r}", file=sys.stderr)
            return 1
        sys.stdout.writelines(lines)
        return 0
    finally:
        if source is not sys.stdin:
            source.close()


if __name__ == "__main__":
    raise SystemExit(main())

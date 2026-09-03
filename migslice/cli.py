"""Command-line entry point for migslice."""
from __future__ import annotations

import argparse
import sys
from typing import IO, List, Optional

from .parser import extract, list_ids


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

    args = parser.parse_args(argv)

    if not args.list and not args.id:
        parser.error("an id is required unless --list is given")

    source = _open_input(args.file)
    try:
        if args.list:
            for migration_id in list_ids(source):
                print(migration_id)
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

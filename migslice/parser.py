"""Streaming parser for concatenated SQL migration files.

Migrations are separated by marker comments of the form:

    -- migrate: <id>

Everything between one marker and the next (or end of input) belongs to
that migration. Nothing here reads the input with .read() or .readlines() -
callers hand in a line iterator (a file object works directly), and a
migration's lines are only held in memory while that one migration is being
assembled. A multi-gigabyte bundle of migrations costs the same memory as a
single migration, not the whole file.
"""
from __future__ import annotations

import re
from typing import Iterable, Iterator, List, NamedTuple, Optional

_MARKER_RE = re.compile(r"^--\s*migrate:\s*(\S+)\s*$")


class Migration(NamedTuple):
    id: str
    lines: List[str]


def iter_migrations(stream: Iterable[str]) -> Iterator[Migration]:
    """Yield each migration in order as the stream is consumed.

    Lines before the first marker are discarded - they're assumed to be a
    header comment or blank space, not part of any migration.
    """
    current_id: Optional[str] = None
    current_lines: List[str] = []

    for line in stream:
        match = _MARKER_RE.match(line)
        if match:
            if current_id is not None:
                yield Migration(current_id, current_lines)
            current_id = match.group(1)
            current_lines = []
        elif current_id is not None:
            current_lines.append(line)

    if current_id is not None:
        yield Migration(current_id, current_lines)


def extract(stream: Iterable[str], target_id: str) -> Optional[List[str]]:
    """Return the lines of the migration matching `target_id`, or None.

    Because `iter_migrations` is a generator, returning as soon as the
    match closes off means the rest of the stream is never pulled through -
    for a file source, everything after the match stays on disk unread.
    """
    for migration in iter_migrations(stream):
        if migration.id == target_id:
            return migration.lines
    return None


def list_ids(stream: Iterable[str]) -> Iterator[str]:
    """Yield migration ids in order, without ever collecting their SQL.

    Kept separate from iter_migrations rather than built on top of it: a
    plain listing has no need to accumulate the body of every migration
    just to throw it away.
    """
    for line in stream:
        match = _MARKER_RE.match(line)
        if match:
            yield match.group(1)

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


def extract_range(
    stream: Iterable[str],
    from_id: Optional[str] = None,
    to_id: Optional[str] = None,
) -> Optional[List[str]]:
    """Return the concatenated lines of every migration from `from_id`
    through `to_id`, inclusive, in the order they appear in the stream.

    Either bound may be omitted: a missing `from_id` starts at the first
    migration in the stream, and a missing `to_id` runs through the last.
    At least one of the two must be given. Ids are matched by stream order,
    not by comparing them as strings or numbers, so this works regardless
    of what the id format looks like.

    Returns None if `from_id` is given but never found, or if the stream
    ends before `to_id` is found - a partial range is not returned, since
    silently truncating a range is more likely to hide a typo than to be
    what the caller wanted.
    """
    if from_id is None and to_id is None:
        raise ValueError("at least one of from_id or to_id is required")

    collecting = from_id is None
    found_from = collecting
    found_to = False
    result: List[str] = []

    for migration in iter_migrations(stream):
        if not collecting and migration.id == from_id:
            collecting = True
            found_from = True
        if collecting:
            result.extend(migration.lines)
            if to_id is not None and migration.id == to_id:
                found_to = True
                break

    if not found_from or (to_id is not None and not found_to):
        return None
    return result


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


def iter_duplicate_ids(stream: Iterable[str]) -> Iterator[str]:
    """Yield an id every time it's seen again after its first marker.

    Built on `list_ids`, so this still never collects a migration's body -
    the only state carried across the whole stream is the set of ids seen
    so far, which for a real migration history is negligible next to the
    SQL itself. If an id appears three times, it's yielded twice, once per
    repeat, so a caller that wants an occurrence count doesn't have to
    re-scan the stream.
    """
    seen = set()
    for migration_id in list_ids(stream):
        if migration_id in seen:
            yield migration_id
        else:
            seen.add(migration_id)

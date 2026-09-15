"""Unit tests for migslice.parser."""
from __future__ import annotations

import unittest
from typing import Iterator, List

from migslice.parser import (
    Migration,
    extract,
    extract_range,
    iter_duplicate_ids,
    iter_migrations,
    list_ids,
)


def _counting_stream(lines: List[str], counter: List[int]) -> Iterator[str]:
    for line in lines:
        counter[0] += 1
        yield line


class IterMigrationsTests(unittest.TestCase):
    def test_basic_split(self):
        stream = [
            "-- migrate: 0001_a\n",
            "CREATE TABLE a;\n",
            "-- migrate: 0002_b\n",
            "CREATE TABLE b;\n",
            "ALTER TABLE b ADD x;\n",
        ]
        migrations = list(iter_migrations(stream))
        self.assertEqual(
            migrations,
            [
                Migration("0001_a", ["CREATE TABLE a;\n"]),
                Migration("0002_b", ["CREATE TABLE b;\n", "ALTER TABLE b ADD x;\n"]),
            ],
        )

    def test_lines_before_first_marker_are_discarded(self):
        stream = [
            "-- a header comment, not a migration\n",
            "\n",
            "-- migrate: 0001_a\n",
            "CREATE TABLE a;\n",
        ]
        migrations = list(iter_migrations(stream))
        self.assertEqual(migrations, [Migration("0001_a", ["CREATE TABLE a;\n"])])

    def test_empty_stream_yields_nothing(self):
        self.assertEqual(list(iter_migrations([])), [])

    def test_marker_with_no_body_yields_empty_lines(self):
        stream = ["-- migrate: 0001_a\n", "-- migrate: 0002_b\n", "SELECT 1;\n"]
        migrations = list(iter_migrations(stream))
        self.assertEqual(
            migrations,
            [Migration("0001_a", []), Migration("0002_b", ["SELECT 1;\n"])],
        )

    def test_trailing_marker_with_no_following_lines(self):
        stream = ["-- migrate: 0001_a\n", "CREATE TABLE a;\n", "-- migrate: 0002_b\n"]
        migrations = list(iter_migrations(stream))
        self.assertEqual(
            migrations,
            [Migration("0001_a", ["CREATE TABLE a;\n"]), Migration("0002_b", [])],
        )

    def test_marker_whitespace_variants(self):
        stream = [
            "--migrate:0001_a\n",
            "--   migrate:   0001_a\n",
            "-- migrate: 0001_a  \n",
        ]
        migrations = list(iter_migrations(stream))
        self.assertEqual([m.id for m in migrations], ["0001_a"] * 3)

    def test_lines_that_merely_resemble_markers_are_not_matched(self):
        stream = [
            "-- migrate: 0001_a\n",
            "-- this mentions migrate: in prose, not a marker\n",
            "SELECT '-- migrate: fake';\n",
        ]
        migrations = list(iter_migrations(stream))
        self.assertEqual(len(migrations), 1)
        self.assertEqual(
            migrations[0].lines,
            [
                "-- this mentions migrate: in prose, not a marker\n",
                "SELECT '-- migrate: fake';\n",
            ],
        )

    def test_marker_requires_an_id(self):
        stream = ["-- migrate: \n", "CREATE TABLE a;\n"]
        # No id after the colon: not a valid marker, so nothing is captured.
        self.assertEqual(list(iter_migrations(stream)), [])

    def test_duplicate_ids_are_both_yielded(self):
        stream = [
            "-- migrate: 0001_a\n",
            "CREATE TABLE a;\n",
            "-- migrate: 0001_a\n",
            "CREATE TABLE a_again;\n",
        ]
        migrations = list(iter_migrations(stream))
        self.assertEqual([m.id for m in migrations], ["0001_a", "0001_a"])

    def test_final_migration_without_trailing_newline(self):
        stream = ["-- migrate: 0001_a\n", "SELECT 1;"]
        migrations = list(iter_migrations(stream))
        self.assertEqual(migrations, [Migration("0001_a", ["SELECT 1;"])])


class ExtractTests(unittest.TestCase):
    def test_extract_returns_matching_lines(self):
        stream = [
            "-- migrate: 0001_a\n",
            "CREATE TABLE a;\n",
            "-- migrate: 0002_b\n",
            "CREATE TABLE b;\n",
        ]
        self.assertEqual(extract(stream, "0002_b"), ["CREATE TABLE b;\n"])

    def test_extract_returns_none_when_id_not_found(self):
        stream = ["-- migrate: 0001_a\n", "CREATE TABLE a;\n"]
        self.assertIsNone(extract(stream, "does_not_exist"))

    def test_extract_on_empty_stream_returns_none(self):
        self.assertIsNone(extract([], "anything"))

    def test_extract_first_match_wins_on_duplicate_ids(self):
        stream = [
            "-- migrate: dup\n",
            "first\n",
            "-- migrate: dup\n",
            "second\n",
        ]
        self.assertEqual(extract(stream, "dup"), ["first\n"])

    def test_extract_stops_pulling_from_the_stream_once_matched(self):
        lines = [
            "-- migrate: 0001_a\n",
            "CREATE TABLE a;\n",
            "-- migrate: 0002_target\n",
            "CREATE TABLE target;\n",
        ]
        # A huge tail after the match should never be pulled through.
        tail = [f"-- migrate: extra_{n}\nfiller\n" for n in range(200_000)]
        counter = [0]
        stream = _counting_stream(lines + tail, counter)

        result = extract(stream, "0002_target")

        self.assertEqual(result, ["CREATE TABLE target;\n"])
        # iter_migrations only needs to look one line past the match to
        # know the next marker (or end of input) closes it off.
        self.assertLessEqual(counter[0], len(lines) + 1)

    def test_extract_over_large_synthetic_input(self):
        def make_stream() -> Iterator[str]:
            for n in range(50_000):
                yield f"-- migrate: mig_{n}\n"
                yield f"-- body line for {n}\n"

        result = extract(make_stream(), "mig_49999")
        self.assertEqual(result, ["-- body line for 49999\n"])


class ExtractRangeTests(unittest.TestCase):
    def _stream(self):
        return [
            "-- migrate: 0001_a\n",
            "CREATE TABLE a;\n",
            "-- migrate: 0002_b\n",
            "CREATE TABLE b;\n",
            "-- migrate: 0003_c\n",
            "CREATE TABLE c;\n",
            "-- migrate: 0004_d\n",
            "CREATE TABLE d;\n",
        ]

    def test_both_bounds_given(self):
        result = extract_range(self._stream(), "0002_b", "0003_c")
        self.assertEqual(result, ["CREATE TABLE b;\n", "CREATE TABLE c;\n"])

    def test_from_only_runs_to_end_of_stream(self):
        result = extract_range(self._stream(), from_id="0003_c")
        self.assertEqual(result, ["CREATE TABLE c;\n", "CREATE TABLE d;\n"])

    def test_to_only_starts_at_first_migration(self):
        result = extract_range(self._stream(), to_id="0002_b")
        self.assertEqual(
            result, ["CREATE TABLE a;\n", "CREATE TABLE b;\n"]
        )

    def test_single_id_range_returns_just_that_migration(self):
        result = extract_range(self._stream(), "0002_b", "0002_b")
        self.assertEqual(result, ["CREATE TABLE b;\n"])

    def test_missing_from_id_returns_none(self):
        self.assertIsNone(extract_range(self._stream(), "nope", "0002_b"))

    def test_missing_to_id_returns_none(self):
        self.assertIsNone(extract_range(self._stream(), "0002_b", "nope"))

    def test_to_before_from_in_stream_order_returns_none(self):
        # 0003_c appears before 0002_b in a --from/--to sense here since
        # the range never opens: collection only starts once from_id is
        # seen, so a to_id that already passed can't close it.
        result = extract_range(self._stream(), from_id="0003_c", to_id="0002_b")
        self.assertIsNone(result)

    def test_neither_bound_given_raises(self):
        with self.assertRaises(ValueError):
            extract_range(self._stream())

    def test_stops_pulling_from_the_stream_once_to_id_is_closed(self):
        lines = self._stream()
        tail = [f"-- migrate: extra_{n}\nfiller\n" for n in range(200_000)]
        counter = [0]
        stream = _counting_stream(lines + tail, counter)

        result = extract_range(stream, "0002_b", "0003_c")

        self.assertEqual(result, ["CREATE TABLE b;\n", "CREATE TABLE c;\n"])
        self.assertLessEqual(counter[0], len(lines) + 1)


class ListIdsTests(unittest.TestCase):
    def test_list_ids_in_order(self):
        stream = [
            "-- migrate: 0001_a\n",
            "CREATE TABLE a;\n",
            "-- migrate: 0002_b\n",
            "CREATE TABLE b;\n",
        ]
        self.assertEqual(list(list_ids(stream)), ["0001_a", "0002_b"])

    def test_list_ids_on_empty_stream(self):
        self.assertEqual(list(list_ids([])), [])

    def test_list_ids_ignores_non_marker_lines(self):
        stream = ["not a marker\n", "-- migrate: only_one\n", "body\n"]
        self.assertEqual(list(list_ids(stream)), ["only_one"])


class IterDuplicateIdsTests(unittest.TestCase):
    def test_no_duplicates_yields_nothing(self):
        stream = ["-- migrate: 0001_a\n", "-- migrate: 0002_b\n"]
        self.assertEqual(list(iter_duplicate_ids(stream)), [])

    def test_repeated_id_is_yielded_once_per_repeat(self):
        stream = [
            "-- migrate: dup\n",
            "-- migrate: 0002_b\n",
            "-- migrate: dup\n",
            "-- migrate: dup\n",
        ]
        self.assertEqual(list(iter_duplicate_ids(stream)), ["dup", "dup"])

    def test_first_occurrence_is_never_reported(self):
        stream = ["-- migrate: only\n"]
        self.assertEqual(list(iter_duplicate_ids(stream)), [])

    def test_empty_stream_yields_nothing(self):
        self.assertEqual(list(iter_duplicate_ids([])), [])

    def test_multiple_ids_each_duplicated(self):
        stream = [
            "-- migrate: a\n",
            "-- migrate: b\n",
            "-- migrate: a\n",
            "-- migrate: b\n",
        ]
        self.assertEqual(list(iter_duplicate_ids(stream)), ["a", "b"])

    def test_stops_pulling_from_the_stream_early_is_not_assumed(self):
        # Unlike extract(), a duplicate scan has to see the whole stream -
        # a later repeat can't be ruled out early.
        lines = [f"-- migrate: id_{n}\n" for n in range(1000)]
        counter = [0]
        stream = _counting_stream(lines, counter)
        self.assertEqual(list(iter_duplicate_ids(stream)), [])
        self.assertEqual(counter[0], len(lines))


if __name__ == "__main__":
    unittest.main()

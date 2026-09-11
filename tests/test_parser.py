"""Unit tests for migslice.parser."""
from __future__ import annotations

import unittest
from typing import Iterator, List

from migslice.parser import Migration, extract, iter_migrations, list_ids


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


if __name__ == "__main__":
    unittest.main()

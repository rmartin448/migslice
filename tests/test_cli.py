"""Unit tests for migslice.cli."""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest

from migslice.cli import main

_DUMP = (
    "-- migrate: 0001_a\n"
    "CREATE TABLE a;\n"
    "-- migrate: 0002_b\n"
    "CREATE TABLE b;\n"
    "-- migrate: 0003_c\n"
    "CREATE TABLE c;\n"
)

_DUMP_WITH_DUPLICATE = (
    "-- migrate: 0001_a\n"
    "CREATE TABLE a;\n"
    "-- migrate: 0001_a\n"
    "CREATE TABLE a_again;\n"
)


class _TempDumpMixin:
    def _write_dump(self, contents: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".sql")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(contents)
        self.addCleanup(os.unlink, path)
        return path


def _run(argv):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class ExtractByIdTests(_TempDumpMixin, unittest.TestCase):
    def test_extract_writes_matching_migration_to_stdout(self):
        path = self._write_dump(_DUMP)
        code, out, err = _run(["0002_b", path])
        self.assertEqual(code, 0)
        self.assertEqual(out, "CREATE TABLE b;\n")
        self.assertEqual(err, "")

    def test_missing_id_exits_1_with_stderr_message(self):
        path = self._write_dump(_DUMP)
        code, out, err = _run(["does_not_exist", path])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("does_not_exist", err)

    def test_reads_from_stdin_when_file_omitted(self):
        with contextlib.redirect_stdin(io.StringIO(_DUMP)):
            code, out, err = _run(["0001_a"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "CREATE TABLE a;\n")

    def test_no_arguments_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as ctx:
            _run([])
        self.assertEqual(ctx.exception.code, 2)

    def test_id_together_with_range_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as ctx:
            _run(["0001_a", "--from", "0001_a"])
        self.assertEqual(ctx.exception.code, 2)


class ListFlagTests(_TempDumpMixin, unittest.TestCase):
    def test_list_prints_ids_in_order(self):
        path = self._write_dump(_DUMP)
        code, out, err = _run(["--list", path])
        self.assertEqual(code, 0)
        self.assertEqual(out, "0001_a\n0002_b\n0003_c\n")
        self.assertEqual(err, "")


class CheckDuplicatesFlagTests(_TempDumpMixin, unittest.TestCase):
    def test_clean_stream_exits_0_with_no_output(self):
        path = self._write_dump(_DUMP)
        code, out, err = _run(["--check-duplicates", path])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual(err, "")

    def test_duplicate_stream_exits_1_and_reports_each_id_once(self):
        path = self._write_dump(_DUMP_WITH_DUPLICATE)
        code, out, err = _run(["--check-duplicates", path])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err.count("0001_a"), 1)


class RangeFlagTests(_TempDumpMixin, unittest.TestCase):
    def test_from_and_to_extracts_inclusive_range(self):
        path = self._write_dump(_DUMP)
        code, out, err = _run(["--from", "0001_a", "--to", "0002_b", path])
        self.assertEqual(code, 0)
        self.assertEqual(out, "CREATE TABLE a;\nCREATE TABLE b;\n")

    def test_from_only_runs_to_end_of_stream(self):
        path = self._write_dump(_DUMP)
        code, out, err = _run(["--from", "0002_b", path])
        self.assertEqual(code, 0)
        self.assertEqual(out, "CREATE TABLE b;\nCREATE TABLE c;\n")

    def test_unresolvable_range_exits_1_with_stderr_message(self):
        path = self._write_dump(_DUMP)
        code, out, err = _run(["--from", "nope", path])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("nope", err)


if __name__ == "__main__":
    unittest.main()

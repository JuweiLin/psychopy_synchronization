"""Windows publication retries preserve the old file until replacement succeeds."""

import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shared.file_io import replace_with_retry


def windows_access_error():
    error = PermissionError(errno.EACCES, "Access is denied")
    error.winerror = 5
    return error


class PublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.pending = Path(temporary.name) / "session.json.tmp"
        self.destination = Path(temporary.name) / "session.json"
        self.pending.write_text("new", encoding="utf-8")
        self.destination.write_text("old", encoding="utf-8")

    def test_transient_lock_then_success_publishes_complete_file(self):
        original_replace = Path.replace
        attempts = []

        def replace(source, destination):
            attempts.append(source)
            if len(attempts) == 1:
                self.assertEqual(self.destination.read_text(), "old")
                raise windows_access_error()
            return original_replace(source, destination)

        with patch.object(Path, "replace", replace), patch("shared.file_io.time.sleep") as sleep:
            replace_with_retry(self.pending, self.destination)
        self.assertEqual(self.destination.read_text(), "new")
        self.assertFalse(self.pending.exists())
        sleep.assert_called_once_with(0.05)

    def test_persistent_lock_preserves_both_files_and_original_error(self):
        error = windows_access_error()
        with patch.object(Path, "replace", side_effect=error) as replace, \
                patch("shared.file_io.time.sleep") as sleep:
            with self.assertRaises(PermissionError) as caught:
                replace_with_retry(self.pending, self.destination)
        self.assertIs(caught.exception, error)
        self.assertEqual(replace.call_count, 8)
        self.assertEqual(sleep.call_count, 7)
        self.assertEqual(self.destination.read_text(), "old")
        self.assertEqual(self.pending.read_text(), "new")

    def test_unrelated_permission_error_does_not_retry(self):
        with patch.object(Path, "replace", side_effect=PermissionError("Denied")), \
                patch("shared.file_io.time.sleep") as sleep:
            with self.assertRaises(PermissionError):
                replace_with_retry(self.pending, self.destination)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Publish closed temporary files, tolerating short Windows file locks."""

import logging
from pathlib import Path
import time


def replace_with_retry(temporary, destination):
    """Retry Windows access/sharing failures without truncating the old file.

    The caller must close the temporary file first. A persistent failure keeps
    both paths intact for recovery and raises the original operating-system
    error. Permission failures on other platforms and unrelated errors fail
    immediately. This does not change file permissions or remove the target.
    """
    temporary, destination = Path(temporary), Path(destination)
    delays = (0.05, 0.1, 0.2, 0.4, 0.8, 1.0, 1.0)
    for attempt in range(len(delays) + 1):
        try:
            temporary.replace(destination)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) not in (5, 32, 33):
                raise
            if attempt == len(delays):
                logging.error("Could not replace %s after retries. The latest temporary file is %s. "
                              "Close programs using these files and check file/folder permissions.",
                              destination, temporary)
                raise
            if attempt == 0:
                logging.warning("Windows denied replacing %s (winerror=%s); retrying for up to 3.55 seconds.",
                                destination, exc.winerror)
            time.sleep(delays[attempt])

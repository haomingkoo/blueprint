"""Shared SQLite connection helper for the understand-repo skill's
scripts. `sweep.py` is the one script that legitimately creates a new
`understanding.db` (it's the sweep writer); every other script only ever
reads/updates an existing sweep, so a missing or typo'd `sweep_dir` should
raise a clean error here rather than let `sqlite3.connect` silently
create a stray empty file that then fails on the next query with a raw
traceback."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class SweepNotFoundError(Exception):
    """Raised when `db_path` doesn't exist -- a typo'd or stale sweep_dir."""


@contextmanager
def open_db(db_path: Path) -> Iterator[sqlite3.Connection]:
    if not db_path.exists():
        raise SweepNotFoundError(f"No sweep found at {db_path} -- check the sweep_dir path.")
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()

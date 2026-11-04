"""SQLite connections always enforce references (TASK-04 §4.1)."""
from contextlib import contextmanager
import sqlite3


def open_database(path, *, timeout=5):
    from spectrumagent.storage.guard import for_database
    guard = for_database(path)
    connection = sqlite3.connect(guard.resolve_write(path, kind="DATABASE_OPEN"), timeout=timeout)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@contextmanager
def connect_database(path, *, timeout=5):
    connection = open_database(path, timeout=timeout)
    try:
        with connection:
            yield connection
    finally:
        connection.close()

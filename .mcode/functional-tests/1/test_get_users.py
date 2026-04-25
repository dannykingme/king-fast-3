"""Functional tests for the king-fast-3 milestone 1 backend.

Scope (per the milestone-1 spec): only the GET /users endpoint is implemented.
POST /users, validation errors, and email-uniqueness behavior are explicitly
out of scope for this milestone.

Tests in this file:

1. ``test_get_users_returns_200_and_empty_list_on_fresh_db`` — verifies the
   lifecycle healthcheck contract: a fresh app responds 200 with ``[]``.
2. ``test_get_users_response_is_json_content_type`` — verifies the response
   declares ``application/json`` so callers can rely on JSON parsing.
3. ``test_get_users_reflects_seeded_rows`` — seeds rows directly into the
   running app's SQLite file and confirms GET /users returns them with the
   expected ``{id, name, email}`` shape and types.
4. ``test_database_file_exists_in_working_directory`` — confirms the SQLite
   database file is created in the app's working directory at startup.
5. ``test_get_users_idempotent_repeated_calls`` — calling GET /users multiple
   times returns the same response (no side effects from a read).

The tests assume the lifecycle scripts (install/build/run/healthcheck) have
already brought the Express server up on ``http://localhost:8000``.
"""

from __future__ import annotations

import os
import sqlite3
import time

import pytest
import requests

# The lifecycle binds the server to PORT=8000 by default.
BASE_URL = "http://localhost:" + os.environ.get("PORT", "8000")

# Resolved DB file the app writes to. main.ts uses
# process.env.DATABASE_URL ?? './users.db', and the lifecycle run script
# does not set DATABASE_URL, so the DB lands in the working directory.
APP_WORKING_DIR = "/l2l/workspace/king-fast-3"
APP_DB_PATH = os.path.join(APP_WORKING_DIR, "users.db")


@pytest.fixture(autouse=True)
def health_check() -> None:
    """Confirm the Express app is reachable before each test runs.

    GET /users itself is the canonical healthcheck for this service per
    the lifecycle spec, so we use it here too.
    """
    resp = requests.get(f"{BASE_URL}/users", timeout=5)
    assert resp.status_code == 200, (
        f"App not reachable at {BASE_URL}/users — got {resp.status_code}"
    )


def _reset_users_table() -> None:
    """Truncate the users table on the live DB so tests start from a known state.

    The app is running and holds an open better-sqlite3 connection on the
    same file, but SQLite handles this concurrent write fine for a
    single-writer scenario like tests.
    """
    # Wait briefly to make sure the app has finished initializing the schema
    # (the lifecycle 'run' script sleeps 2s, but be defensive).
    for _ in range(20):
        if os.path.exists(APP_DB_PATH):
            break
        time.sleep(0.1)

    conn = sqlite3.connect(APP_DB_PATH, timeout=5)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT NOT NULL, "
            "email TEXT NOT NULL UNIQUE)"
        )
        conn.execute("DELETE FROM users")
        conn.commit()
    finally:
        conn.close()


class TestGetUsersFreshDb:
    """GET /users with no rows — the foundation milestone's headline contract."""

    def setup_method(self) -> None:
        _reset_users_table()

    def test_get_users_returns_200_and_empty_list_on_fresh_db(self) -> None:
        """The lifecycle healthcheck contract: 200 + ``[]`` on an empty table."""
        resp = requests.get(f"{BASE_URL}/users", timeout=10)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_users_response_is_json_content_type(self) -> None:
        """The response must declare application/json so clients can parse it."""
        resp = requests.get(f"{BASE_URL}/users", timeout=10)
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "application/json" in content_type.lower(), (
            f"Expected application/json content-type, got: {content_type!r}"
        )

    def test_get_users_idempotent_repeated_calls(self) -> None:
        """Read-only endpoint: repeated calls return the same body."""
        first = requests.get(f"{BASE_URL}/users", timeout=10)
        second = requests.get(f"{BASE_URL}/users", timeout=10)
        third = requests.get(f"{BASE_URL}/users", timeout=10)
        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 200
        assert first.json() == second.json() == third.json() == []


class TestGetUsersWithSeededRows:
    """GET /users with rows seeded directly into the app's SQLite file.

    Confirms the response shape ``{id, name, email}`` and that rows the
    app sees through its own connection are returned faithfully.
    """

    def setup_method(self) -> None:
        _reset_users_table()
        conn = sqlite3.connect(APP_DB_PATH, timeout=5)
        try:
            conn.executemany(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                [
                    ("Alice", "alice@example.com"),
                    ("Bob", "bob@example.com"),
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def test_get_users_reflects_seeded_rows(self) -> None:
        """Seeded rows appear in the response with the expected shape and types."""
        resp = requests.get(f"{BASE_URL}/users", timeout=10)
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 2

        # Sort by name to make assertions stable regardless of insert order.
        body_sorted = sorted(body, key=lambda u: u["name"])
        alice, bob = body_sorted

        # Field set must be exactly {id, name, email} for each row.
        for row in body_sorted:
            assert set(row.keys()) == {"id", "name", "email"}, (
                f"Unexpected keys: {set(row.keys())}"
            )
            assert isinstance(row["id"], int)
            assert isinstance(row["name"], str)
            assert isinstance(row["email"], str)

        assert alice["name"] == "Alice"
        assert alice["email"] == "alice@example.com"
        assert bob["name"] == "Bob"
        assert bob["email"] == "bob@example.com"


class TestDatabaseFile:
    """The SQLite DB file should exist in the working directory after startup."""

    def test_database_file_exists_in_working_directory(self) -> None:
        """The app creates ./users.db at module load time."""
        assert os.path.exists(APP_DB_PATH), (
            f"Expected SQLite file at {APP_DB_PATH} to exist after app startup"
        )

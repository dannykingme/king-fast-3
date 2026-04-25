"""Functional tests for the king-fast-3 milestone 2 backend.

Scope (per the milestone-2 spec): the POST /users endpoint is now
implemented with Zod validation, an email-uniqueness check, and a
201 Created response shape.

Tests in this file:

1. ``test_create_user_returns_201_and_body_shape`` — the canonical
   happy path: posting ``{name, email}`` returns 201 and a body with
   the matching name/email and an integer ``id``.
2. ``test_created_user_appears_in_get_users`` — round-trips the new
   user through GET /users to confirm it landed in the DB.
3. ``test_create_user_duplicate_email_returns_400`` — re-posting the
   same email returns ``400 { detail: "Email already registered" }``,
   matching the FastAPI source's ``HTTPException`` shape.
4. ``test_create_user_missing_name_returns_400`` — Zod validation
   failure is reported as 400 per the project spec (not 422).
5. ``test_create_user_missing_email_returns_400`` — same handling for
   a missing email field.
6. ``test_create_user_response_is_json_content_type`` — the response
   declares ``application/json`` so callers can rely on JSON parsing.

The tests assume the lifecycle scripts (install/build/run/healthcheck)
have already brought the Express server up on ``http://localhost:8000``.
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
    """Truncate the users table on the live DB so tests start fresh.

    The app holds an open better-sqlite3 connection on the same file;
    SQLite serializes the writes so this is safe for the single-writer
    test scenario.
    """
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


class TestCreateUserHappyPath:
    """POST /users with valid input — the milestone-2 headline contract."""

    def setup_method(self) -> None:
        _reset_users_table()

    def test_create_user_returns_201_and_body_shape(self) -> None:
        """Posting valid {name,email} returns 201 with {id,name,email}."""
        payload = {"name": "John Doe", "email": "john@example.com"}
        resp = requests.post(f"{BASE_URL}/users", json=payload, timeout=10)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "John Doe"
        assert body["email"] == "john@example.com"
        assert "id" in body
        assert isinstance(body["id"], int)

    def test_created_user_appears_in_get_users(self) -> None:
        """A user created via POST is visible via GET /users."""
        payload = {"name": "Jane Doe", "email": "jane@example.com"}
        create = requests.post(f"{BASE_URL}/users", json=payload, timeout=10)
        assert create.status_code == 201
        created = create.json()

        listing = requests.get(f"{BASE_URL}/users", timeout=10)
        assert listing.status_code == 200
        body = listing.json()
        assert isinstance(body, list)
        assert any(
            row["id"] == created["id"]
            and row["name"] == "Jane Doe"
            and row["email"] == "jane@example.com"
            for row in body
        ), f"Created user not present in GET /users response: {body!r}"

    def test_create_user_response_is_json_content_type(self) -> None:
        """The response must declare application/json so clients can parse it."""
        payload = {"name": "Carol", "email": "carol@example.com"}
        resp = requests.post(f"{BASE_URL}/users", json=payload, timeout=10)
        assert resp.status_code == 201
        content_type = resp.headers.get("content-type", "")
        assert "application/json" in content_type.lower(), (
            f"Expected application/json content-type, got: {content_type!r}"
        )


class TestCreateUserDuplicateEmail:
    """Posting a duplicate email must yield the FastAPI-shaped 400 detail."""

    def setup_method(self) -> None:
        _reset_users_table()

    def test_create_user_duplicate_email_returns_400(self) -> None:
        """Re-using an email returns 400 with detail 'Email already registered'."""
        payload = {"name": "Alice", "email": "dup@example.com"}
        first = requests.post(f"{BASE_URL}/users", json=payload, timeout=10)
        assert first.status_code == 201

        second = requests.post(
            f"{BASE_URL}/users",
            json={"name": "Alice2", "email": "dup@example.com"},
            timeout=10,
        )
        assert second.status_code == 400
        body = second.json()
        assert body.get("detail") == "Email already registered", (
            f"Unexpected error body: {body!r}"
        )


class TestCreateUserValidationErrors:
    """Missing required fields must be rejected with 400."""

    def setup_method(self) -> None:
        _reset_users_table()

    def test_create_user_missing_name_returns_400(self) -> None:
        """Omitting `name` triggers Zod validation → 400 with a detail string."""
        resp = requests.post(
            f"{BASE_URL}/users",
            json={"email": "noname@example.com"},
            timeout=10,
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)

    def test_create_user_missing_email_returns_400(self) -> None:
        """Omitting `email` triggers Zod validation → 400 with a detail string."""
        resp = requests.post(
            f"{BASE_URL}/users",
            json={"name": "NoEmail"},
            timeout=10,
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)

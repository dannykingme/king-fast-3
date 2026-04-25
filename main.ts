/**
 * king-fast-3 — TypeScript/Express port of the users service.
 *
 * Scaffolds a single-process HTTP API backed by SQLite (better-sqlite3).
 * This module exports both the Express `app` instance and the underlying
 * `db` handle so the test harness (test_main.ts) can drive HTTP requests
 * via supertest and reset the schema between tests without opening a
 * second connection.
 *
 * Behavior:
 *   - DATABASE_URL is resolved from the environment (default `./users.db`).
 *   - The `users` table is created at module load via
 *     `CREATE TABLE IF NOT EXISTS`, mirroring the original
 *     SQLAlchemy `Base.metadata.create_all` pattern.
 *   - When run as a script (`node dist/main.js` or `tsx main.ts`),
 *     the app binds to `$HOST:$PORT` (defaults: `0.0.0.0:8000`).
 */

import express, { Request, Response } from 'express';
import Database from 'better-sqlite3';
import { z } from 'zod';

/**
 * Resolved SQLite filesystem path. Falls back to `./users.db` so the
 * service runs out of the box without configuration. Tests override
 * this by setting `process.env.DATABASE_URL` before importing this
 * module.
 */
const DATABASE_URL: string = process.env.DATABASE_URL ?? './users.db';

/**
 * Open better-sqlite3 connection used by the request handlers. Exported
 * so tests can issue DDL (DROP/CREATE TABLE) against the same handle
 * for per-test isolation.
 */
export const db: Database.Database = new Database(DATABASE_URL);

/**
 * Initialize the `users` schema. Idempotent — safe to call repeatedly.
 *
 * @returns void
 */
function initSchema(): void {
  db.exec(
    'CREATE TABLE IF NOT EXISTS users (' +
      'id INTEGER PRIMARY KEY AUTOINCREMENT, ' +
      'name TEXT NOT NULL, ' +
      'email TEXT NOT NULL UNIQUE' +
      ')'
  );
}

initSchema();

/**
 * Shape of a row in the `users` table as returned to API consumers.
 */
export interface UserRow {
  id: number;
  name: string;
  email: string;
}

/**
 * Zod schema for the `POST /users` request body. Mirrors the original
 * Pydantic `UserCreate` model (`name: str`, `email: str`) — both fields
 * are required strings, no further format validation is applied so that
 * behavior matches the FastAPI source verbatim.
 */
export const UserCreate = z.object({
  name: z.string(),
  email: z.string(),
});

/**
 * Inferred TypeScript type for a validated `POST /users` payload.
 * Provided as the static-type counterpart to the Zod schema, replacing
 * Pydantic's typed model class on the Python side.
 */
export type UserCreateInput = z.infer<typeof UserCreate>;

/**
 * Configured Express application. Exported so `supertest(app)` can drive
 * it without binding a TCP port; also passed to `app.listen` when this
 * module is the script entrypoint.
 */
export const app = express();

app.use(express.json());

/**
 * GET /users — return all users in the table.
 *
 * @param _req - Express request (no body or query params consumed).
 * @param res  - Express response; emits a JSON array of user rows
 *               with shape `{ id, name, email }` and HTTP 200.
 * @returns void
 */
app.get('/users', (_req: Request, res: Response): void => {
  const rows = db
    .prepare('SELECT id, name, email FROM users')
    .all() as UserRow[];
  res.status(200).json(rows);
});

/**
 * POST /users — create a new user.
 *
 * Validates the JSON body against the `UserCreate` Zod schema, then
 * checks for an existing row with the same email. On conflict the
 * handler responds with `400 { detail: "Email already registered" }`,
 * mirroring the FastAPI source's `HTTPException(status_code=400, ...)`
 * behavior (decision +++5+++ in the project spec).
 *
 * On success it inserts a new row, then assembles the response from the
 * validated input plus `Number(result.lastInsertRowid)` (per milestone
 * design decision 3, approach 2 — no extra SELECT round-trip), and
 * responds with `201 { id, name, email }`.
 *
 * @param req - Express request whose JSON body must satisfy `UserCreate`.
 * @param res - Express response used to send 201 with the created user
 *              or 400 with `{ detail }` on validation/conflict errors.
 * @returns void
 */
app.post('/users', (req: Request, res: Response): void => {
  const parsed = UserCreate.safeParse(req.body);
  if (!parsed.success) {
    const detail =
      parsed.error.issues[0]?.message ?? 'Invalid request body';
    res.status(400).json({ detail });
    return;
  }

  const { name, email } = parsed.data;

  const existing = db
    .prepare('SELECT id FROM users WHERE email = ?')
    .get(email) as { id: number } | undefined;
  if (existing !== undefined) {
    res.status(400).json({ detail: 'Email already registered' });
    return;
  }

  let lastInsertRowid: number | bigint;
  try {
    const result = db
      .prepare('INSERT INTO users (name, email) VALUES (?, ?)')
      .run(name, email);
    lastInsertRowid = result.lastInsertRowid;
  } catch (err) {
    // SQLite UNIQUE constraint violation can race past the SELECT above
    // under concurrent inserts. Translate it to the same 400 shape so
    // we don't expose a 500 to the client (parity-preserving with the
    // original Python behavior, where the IntegrityError would also be
    // caller-visible only as a 500 absent special handling).
    const message = err instanceof Error ? err.message : String(err);
    if (message.includes('UNIQUE constraint failed')) {
      res.status(400).json({ detail: 'Email already registered' });
      return;
    }
    throw err;
  }

  const created: UserRow = {
    id: Number(lastInsertRowid),
    name,
    email,
  };
  res.status(201).json(created);
});

/**
 * Start the HTTP server when this module is invoked directly.
 *
 * Honors `HOST` and `PORT` environment variables (defaults: `0.0.0.0`
 * and `8000`) so the lifecycle scripts can bind the service consistently
 * with the origin uvicorn-based deployment.
 */
if (require.main === module) {
  const port: number = Number(process.env.PORT ?? 8000);
  const host: string = process.env.HOST ?? '0.0.0.0';
  app.listen(port, host, () => {
    // eslint-disable-next-line no-console
    console.log(`king-fast-3 listening on http://${host}:${port}`);
  });
}

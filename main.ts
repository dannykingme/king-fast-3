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

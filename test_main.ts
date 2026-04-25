/**
 * End-to-end test for king-fast-3 (Jest + supertest).
 *
 * Mirrors `test_main.py` in spirit: an isolated SQLite file is used,
 * the `users` table is dropped and recreated before each test, and
 * supertest drives the exported Express `app` directly (no TCP listener).
 *
 * NOTE: `process.env.DATABASE_URL` MUST be set before requiring `./main`,
 * because `main.ts` opens its better-sqlite3 connection at module load.
 */

process.env.DATABASE_URL = './test_users.db';

// eslint-disable-next-line @typescript-eslint/no-var-requires
import request from 'supertest';
import { app, db } from './main';

/**
 * Reset the `users` table to a known empty state. Issued via the
 * shared `db` handle so we don't need a second connection.
 *
 * @returns void
 */
function resetUsersTable(): void {
  db.exec('DROP TABLE IF EXISTS users');
  db.exec(
    'CREATE TABLE users (' +
      'id INTEGER PRIMARY KEY AUTOINCREMENT, ' +
      'name TEXT NOT NULL, ' +
      'email TEXT NOT NULL UNIQUE' +
      ')'
  );
}

beforeEach(() => {
  resetUsersTable();
});

describe('GET /users', () => {
  /**
   * The smoke test for the foundation milestone: with the table freshly
   * (re)created and empty, GET /users must return HTTP 200 with an
   * empty JSON array. This proves the Express app, better-sqlite3
   * driver, schema initialization, and route wiring all work together.
   */
  test('returns 200 and an empty list on a fresh DB', async () => {
    const response = await request(app).get('/users');

    expect(response.status).toBe(200);
    expect(response.headers['content-type']).toMatch(/application\/json/);
    expect(response.body).toEqual([]);
  });
});

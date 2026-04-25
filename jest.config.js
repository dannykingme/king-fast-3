/**
 * Jest configuration for the king-fast-3 service.
 *
 * Uses ts-jest's CommonJS preset so TypeScript test files (test_main.ts)
 * are compiled in-process. Test discovery is restricted to the flat
 * test_main.ts file at the repo root to mirror the project layout
 * mandated by the modernization spec.
 */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['<rootDir>/test_main.ts'],
  moduleFileExtensions: ['ts', 'js', 'json'],
  testTimeout: 15000,
};

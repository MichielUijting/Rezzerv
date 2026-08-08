async function globalTeardown() {
  // Cleanup is owned by scripts/run-frontend-regression-report.ps1,
  // which has retry/backoff for temporary SQLite locks.
}

export default globalTeardown;

// @ts-check
const { defineConfig } = require("@playwright/test");

// Requires the API (and its DB) already running -- `docker compose up -d db api` from the repo
// root -- same convention as the Python test suites (see SESSION_LOG.md). This config only
// brings up the Next.js dev server.
module.exports = defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});

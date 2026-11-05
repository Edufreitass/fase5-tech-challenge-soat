import { defineConfig } from "@playwright/test";

/** Smoke tests locais: navegador real e respostas controladas, sem recursos AWS. */
export default defineConfig({
  testDir: "tests/browser",
  fullyParallel: true,
  workers: 2,
  forbidOnly: true,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    browserName: "chromium",
    channel: process.env.E2E_CHANNEL || undefined,
    headless: true,
    locale: "pt-BR",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});

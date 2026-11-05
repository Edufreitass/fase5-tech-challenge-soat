import { defineConfig } from "@playwright/test";

// E2E contra o ambiente publicado: E2E_URL (ex.: https://xxxx.cloudfront.net) e credenciais AWS do ambiente
// (perfil AWS ou OIDC no CI) para criar/remover usuarios de teste no Cognito.
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.E2E_URL,
    channel: process.env.E2E_CHANNEL || undefined, // "chrome" para usar o Chrome instalado
    locale: "pt-BR",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});

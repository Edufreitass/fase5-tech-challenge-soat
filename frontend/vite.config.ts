import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";
import { opcoesDev } from "./src/lib/environment.ts";

// Somente em `vite dev`: serve /config.json (em producao ele vem do Terraform) com IDs vindos do ambiente.
const configDev = (): Plugin => ({
  name: "config-dev",
  apply: "serve",
  configureServer(servidor) {
    servidor.middlewares.use("/config.json", (_req, res) => {
      res.setHeader("Content-Type", "application/json");
      const e = process.env;
      res.end(
        JSON.stringify({
          apiBase: "/api",
          versaoTermo: e.VERSAO_TERMO ?? "2026-10-v1",
          regiao: e.AWS_REGION ?? "us-east-1",
          clientes: { clientId: e.CLIENT_ID_CLIENTES ?? "", dominio: e.DOMINIO_CLIENTES ?? "" },
          funcionarios: {
            clientId: e.CLIENT_ID_FUNCIONARIOS ?? "",
            dominio: e.DOMINIO_FUNCIONARIOS ?? "",
          },
        }),
      );
    });
  },
});

// Em desenvolvimento, `/api` aponta para API_ALVO, quando configurada.
const opcoes = opcoesDev(process.env);

export default defineConfig({
  plugins: [react(), tailwindcss(), configDev()],
  build: { sourcemap: false, chunkSizeWarningLimit: 700 },
  server: { proxy: opcoes.proxy },
});

import { render, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { obter } from "../lib/api";
import { salvarSessao } from "../lib/auth";
import { definirConfig } from "../lib/config";
import { AuthProvider } from "./AuthContext";

const CFG = {
  apiBase: "/api",
  versaoTermo: "2026-10-v1",
  regiao: "us-east-1",
  clientes: { clientId: "cli", dominio: "dom-cli" },
  funcionarios: { clientId: "fun", dominio: "dom-fun" },
};

// Efeito de pagina: roda antes do efeito do AuthProvider que chama definirContexto (regressao: saia sem token).
function Pagina() {
  useEffect(() => {
    void obter("/veiculos/v1").catch(() => undefined);
  }, []);
  return null;
}

it("a primeira busca de um carregamento completo ja vai com o token da sessao guardada", async () => {
  definirConfig(CFG);
  salvarSessao({ accessToken: "tok", expiraEm: Date.now() + 600_000, pool: "funcionarios" });
  const buscar = jest
    .fn<ReturnType<typeof fetch>, Parameters<typeof fetch>>()
    .mockResolvedValue(new Response("{}", { status: 200 }));
  global.fetch = buscar;
  render(
    <AuthProvider>
      <Pagina />
    </AuthProvider>,
  );
  await waitFor(() => expect(buscar).toHaveBeenCalled());
  const [url, init] = buscar.mock.calls[0] ?? [];
  expect(url).toBe("/api/veiculos/v1");
  expect(init?.headers).toMatchObject({ Authorization: "Bearer tok" });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { AuthProvider } from "../context/AuthContext";
import { ErroApi } from "../lib/api";
import { definirConfig } from "../lib/config";
import { Layout } from "./Layout";

jest.mock("../lib/api", () => ({ ...jest.requireActual("../lib/api"), obter: jest.fn() }));
const api = require("../lib/api") as { obter: jest.Mock };
const jwt = (c: object) => `x.${btoa(JSON.stringify(c))}.y`;

const montar = (pool?: "clientes" | "funcionarios", grupos: string[] = [], idToken?: string) => {
  if (pool)
    sessionStorage.setItem(
      "revenda.sessao",
      JSON.stringify({
        accessToken: jwt({ "cognito:groups": grupos }),
        idToken,
        expiraEm: Date.now() + 1e6,
        pool,
      }),
    );
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<p>conteudo</p>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
};

beforeEach(() => {
  jest.resetAllMocks();
  api.obter.mockResolvedValue({
    dados: { nomeCompleto: "Maria Silva Souza", cadastroCompleto: true, camposPendentes: [] },
    etag: null,
  });
  sessionStorage.clear();
  definirConfig({
    apiBase: "/api",
    versaoTermo: "v",
    regiao: "us-east-1",
    clientes: { clientId: "c", dominio: "d" },
    funcionarios: { clientId: "f", dominio: "e" },
  });
});

describe("Layout", () => {
  it("anonimo ve Entrar e so o catalogo", () => {
    montar();
    expect(screen.getAllByRole("link", { name: "Entrar" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "Minhas compras" })).not.toBeInTheDocument();
    expect(screen.getByText("conteudo")).toBeInTheDocument();
  });

  it("cliente ve compras e perfil e consegue sair", async () => {
    montar("clientes");
    expect(screen.getByRole("link", { name: "Minhas compras" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Meu perfil" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Painel" })).not.toBeInTheDocument();
    // O logout navega para o Cognito (jsdom nao implementa navegacao e so registra o aviso).
    const aviso = jest.spyOn(console, "error").mockImplementation(() => undefined);
    await userEvent.click(screen.getByRole("button", { name: "Sair" }));
    expect(sessionStorage.getItem("revenda.sessao")).toBeNull();
    aviso.mockRestore();
  });

  it("funcionario ve o painel e abre o menu movel", async () => {
    montar("funcionarios", ["admin"]);
    expect(screen.getByRole("link", { name: "Painel" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Abrir menu" }));
    expect(screen.getByRole("button", { name: "Fechar menu" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("mostra o nome do cliente (do cadastro) no menu", async () => {
    montar("clientes");
    expect(await screen.findByText("Maria")).toBeInTheDocument();
    expect(screen.queryByText(/Complete seu cadastro/)).not.toBeInTheDocument();
  });

  it("avisa quem ainda nao tem cadastro, com atalho para completar", async () => {
    api.obter.mockRejectedValue(
      new ErroApi(
        403,
        "Cadastro de cliente inexistente",
        "x",
        [],
        undefined,
        "perfil-cliente-inexistente",
      ),
    );
    montar("clientes", [], jwt({ email: "joana@x.com" }));
    expect(
      await screen.findByText(/complete seu cadastro para poder reservar/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Completar cadastro" })).toHaveAttribute(
      "href",
      "/perfil",
    );
    expect(screen.getByTestId("usuario-nome")).toHaveTextContent("joana"); // sem cadastro: usa o e-mail
  });

  it("avisa as pendencias do cadastro incompleto", async () => {
    api.obter.mockResolvedValue({
      dados: { nomeCompleto: "Ana Lima", cadastroCompleto: false, camposPendentes: ["rg"] },
      etag: null,
    });
    montar("clientes");
    expect(await screen.findByText(/falta: RG/)).toBeInTheDocument();
  });

  it("funcionario ve o nome do ID token", () => {
    montar("funcionarios", ["vendedor"], jwt({ name: "Carlos Vendedor", email: "c@x.com" }));
    expect(screen.getByTestId("usuario-nome")).toHaveTextContent("Carlos");
    expect(api.obter).not.toHaveBeenCalled();
  });
});

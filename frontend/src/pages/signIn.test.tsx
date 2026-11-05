import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { Protegida, SoAnonimo } from "../App";
import { AuthProvider } from "../context/AuthContext";
import { ErroApi } from "../lib/api";
import { definirConfig } from "../lib/config";
import { destinoAposLogin, Entrar } from "./SignIn";

jest.mock("../lib/api", () => ({ ...jest.requireActual("../lib/api"), obter: jest.fn() }));
const api = require("../lib/api") as { obter: jest.Mock };

jest.mock("../lib/cognito", () => {
  const real = jest.requireActual("../lib/cognito");
  return {
    ...real,
    entrar: jest.fn(),
    responderNovaSenha: jest.fn(),
    responderMfa: jest.fn(),
    iniciarMfa: jest.fn(),
    concluirMfa: jest.fn(),
    cadastrar: jest.fn(),
    confirmarCadastro: jest.fn(),
    reenviarCodigo: jest.fn(),
    esqueciSenha: jest.fn(),
    redefinirSenha: jest.fn(),
  };
});
const c = require("../lib/cognito") as jest.Mocked<typeof import("../lib/cognito")>;

const token = (grupos: string[]) => `x.${btoa(JSON.stringify({ "cognito:groups": grupos }))}.y`;
const sessao = (pool: import("../lib/auth").TipoPool, grupos: string[] = []) => ({
  sessao: { accessToken: token(grupos), expiraEm: Date.now() + 1e6, pool },
});

function montar() {
  return render(
    <MemoryRouter initialEntries={["/entrar"]}>
      <AuthProvider>
        <Routes>
          <Route path="/entrar" element={<Entrar />} />
          <Route path="/compras" element={<p>area do cliente</p>} />
          <Route path="/perfil" element={<p>completar cadastro</p>} />
          <Route path="/painel" element={<p>area da loja</p>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

const digitar = async (rotulo: string | RegExp, valor: string) =>
  userEvent.type(screen.getByLabelText(rotulo), valor);

beforeEach(() => {
  jest.resetAllMocks();
  api.obter.mockResolvedValue({ dados: {}, etag: null }); // cliente ja cadastrado
  sessionStorage.clear();
  definirConfig({
    apiBase: "/api",
    versaoTermo: "v",
    regiao: "us-east-1",
    clientes: { clientId: "c", dominio: "d" },
    funcionarios: { clientId: "f", dominio: "e" },
  });
});

describe("tela de login propria", () => {
  it("cliente entra e vai para suas compras", async () => {
    c.entrar.mockResolvedValue(sessao("clientes"));
    montar();
    expect(screen.getByRole("heading", { name: /Entrar/ })).toBeInTheDocument();
    await digitar("E-mail", "ana@x.com");
    await digitar("Senha", "Senha#12345x");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByText("area do cliente")).toBeInTheDocument();
    expect(c.entrar).toHaveBeenCalledWith("clientes", "ana@x.com", "Senha#12345x");
  });

  it("mostra erro de credencial e valida e-mail", async () => {
    c.entrar.mockRejectedValue(
      new c.ErroCognito("NotAuthorizedException", "E-mail ou senha incorretos."),
    );
    montar();
    await digitar("E-mail", "ana@x.com");
    await digitar("Senha", "errada");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha incorretos.");
    await userEvent.click(screen.getByRole("button", { name: "Mostrar senha" }));
    expect(screen.getByLabelText("Senha")).toHaveAttribute("type", "text");
  });

  it("funcionario: nova senha, ativacao do MFA com QR e entrada no painel", async () => {
    const d1: import("../lib/cognito").Desafio = { tipo: "novaSenha", sessao: "s1", usuario: "u" };
    const d2: import("../lib/cognito").Desafio = { tipo: "mfaSetup", sessao: "s2", usuario: "u" };
    c.entrar.mockResolvedValue({ desafio: d1 });
    c.responderNovaSenha.mockResolvedValue({ desafio: d2 });
    c.iniciarMfa.mockResolvedValue({ segredo: "ABCDEF234567", sessao: "s3" });
    c.concluirMfa.mockResolvedValue(sessao("funcionarios", ["vendedor"]));
    montar();
    await userEvent.click(screen.getByRole("tab", { name: /Sou funcionário/ }));
    expect(screen.queryByRole("button", { name: "Criar conta" })).not.toBeInTheDocument();
    await digitar("E-mail", "loja@x.com");
    await digitar("Senha", "Temp#Senha123");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("heading", { name: /Defina sua senha/ })).toBeInTheDocument();
    await digitar("Nova senha", "fraca");
    await userEvent.click(screen.getByRole("button", { name: "Salvar e continuar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("não atende");
    await userEvent.clear(screen.getByLabelText("Nova senha"));
    await digitar("Nova senha", "Nova#Senha1234");
    await userEvent.click(screen.getByRole("button", { name: "Salvar e continuar" }));
    expect(await screen.findByTestId("chave-mfa")).toHaveTextContent("ABCDEF234567");
    expect(screen.getByLabelText("QR code do autenticador")).toBeInTheDocument();
    await digitar("Código do aplicativo", "123456");
    await userEvent.click(screen.getByRole("button", { name: "Ativar e entrar" }));
    expect(await screen.findByText("area da loja")).toBeInTheDocument();
    expect(c.concluirMfa).toHaveBeenCalledWith("funcionarios", d2, "s3", "123456");
  });

  it("funcionario com MFA ja ativo informa so o codigo", async () => {
    c.entrar.mockResolvedValue({ desafio: { tipo: "mfaCodigo", sessao: "s", usuario: "u" } });
    c.responderMfa.mockResolvedValue(sessao("funcionarios", ["admin"]));
    montar();
    await userEvent.click(screen.getByRole("tab", { name: /Sou funcionário/ }));
    await digitar("E-mail", "adm@x.com");
    await digitar("Senha", "Senha#12345x");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    await digitar("Código do aplicativo", "999999");
    await userEvent.click(screen.getByRole("button", { name: "Verificar" }));
    expect(await screen.findByText("area da loja")).toBeInTheDocument();
  });

  it("cadastro valida a senha, confirma o e-mail e volta ao login", async () => {
    c.cadastrar.mockResolvedValue({});
    c.confirmarCadastro.mockResolvedValue({});
    c.reenviarCodigo.mockResolvedValue({});
    montar();
    await userEvent.click(screen.getByRole("button", { name: "Criar conta" }));
    await digitar("E-mail", "novo@x.com");
    await digitar("Senha", "curta");
    expect(screen.getByRole("list", { name: "Requisitos da senha" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Criar conta" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("não atende");
    await userEvent.clear(screen.getByLabelText("Senha"));
    await digitar("Senha", "Senha#12345x");
    await userEvent.click(screen.getByRole("button", { name: "Criar conta" }));
    expect(await screen.findByRole("heading", { name: /Confirme seu e-mail/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reenviar código" }));
    expect(
      await screen.findByText("Código reenviado. Confira sua caixa de entrada."),
    ).toBeInTheDocument();
    await digitar("Código", "12a3456");
    // Conta nova: ao confirmar, entra com a senha criada e segue para completar o cadastro (sem passar pelo login).
    c.entrar.mockResolvedValue(sessao("clientes"));
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
    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(c.confirmarCadastro).toHaveBeenCalledWith("novo@x.com", "123456");
    expect(c.entrar).toHaveBeenCalledWith("clientes", "novo@x.com", "Senha#12345x");
    expect(await screen.findByText("completar cadastro")).toBeInTheDocument();
  });

  it("cliente sem cadastro que entra pelo login tambem vai completar o cadastro", async () => {
    c.entrar.mockResolvedValue(sessao("clientes"));
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
    montar();
    await digitar("E-mail", "ana@x.com");
    await digitar("Senha", "Senha#12345x");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByText("completar cadastro")).toBeInTheDocument();
  });

  it("se a entrada automatica falhar apos confirmar, volta ao login com aviso", async () => {
    c.cadastrar.mockResolvedValue({});
    c.confirmarCadastro.mockResolvedValue({});
    c.entrar.mockRejectedValue(new Error("falhou"));
    montar();
    await userEvent.click(screen.getByRole("button", { name: "Criar conta" }));
    await digitar("E-mail", "novo@x.com");
    await digitar("Senha", "Senha#12345x");
    await userEvent.click(screen.getByRole("button", { name: "Criar conta" }));
    await digitar("Código", "123456");
    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(await screen.findByText(/E-mail confirmado/)).toBeInTheDocument();
  });

  it("login de conta nao confirmada leva a confirmacao", async () => {
    c.entrar.mockRejectedValue(new c.ErroCognito("UserNotConfirmedException", "x"));
    montar();
    await digitar("E-mail", "a@x.com");
    await digitar("Senha", "Senha#12345x");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("heading", { name: /Confirme seu e-mail/ })).toBeInTheDocument();
  });

  it("recupera a senha com codigo por e-mail", async () => {
    c.esqueciSenha.mockResolvedValue({});
    c.redefinirSenha.mockResolvedValue({});
    montar();
    await userEvent.click(screen.getByRole("button", { name: "Esqueci minha senha" }));
    await digitar("E-mail", "a@x.com");
    await userEvent.click(screen.getByRole("button", { name: "Enviar código" }));
    expect(await screen.findByRole("heading", { name: /Nova senha/ })).toBeInTheDocument();
    await digitar("Código", "123456");
    await digitar("Nova senha", "Outra#Senha123");
    await userEvent.click(screen.getByRole("button", { name: "Redefinir senha" }));
    await waitFor(() =>
      expect(c.redefinirSenha).toHaveBeenCalledWith(
        "clientes",
        "a@x.com",
        "123456",
        "Outra#Senha123",
      ),
    );
    expect(await screen.findByText(/Senha redefinida/)).toBeInTheDocument();
  });

  it("rejeita e-mail invalido antes de chamar o Cognito", async () => {
    montar();
    await digitar("E-mail", "invalido");
    await digitar("Senha", "x");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(c.entrar).not.toHaveBeenCalled();
  });
});

describe("correcoes do teste E2E no login", () => {
  it("a senha digitada no login nao vai para Criar conta", async () => {
    montar();
    await digitar("E-mail", "ana@x.com");
    await digitar("Senha", "SenhaErrada#1");
    await userEvent.click(screen.getByRole("button", { name: "Criar conta" }));
    expect(await screen.findByRole("heading", { name: /Criar conta/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toHaveValue("");
    expect(screen.getByLabelText("E-mail")).toHaveValue("ana@x.com");
  });

  it("reenviar codigo com erro nao mostra o aviso antigo junto", async () => {
    c.cadastrar.mockResolvedValue({});
    c.reenviarCodigo.mockRejectedValue(
      new c.ErroCognito("LimitExceededException", "Muitas tentativas. Aguarde alguns minutos."),
    );
    montar();
    await userEvent.click(screen.getByRole("button", { name: "Criar conta" }));
    await digitar("E-mail", "novo@x.com");
    await digitar("Senha", "Senha#12345x");
    await userEvent.click(screen.getByRole("button", { name: "Criar conta" }));
    expect(await screen.findByText(/Enviamos um código/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reenviar código" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Muitas tentativas");
    expect(screen.queryByText(/Enviamos um código/)).not.toBeInTheDocument();
  });

  it("primeiro acesso pode ser cancelado e volta ao login", async () => {
    c.entrar.mockResolvedValue({ desafio: { tipo: "novaSenha", sessao: "s", usuario: "u" } });
    montar();
    await userEvent.click(screen.getByRole("tab", { name: /Sou funcionário/ }));
    await digitar("E-mail", "adm@x.com");
    await digitar("Senha", "Temporaria#123");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("heading", { name: /Defina sua senha/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancelar e voltar ao login" }));
    expect(await screen.findByRole("heading", { name: /^Entrar/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toHaveValue("");
  });

  it("depois do login volta para a pagina que pediu o login", () => {
    expect(destinoAposLogin("cliente", "/veiculos/9")).toBe("/veiculos/9");
    expect(destinoAposLogin("cliente", "/painel")).toBe("/compras");
    expect(destinoAposLogin("cliente", undefined)).toBe("/compras");
    expect(destinoAposLogin("admin", "/perfil")).toBe("/painel");
    expect(destinoAposLogin("vendedor", "/veiculos?marca=Fiat")).toBe("/veiculos?marca=Fiat");
    expect(destinoAposLogin("admin", "/entrar")).toBe("/painel");
  });
});

describe("rotas protegidas e /entrar", () => {
  function app(caminho: string) {
    return render(
      <MemoryRouter initialEntries={[caminho]}>
        <AuthProvider>
          <Routes>
            <Route
              path="/entrar"
              element={
                <SoAnonimo>
                  <Entrar />
                </SoAnonimo>
              }
            />
            <Route
              path="/compras"
              element={
                <Protegida papeis={["cliente"]}>
                  <p>area do cliente</p>
                </Protegida>
              }
            />
            <Route path="/painel" element={<p>area da loja</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
  }

  it("quem ja esta logado nao ve o login", async () => {
    sessionStorage.setItem(
      "revenda.sessao",
      JSON.stringify(sessao("funcionarios", ["admin"]).sessao),
    );
    app("/entrar");
    expect(await screen.findByText("area da loja")).toBeInTheDocument();
  });

  it("rota protegida manda ao login e, depois de entrar, volta para ela", async () => {
    c.entrar.mockResolvedValue(sessao("clientes"));
    app("/compras");
    expect(await screen.findByRole("heading", { name: /^Entrar/ })).toBeInTheDocument();
    await digitar("E-mail", "ana@x.com");
    await digitar("Senha", "Senha#12345x");
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByText("area do cliente")).toBeInTheDocument();
  });
});

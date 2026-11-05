import { chamar, definirContexto, ErroApi } from "./api";
import { claims, consumirAvisoDoLogin, lerSessao, papelDe } from "./auth";
import { entrar } from "./cognito";
import { carregarConfig, definirConfig } from "./config";
import { textoDoFormulario } from "./forms";
import { retornoInterno } from "./navigation";

const CONFIG = {
  apiBase: "/api",
  versaoTermo: "v1",
  regiao: "us-east-1",
  clientes: { clientId: "cliente", dominio: "clientes" },
  funcionarios: { clientId: "funcionario", dominio: "funcionarios" },
};

beforeEach(() => {
  sessionStorage.clear();
  definirConfig(CONFIG);
});

describe("dados externos", () => {
  it.each([
    null,
    [],
    {},
    { accessToken: 12 },
    { accessToken: "a", expiraEm: "amanha", pool: "clientes" },
    { accessToken: "a", expiraEm: 123, pool: "desconhecido" },
    { accessToken: "a", expiraEm: 123, pool: "clientes", refreshToken: {} },
  ])("descarta sessao fora do contrato: %j", (dados: unknown) => {
    // Arrange
    sessionStorage.setItem("revenda.sessao", JSON.stringify(dados));

    // Act
    const sessao = lerSessao();

    // Assert
    expect(sessao).toBeNull();
  });

  it("descarta recado de login que nao seja texto", () => {
    sessionStorage.setItem("revenda.aviso-login", "{}");

    const aviso = consumirAvisoDoLogin();

    expect(aviso).toBeNull();
    expect(sessionStorage.getItem("revenda.aviso-login")).toBeNull();
  });

  it("decodifica UTF-8 e descarta claims com tipos invalidos", () => {
    const carga = { name: "João", email: {}, sub: "c1", "cognito:groups": "admin" };
    const bytes = new TextEncoder().encode(JSON.stringify(carga));
    const token = `x.${btoa(String.fromCharCode(...bytes))}.y`;

    const dados = claims(token);

    expect(dados).toEqual({ name: "João", sub: "c1" });
    expect(papelDe({ accessToken: token, expiraEm: 100, pool: "funcionarios" })).toBeNull();
  });

  it.each([null, [], {}, { ...CONFIG, clientes: { clientId: 123 } }])(
    "rejeita configuracao invalida: %j",
    async (dados: unknown) => {
      // Um mock tipado usa a assinatura real da funcao de rede.
      const fetchConfig = jest
        .fn<ReturnType<typeof fetch>, Parameters<typeof fetch>>()
        .mockResolvedValue(new Response(JSON.stringify(dados)));

      const resultado = carregarConfig(fetchConfig);

      await expect(resultado).rejects.toThrow("Configuração do ambiente inválida.");
    },
  );

  it("nao trata arquivos de um formulario como texto", () => {
    const formulario = document.createElement("form");
    const campo = document.createElement("input");
    campo.name = "anexo";
    campo.type = "file";
    formulario.append(campo);

    const ler = textoDoFormulario(formulario);

    expect(ler("anexo")).toBe("");
    expect(ler("ausente")).toBe("");
  });
});

describe("respostas HTTP", () => {
  it.each([null, [], { title: 42, detail: {}, errors: "texto" }])(
    "mantem um erro de API legivel para problem+json invalido: %j",
    async (corpo: unknown) => {
      const buscar = jest
        .fn<ReturnType<typeof fetch>, Parameters<typeof fetch>>()
        .mockResolvedValue(new Response(JSON.stringify(corpo), { status: 503 }));
      definirContexto({ sessao: () => null, atualizar: jest.fn(), buscar });

      const resultado = chamar("/veiculos");

      await expect(resultado).rejects.toMatchObject({ status: 503, titulo: "Erro 503" });
    },
  );

  it("converte JSON invalido em erro de integracao", async () => {
    const buscar = jest
      .fn<ReturnType<typeof fetch>, Parameters<typeof fetch>>()
      .mockResolvedValue(new Response("<html>proxy indisponivel</html>"));
    definirContexto({ sessao: () => null, atualizar: jest.fn(), buscar });

    const resultado = chamar("/veiculos");

    await expect(resultado).rejects.toBeInstanceOf(ErroApi);
    await expect(resultado).rejects.toMatchObject({ status: 502, titulo: "Resposta inválida" });
  });
});

it.each([
  null,
  [],
  { AuthenticationResult: { AccessToken: "a", ExpiresIn: "3600" } },
  { AuthenticationResult: { AccessToken: 12, ExpiresIn: 3600 } },
])("rejeita resposta de login malformada: %j", async (corpo: unknown) => {
  definirConfig(CONFIG);
  const buscar = jest
    .fn<ReturnType<typeof fetch>, Parameters<typeof fetch>>()
    .mockResolvedValue(new Response(JSON.stringify(corpo)));

  const resultado = entrar("clientes", "cliente@example.com", "SenhaDeTeste", buscar);

  await expect(resultado).rejects.toMatchObject({ codigo: "RespostaInvalida" });
});

it.each([
  null,
  { de: 123 },
  { de: "https://example.com" },
  { de: "//example.com" },
  { de: "/\\example.com" },
])("descarta destino de navegacao invalido: %j", (estado: unknown) => {
  const caminho = retornoInterno(estado);

  expect(caminho).toBeUndefined();
});

it("preserva caminho local com filtros", () => {
  const caminho = retornoInterno({ de: "/veiculos?marca=Fiat&pagina=2" });

  expect(caminho).toBe("/veiculos?marca=Fiat&pagina=2");
});

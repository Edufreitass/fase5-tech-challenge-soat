import { chamar, definirContexto, ErroApi, montarUrl } from "./api";
import { claims, lerSessao, papelDe, renovar, type Sessao, sair, salvarSessao } from "./auth";
import * as cognito from "./cognito";
import { carregarConfig, config, definirConfig } from "./config";
import {
  acentuar,
  apenasDigitos,
  dataHora,
  km,
  moeda,
  pendencias,
  restante,
  telefoneE164,
  telefoneFormatado,
  titulo,
} from "./formatters/format";
import { mensagemDe } from "./hooks/use";
import { montarFluxo, VENDA_FINAL } from "./saga";
import { emailValido, requisitosDaSenha, senhaValida } from "./validators/password";

const CFG = {
  apiBase: "/api",
  versaoTermo: "2026-10-v1",
  regiao: "us-east-1",
  clientes: { clientId: "cli", dominio: "dom-cli" },
  funcionarios: { clientId: "fun", dominio: "dom-fun" },
};

const jwt = (carga: object) => `x.${btoa(JSON.stringify(carga))}.y`;
const simulado = (f: typeof fetch) => jest.fn(f);
const resposta = (corpo: unknown, init: ResponseInit = { status: 200 }) =>
  Promise.resolve(new Response(corpo === null ? null : JSON.stringify(corpo), init));

beforeEach(() => {
  definirConfig(CFG);
  sessionStorage.clear();
  definirContexto({ sessao: () => null, atualizar: salvarSessao });
});

describe("format", () => {
  it("formata moeda, km e digitos", () => {
    expect(moeda("129900.00").replace(/\s/g, " ")).toBe("R$ 129.900,00");
    expect(moeda("abc")).toBe("-");
    expect(km(36000)).toBe("36.000 km");
    expect(apenasDigitos("529.982.247-25")).toBe("52998224725");
    expect(titulo("AGUARDANDO_PAGAMENTO")).toBe("Aguardando pagamento");
  });
  it("rotula enums com acentos e siglas", () => {
    expect(
      [
        "DISPONIVEL",
        "CONCLUIDO",
        "ELETRICO",
        "HIBRIDO",
        "AUTOMATICO",
        "CVT",
        "GNV",
        "DESISTENCIA",
        "NAO_RETIRADO",
        "ADMIN",
        "FLEX",
        "AGUARDANDO_RETIRADA",
      ].map(titulo),
    ).toEqual([
      "Disponível",
      "Concluído",
      "Elétrico",
      "Híbrido",
      "Automático",
      "CVT",
      "GNV",
      "Desistência",
      "Não retirado",
      "Administrador",
      "Flex",
      "Aguardando retirada",
    ]);
  });
  it("descreve pendencias do cadastro em texto", () => {
    expect(pendencias(["rg"])).toBe("RG");
    expect(pendencias(["rg", "email"])).toBe("RG e e-mail confirmado");
    expect(pendencias(["rg", "email", "consentimento"])).toBe(
      "RG, e-mail confirmado e aceite dos termos vigentes",
    );
    expect(pendencias([])).toBe("");
  });
  it("acentua mensagens ASCII da API", () => {
    expect(acentuar("Veiculo nao encontrado.")).toBe("Veículo não encontrado.");
    expect(acentuar("Ja existe funcionario com este e-mail.")).toBe(
      "Já existe funcionário com este e-mail.",
    );
    expect(acentuar("A retirada so pode ser confirmada com a venda PAGA.")).toBe(
      "A retirada só pode ser confirmada com a venda PAGA.",
    );
    expect(acentuar("A documentacao so esta disponivel com a venda PAGA.")).toBe(
      "A documentação só está disponível com a venda PAGA.",
    );
    expect(acentuar("Veiculo nao esta mais disponivel")).toBe("Veículo não está mais disponível");
    expect(acentuar("So e possivel passar de PAGO para CONCLUIDO.")).toBe(
      "Só é possível passar de PAGO para CONCLUIDO.",
    );
    expect(acentuar("EXECUCAO_CONTRATO e obrigatoria")).toBe("EXECUCAO_CONTRATO é obrigatória");
    expect(acentuar("Endereco e RG nao podem ser alterados com compra em andamento.")).toBe(
      "Endereço e RG não podem ser alterados com compra em andamento.",
    );
    expect(acentuar("Para esta venda")).toBe("Para esta venda");
    expect(
      mensagemDe(
        new ErroApi(422, "Erro de validacao", undefined, [
          { campo: "cnh", mensagem: "CNH deve ter 11 digitos" },
        ]),
      ),
    ).toBe("Erro de validação (CNH: CNH deve ter 11 dígitos)");
    expect(
      mensagemDe(
        new ErroApi(422, "Erro de validacao", undefined, [
          { campo: "dataNascimento", mensagem: "o titular deve ter 18 anos ou mais" },
          { campo: "endereco.cep", mensagem: "CEP deve ter 8 digitos" },
          { campo: ".", mensagem: "Corpo invalido" },
          { campo: "outro.campo", mensagem: "x" },
          { campo: "body.nomeCompleto", mensagem: "y" },
        ]),
      ),
    ).toBe(
      "Erro de validação (Data de nascimento: o titular deve ter 18 anos ou mais; CEP: CEP deve ter 8 dígitos; Corpo inválido; outro.campo: x; Nome completo: y)",
    );
  });
  it("formata telefone E.164 para exibicao", () => {
    expect(telefoneFormatado("+5511987654321")).toBe("(11) 98765-4321");
    expect(telefoneFormatado("+555532221234")).toBe("(55) 3222-1234");
    expect(telefoneFormatado("+1 555")).toBe("+1 555");
  });
  it("normaliza telefone para E.164 sem confundir o DDD 55 com o codigo do pais", () => {
    expect(telefoneE164("(11) 98765-4321")).toBe("+5511987654321");
    expect(telefoneE164("(11) 3456-7890")).toBe("+551134567890");
    expect(telefoneE164("(55) 99876-5432")).toBe("+5555998765432");
    expect(telefoneE164("(55) 3222-1234")).toBe("+555532221234");
    expect(telefoneE164("+55 (11) 98765-4321")).toBe("+5511987654321");
    expect(telefoneE164("+55 (55) 99876-5432")).toBe("+5555998765432");
    expect(telefoneE164("5511 9876")).toBeNull();
    expect(telefoneE164("123456789012345")).toBeNull();
  });
  it("formata datas e tempo restante", () => {
    expect(dataHora(null)).toBe("-");
    expect(dataHora("invalida")).toBe("-");
    expect(dataHora("2026-10-19T12:00:00Z")).toMatch(/\d{2}\/\d{2}\/\d{2}/);
    const agora = Date.parse("2026-10-19T00:00:00Z");
    expect(restante("2026-10-19T01:05:00Z", agora)).toBe("1h 05min");
    expect(restante("2026-10-19T00:30:00Z", agora)).toBe("30min");
    expect(restante("2026-10-18T00:00:00Z", agora)).toBe("expirado");
    expect(restante(null)).toBe("-");
  });
});

describe("saga", () => {
  it("marca etapas feitas, atual e pendentes", () => {
    const estados = montarFluxo("AGUARDANDO_PAGAMENTO").map((n) => n.estado);
    expect(estados).toEqual(["feito", "atual", "pendente", "pendente"]);
    expect(montarFluxo("CONCLUIDO").every((n) => n.estado === "feito")).toBe(true);
  });
  it("mostra o desfecho de cancelamento e estorno", () => {
    expect(montarFluxo("CANCELADO").at(-1)).toMatchObject({
      rotulo: "Compra cancelada",
      estado: "falha",
    });
    const estornado = montarFluxo("ESTORNADO");
    expect(estornado).toHaveLength(4);
    expect(estornado.at(-1)?.estado).toBe("falha");
  });
  it("identifica status finais", () => {
    expect(VENDA_FINAL("CONCLUIDO")).toBe(true);
    expect(VENDA_FINAL("PAGO")).toBe(false);
  });
});

describe("config", () => {
  it("carrega e expoe a configuracao", async () => {
    definirConfig(null);
    expect(() => config()).toThrow();
    await carregarConfig(() => resposta(CFG));
    expect(config().apiBase).toBe("/api");
    await expect(carregarConfig(() => resposta({}, { status: 500 }))).rejects.toThrow();
  });
});

describe("auth", () => {
  it("renova a sessao pelo refresh token e falha sem ele", async () => {
    const base: Sessao = { accessToken: "a", refreshToken: "r", expiraEm: 0, pool: "clientes" };
    const nova = await renovar(base, () =>
      resposta({ AuthenticationResult: { AccessToken: "novo", ExpiresIn: 60 } }),
    );
    expect(nova).toMatchObject({ accessToken: "novo", refreshToken: "r" });
    expect(lerSessao()?.accessToken).toBe("novo");
    expect(await renovar({ ...base, refreshToken: undefined })).toBeNull();
    expect(
      await renovar(base, () => resposta({ __type: "NotAuthorizedException" }, { status: 400 })),
    ).toBeNull();
  });

  it("sai limpando a sessao e revogando o refresh token", async () => {
    salvarSessao({ accessToken: "a", refreshToken: "r", expiraEm: 1, pool: "funcionarios" });
    const buscar = jest.fn(() => resposta({}));
    Object.assign(globalThis, { fetch: buscar });
    await sair(lerSessao());
    expect(lerSessao()).toBeNull();
    expect(JSON.stringify(buscar.mock.calls[0])).toContain("RevokeToken");
  });

  it("deriva o papel dos claims", () => {
    expect(claims("lixo")).toEqual({});
    expect(papelDe(null)).toBeNull();
    expect(papelDe({ accessToken: "a", expiraEm: 1, pool: "clientes" })).toBe("cliente");
    expect(
      papelDe({
        accessToken: jwt({ "cognito:groups": ["admin"] }),
        expiraEm: 1,
        pool: "funcionarios",
      }),
    ).toBe("admin");
    expect(
      papelDe({
        accessToken: jwt({ "cognito:groups": ["vendedor"] }),
        expiraEm: 1,
        pool: "funcionarios",
      }),
    ).toBe("vendedor");
  });
});

describe("senha", () => {
  it("aplica a politica de 12+ caracteres com 4 classes", () => {
    expect(senhaValida("Abcdef123!xy")).toBe(true);
    expect(senhaValida("abcdef123!xy")).toBe(false);
    expect(senhaValida("Abc1!")).toBe(false);
    expect(
      requisitosDaSenha("a")
        .filter((r) => r.ok)
        .map((r) => r.id),
    ).toEqual(["minuscula"]);
    expect(emailValido("a@b.co")).toBe(true);
    expect(emailValido("a@b")).toBe(false);
  });
});

describe("cognito", () => {
  const chamadas = (b: jest.Mock) =>
    b.mock.calls.map(([, init]) => ({
      alvo: (init.headers as Record<string, string>)["X-Amz-Target"]?.split(".")[1],
      corpo: JSON.parse(init.body as string),
    }));

  it("entra com senha e devolve a sessao", async () => {
    const buscar = simulado(() =>
      resposta({
        AuthenticationResult: { AccessToken: "tok", RefreshToken: "ref", ExpiresIn: 3600 },
      }),
    );
    const r = await cognito.entrar("clientes", " a@b.com ", "Senha#12345x", buscar);
    expect(r).toMatchObject({
      sessao: { accessToken: "tok", refreshToken: "ref", pool: "clientes" },
    });
    expect(chamadas(buscar)[0]).toMatchObject({
      alvo: "InitiateAuth",
      corpo: {
        AuthFlow: "USER_PASSWORD_AUTH",
        ClientId: "cli",
        AuthParameters: { USERNAME: "a@b.com" },
      },
    });
    expect(buscar.mock.calls[0]?.[0]).toBe("https://cognito-idp.us-east-1.amazonaws.com/");
  });

  it("devolve os desafios de nova senha e MFA com o usuario do desafio", async () => {
    const desafio = (nome: string) =>
      jest.fn(() =>
        resposta({
          ChallengeName: nome,
          Session: "s1",
          ChallengeParameters: { USER_ID_FOR_SRP: "uuid-1" },
        }),
      );
    expect(
      await cognito.entrar("funcionarios", "f@x.com", "x", desafio("NEW_PASSWORD_REQUIRED")),
    ).toEqual({ desafio: { tipo: "novaSenha", sessao: "s1", usuario: "uuid-1" } });
    expect(
      await cognito.entrar("funcionarios", "f@x.com", "x", desafio("MFA_SETUP")),
    ).toMatchObject({ desafio: { tipo: "mfaSetup" } });
    expect(
      await cognito.entrar("funcionarios", "f@x.com", "x", desafio("SOFTWARE_TOKEN_MFA")),
    ).toMatchObject({ desafio: { tipo: "mfaCodigo" } });
    await expect(cognito.entrar("funcionarios", "f@x.com", "x", desafio("CUSTOM"))).rejects.toThrow(
      /não é suportado/,
    );
  });

  it("responde aos desafios e conclui o MFA_SETUP", async () => {
    const d = { tipo: "mfaSetup" as const, sessao: "s1", usuario: "uuid-1" };
    const buscar = jest
      .fn()
      .mockReturnValueOnce(resposta({ SecretCode: "SEGREDO", Session: "s2" }))
      .mockReturnValueOnce(resposta({ Status: "SUCCESS", Session: "s3" }))
      .mockReturnValueOnce(resposta({ AuthenticationResult: { AccessToken: "t", ExpiresIn: 60 } }));
    expect(await cognito.iniciarMfa(d, buscar)).toEqual({
      segredo: "SEGREDO",
      sessao: "s2",
    });
    const fim = await cognito.concluirMfa("funcionarios", d, "s2", " 123456 ", buscar);
    expect(fim).toMatchObject({ sessao: { accessToken: "t", pool: "funcionarios" } });
    expect(chamadas(buscar).map((c) => c.alvo)).toEqual([
      "AssociateSoftwareToken",
      "VerifySoftwareToken",
      "RespondToAuthChallenge",
    ]);
    expect(chamadas(buscar)[1]?.corpo).toMatchObject({ Session: "s2", UserCode: "123456" });
    expect(chamadas(buscar)[2]?.corpo).toMatchObject({
      ChallengeName: "MFA_SETUP",
      Session: "s3",
      ChallengeResponses: { USERNAME: "uuid-1" },
    });
  });

  it("envia nova senha e codigo MFA como respostas de desafio", async () => {
    const buscar = jest.fn(() =>
      resposta({ AuthenticationResult: { AccessToken: "t", ExpiresIn: 60 } }),
    );
    await cognito.responderNovaSenha(
      "funcionarios",
      { tipo: "novaSenha", sessao: "s", usuario: "u" },
      "Nova#Senha123",
      buscar,
    );
    await cognito.responderMfa(
      "funcionarios",
      { tipo: "mfaCodigo", sessao: "s", usuario: "u" },
      "654321",
      buscar,
    );
    expect(chamadas(buscar)[0]?.corpo).toMatchObject({
      ChallengeName: "NEW_PASSWORD_REQUIRED",
      ChallengeResponses: { NEW_PASSWORD: "Nova#Senha123" },
    });
    expect(chamadas(buscar)[1]?.corpo).toMatchObject({
      ChallengeName: "SOFTWARE_TOKEN_MFA",
      ChallengeResponses: { SOFTWARE_TOKEN_MFA_CODE: "654321" },
    });
  });

  it("cadastro, confirmacao e recuperacao de senha", async () => {
    const buscar = jest.fn(() => resposta({}));
    await cognito.cadastrar("a@b.com", "Senha#12345x", buscar);
    await cognito.confirmarCadastro("a@b.com", "123456", buscar);
    await cognito.reenviarCodigo("a@b.com", buscar);
    await cognito.esqueciSenha("clientes", "a@b.com", buscar);
    await cognito.redefinirSenha("clientes", "a@b.com", "123456", "Nova#Senha123", buscar);
    expect(chamadas(buscar).map((c) => c.alvo)).toEqual([
      "SignUp",
      "ConfirmSignUp",
      "ResendConfirmationCode",
      "ForgotPassword",
      "ConfirmForgotPassword",
    ]);
    expect(chamadas(buscar)[0]?.corpo).toMatchObject({
      UserAttributes: [{ Name: "email", Value: "a@b.com" }],
    });
  });

  it("traduz erros do Cognito", async () => {
    const falha = (tipo: string) =>
      jest.fn(() => resposta({ __type: `com.amazonaws#${tipo}`, message: "x" }, { status: 400 }));
    await expect(
      cognito.entrar("clientes", "a@b.com", "x", falha("NotAuthorizedException")),
    ).rejects.toMatchObject({
      codigo: "NotAuthorizedException",
      message: "E-mail ou senha incorretos.",
    });
    await expect(
      cognito.cadastrar("a@b.com", "x", falha("UsernameExistsException")),
    ).rejects.toThrow(/Já existe/);
    await expect(cognito.cadastrar("a@b.com", "x", falha("Desconhecido"))).rejects.toThrow("x");
  });

  it("repete a chamada enquanto o Cognito ainda nao propagou o fluxo habilitado", async () => {
    const buscar = jest
      .fn()
      .mockReturnValueOnce(
        resposta(
          {
            __type: "InvalidParameterException",
            message: "USER_PASSWORD_AUTH flow not enabled for this client",
          },
          { status: 400 },
        ),
      )
      .mockReturnValueOnce(resposta({ AuthenticationResult: { AccessToken: "t", ExpiresIn: 60 } }));
    const r = await cognito.entrar("clientes", "a@b.com", "x", buscar);
    expect(r).toMatchObject({ sessao: { accessToken: "t" } });
    expect(buscar).toHaveBeenCalledTimes(2);
  });

  it("revogar nao lanca erro mesmo se o Cognito falhar", async () => {
    await expect(
      cognito.revogar(
        "clientes",
        "r",
        jest.fn(() => resposta({}, { status: 500 })),
      ),
    ).resolves.toBeUndefined();
  });
});

describe("api", () => {
  it("monta URL ignorando parametros vazios", () => {
    expect(montarUrl("/veiculos", { limit: 5, marca: "", modelo: undefined })).toBe(
      "/api/veiculos?limit=5",
    );
  });

  it("envia Authorization, If-Match e devolve ETag", async () => {
    const buscar = simulado(() => resposta({ ok: 1 }, { status: 200, headers: { ETag: '"v2"' } }));
    definirContexto({
      sessao: () => ({ accessToken: "tok", expiraEm: Date.now() + 600_000, pool: "clientes" }),
      atualizar: jest.fn(),
      buscar: buscar,
    });
    const r = await chamar("/clientes/meu-perfil", {
      metodo: "PATCH",
      corpo: { a: 1 },
      ifMatch: '"v1"',
    });
    expect(r).toEqual({ dados: { ok: 1 }, etag: '"v2"' });
    const init = buscar.mock.calls[0]?.[1];
    expect(init?.headers).toMatchObject({
      Authorization: "Bearer tok",
      "If-Match": '"v1"',
      "Content-Type": "application/json",
    });
  });

  it("converte problem+json em ErroApi com Retry-After", async () => {
    const buscar = () =>
      resposta(
        { title: "Indisponivel", detail: "tente depois", errors: [{ campo: "x", mensagem: "y" }] },
        { status: 503, headers: { "Retry-After": "7" } },
      );
    definirContexto({ sessao: () => null, atualizar: jest.fn(), buscar: buscar });
    const erro = await chamar("/vendas").catch((e) => e);
    expect(erro).toBeInstanceOf(ErroApi);
    expect(erro).toMatchObject({ status: 503, retryAfter: 7, detalhe: "tente depois" });
  });

  it("tenta renovar o token em 401 e repete a chamada", async () => {
    const atualizar = jest.fn();
    const chamadas: string[] = [];
    const buscar = jest.fn((url: RequestInfo | URL, init?: RequestInit) => {
      if (String(url).includes("cognito-idp"))
        return resposta({ AuthenticationResult: { AccessToken: "novo", ExpiresIn: 3600 } });
      chamadas.push(String(((init?.headers ?? {}) as Record<string, string>).Authorization));
      return chamadas.length === 1
        ? resposta({ title: "Nao autorizado" }, { status: 401 })
        : resposta({ ok: true });
    });
    definirContexto({
      sessao: () => ({
        accessToken: "velho",
        refreshToken: "r",
        expiraEm: Date.now() + 600_000,
        pool: "clientes",
      }),
      atualizar,
      buscar: buscar,
    });
    const r = await chamar<{ ok: boolean }>("/vendas");
    expect(r.dados.ok).toBe(true);
    expect(chamadas).toEqual(["Bearer velho", "Bearer novo"]);
    expect(atualizar).toHaveBeenCalled();
  });

  it("falha de rede e 5xx sem corpo viram mensagens para o usuario", async () => {
    definirContexto({
      sessao: () => null,
      atualizar: jest.fn(),
      buscar: jest.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    });
    await expect(chamar("/veiculos")).rejects.toMatchObject({
      status: 0,
      detalhe: expect.stringMatching(/Não foi possível conectar ao servidor/),
    });
    definirContexto({
      sessao: () => null,
      atualizar: jest.fn(),
      buscar: () => resposta("<html>Bad Gateway</html>", { status: 502 }),
    });
    const erro = await chamar("/veiculos").catch((e) => e);
    expect(mensagemDe(erro)).toBe(
      "O serviço está indisponível no momento. Tente de novo em instantes.",
    );
    // 5xx com problem+json continua mostrando o detalhe da API.
    definirContexto({
      sessao: () => null,
      atualizar: jest.fn(),
      buscar: () =>
        resposta(
          { title: "Falha", detail: "Gateway de pagamento temporariamente indisponivel." },
          { status: 503 },
        ),
    });
    expect(mensagemDe(await chamar("/vendas").catch((e) => e))).toBe(
      "Gateway de pagamento temporariamente indisponível.",
    );
  });

  it("login sem rede ou com o Cognito fora do ar explica o problema", async () => {
    await expect(
      cognito.entrar("clientes", "a@b.c", "x", () =>
        Promise.reject(new TypeError("Failed to fetch")),
      ),
    ).rejects.toThrow("Não foi possível conectar");
    await expect(
      cognito.entrar("clientes", "a@b.c", "x", () => resposta("Bad Gateway", { status: 502 })),
    ).rejects.toThrow("serviço de login está indisponível");
  });

  it("falha com 401 quando o token expirou e nao renova", async () => {
    definirContexto({
      sessao: () => ({ accessToken: "a", expiraEm: 0, pool: "clientes" }),
      atualizar: jest.fn(),
      buscar: jest.fn(),
    });
    await expect(chamar("/vendas")).rejects.toMatchObject({ status: 401 });
    // A tela de login explica por que a pessoa voltou para ela.
    expect(JSON.parse(sessionStorage.getItem("revenda.aviso-login") ?? "null")).toMatch(
      /sessão expirou/,
    );
  });
});

describe("transacaoDoPix", () => {
  const { transacaoDoPix } = require("./pix") as typeof import("./pix");
  it("extrai o id da cobranca do payload Pix do gateway simulado", () => {
    expect(
      transacaoDoPix("00020126580014BR.GOV.BCB.PIX0136tx_0123456789abcdef5204000053039865406"),
    ).toBe("tx_0123456789abcdef");
  });
  it("devolve null para codigo ausente ou de outro formato", () => {
    expect(transacaoDoPix(null)).toBeNull();
    expect(transacaoDoPix("00020126...")).toBeNull();
  });
});

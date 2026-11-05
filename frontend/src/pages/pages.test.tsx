import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { Protegida, SoAnonimo } from "../App";
import { AuthProvider } from "../context/AuthContext";
import { ErroApi } from "../lib/api";
import { definirConfig } from "../lib/config";
import { Catalogo } from "./Catalog";
import { Painel } from "./Dashboard";
import { Home } from "./Home";
import { ConfiguracaoInicial } from "./InitialSetup";
import { Perfil } from "./Profile";
import { CompraDetalhe } from "./PurchaseDetail";
import { Compras } from "./Purchases";
import { Entrar } from "./SignIn";
import { VeiculoDetalhe } from "./VehicleDetail";

jest.mock("../lib/api", () => {
  const real = jest.requireActual("../lib/api");
  return {
    ...real,
    obter: jest.fn(),
    chamar: jest.fn(),
    enviarJson: jest.fn(),
    remover: jest.fn(),
  };
});
const api = require("../lib/api") as Record<
  "obter" | "chamar" | "enviarJson" | "remover",
  jest.Mock
>;

const v = (id: string, extra = {}) => ({
  id,
  marca: "Fiat",
  modelo: `Modelo ${id}`,
  anoFabricacao: 2020,
  anoModelo: 2021,
  cor: "Prata",
  preco: "42900.00",
  quilometragem: 58000,
  combustivel: "FLEX",
  cambio: "MANUAL",
  status: "DISPONIVEL",
  ...extra,
});
const venda = (status: string, extra = {}) => ({
  id: "venda1",
  status,
  veiculo: { marca: "Fiat", modelo: "Mobi" },
  precoNegociado: "42900.00",
  criadoEm: "2026-10-19T12:00:00Z",
  pagamento: null,
  ...extra,
});
const ok = (dados: unknown, etag: string | null = null) => Promise.resolve({ dados, etag });

function montar(
  caminho: string,
  rotas: { path: string; el: React.ReactNode }[],
  sessao?: "clientes" | "funcionarios",
) {
  if (sessao)
    sessionStorage.setItem(
      "revenda.sessao",
      JSON.stringify({ accessToken: "a.e30=.b", expiraEm: Date.now() + 1e6, pool: sessao }),
    );
  return render(
    <MemoryRouter initialEntries={[caminho]}>
      <AuthProvider>
        <Routes>
          {rotas.map((r) => (
            <Route key={r.path} path={r.path} element={r.el} />
          ))}
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  jest.resetAllMocks();
  sessionStorage.clear();
  definirConfig({
    apiBase: "/api",
    versaoTermo: "2026-10-v1",
    regiao: "us-east-1",
    clientes: { clientId: "c", dominio: "d" },
    funcionarios: { clientId: "f", dominio: "e" },
  });
});

const lote = (n: number) =>
  Array.from({ length: n }, (_, k) =>
    v(String(k + 1), {
      marca: k % 2 ? "Honda" : "Fiat",
      preco: String(30000 + k * 1000),
      versao: 3,
    }),
  );

describe("Home e catalogo", () => {
  it("Home mostra busca rapida e destaques, sem CTA de cadastro no corpo", async () => {
    api.obter.mockReturnValue(ok({ itens: lote(4) }));
    montar("/", [{ path: "/", el: <Home /> }]);
    expect((await screen.findAllByText(/Modelo 1/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Explorar veículos/ })).toHaveAttribute(
      "href",
      "/veiculos",
    );
    expect(screen.getByRole("button", { name: /Buscar/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Marca")).toBeInTheDocument();
    expect(screen.queryByText(/Entrar ou cadastrar/)).not.toBeInTheDocument();
    expect(screen.getByText(/Como funciona/, { selector: "h2" })).toBeInTheDocument();
  });

  it("Catalogo pagina de 10 em 10 e filtra por listas", async () => {
    api.obter.mockReturnValue(ok({ itens: lote(23) }));
    montar("/veiculos", [{ path: "/veiculos", el: <Catalogo /> }]);
    expect(await screen.findByText("Mostrando 1–10 de 23")).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(10);
    await userEvent.click(screen.getByRole("button", { name: "Página 3" }));
    expect(await screen.findByText("Mostrando 21–23 de 23")).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(3);
    await userEvent.selectOptions(screen.getByLabelText("Marca"), "Honda");
    expect(await screen.findByText(/de 11$/)).toBeInTheDocument();
    expect(screen.getByLabelText("Modelo")).not.toBeDisabled();
  });

  it("Catalogo recusa faixas invertidas e ordena por maior preco", async () => {
    api.obter.mockReturnValue(ok({ itens: lote(12) }));
    montar("/veiculos", [{ path: "/veiculos", el: <Catalogo /> }]);
    await screen.findByText("Mostrando 1–10 de 12");
    await userEvent.selectOptions(screen.getByLabelText("Preço a partir de"), "40000");
    await userEvent.selectOptions(screen.getByLabelText("Preço até"), "10000");
    expect(await screen.findByRole("alert")).toHaveTextContent("preço mínimo não pode ser maior");
    await userEvent.click(screen.getByRole("button", { name: /Limpar filtros/ }));
    await userEvent.selectOptions(screen.getByLabelText("Ordenar por"), "preco_desc");
    expect(screen.getAllByRole("article")[0]).toHaveTextContent("Modelo 12");
  });

  it("Catalogo busca por modelo sem acento e permite remover filtro ativo", async () => {
    api.obter.mockReturnValue(ok({ itens: lote(23) }));
    montar("/veiculos", [{ path: "/veiculos", el: <Catalogo /> }]);
    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(10));
    await userEvent.type(screen.getByRole("searchbox", { name: "Modelo ou marca" }), "MODELO 2");
    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(5));
    expect(screen.getAllByRole("article")[0]).toHaveTextContent("Modelo 2");
    await userEvent.click(screen.getByRole("button", { name: "Remover filtro Busca: MODELO 2" }));
    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(10));
  });

  it("Catalogo mostra erro da API", async () => {
    api.obter.mockRejectedValueOnce(new ErroApi(503, "Indisponivel", "tente depois", [], 5));
    montar("/veiculos", [{ path: "/veiculos", el: <Catalogo /> }]);
    expect(await screen.findByRole("alert")).toHaveTextContent("Tente de novo em 5s");
  });
});

describe("compra", () => {
  const clienteOk = { id: "c", cadastroCompleto: true, camposPendentes: [] };
  const rotas = (cliente: unknown) => (caminho: string) =>
    caminho === "/clientes/meu-perfil"
      ? cliente instanceof Error
        ? Promise.reject(cliente)
        : ok(cliente)
      : ok(v("9"));

  it("VeiculoDetalhe reserva como cliente e vai para a compra", async () => {
    api.obter.mockImplementation(rotas(clienteOk));
    api.enviarJson.mockReturnValue(ok({ id: "venda9" }));
    montar(
      "/veiculos/9",
      [
        { path: "/veiculos/:id", el: <VeiculoDetalhe /> },
        { path: "/compras/:id", el: <p>tela da compra</p> },
      ],
      "clientes",
    );
    await userEvent.click(await screen.findByRole("button", { name: "Reservar e comprar" }));
    // Reservar exige confirmacao: o primeiro clique so abre o resumo.
    expect(api.enviarJson).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: "Confirmar reserva" })).toHaveTextContent(
      "Fiat Modelo 9",
    );
    await userEvent.click(screen.getByRole("button", { name: "Confirmar reserva" }));
    expect(api.enviarJson).toHaveBeenCalledWith("/vendas", { veiculoId: "9" });
    expect(await screen.findByText("tela da compra")).toBeInTheDocument();
  });

  it("VeiculoDetalhe anonimo e indisponivel", async () => {
    api.obter.mockReturnValue(ok(v("9", { status: "RESERVADO" })));
    montar("/veiculos/9", [{ path: "/veiculos/:id", el: <VeiculoDetalhe /> }]);
    expect(await screen.findByText(/não está disponível/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Entrar para comprar" })).not.toBeInTheDocument();
  });

  it("VeiculoDetalhe mostra falha da reserva", async () => {
    api.obter.mockImplementation(rotas(clienteOk));
    api.enviarJson.mockRejectedValue(new ErroApi(409, "Conflito", "Veiculo ja reservado"));
    montar("/veiculos/9", [{ path: "/veiculos/:id", el: <VeiculoDetalhe /> }], "clientes");
    await userEvent.click(await screen.findByRole("button", { name: "Reservar e comprar" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmar reserva" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Veículo já reservado");
    expect(screen.getByRole("button", { name: "Reservar e comprar" })).toBeInTheDocument();
  });

  it("VeiculoDetalhe sem cadastro pede o cadastro em vez de falhar ao reservar", async () => {
    api.obter.mockImplementation(
      rotas(
        new ErroApi(
          403,
          "Cadastro de cliente inexistente",
          "Faca o cadastro",
          [],
          undefined,
          "perfil-cliente-inexistente",
        ),
      ),
    );
    montar("/veiculos/9", [{ path: "/veiculos/:id", el: <VeiculoDetalhe /> }], "clientes");
    expect(
      await screen.findByText("Para reservar, primeiro faça seu cadastro."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Completar cadastro" })).toHaveAttribute(
      "href",
      "/perfil",
    );
    expect(screen.queryByRole("button", { name: "Reservar e comprar" })).not.toBeInTheDocument();
  });

  it("VeiculoDetalhe com cadastro incompleto lista as pendencias", async () => {
    api.obter.mockImplementation(
      rotas({ id: "c", cadastroCompleto: false, camposPendentes: ["rg"] }),
    );
    montar("/veiculos/9", [{ path: "/veiculos/:id", el: <VeiculoDetalhe /> }], "clientes");
    expect(await screen.findByText("Para reservar, falta informar: RG.")).toBeInTheDocument();
  });

  it("Compras lista o historico", async () => {
    api.obter.mockReturnValue(ok({ itens: [venda("PAGO")] }));
    montar("/compras", [{ path: "/compras", el: <Compras /> }], "clientes");
    expect(await screen.findByText("Mobi")).toBeInTheDocument();
    expect(screen.getByText("Pago")).toBeInTheDocument();
  });

  it("CompraDetalhe mostra o Pix, copia o codigo e permite desistir", async () => {
    const pagamento = {
      id: "p",
      metodo: "PIX",
      status: "PENDENTE",
      pixCopiaECola: "000201PIX",
      valor: "42900.00",
      expiraEm: new Date(Date.now() + 3.6e6).toISOString(),
    };
    api.obter.mockReturnValue(
      ok(
        venda("AGUARDANDO_PAGAMENTO", {
          pagamento,
          historico: [{ para: "CRIADO", ocorridoEm: "2026-10-19T12:00:00Z", ator: "CLIENTE" }],
        }),
      ),
    );
    api.chamar.mockReturnValue(ok({}));
    const escrever = jest.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText: escrever } });
    window.confirm = jest.fn(() => true);
    montar("/compras/venda1", [{ path: "/compras/:id", el: <CompraDetalhe /> }], "clientes");
    expect(await screen.findByLabelText("Código Pix copia e cola")).toHaveValue("000201PIX");
    await userEvent.click(screen.getByRole("button", { name: "Copiar código" }));
    expect(escrever).toHaveBeenCalledWith("000201PIX");
    expect(await screen.findByText("Copiado ✓")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Desistir da compra" }));
    expect(api.chamar).toHaveBeenCalledWith("/vendas/venda1/desistencia", { metodo: "POST" });
    expect(await screen.findByText(/Desistência em processamento/)).toBeInTheDocument();
  });

  it("CompraDetalhe oferece próximo passo ao encerrar uma compra", async () => {
    api.obter.mockReturnValue(
      ok(venda("CANCELADO", { motivoCancelamento: "DESISTENCIA_CLIENTE", historico: [] })),
    );
    montar("/compras/venda1", [{ path: "/compras/:id", el: <CompraDetalhe /> }], "clientes");
    expect(await screen.findByRole("link", { name: "Ver outros veículos" })).toHaveAttribute(
      "href",
      "/veiculos",
    );
    expect(screen.getByText("Compra encerrada: Cancelado.")).toBeInTheDocument();
  });
});

describe("perfil e painel", () => {
  it("Perfil sem cadastro: obrigatorios com *, opcionais sinalizados, validacoes e envio", async () => {
    const cliente = {
      id: "c",
      nomeCompleto: "Ana",
      cpf: "***.***.***-25",
      email: "a@b.c",
      telefone: "+5511",
      endereco: { cep: "1", logradouro: "R", numero: "1", bairro: "B", cidade: "C", uf: "SP" },
      rg: null,
      cnh: null,
      cadastroCompleto: false,
      camposPendentes: ["rg"],
      status: "ATIVO",
      dataNascimento: "2000-01-01",
    };
    api.obter
      .mockRejectedValueOnce(
        new ErroApi(
          403,
          "Cadastro de cliente inexistente",
          "Faca o cadastro",
          [],
          undefined,
          "perfil-cliente-inexistente",
        ),
      )
      .mockReturnValue(ok(cliente));
    api.enviarJson.mockReturnValue(ok({}));
    montar("/perfil", [{ path: "/perfil", el: <Perfil /> }], "clientes");
    const nome = await screen.findByLabelText(/Nome completo/);
    // A etapa inicial mostra somente os campos pessoais obrigatórios.
    for (const r of [/Nome completo/, /^CPF/, /Data de nascimento/, /Telefone com DDD/])
      expect(screen.getByLabelText(r)).toBeRequired();
    await userEvent.type(nome, "Ana Souza");
    await userEvent.type(screen.getByLabelText(/^CPF/), "111.111.111-11");
    await userEvent.type(screen.getByLabelText(/Data de nascimento/), "2000-01-01");
    await userEvent.type(screen.getByLabelText(/Telefone com DDD/), "(55) 99876-5432");
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("CPF inválido");
    await userEvent.clear(screen.getByLabelText(/^CPF/));
    await userEvent.type(screen.getByLabelText(/^CPF/), "529.982.247-25");
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));
    for (const r of [/^CEP/, /Logradouro/, /^Número \*$/, /Bairro/, /Cidade/, /Estado \(UF\)/])
      expect(screen.getByLabelText(r)).toBeRequired();
    expect(screen.getByLabelText(/Complemento/)).not.toBeRequired();
    expect(screen.getByText(/Complemento/, { selector: "label" })).toHaveTextContent("(opcional)");
    await userEvent.type(screen.getByLabelText(/^CEP/), "01310-100");
    await userEvent.type(screen.getByLabelText(/Logradouro/), "Av Paulista");
    await userEvent.type(screen.getByLabelText(/^Número \*$/), "1");
    await userEvent.type(screen.getByLabelText(/Bairro/), "Centro");
    await userEvent.type(screen.getByLabelText(/Cidade/), "Sao Paulo");
    await userEvent.selectOptions(screen.getByLabelText(/Estado \(UF\)/), "SP");
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));
    for (const r of [/Número do RG/, /Órgão emissor/, /UF do RG/]) {
      expect(screen.getByLabelText(r)).not.toBeRequired();
      expect(screen.getByText(r, { selector: "label" })).toHaveTextContent("(opcional)");
    }
    await userEvent.click(screen.getByRole("checkbox", { name: /Aceito os termos/ }));
    await userEvent.type(screen.getByLabelText(/Número do RG/), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Concluir cadastro" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "preencha número, órgão emissor e UF do RG",
    );
    await userEvent.clear(screen.getByLabelText(/Número do RG/));
    await userEvent.click(screen.getByRole("button", { name: "Concluir cadastro" }));
    await waitFor(() => expect(api.enviarJson).toHaveBeenCalled());
    expect(api.enviarJson.mock.calls[0][1]).toMatchObject({
      telefone: "+5555998765432",
      endereco: { uf: "SP", complemento: null },
      consentimento: { versaoTermo: "2026-10-v1", finalidades: ["EXECUCAO_CONTRATO"] },
      rg: null,
    });
    expect(await screen.findByText("Para comprar, falta informar: RG.")).toBeInTheDocument();
    expect(screen.getByText(/Cadastro concluído/)).toBeInTheDocument();
  });

  it("Perfil permite informar RG e CNH depois (PATCH com If-Match)", async () => {
    const cliente = {
      id: "c",
      nomeCompleto: "Ana",
      cpf: "***",
      email: "a@b.c",
      telefone: "+5511",
      endereco: { cep: "1", logradouro: "R", numero: "1", bairro: "B", cidade: "C", uf: "SP" },
      rg: null,
      cnh: null,
      cadastroCompleto: false,
      camposPendentes: ["rg"],
      status: "ATIVO",
      dataNascimento: "2000-01-01",
    };
    api.obter.mockReturnValue(ok(cliente, '"v2"'));
    api.chamar.mockReturnValue(ok({}));
    montar("/perfil", [{ path: "/perfil", el: <Perfil /> }], "clientes");
    await userEvent.type(await screen.findByLabelText(/Número do RG/), "12.345.678-9");
    await userEvent.type(screen.getByLabelText(/Órgão emissor/), "SSP");
    await userEvent.selectOptions(screen.getByLabelText(/UF do RG/), "SP");
    await userEvent.click(screen.getByRole("button", { name: "Salvar documentos" }));
    expect(await screen.findByText("Documentos salvos.")).toBeInTheDocument();
    expect(api.chamar).toHaveBeenCalledWith("/clientes/meu-perfil", {
      metodo: "PATCH",
      corpo: { rg: { numero: "12.345.678-9", orgaoEmissor: "SSP", uf: "SP" } },
      ifMatch: '"v2"',
    });
  });

  it("Painel de vendedor lista veiculos paginados e abre Vendas com status PAGO", async () => {
    api.obter.mockImplementation((caminho: string) =>
      ok({ itens: caminho === "/vendas" ? [venda("PAGO")] : lote(12) }),
    );
    montar("/painel", [{ path: "/painel", el: <Painel /> }], "funcionarios");
    expect(await screen.findAllByText("Fiat Modelo 1")).toHaveLength(2); // cartão mobile + tabela desktop
    expect(screen.getAllByRole("row")).toHaveLength(11); // cabecalho + 10
    expect(screen.queryByRole("tab", { name: "Equipe" })).not.toBeInTheDocument();
    api.chamar.mockReturnValue(ok({}));
    expect(screen.getByLabelText("Status")).toHaveValue("DISPONIVEL");
    expect(screen.queryByRole("option", { name: "Todos" })).not.toBeInTheDocument();
    window.confirm = jest.fn(() => true);
    await userEvent.click(screen.getByRole("button", { name: "Inativar Fiat Modelo 1" }));
    expect(window.confirm).toHaveBeenCalled();
    expect(api.chamar).toHaveBeenCalledWith("/veiculos/1/inativacao", {
      metodo: "POST",
      ifMatch: '"v3"',
    });
    expect(
      await screen.findByText("Fiat Modelo 1 inativado: saiu do catálogo."),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Vendas" }));
    expect(
      await screen.findByRole("button", { name: "Registrar retirada de Fiat Mobi" }),
    ).toBeInTheDocument();
    expect(api.obter).toHaveBeenCalledWith(
      "/vendas",
      expect.objectContaining({ status: "PAGO" }),
      true,
    );
    await userEvent.click(screen.getByRole("button", { name: "Registrar retirada de Fiat Mobi" }));
    api.enviarJson.mockReturnValue(ok({}));
    await userEvent.selectOptions(screen.getByLabelText("Documento apresentado"), "CNH");
    await userEvent.type(screen.getByLabelText("Protocolo da documentação"), "PROTO-1");
    await userEvent.click(screen.getByRole("button", { name: "Confirmar retirada" }));
    expect(await screen.findByText(/a venda será concluída em instantes/)).toBeInTheDocument();
    expect(api.enviarJson).toHaveBeenCalledWith(
      "/vendas/venda1/retirada",
      expect.objectContaining({ conferencia: { documentoApresentado: "CNH" } }),
    );
    // Enquanto a saga conclui, a venda nao oferece a retirada de novo.
    expect(screen.queryByRole("button", { name: /Registrar retirada de/ })).not.toBeInTheDocument();
    expect(screen.getByText("Retirada registrada")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Status da venda"), "CONCLUIDO");
    expect(screen.queryByText(/a venda será concluída em instantes/)).not.toBeInTheDocument();
  });

  it("Painel de admin lista a equipe e convida funcionario", async () => {
    const funcionario = {
      id: "f1",
      nome: "Maria",
      email: "m@x.com",
      grupos: ["admin"],
      ativo: true,
      mfaConfigurado: true,
    };
    api.obter.mockImplementation((caminho: string) =>
      ok({ itens: caminho === "/administracao/funcionarios" ? [funcionario] : lote(2) }),
    );
    api.enviarJson.mockReturnValue(ok({}));
    const token = `x.${btoa(JSON.stringify({ "cognito:groups": ["admin"] }))}.y`;
    sessionStorage.setItem(
      "revenda.sessao",
      JSON.stringify({ accessToken: token, expiraEm: Date.now() + 1e6, pool: "funcionarios" }),
    );
    montar("/painel", [{ path: "/painel", el: <Painel /> }]);
    await userEvent.click(await screen.findByRole("tab", { name: "Equipe" }));
    expect(await screen.findByText("Maria")).toBeInTheDocument();
    expect(screen.getByText("MFA ativo")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Nome"), "Joao Silva");
    await userEvent.type(screen.getByLabelText("E-mail"), "joao@x.com");
    // Duplo clique com a resposta ainda pendente envia um convite so (antes o segundo dava "ja existe" logo apos o sucesso).
    let responder: (v: unknown) => void = () => undefined;
    api.enviarJson.mockReturnValueOnce(
      new Promise((r) => {
        responder = r;
      }),
    );
    await userEvent.dblClick(screen.getByRole("button", { name: "Convidar" }));
    expect(api.enviarJson).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Enviando…" })).toBeDisabled();
    await act(async () => responder({ dados: {}, etag: null }));
    expect(api.enviarJson).toHaveBeenCalledWith("/administracao/funcionarios", {
      nome: "Joao Silva",
      email: "joao@x.com",
      grupo: "vendedor",
    });
    expect(await screen.findByText("Convite enviado para joao@x.com.")).toBeInTheDocument();
  });
});

describe("correcoes do teste E2E", () => {
  it("Catalogo: a URL manda nos filtros e valores invalidos sao descartados (C1, C2, C4)", async () => {
    api.obter.mockReturnValue(ok({ itens: lote(12) }));
    montar("/veiculos?marca=Honda&precoMin=45000&cor=Inexistente&ordem=xyz", [
      { path: "/veiculos", el: <Catalogo /> },
    ]);
    expect(await screen.findByText("Mostrando 1–6 de 6")).toBeInTheDocument();
    expect(screen.getByLabelText("Marca")).toHaveValue("Honda");
    expect(screen.getByLabelText("Preço a partir de")).toHaveValue("");
    expect(screen.getByLabelText("Cor")).toHaveValue("");
    expect(screen.getByLabelText("Ordenar por")).toHaveValue("preco_asc");
    await userEvent.click(screen.getByRole("button", { name: /Limpar filtros/ }));
    expect(await screen.findByText("Mostrando 1–10 de 12")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Limpar filtros/ })).toBeDisabled();
    // So a ordenacao mudou: ainda da para limpar.
    await userEvent.selectOptions(screen.getByLabelText("Ordenar por"), "preco_desc");
    expect(screen.getByRole("button", { name: /Limpar filtros/ })).toBeEnabled();
  });

  it("Catalogo: a pagina vem da URL (C3) e o card leva a origem para o detalhe (V2)", async () => {
    api.obter.mockReturnValue(ok({ itens: lote(12) }));
    montar("/veiculos?pagina=2", [{ path: "/veiculos", el: <Catalogo /> }]);
    expect(await screen.findByText("Mostrando 11–12 de 12")).toBeInTheDocument();
    const link = screen.getAllByRole("link", { name: /Ver Fiat|Ver Honda/ })[0];
    expect(JSON.parse(link?.getAttribute("data-state") ?? "{}")).toEqual({
      de: "/veiculos?pagina=2",
    });
  });

  it("VeiculoDetalhe: ID inexistente mostra mensagem e caminho de volta (V1)", async () => {
    api.obter.mockRejectedValue(
      new ErroApi(404, "Recurso nao encontrado", "Veiculo nao encontrado."),
    );
    montar("/veiculos/x", [{ path: "/veiculos/:id", el: <VeiculoDetalhe /> }]);
    expect(
      await screen.findByRole("heading", { level: 1, name: /Veículo não encontrado/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("vendido ou retirado do catálogo");
    expect(screen.getByRole("link", { name: "Ver veículos disponíveis" })).toHaveAttribute(
      "href",
      "/veiculos",
    );
  });

  it("VeiculoDetalhe: cancelar a confirmacao nao reserva e falha ao checar o cadastro e explicada", async () => {
    api.obter.mockImplementation((caminho: string) =>
      caminho === "/clientes/meu-perfil"
        ? ok({ id: "c", cadastroCompleto: true, camposPendentes: [] })
        : ok(v("9")),
    );
    montar("/veiculos/9", [{ path: "/veiculos/:id", el: <VeiculoDetalhe /> }], "clientes");
    await userEvent.click(await screen.findByRole("button", { name: "Reservar e comprar" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(api.enviarJson).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Reservar e comprar" })).toBeInTheDocument();
  });

  it("VeiculoDetalhe: se outro cliente reservou antes, a tela deixa de oferecer a reserva", async () => {
    api.obter.mockImplementation((caminho: string) =>
      caminho === "/clientes/meu-perfil"
        ? ok({ id: "c", cadastroCompleto: true, camposPendentes: [] })
        : ok(v("9")),
    );
    api.enviarJson.mockRejectedValue(
      new ErroApi(
        409,
        "Conflito",
        "O veiculo foi reservado por outro cliente.",
        [],
        undefined,
        "veiculo-indisponivel",
      ),
    );
    montar("/veiculos/9", [{ path: "/veiculos/:id", el: <VeiculoDetalhe /> }], "clientes");
    await userEvent.click(await screen.findByRole("button", { name: "Reservar e comprar" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmar reserva" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O veículo foi reservado por outro cliente.",
    );
    // O status lido ainda e DISPONIVEL (a saga atualiza depois), mas a tela ja trata o veiculo como reservado.
    expect(screen.queryByRole("button", { name: "Reservar e comprar" })).not.toBeInTheDocument();
    expect(screen.getByText("Reservado")).toBeInTheDocument();
    expect(screen.getByText(/não está disponível/)).toBeInTheDocument();
  });

  it("VeiculoDetalhe: com compra em andamento, o aviso leva as compras", async () => {
    api.obter.mockImplementation((caminho: string) =>
      caminho === "/clientes/meu-perfil"
        ? ok({ id: "c", cadastroCompleto: true, camposPendentes: [] })
        : ok(v("9")),
    );
    api.enviarJson.mockRejectedValue(
      new ErroApi(
        409,
        "Conflito",
        "Voce ja possui uma compra em andamento.",
        [],
        undefined,
        "reserva-ativa-existente",
      ),
    );
    montar("/veiculos/9", [{ path: "/veiculos/:id", el: <VeiculoDetalhe /> }], "clientes");
    await userEvent.click(await screen.findByRole("button", { name: "Reservar e comprar" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmar reserva" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Você já possui uma compra em andamento.",
    );
    expect(screen.getByRole("link", { name: "Ver minhas compras" })).toHaveAttribute(
      "href",
      "/compras",
    );
  });

  it("VeiculoDetalhe: erro ao verificar o cadastro aparece com opcao de tentar de novo", async () => {
    let falhar = true;
    api.obter.mockImplementation((caminho: string) => {
      if (caminho !== "/clientes/meu-perfil") return ok(v("9"));
      if (falhar) return Promise.reject(new ErroApi(401, "Sessão expirada", "Entre novamente."));
      return ok({ id: "c", cadastroCompleto: true, camposPendentes: [] });
    });
    montar("/veiculos/9", [{ path: "/veiculos/:id", el: <VeiculoDetalhe /> }], "clientes");
    expect(await screen.findByText(/Não foi possível verificar seu cadastro/)).toBeInTheDocument();
    falhar = false;
    await userEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByRole("button", { name: "Reservar e comprar" })).toBeInTheDocument();
  });

  it("CompraDetalhe: venda inexistente nao fica consultando a API (D1, D2)", async () => {
    jest.useFakeTimers();
    try {
      api.obter.mockImplementation((caminho: string) =>
        caminho.startsWith("/vendas/")
          ? Promise.reject(new ErroApi(404, "Recurso nao encontrado", "Venda nao encontrada."))
          : ok({ id: "c", cadastroCompleto: true, camposPendentes: [] }),
      );
      montar("/compras/x", [{ path: "/compras/:id", el: <CompraDetalhe /> }], "clientes");
      expect(
        await screen.findByRole("heading", { level: 1, name: /Compra não encontrada/ }),
      ).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Ver minhas compras" })).toHaveAttribute(
        "href",
        "/compras",
      );
      await act(async () => {
        jest.advanceTimersByTime(20_000);
      });
      expect(api.obter.mock.calls.filter(([c]) => c === "/vendas/x")).toHaveLength(1);
    } finally {
      jest.useRealTimers();
    }
  });

  it("CompraDetalhe: depois de cancelada, some o aviso de processamento e o motivo vem acentuado (D3)", async () => {
    api.obter
      .mockReturnValueOnce(ok(venda("AGUARDANDO_PAGAMENTO")))
      .mockReturnValue(ok(venda("CANCELADO", { motivoCancelamento: "DESISTENCIA" })));
    api.chamar.mockReturnValue(ok({}));
    window.confirm = jest.fn(() => true);
    montar("/compras/venda1", [{ path: "/compras/:id", el: <CompraDetalhe /> }]);
    await userEvent.click(await screen.findByRole("button", { name: "Desistir da compra" }));
    expect(await screen.findByText("Desistência")).toBeInTheDocument();
    expect(screen.queryByText(/Desistência em processamento/)).not.toBeInTheDocument();
  });

  const clienteCompleto = {
    id: "c",
    nomeCompleto: "Ana Souza",
    cpf: "***",
    email: "a@b.c",
    telefone: "+5511987654321",
    endereco: {
      cep: "01310100",
      logradouro: "Av Paulista",
      numero: "1",
      complemento: null,
      bairro: "Centro",
      cidade: "Sao Paulo",
      uf: "SP",
    },
    rg: null,
    cnh: null,
    cadastroCompleto: false,
    camposPendentes: ["rg"],
    status: "ATIVO",
    dataNascimento: "2000-01-01",
  };

  it("Perfil: edita nome, telefone e endereco enviando so o que mudou (P3, P4)", async () => {
    api.obter.mockReturnValue(ok(clienteCompleto, '"v4"'));
    api.chamar.mockReturnValue(ok({}));
    montar("/perfil", [{ path: "/perfil", el: <Perfil /> }], "clientes");
    expect(await screen.findByText("(11) 98765-4321")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Editar dados" }));
    const tel = screen.getByLabelText(/Telefone com DDD/);
    await userEvent.clear(tel);
    await userEvent.type(tel, "(55) 99876-5432");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    expect(api.chamar).toHaveBeenCalledWith("/clientes/meu-perfil", {
      metodo: "PATCH",
      corpo: { telefone: "+5555998765432" },
      ifMatch: '"v4"',
    });
    expect(await screen.findByText("Dados atualizados.")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Editar dados" }));
    await userEvent.clear(screen.getByLabelText(/Bairro/));
    await userEvent.type(screen.getByLabelText(/Bairro/), "Bela Vista");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    expect(api.chamar).toHaveBeenLastCalledWith("/clientes/meu-perfil", {
      metodo: "PATCH",
      corpo: { endereco: expect.objectContaining({ bairro: "Bela Vista", cep: "01310-100" }) },
      ifMatch: '"v4"',
    });
  });

  it("Perfil: cadastro recusa menor de 18 anos antes de enviar", async () => {
    api.obter.mockRejectedValue(
      new ErroApi(
        403,
        "Cadastro de cliente inexistente",
        "Faca o cadastro",
        [],
        undefined,
        "perfil-cliente-inexistente",
      ),
    );
    montar("/perfil", [{ path: "/perfil", el: <Perfil /> }], "clientes");
    const nasc = await screen.findByLabelText(/Data de nascimento/);
    const limite = `${new Date().getFullYear() - 18}`;
    expect(nasc.getAttribute("max")?.startsWith(limite)).toBe(true);
    await userEvent.type(screen.getByLabelText(/Nome completo/), "Ana Souza");
    await userEvent.type(screen.getByLabelText(/^CPF/), "529.982.247-25");
    await userEvent.type(screen.getByLabelText(/Telefone com DDD/), "11987654321");
    await userEvent.type(nasc, `${new Date().getFullYear() - 10}-01-01`);
    // A primeira etapa bloqueia a data inválida no campo e não avança nem envia.
    expect((nasc as HTMLInputElement).validity.rangeOverflow).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(screen.getByText("Etapa 1 de 3")).toBeInTheDocument();
    expect(api.enviarJson).not.toHaveBeenCalled();
    // Sem a validação nativa, a validação do envio ainda explica o limite de idade.
    nasc.removeAttribute("max");
    await userEvent.click(screen.getByRole("button", { name: "Continuar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("É preciso ter 18 anos ou mais");
    expect(api.enviarJson).not.toHaveBeenCalled();
  });

  it("Perfil: CNH valida 11 digitos e pode ser salva sem RG (P5, P6)", async () => {
    api.obter.mockReturnValue(ok(clienteCompleto, '"v4"'));
    api.chamar.mockReturnValue(ok({}));
    montar("/perfil", [{ path: "/perfil", el: <Perfil /> }], "clientes");
    expect(await screen.findByLabelText(/Número do RG/)).toBeRequired();
    await userEvent.type(screen.getByLabelText(/^CNH/), "123ab");
    expect(screen.getByLabelText(/Número do RG/)).not.toBeRequired();
    await userEvent.click(screen.getByRole("button", { name: "Salvar documentos" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A CNH deve ter 11 dígitos.");
    await userEvent.type(screen.getByLabelText(/^CNH/), "45678901");
    await userEvent.click(screen.getByRole("button", { name: "Salvar documentos" }));
    expect(api.chamar).toHaveBeenCalledWith("/clientes/meu-perfil", {
      metodo: "PATCH",
      corpo: { cnh: "12345678901" },
      ifMatch: '"v4"',
    });
  });

  it("Perfil: exclusao leva ao login com confirmacao; exportacao avisa e nao revoga o link na hora (P7, P8)", async () => {
    api.obter.mockReturnValue(ok(clienteCompleto, '"v4"'));
    api.chamar.mockReturnValue(ok({ titular: {} }));
    api.remover.mockReturnValue(ok(null));
    const revogar = jest.fn();
    Object.assign(URL, { createObjectURL: jest.fn(() => "blob:x"), revokeObjectURL: revogar });
    jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    window.confirm = jest.fn(() => true);
    montar(
      "/perfil",
      [
        {
          path: "/perfil",
          el: (
            <Protegida papeis={["cliente"]}>
              <Perfil />
            </Protegida>
          ),
        },
        {
          path: "/entrar",
          el: (
            <SoAnonimo>
              <Entrar />
            </SoAnonimo>
          ),
        },
      ],
      "clientes",
    );
    await userEvent.click(await screen.findByRole("button", { name: "Exportar meus dados" }));
    expect(await screen.findByText(/meus-dados.json foi baixado/)).toBeInTheDocument();
    expect(revogar).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Excluir minha conta" }));
    expect(
      await screen.findByText("Sua conta foi excluída e seus dados pessoais foram anonimizados."),
    ).toBeInTheDocument();
    expect(sessionStorage.getItem("revenda.sessao")).toBeNull();
  });

  it("Painel: edita veiculo enviando so o que mudou (G2) e cadastro confirma (PN6)", async () => {
    const carro = v("1", {
      versao: 5,
      placa: "ABC1D23",
      renavam: "12345678900",
      chassi: "9BWZZZ377VT004251",
    });
    api.obter.mockReturnValue(ok({ itens: [carro] }));
    api.chamar.mockReturnValue(ok({}));
    montar("/painel", [{ path: "/painel", el: <Painel /> }], "funcionarios");
    await userEvent.click(await screen.findByRole("button", { name: "Editar Fiat Modelo 1" }));
    const preco = screen.getByLabelText("Preço (R$)", { selector: "#ed-preco" });
    await userEvent.clear(preco);
    await userEvent.type(preco, "39900");
    await userEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    expect(api.chamar).toHaveBeenCalledWith("/veiculos/1", {
      metodo: "PATCH",
      corpo: { preco: "39900.00" },
      ifMatch: '"v5"',
    });
    expect(await screen.findByText("Fiat Modelo 1 atualizado.")).toBeInTheDocument();
  });

  it("Painel: veiculo reservado nao edita preco, chassi nem RENAVAM", async () => {
    api.obter.mockReturnValue(
      ok({
        itens: [
          v("1", {
            status: "RESERVADO",
            versao: 2,
            renavam: "12345678900",
            chassi: "9BWZZZ377VT004251",
          }),
        ],
      }),
    );
    montar("/painel", [{ path: "/painel", el: <Painel /> }], "funcionarios");
    await userEvent.selectOptions(await screen.findByLabelText("Status"), "RESERVADO");
    await userEvent.click(await screen.findByRole("button", { name: "Editar Fiat Modelo 1" }));
    expect(screen.getByLabelText("Preço (R$)", { selector: "#ed-preco" })).toBeDisabled();
    expect(screen.getByLabelText("RENAVAM", { selector: "#ed-renavam" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Inativar/ })).not.toBeInTheDocument();
  });

  it("Painel: admin troca o perfil e desativa outro funcionario, mas nao a si mesmo (PN4)", async () => {
    const eu = {
      id: "f0",
      nome: "",
      email: "eu@x.com",
      grupos: ["admin"],
      ativo: true,
      mfaConfigurado: true,
    };
    const outro = {
      id: "f1",
      nome: "Maria",
      email: "m@x.com",
      grupos: ["vendedor"],
      ativo: true,
      mfaConfigurado: false,
    };
    api.obter.mockImplementation((caminho: string) =>
      ok({ itens: caminho === "/administracao/funcionarios" ? [eu, outro] : [] }),
    );
    api.chamar.mockReturnValue(ok({}));
    window.confirm = jest.fn(() => true);
    const jwt = (c: object) => `x.${btoa(JSON.stringify(c))}.y`;
    sessionStorage.setItem(
      "revenda.sessao",
      JSON.stringify({
        accessToken: jwt({ "cognito:groups": ["admin"] }),
        idToken: jwt({ email: "eu@x.com" }),
        expiraEm: Date.now() + 1e6,
        pool: "funcionarios",
      }),
    );
    montar("/painel", [{ path: "/painel", el: <Painel /> }]);
    await userEvent.click(await screen.findByRole("tab", { name: "Equipe" }));
    expect(await screen.findByText("(você)")).toBeInTheDocument();
    expect(screen.getByText("eu", { selector: "p" })).toBeInTheDocument(); // sem nome: parte local do e-mail
    expect(screen.getAllByRole("button", { name: "Desativar" })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Tornar administrador" }));
    expect(api.chamar).toHaveBeenCalledWith("/administracao/funcionarios/f1", {
      metodo: "PATCH",
      corpo: { grupo: "admin" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Desativar" }));
    expect(api.chamar).toHaveBeenLastCalledWith("/administracao/funcionarios/f1", {
      metodo: "PATCH",
      corpo: { ativo: false },
    });
    expect(await screen.findByText("Maria desativado.")).toBeInTheDocument();
  });
});

const PIX =
  "00020126580014BR.GOV.BCB.PIX0136tx_0123456789abcdef5204000053039865406429.005802BR6304ABCD";

describe("Simulacao de pagamento (gateway Pix simulado)", () => {
  async function abrirVendas(rota: (c: string) => unknown) {
    api.obter.mockImplementation((c: string) => ok(rota(c)));
    montar("/painel", [{ path: "/painel", el: <Painel /> }], "funcionarios");
    await userEvent.click(await screen.findByRole("tab", { name: "Vendas" }));
    await userEvent.selectOptions(
      await screen.findByLabelText("Status da venda"),
      "AGUARDANDO_PAGAMENTO",
    );
  }
  const rotas = (c: string) =>
    c === "/vendas/venda1"
      ? venda("AGUARDANDO_PAGAMENTO", {
          pagamento: {
            id: "p",
            metodo: "PIX",
            status: "PENDENTE",
            pixCopiaECola: PIX,
            valor: "429.00",
            expiraEm: "x",
          },
        })
      : { itens: c === "/vendas" ? [venda("AGUARDANDO_PAGAMENTO")] : lote(1) };

  it("aprova o pagamento chamando o gateway com o id da cobranca do Pix", async () => {
    await abrirVendas(rotas);
    api.enviarJson.mockReturnValue(ok({}));
    await userEvent.click(
      await screen.findByRole("button", { name: "Simular pagamento de Fiat Mobi" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Aprovar pagamento" }));
    expect(api.enviarJson).toHaveBeenCalledWith(
      "/_simulacao/pagamentos/cobrancas/tx_0123456789abcdef/simular",
      {
        resultado: "APROVADO",
      },
    );
    expect(await screen.findByText(/Pagamento aprovado/)).toBeInTheDocument();
  });

  it("recusa o pagamento", async () => {
    await abrirVendas(rotas);
    api.enviarJson.mockReturnValue(ok({}));
    await userEvent.click(
      await screen.findByRole("button", { name: "Simular pagamento de Fiat Mobi" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Recusar pagamento" }));
    expect(api.enviarJson).toHaveBeenCalledWith(
      "/_simulacao/pagamentos/cobrancas/tx_0123456789abcdef/simular",
      {
        resultado: "RECUSADO",
      },
    );
    expect(await screen.findByText(/Pagamento recusado/)).toBeInTheDocument();
  });

  it("avisa quando a venda ainda nao tem codigo Pix", async () => {
    await abrirVendas((c) => (c === "/vendas/venda1" ? venda("AGUARDANDO_PAGAMENTO") : rotas(c)));
    await userEvent.click(
      await screen.findByRole("button", { name: "Simular pagamento de Fiat Mobi" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Aprovar pagamento" }));
    expect(await screen.findByText(/ainda não tem um código Pix válido/)).toBeInTheDocument();
    expect(api.enviarJson).not.toHaveBeenCalled();
  });
});

describe("Configuracao inicial", () => {
  const abrir = () =>
    montar("/configuracao-inicial", [
      { path: "/configuracao-inicial", el: <ConfiguracaoInicial /> },
    ]);

  it("convida o administrador declarado na implantacao", async () => {
    api.obter.mockReturnValue(ok({ necessaria: true }));
    api.chamar.mockReturnValue(ok({}));
    abrir();
    await userEvent.click(
      await screen.findByRole("button", { name: "Enviar convite ao administrador" }),
    );
    expect(api.chamar).toHaveBeenCalledWith("/configuracao-inicial", {
      metodo: "POST",
      autenticado: false,
    });
    expect(await screen.findByText(/Enviamos a senha temporária/)).toBeInTheDocument();
  });

  it("mostra o erro quando o convite falha", async () => {
    api.obter.mockReturnValue(ok({ necessaria: true }));
    api.chamar.mockRejectedValue(
      new ErroApi(409, "Conflito", "A configuracao inicial ja foi concluida."),
    );
    abrir();
    await userEvent.click(
      await screen.findByRole("button", { name: "Enviar convite ao administrador" }),
    );
    expect(await screen.findByText(/configuração inicial já foi concluída/)).toBeInTheDocument();
  });

  it("fecha o fluxo quando ja existe administrador", async () => {
    api.obter.mockReturnValue(ok({ necessaria: false }));
    abrir();
    expect(await screen.findByText("Configuração concluída")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Enviar convite ao administrador" }),
    ).not.toBeInTheDocument();
  });
});

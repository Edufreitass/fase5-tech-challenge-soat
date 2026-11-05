import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { Protegida } from "../App";
import { AuthProvider } from "../context/AuthContext";
import { FalhaInicial } from "./InitialFailure";
import { SagaFlow } from "./SagaFlow";
import { Aviso, StatusBadge, Titulo } from "./ui";
import { VeiculoCard } from "./VehicleCard";

const veiculo = {
  id: "v1",
  marca: "Fiat",
  modelo: "Mobi Like 1.0",
  anoFabricacao: 2020,
  anoModelo: 2021,
  cor: "Prata",
  preco: "42900.00",
  quilometragem: 58000,
  combustivel: "FLEX",
  cambio: "MANUAL",
  status: "DISPONIVEL" as const,
};

describe("componentes", () => {
  it("VeiculoCard mostra dados, preco e link de detalhes", () => {
    render(
      <MemoryRouter>
        <VeiculoCard veiculo={veiculo} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Mobi Like 1.0")).toBeInTheDocument();
    expect(screen.getByText(/42\.900,00/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ver Fiat Mobi/ })).toHaveAttribute(
      "href",
      "/veiculos/v1",
    );
    expect(screen.getByText("Disponível")).toBeInTheDocument();
  });

  it("StatusBadge, Aviso e Titulo renderizam o conteudo", () => {
    render(
      <>
        <StatusBadge status="AGUARDANDO_PAGAMENTO" />
        <Aviso>falhou</Aviso>
        <Titulo sub="sub">Olá</Titulo>
      </>,
    );
    expect(screen.getByText("Aguardando pagamento")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("falhou");
    expect(screen.getByText("sub")).toBeInTheDocument();
  });

  it("SagaFlow fica na vertical no celular e na horizontal em tela larga", () => {
    const original = window.matchMedia;
    try {
      for (const [larga, eixo] of [
        [false, "y"],
        [true, "x"],
      ] as const) {
        window.matchMedia = jest.fn(() => ({
          matches: larga,
          addEventListener: jest.fn(),
          removeEventListener: jest.fn(),
        })) as never;
        const { unmount } = render(<SagaFlow status="PAGO" />);
        const ultimo = screen.getAllByRole("listitem").at(-1);
        expect(Number(ultimo?.dataset[eixo])).toBeGreaterThan(0);
        expect(Number(ultimo?.dataset[eixo === "x" ? "y" : "x"])).toBeLessThan(30);
        unmount();
      }
    } finally {
      window.matchMedia = original;
    }
  });

  it("SagaFlow lista as etapas conforme o status", () => {
    render(<SagaFlow status="PAGO" />);
    const itens = screen.getAllByRole("listitem");
    expect(itens.map((i) => i.dataset.estado)).toEqual(["feito", "feito", "atual", "pendente"]);
    expect(screen.getByText("Pagamento confirmado")).toBeInTheDocument();
  });
});

describe("rotas protegidas e login", () => {
  const app = (papelSessao: string | null) => {
    if (papelSessao)
      sessionStorage.setItem(
        "revenda.sessao",
        JSON.stringify({
          accessToken: `x.${btoa(JSON.stringify({ "cognito:groups": ["vendedor"] }))}.y`,
          expiraEm: Date.now() + 1e6,
          pool: papelSessao,
        }),
      );
    return render(
      <MemoryRouter initialEntries={["/area"]}>
        <AuthProvider>
          <Routes>
            <Route
              path="/area"
              element={
                <Protegida papeis={["cliente"]}>
                  <p>conteudo do cliente</p>
                </Protegida>
              }
            />
            <Route path="/entrar" element={<p>tela de login</p>} />
            <Route path="/" element={<p>inicio</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
  };
  beforeEach(() => sessionStorage.clear());

  it("redireciona anonimo ao login", async () => {
    app(null);
    expect(await screen.findByText("tela de login")).toBeInTheDocument();
  });
  it("libera o papel correto e barra o incorreto", async () => {
    app("clientes");
    expect(await screen.findByText("conteudo do cliente")).toBeInTheDocument();
  });
  it("barra funcionario em rota de cliente", async () => {
    app("funcionarios");
    expect(await screen.findByText("inicio")).toBeInTheDocument();
  });
});

describe("FalhaInicial", () => {
  it("explica a falha ao abrir e permite tentar de novo", async () => {
    const aoTentar = jest.fn();
    render(<FalhaInicial aoTentar={aoTentar} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Não foi possível abrir a loja",
    );
    screen.getByRole("button", { name: "Tentar de novo" }).click();
    expect(aoTentar).toHaveBeenCalled();
  });
});

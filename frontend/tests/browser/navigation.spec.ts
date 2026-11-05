import { expect, test } from "@playwright/test";

const VEICULO = {
  id: "v1",
  marca: "Fiat",
  modelo: "Argo",
  anoFabricacao: 2022,
  anoModelo: 2023,
  cor: "Prata",
  preco: "55000.00",
  quilometragem: 10000,
  status: "DISPONIVEL",
  combustivel: "FLEX",
  cambio: "MANUAL",
};

// Os testes usam o roteador e o cliente HTTP reais. Apenas a rede e simulada.
test.beforeEach(async ({ page }) => {
  await page.route("**/config.json", (route) =>
    route.fulfill({
      json: {
        apiBase: "/api",
        versaoTermo: "v1",
        regiao: "us-east-1",
        clientes: { clientId: "local", dominio: "local" },
        funcionarios: { clientId: "local", dominio: "local" },
      },
    }),
  );
  await page.route("**/api/**", (route) => {
    const caminho = new URL(route.request().url()).pathname;
    if (caminho === "/api/veiculos")
      return route.fulfill({ json: { itens: [VEICULO], nextToken: null } });
    if (caminho === "/api/veiculos/v1") return route.fulfill({ json: VEICULO });
    return route.fulfill({ status: 404, json: { title: "Recurso nao encontrado" } });
  });
});

test("catalogo chama a rota do backend e abre o detalhe", async ({ page }) => {
  // Arrange
  const requisicoes: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) requisicoes.push(new URL(request.url()).pathname);
  });

  // Act
  await page.goto("/veiculos");
  await page.getByRole("link", { name: "Fiat Argo" }).click();

  // Assert
  await expect(page).toHaveURL(/\/veiculos\/v1$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Argo");
  expect(requisicoes).toContain("/api/veiculos");
  expect(requisicoes).not.toContain("/api/vehicles");
  await expect(page.getByRole("link", { name: "Voltar ao catálogo" })).toHaveAttribute(
    "href",
    "/veiculos",
  );
});

test("visitante e direcionado ao login ao abrir uma rota protegida", async ({ page }) => {
  await page.goto("/compras");

  await expect(page).toHaveURL(/\/entrar$/);
  await expect(page.getByRole("heading", { name: /^Entrar\.?$/ })).toBeVisible();
  await expect(page.getByLabel("E-mail", { exact: true })).toBeVisible();
});

test("sessao malformada nao quebra a aplicacao nem libera o perfil", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem(
      "revenda.sessao",
      JSON.stringify({ pool: "clientes", accessToken: 123 }),
    );
  });

  await page.goto("/perfil");

  await expect(page).toHaveURL(/\/entrar$/);
  await expect(page.getByRole("heading", { name: /^Entrar\.?$/ })).toBeVisible();
});

test("estoque indisponivel mostra erro de rede sem deixar carregamento preso", async ({ page }) => {
  await page.route("**/api/veiculos?**", (route) => route.abort("failed"));

  await page.goto("/veiculos");

  await expect(page.getByRole("alert")).toContainText("Não foi possível conectar ao servidor");
  await expect(page.getByRole("status", { name: "Carregando" })).toHaveCount(0);
});

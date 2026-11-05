import { expect, test } from "@playwright/test";

test.describe("visitante", () => {
  test("home organizada, sem botao de cadastro no corpo, e busca rapida leva ao catalogo filtrado", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Seu próximo carro/ })).toBeVisible();
    await expect(page.getByRole("main").getByText(/Entrar ou cadastrar/)).toHaveCount(0);
    await expect(
      page.getByRole("main").getByRole("link", { name: /Explorar veículos/ }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: /Como funciona/ })).toBeVisible();
    // As listas sao montadas a partir do estoque carregado da API.
    await expect(page.getByLabel("Marca").locator("option")).not.toHaveCount(1);
    expect(await page.getByLabel("Marca").locator("option").count()).toBeGreaterThan(2);
    await page.getByLabel("Marca", { exact: true }).selectOption({ index: 1 });
    await page.getByRole("button", { name: /Buscar/ }).click();
    await expect(page).toHaveURL(/\/veiculos\?marca=/);
    await expect(page.getByRole("article").first()).toBeVisible();
  });

  test("catalogo pagina de 10 em 10, filtra por listas e valida faixas", async ({ page }) => {
    await page.goto("/veiculos");
    await expect(page.getByText(/Mostrando 1–10 de \d+/)).toBeVisible();
    expect(await page.getByRole("article").count()).toBe(10);
    await page.getByRole("button", { name: "Página 2" }).click();
    await expect(page.getByText(/Mostrando 11–/)).toBeVisible();
    await page.getByLabel("Marca", { exact: true }).selectOption({ index: 1 });
    await expect(page.getByText(/Mostrando 1–/)).toBeVisible();
    // Faixa invertida: o catalogo recusa e avisa.
    await page.getByRole("button", { name: /Limpar filtros/ }).click();
    const precos = await page
      .getByLabel("Preço a partir de")
      .locator("option")
      .evaluateAll((o) => (o as HTMLOptionElement[]).map((x) => x.value).filter(Boolean));
    const menor = precos.at(0);
    const maior = precos.at(-1);
    if (!menor || !maior)
      throw new Error("O catálogo precisa de opções de preço para este cenário.");
    await page.getByLabel("Preço a partir de").selectOption(maior);
    await page.getByLabel("Preço até").selectOption(menor);
    await expect(page.getByRole("alert")).toContainText("preço mínimo não pode ser maior");
    // Cada card exibe a imagem do veiculo na cor do anuncio.
    await page.getByRole("button", { name: /Limpar filtros/ }).click();
    await expect(
      page.getByRole("article").first().locator("svg[role=img], a svg").first(),
    ).toBeVisible();
  });

  test("area logada exige login e mobile nao tem rolagem horizontal", async ({ page }) => {
    await page.goto("/painel");
    await expect(page).toHaveURL(/\/entrar$/);
    await page.setViewportSize({ width: 390, height: 800 });
    for (const rota of ["/", "/veiculos", "/entrar"]) {
      await page.goto(rota);
      await expect(page.locator("main")).toBeVisible();
      const estouro = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(estouro, `rolagem horizontal em ${rota}`).toBeLessThanOrEqual(1);
    }
  });

  test("detalhe do veículo mantém preço e ação de compra visíveis no mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/veiculos");
    const primeiro = page.getByRole("article").first();
    await expect(primeiro).toBeVisible();
    await primeiro.getByRole("link", { name: /^Ver / }).click();
    const compra = page.getByRole("complementary", { name: "Comprar veículo" });
    await expect(compra).toBeVisible();
    await expect(compra.getByText("Preço", { exact: true }).last()).toBeVisible();
    await expect(compra.getByRole("link", { name: "Entrar para comprar" })).toBeVisible();
    await expect(page.getByText("Ilustração de referência").first()).toBeVisible();
    const estouro = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(estouro, "rolagem horizontal no detalhe mobile").toBeLessThanOrEqual(1);
  });
});

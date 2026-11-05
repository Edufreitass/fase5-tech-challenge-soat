import { expect, test } from "@playwright/test";
import {
  apagar,
  type Conta,
  chassiUnico,
  criarFuncionario,
  renavamValido,
  SENHA,
} from "./environment";
import { codigoTotp, entrar, primeiroAcesso } from "./helpers";

test.describe
  .serial("funcionario (vendedor)", () => {
    let conta: Conta;
    let segredo = "";
    test.beforeAll(async () => {
      conta = await criarFuncionario("vendedor");
    });
    test.afterAll(async () => {
      await apagar(conta);
    });

    test("primeiro acesso: troca a senha, ativa o MFA e entra no painel", async ({ page }) => {
      segredo = await primeiroAcesso(page, conta);
      await expect(page.getByRole("heading", { name: /Painel/ })).toBeVisible();
      await expect(page.getByRole("tab", { name: "Equipe" })).toHaveCount(0); // vendedor nao ve a equipe
    });

    test("painel: veiculos paginados, vendas sem erro de validacao e cadastro/inativacao de veiculo", async ({
      page,
    }) => {
      page.on("response", async (r) => {
        if (r.url().includes("/api/") && r.status() >= 400)
          console.log(
            "HTTP",
            r.status(),
            r.request().method(),
            r.url().replace(/^https?:\/\/[^/]+/, ""),
            (await r.text()).slice(0, 400),
          );
      });
      // Inativar pede confirmacao (window.confirm): aceita em todo o teste.
      page.on("dialog", (d) => void d.accept());
      await entrar(page, "funcionario", conta.email, SENHA);
      await page.getByLabel("Código do aplicativo").fill(await codigoTotp(segredo, 1));
      await page.getByRole("button", { name: "Verificar" }).click();
      await expect(page).toHaveURL(/\/painel$/);

      // Limpeza de execucoes anteriores interrompidas: inativa veiculos de teste que ficaram ativos.
      for (let i = 0; i < 10; i++) {
        const sobra = page
          .getByRole("row")
          .filter({ hasText: /E2E \d+/ })
          .getByRole("button", { name: "Inativar" })
          .first();
        if (!(await sobra.isVisible().catch(() => false))) break;
        await sobra.click();
        await page.waitForTimeout(800);
      }

      // Veiculos: 10 linhas por pagina.
      await expect(page.getByText(/Mostrando 1–10 de \d+/)).toBeVisible();
      await expect(page.getByRole("row")).toHaveCount(11);
      const antes = Number(
        (await page.getByText(/Mostrando 1–10 de \d+/).textContent())?.match(/de (\d+)/)?.[1],
      );

      // Vendas: o status e obrigatorio na API; a tela ja envia um e nao exibe erro.
      await page.getByRole("tab", { name: "Vendas" }).click();
      await expect(page.getByLabel("Status da venda")).toHaveValue("PAGO");
      await expect(page.getByRole("alert")).toHaveCount(0);
      for (const status of ["AGUARDANDO_PAGAMENTO", "CONCLUIDO", "CANCELADO", "ESTORNADO"]) {
        await page.getByLabel("Status da venda").selectOption(status);
        await expect(page.getByRole("alert")).toHaveCount(0);
        await expect(page.getByText(/Mostrando|Nenhuma venda/).first()).toBeVisible();
      }

      // Cadastro de veiculo com validacoes do formulario.
      await page.getByRole("tab", { name: "Veículos" }).click();
      await page.getByText("Cadastrar veículo").click();
      const modelo = `E2E ${Date.now() % 100000}`;
      await page.getByLabel("Modelo", { exact: true }).fill(modelo);
      await page.getByLabel("Marca", { exact: true }).fill("Fiat"); // texto livre com sugestoes (datalist)
      await page.getByLabel("Ano de fabricação").fill("2022");
      await page.getByLabel("Ano do modelo").fill("2023");
      await page.getByLabel("Cor", { exact: true }).fill("Azul Surf");
      await page.getByLabel("Quilometragem").fill("1200");
      await page.getByLabel("RENAVAM").fill("12345678901"); // digito verificador invalido
      await page.getByLabel("Chassi").fill(chassiUnico());
      // Preco negativo: o proprio formulario recusa (min=0,01).
      await page.getByLabel("Preço (R$)").fill("-5");
      expect(
        await page
          .getByLabel("Preço (R$)")
          .evaluate((e) => !(e as HTMLInputElement).validity.valid),
        "preco negativo deve ser recusado",
      ).toBe(true);
      // RENAVAM com digito verificador errado: a tela explica antes de chamar a API.
      await page.getByLabel("Preço (R$)").fill("1000.00");
      await page.getByRole("button", { name: "Salvar veículo" }).click();
      await expect(page.getByRole("alert")).toContainText("RENAVAM inválido");
      await page.getByLabel("RENAVAM").fill(renavamValido());
      await page.getByRole("button", { name: "Salvar veículo" }).click();
      await expect(page.getByRole("row").filter({ hasText: modelo })).toBeVisible();
      const depois = Number(
        (await page.getByText(/Mostrando 1–10 de \d+/).textContent())?.match(/de (\d+)/)?.[1],
      );
      expect(depois).toBe(antes + 1);

      // Inativa o veiculo de teste.
      await page
        .getByRole("row")
        .filter({ hasText: modelo })
        .getByRole("button", { name: "Inativar" })
        .click();
      // A listagem e agrupada por status: o veiculo passa a aparecer no filtro "Inativo" (e sai dos disponiveis).
      await expect(page.getByRole("row").filter({ hasText: modelo })).toHaveCount(0);
      await page.getByLabel("Status", { exact: true }).selectOption("INATIVO");
      await expect(
        page.getByRole("row").filter({ hasText: modelo }).getByText("Inativo"),
      ).toBeVisible();

      // Sair encerra a sessao: a area da loja volta a exigir login.
      await page.getByRole("button", { name: /Sair/ }).first().click();
      await page.goto("/painel");
      await expect(page).toHaveURL(/\/entrar$/);
    });
  });

test.describe("funcionario (admin)", () => {
  let conta: Conta;
  test.beforeAll(async () => {
    conta = await criarFuncionario("admin");
  });
  test.afterAll(async () => {
    await apagar(conta);
  });

  test("admin ve a aba Equipe com a lista renderizada (sem tela preta)", async ({ page }) => {
    await primeiroAcesso(page, conta);
    await page.getByRole("tab", { name: "Equipe" }).click();
    await expect(page.getByRole("heading", { name: /Painel/ })).toBeVisible();
    await expect(page.getByText(conta.email)).toBeVisible();
    await expect(
      page.getByRole("listitem").filter({ hasText: conta.email }).getByText("Admin").first(),
    ).toBeVisible();
    await expect(page.getByLabel("E-mail")).toBeVisible(); // formulario de convite
    await expect(page.getByRole("alert")).toHaveCount(0);
  });
});

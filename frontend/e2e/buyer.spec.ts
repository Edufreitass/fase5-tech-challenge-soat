import { expect, type Page, test } from "@playwright/test";
import {
  apagar,
  type Conta,
  clienteDoPool,
  confirmarCadastro,
  cpfValido,
  criarCliente,
  SENHA,
  sessaoPorAdmin,
} from "./environment";
import { entrar } from "./helpers";

test.describe
  .serial("comprador", () => {
    let conta: Conta;
    test.beforeAll(async () => {
      conta = await criarCliente();
    });
    test.afterAll(async () => {
      await apagar(conta);
    });

    test("senha incorreta mostra erro e nao entra", async ({ page }) => {
      await entrar(page, "cliente", conta.email, "Errada#12345x");
      await expect(page.getByRole("alert")).toContainText("E-mail ou senha incorretos");
      await expect(page).toHaveURL(/\/entrar$/);
    });

    test("login pela tela de conta sem cadastro leva direto ao cadastro", async ({ page }) => {
      await entrar(page, "cliente", conta.email, SENHA);
      await expect(page).toHaveURL(/\/perfil$/);
      await expect(page.getByRole("heading", { name: /Cadastro/ })).toBeVisible();
    });

    test("sem cadastro: perfil mostra o formulario e a reserva pede o cadastro", async ({
      page,
      request,
    }) => {
      await sessaoInjetada(page, request, conta);
      await page.goto("/perfil");
      await expect(page.getByRole("heading", { name: /Cadastro/ })).toBeVisible();
      await expect(page.getByRole("button", { name: "Continuar" })).toBeVisible();
      await page.goto("/veiculos");
      await page.getByRole("article").first().getByRole("link", { name: /Ver / }).click();
      await expect(page.getByText("Para reservar, primeiro faça seu cadastro.")).toBeVisible();
      await expect(page.getByRole("link", { name: "Completar cadastro" }).first()).toBeVisible();
      await expect(page.getByRole("button", { name: "Reservar e comprar" })).toHaveCount(0);
    });

    test("cadastra o perfil, escolhe um veiculo, paga com Pix (codigo), desiste e exclui a conta", async ({
      page,
      request,
    }) => {
      await sessaoInjetada(page, request, conta);
      await page.goto("/compras");
      await expect(page.getByText("Você ainda não tem compras")).toBeVisible();

      // Sem cadastro: aviso no topo e nome (e-mail) no menu; o RG e opcional no cadastro e exigido so para comprar.
      await expect(page.getByText(/complete seu cadastro para poder reservar/)).toBeVisible();
      await page.getByRole("link", { name: "Completar cadastro" }).click();
      await expect(page.getByText("Etapa 1 de 3")).toBeVisible();
      for (const r of [/Nome completo/, /^CPF/, /Data de nascimento/, /Telefone com DDD/])
        await expect(page.getByLabel(r)).toHaveAttribute("required", "");
      await page.getByLabel(/Nome completo/).fill("Cliente E2E Teste");
      await page.getByLabel(/^CPF/).fill("111.111.111-11");
      await page.getByLabel(/Data de nascimento/).fill("1990-05-12");
      await page.getByLabel(/Telefone com DDD/).fill("11987654321");
      await page.getByRole("button", { name: "Continuar" }).click();
      await expect(page.getByRole("alert")).toContainText("CPF inválido");
      await page.getByLabel(/^CPF/).fill(cpfValido());
      await page.getByRole("button", { name: "Continuar" }).click();
      for (const r of [/^CEP/, /Logradouro/, /^Número \*$/, /Bairro/, /Cidade/, /Estado \(UF\)/])
        await expect(page.getByLabel(r)).toHaveAttribute("required", "");
      await expect(page.getByLabel(/Complemento/)).not.toHaveAttribute("required", "");
      await page.getByLabel(/^CEP/).fill("01310-100");
      await page.getByLabel(/Logradouro/).fill("Avenida Paulista");
      await page.getByLabel(/^Número \*$/).fill("1000");
      await page.getByLabel(/Bairro/).fill("Bela Vista");
      await page.getByLabel(/Cidade/).fill("São Paulo");
      await page.getByLabel(/Estado \(UF\)/).selectOption("SP");
      await page.getByRole("button", { name: "Continuar" }).click();
      for (const r of [/Número do RG/, /Órgão emissor/, /UF do RG/])
        await expect(page.getByLabel(r)).not.toHaveAttribute("required", "");
      await page.getByRole("checkbox", { name: /Aceito os termos/ }).check();
      await page.getByRole("button", { name: "Concluir cadastro" }).click();
      await expect(page.getByRole("heading", { name: /Meu perfil/ })).toBeVisible();
      await expect(page.getByText(/Cadastro concluído/)).toBeVisible();
      await expect(page.getByText(/\*\*\*\.\*\*\*/)).toBeVisible(); // CPF sempre mascarado
      await expect(page.getByTestId("usuario-nome")).toHaveText("Cliente"); // nome do cadastro no menu
      await expect(page.getByText(/Para comprar, falta informar: RG/)).toBeVisible();

      // Sem RG a reserva pede o documento; o RG entra pelo perfil (PATCH).
      await page.getByRole("link", { name: "Veículos" }).first().click();
      await page.getByRole("article").first().getByRole("link", { name: /Ver / }).click();
      await expect(page.getByText(/Para reservar, falta informar: RG/)).toBeVisible();
      await expect(page.getByRole("button", { name: "Reservar e comprar" })).toHaveCount(0);
      await page.getByRole("link", { name: "Completar cadastro" }).first().click();
      await page
        .getByRole("form", { name: "Documentos" })
        .getByLabel(/Número do RG/)
        .fill("12.345.678-9");
      await page
        .getByRole("form", { name: "Documentos" })
        .getByLabel(/Órgão emissor/)
        .fill("SSP");
      await page
        .getByRole("form", { name: "Documentos" })
        .getByLabel(/UF do RG/)
        .selectOption("SP");
      await page.getByRole("button", { name: "Salvar documentos" }).click();
      await expect(page.getByText("Documentos salvos.")).toBeVisible();
      await expect(page.getByText(/Para comprar, falta informar/)).toHaveCount(0);
      await expect(page.getByText(/complete seu cadastro/i)).toHaveCount(0); // aviso do topo some

      // Catalogo -> detalhe -> reserva.
      await page.getByRole("link", { name: "Veículos" }).first().click();
      await expect(page.getByText(/Mostrando 1–10 de/)).toBeVisible();
      await page.getByRole("article").first().getByRole("link", { name: /Ver / }).click();
      await expect(page.getByRole("button", { name: "Reservar e comprar" })).toBeVisible();
      await page.getByRole("button", { name: "Reservar e comprar" }).click();
      // A reserva pede confirmacao (resumo com modelo e preco) antes de criar a venda.
      await page
        .getByRole("group", { name: "Confirmar reserva" })
        .getByRole("button", { name: "Confirmar reserva" })
        .click();

      // Compra: a saga gera o Pix e a linha do tempo mostra o andamento.
      await expect(page).toHaveURL(/\/compras\/[0-9a-f-]+$/);
      await expect(page.getByLabel("Código Pix copia e cola")).toBeVisible({ timeout: 90_000 });
      await expect(page.getByTestId("fluxo").or(page.locator(".react-flow")).first()).toBeVisible();
      await expect(page.locator(".react-flow__node.atual")).toContainText("Aguardando Pix");

      // Desistencia: libera o veiculo e a venda termina cancelada.
      page.once("dialog", (d) => void d.accept());
      await page.getByRole("button", { name: "Desistir da compra" }).click();
      await expect(page.getByText("Cancelado").first()).toBeVisible({ timeout: 90_000 });
      await page.getByRole("link", { name: "Minhas compras" }).first().click();
      await expect(
        page.getByRole("listitem").filter({ hasText: "Cancelado" }).first(),
      ).toBeVisible();

      // LGPD: exclusao da conta anonimiza o perfil e encerra a sessao.
      await excluirConta(page);
      await expect(page).toHaveURL(/\/entrar$/);
    });

    test("cadastro por e-mail: formulario, confirmacao e primeiro login", async ({ page }) => {
      const novo = `e2e.cadastro.${Date.now()}@example.com`;
      const cadastrada = await clienteDoPool(novo);
      try {
        await page.goto("/entrar");
        await page.getByRole("button", { name: "Criar conta" }).click();
        await page.getByLabel("E-mail").fill(novo);
        await page.getByLabel("Senha", { exact: true }).fill("fraca");
        await page.getByRole("button", { name: "Criar conta" }).click();
        await expect(page.getByRole("alert")).toContainText("não atende");
        await page.getByLabel("Senha", { exact: true }).fill(SENHA);
        await page.getByRole("button", { name: "Criar conta" }).click();
        await expect(page.getByRole("heading", { name: /Confirme seu e-mail/ })).toBeVisible();
        // O codigo chega por e-mail; no teste o administrador confirma a conta. Um codigo errado e recusado com aviso.
        await confirmarCadastro(novo);
        await page.getByLabel("Código").fill("000000");
        await page.getByRole("button", { name: "Confirmar" }).click();
        await expect(page.getByRole("alert")).toBeVisible();
        // Conta nova sem cadastro: o login leva direto ao preenchimento dos dados.
        await entrar(page, "cliente", novo, SENHA);
        await expect(page).toHaveURL(/\/perfil$/);
        await expect(page.getByRole("heading", { name: /Cadastro/ })).toBeVisible();
        await expect(page.getByTestId("usuario-nome")).toHaveText(novo.split("@")[0] ?? novo);
      } finally {
        await apagar(cadastrada);
      }
    });

    test("cliente nao acessa o painel da loja", async ({ page }) => {
      const outro = await criarCliente();
      try {
        await entrar(page, "cliente", outro.email, SENHA);
        await expect(page).toHaveURL(/\/perfil$/); // conta nova: cai no cadastro
        await expect(page.getByRole("link", { name: "Painel" })).toHaveCount(0);
        await page.goto("/painel");
        await expect(page).not.toHaveURL(/\/painel$/);
      } finally {
        await apagar(outro);
      }
    });
  });

async function excluirConta(page: Page): Promise<void> {
  await page.getByRole("link", { name: "Meu perfil" }).first().click();
  page.once("dialog", (d) => void d.accept());
  await page.getByRole("button", { name: "Excluir minha conta" }).click();
}

/** Sessao obtida por auth administrativa: isola o fluxo de compra da tela de login (testada a parte). */
async function sessaoInjetada(
  page: Page,
  request: import("@playwright/test").APIRequestContext,
  conta: Conta,
): Promise<void> {
  const cfg = await (await request.get("/config.json")).json();
  const sessao = await sessaoPorAdmin(conta, cfg.clientes.clientId);
  await page.addInitScript((s) => sessionStorage.setItem("revenda.sessao", s), sessao);
}

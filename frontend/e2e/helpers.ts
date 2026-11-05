import { expect, type Page } from "@playwright/test";
import { generate } from "otplib";
import { type Conta, SENHA, SENHA_TEMPORARIA } from "./environment";

export async function abrirLogin(page: Page, tipo: "cliente" | "funcionario"): Promise<void> {
  await page.goto("/entrar");
  await page
    .getByRole("tab", { name: tipo === "cliente" ? /Sou cliente/ : /Sou funcionário/ })
    .click();
}

export async function entrar(
  page: Page,
  tipo: "cliente" | "funcionario",
  email: string,
  senha: string,
): Promise<void> {
  await abrirLogin(page, tipo);
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(senha);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
}

/** Codigo TOTP de um passo a frente: evita a rejeicao de codigo repetido na mesma janela de 30 s. */
export const codigoTotp = (segredo: string, passos = 0): Promise<string> =>
  generate({ secret: segredo, epoch: Math.floor(Date.now() / 1000) + passos * 30 });

/** Primeiro acesso de funcionario: senha temporaria -> senha nova -> ativacao do MFA. Devolve o segredo TOTP. */
export async function primeiroAcesso(page: Page, conta: Conta): Promise<string> {
  await entrar(page, "funcionario", conta.email, SENHA_TEMPORARIA);
  await expect(page.getByRole("heading", { name: /Defina sua senha/ })).toBeVisible();
  await page.getByLabel("Nova senha").fill(SENHA);
  await page.getByRole("button", { name: "Salvar e continuar" }).click();
  await expect(page.getByRole("heading", { name: /Ative a verificação/ })).toBeVisible();
  await expect(page.getByLabel("QR code do autenticador")).toBeVisible();
  const segredo = (await page.getByTestId("chave-mfa").textContent())?.trim();
  if (!segredo) throw new Error("O autenticador não retornou o segredo TOTP.");
  await page.getByLabel("Código do aplicativo").fill(await codigoTotp(segredo));
  await page.getByRole("button", { name: "Ativar e entrar" }).click();
  await expect(page).toHaveURL(/\/painel$/);
  return segredo;
}

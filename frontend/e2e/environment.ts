import { randomBytes } from "node:crypto";
import {
  AdminAddUserToGroupCommand,
  AdminCreateUserCommand,
  AdminDeleteUserCommand,
  AdminSetUserPasswordCommand,
  CognitoIdentityProviderClient,
  ListUserPoolsCommand,
} from "@aws-sdk/client-cognito-identity-provider";

const cognito = new CognitoIdentityProviderClient({
  region: process.env.AWS_REGION ?? "us-east-1",
});

/** Senha efêmera gerada a cada execução (atende à política do Cognito); nada fica no repositório. */
const senhaAleatoria = (prefixo: string) => `${prefixo}#${randomBytes(12).toString("hex")}aA1`;

export const SENHA = process.env.E2E_SENHA ?? senhaAleatoria("E2e");
export const SENHA_TEMPORARIA = process.env.E2E_SENHA_TEMPORARIA ?? senhaAleatoria("Tmp");

export interface Conta {
  email: string;
  pool: string;
}

const pools: Record<string, string> = {};

/** Descobre o ID do pool pelo nome (revenda-dev-clientes / revenda-dev-funcionarios). */
async function poolId(tipo: "clientes" | "funcionarios"): Promise<string> {
  if (pools[tipo]) return pools[tipo];
  const r = await cognito.send(new ListUserPoolsCommand({ MaxResults: 20 }));
  const achado = r.UserPools?.find(
    (p) => p.Name?.endsWith(`-${tipo}`) && p.Name.startsWith("revenda"),
  );
  if (!achado?.Id)
    throw new Error(`Pool ${tipo} nao encontrado (credenciais AWS do ambiente configuradas?)`);
  pools[tipo] = achado.Id;
  return achado.Id;
}

const emailUnico = (prefixo: string) => `${prefixo}.${randomBytes(4).toString("hex")}@example.com`;

/** Cliente confirmado, com senha permanente (o cadastro por e-mail e coberto em outro teste). */
export async function criarCliente(): Promise<Conta> {
  const pool = await poolId("clientes");
  const email = emailUnico("e2e.cliente");
  await cognito.send(
    new AdminCreateUserCommand({
      UserPoolId: pool,
      Username: email,
      MessageAction: "SUPPRESS",
      UserAttributes: [
        { Name: "email", Value: email },
        { Name: "email_verified", Value: "true" },
      ],
    }),
  );
  await cognito.send(
    new AdminSetUserPasswordCommand({
      UserPoolId: pool,
      Username: email,
      Password: SENHA,
      Permanent: true,
    }),
  );
  return { email, pool };
}

/** Funcionario recem-convidado: senha temporaria, sem MFA (o primeiro acesso passa pela tela de login). */
export async function criarFuncionario(grupo: "vendedor" | "admin"): Promise<Conta> {
  const pool = await poolId("funcionarios");
  const email = emailUnico(`e2e.${grupo}`);
  await cognito.send(
    new AdminCreateUserCommand({
      UserPoolId: pool,
      Username: email,
      MessageAction: "SUPPRESS",
      TemporaryPassword: SENHA_TEMPORARIA,
      UserAttributes: [
        { Name: "email", Value: email },
        { Name: "email_verified", Value: "true" },
      ],
    }),
  );
  await cognito.send(
    new AdminAddUserToGroupCommand({ UserPoolId: pool, Username: email, GroupName: grupo }),
  );
  return { email, pool };
}

export async function confirmarCadastro(email: string): Promise<void> {
  const { AdminConfirmSignUpCommand } = await import("@aws-sdk/client-cognito-identity-provider");
  await cognito.send(
    new AdminConfirmSignUpCommand({ UserPoolId: await poolId("clientes"), Username: email }),
  );
}

export async function clienteDoPool(email: string): Promise<Conta> {
  return { email, pool: await poolId("clientes") };
}

export async function apagar(conta: Conta): Promise<void> {
  await cognito
    .send(new AdminDeleteUserCommand({ UserPoolId: conta.pool, Username: conta.email }))
    .catch(() => undefined);
}

/** CPF valido aleatorio (digitos verificadores calculados). */
export function cpfValido(): string {
  const base = Array.from({ length: 9 }, () => Math.floor(Math.random() * 10));
  if (new Set(base).size === 1) base[0] = ((base[0] ?? 0) + 1) % 10;
  const dv = (d: number[]) => {
    const soma = d.reduce((s, n, i) => s + n * (d.length + 1 - i), 0);
    const r = (soma * 10) % 11;
    return r === 10 ? 0 : r;
  };
  const d1 = dv(base);
  const d2 = dv([...base, d1]);
  const n = [...base, d1, d2].join("");
  return `${n.slice(0, 3)}.${n.slice(3, 6)}.${n.slice(6, 9)}-${n.slice(9)}`;
}

/** Sessao de cliente obtida por auth administrativa (sem passar pela tela de login): isola o que se testa. */
export async function sessaoPorAdmin(
  conta: Conta,
  clientId: string,
  senha = SENHA,
): Promise<string> {
  const { AdminInitiateAuthCommand } = await import("@aws-sdk/client-cognito-identity-provider");
  const r = await cognito.send(
    new AdminInitiateAuthCommand({
      UserPoolId: conta.pool,
      ClientId: clientId,
      AuthFlow: "ADMIN_USER_PASSWORD_AUTH",
      AuthParameters: { USERNAME: conta.email, PASSWORD: senha },
    }),
  );
  const a = r.AuthenticationResult;
  if (!a?.AccessToken) throw new Error("Cognito não retornou uma sessão autenticada.");
  return JSON.stringify({
    accessToken: a.AccessToken,
    refreshToken: a.RefreshToken,
    expiraEm: Date.now() + (a.ExpiresIn ?? 3600) * 1000,
    pool: "clientes",
  });
}

/** RENAVAM valido (11 digitos com digito verificador). */
export function renavamValido(): string {
  const base = Array.from({ length: 10 }, () => Math.floor(Math.random() * 10)).join("");
  const pesos = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3];
  const soma = [...base].reverse().reduce((s, d, i) => s + Number(d) * (pesos[i] ?? 0), 0);
  const r = (soma * 10) % 11;
  return `${base}${r === 10 ? 0 : r}`;
}

/** Chassi valido e unico (17 caracteres, sem I, O e Q). */
export function chassiUnico(): string {
  const letras = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789";
  return Array.from({ length: 17 }, () => letras[Math.floor(Math.random() * letras.length)]).join(
    "",
  );
}

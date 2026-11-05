// Cliente minimo da API publica do Cognito (sem SDK): login por senha, desafios (nova senha, MFA TOTP),
// cadastro com codigo por e-mail e recuperacao de senha. So os app clients publicos sao usados (sem segredo).

import type { Sessao, TipoPool } from "./auth";
import { config } from "./config";
import { ehObjeto } from "./json";

export class ErroCognito extends Error {
  constructor(
    public codigo: string,
    mensagem: string,
  ) {
    super(mensagem);
  }
}

const MENSAGENS: Record<string, string> = {
  NotAuthorizedException: "E-mail ou senha incorretos.",
  UserNotFoundException: "E-mail ou senha incorretos.",
  UserNotConfirmedException: "Confirme seu e-mail para entrar.",
  PasswordResetRequiredException: "É preciso redefinir sua senha.",
  InvalidPasswordException: "A senha não atende à política de segurança.",
  UsernameExistsException: "Já existe uma conta com este e-mail.",
  CodeMismatchException: "Código inválido. Confira e tente de novo.",
  ExpiredCodeException: "O código expirou. Solicite um novo.",
  EnableSoftwareTokenMFAException: "Código inválido. Confira o aplicativo autenticador.",
  LimitExceededException: "Muitas tentativas. Aguarde alguns minutos.",
  TooManyRequestsException: "Muitas tentativas. Aguarde alguns minutos.",
  InvalidParameterException: "Dados inválidos. Revise os campos.",
};

type Json = Record<string, unknown>;

const ESPERA_REPETICAO_MS = 400;

const endpoint = (): string => `https://cognito-idp.${config().regiao}.amazonaws.com/`;
const TENTATIVAS_PROPAGACAO = 6;

async function chamar<T = Json>(
  operacao: string,
  corpo: Json,
  buscar: typeof fetch = (...a) => fetch(...a),
): Promise<T> {
  let r: Response;
  let dados: Json = {};
  // Depois que um fluxo de login e habilitado no app client, os servidores do Cognito levam um tempo para convergir e
  // alguns respondem "flow not enabled for this client": repete a chamada (so para essa resposta) ate um servidor atualizado atender.
  for (let tentativa = 1; ; tentativa++) {
    try {
      r = await buscar(endpoint(), {
        method: "POST",
        headers: {
          "Content-Type": "application/x-amz-json-1.1",
          "X-Amz-Target": `AWSCognitoIdentityProviderService.${operacao}`,
        },
        body: JSON.stringify(corpo),
      });
    } catch {
      throw new ErroCognito(
        "ErroDeRede",
        "Não foi possível conectar. Verifique sua conexão e tente de novo.",
      );
    }
    const bruto: unknown = await r.json().catch(() => null);
    if (r.ok && !ehObjeto(bruto)) throw respostaInvalida();
    dados = ehObjeto(bruto) ? bruto : {};
    const propagando =
      !r.ok && /flow not enabled for this client/i.test(String(dados.message ?? ""));
    if (!propagando || tentativa >= TENTATIVAS_PROPAGACAO) break;
    await new Promise((ok) => setTimeout(ok, ESPERA_REPETICAO_MS));
  }
  if (!r.ok) {
    const codigo =
      String(dados.__type ?? "Erro")
        .split("#")
        .pop() ?? "Erro";
    if (r.status >= 500 && !dados.__type)
      throw new ErroCognito(
        "ServicoIndisponivel",
        "O serviço de login está indisponível no momento. Tente de novo em instantes.",
      );
    throw new ErroCognito(
      codigo,
      MENSAGENS[codigo] ??
        (codigo === "InvalidPasswordException"
          ? (MENSAGENS.InvalidPasswordException ?? "Senha inválida.")
          : String(dados.message ?? "Não foi possível concluir a operação.")),
    );
  }
  return dados as T;
}

export type Desafio =
  | { tipo: "novaSenha"; sessao: string; usuario: string }
  | { tipo: "mfaSetup"; sessao: string; usuario: string }
  | { tipo: "mfaCodigo"; sessao: string; usuario: string };

export type ResultadoLogin = { sessao: Sessao } | { desafio: Desafio };

interface RespostaAuth {
  AuthenticationResult?: {
    AccessToken: string;
    IdToken?: string;
    RefreshToken?: string;
    ExpiresIn: number;
  };
  ChallengeName?: string;
  ChallengeParameters?: Record<string, string>;
  Session?: string;
}

const clientId = (pool: TipoPool): string => config()[pool].clientId;

function interpretar(pool: TipoPool, r: RespostaAuth, email: string): ResultadoLogin {
  if (r.AuthenticationResult) {
    return { sessao: montarSessao(pool, r.AuthenticationResult) };
  }
  const usuario = r.ChallengeParameters?.USER_ID_FOR_SRP ?? email;
  const sessao = r.Session ?? "";
  const tipos: Record<string, Desafio["tipo"]> = {
    NEW_PASSWORD_REQUIRED: "novaSenha",
    MFA_SETUP: "mfaSetup",
    SOFTWARE_TOKEN_MFA: "mfaCodigo",
  };
  const tipo = tipos[r.ChallengeName ?? ""];
  if (!tipo)
    throw new ErroCognito("DesafioNaoSuportado", "Este tipo de verificação não é suportado.");
  return { desafio: { tipo, sessao, usuario } };
}

export async function entrar(
  pool: TipoPool,
  email: string,
  senha: string,
  buscar?: typeof fetch,
): Promise<ResultadoLogin> {
  const r = await chamar<RespostaAuth>(
    "InitiateAuth",
    {
      AuthFlow: "USER_PASSWORD_AUTH",
      ClientId: clientId(pool),
      AuthParameters: { USERNAME: email.trim(), PASSWORD: senha },
    },
    buscar,
  );
  return interpretar(pool, r, email.trim());
}

export async function responder(
  pool: TipoPool,
  d: Desafio,
  resposta: Record<string, string>,
  buscar?: typeof fetch,
): Promise<ResultadoLogin> {
  const nome = {
    novaSenha: "NEW_PASSWORD_REQUIRED",
    mfaSetup: "MFA_SETUP",
    mfaCodigo: "SOFTWARE_TOKEN_MFA",
  }[d.tipo];
  const r = await chamar<RespostaAuth>(
    "RespondToAuthChallenge",
    {
      ClientId: clientId(pool),
      ChallengeName: nome,
      Session: d.sessao,
      ChallengeResponses: { USERNAME: d.usuario, ...resposta },
    },
    buscar,
  );
  return interpretar(pool, r, d.usuario);
}

export const responderNovaSenha = (
  pool: TipoPool,
  d: Desafio,
  novaSenha: string,
  buscar?: typeof fetch,
) => responder(pool, d, { NEW_PASSWORD: novaSenha }, buscar);
export const responderMfa = (pool: TipoPool, d: Desafio, codigo: string, buscar?: typeof fetch) =>
  responder(pool, d, { SOFTWARE_TOKEN_MFA_CODE: codigo.trim() }, buscar);

/** Gera a chave do autenticador (TOTP) durante o MFA_SETUP; devolve a sessao a usar na verificacao. */
export async function iniciarMfa(
  d: Desafio,
  buscar?: typeof fetch,
): Promise<{ segredo: string; sessao: string }> {
  const r = await chamar<{ SecretCode: string; Session: string }>(
    "AssociateSoftwareToken",
    { Session: d.sessao },
    buscar,
  );
  return { segredo: r.SecretCode, sessao: r.Session };
}

/** Confere o primeiro codigo do autenticador e conclui o MFA_SETUP (devolve a sessao autenticada). */
export async function concluirMfa(
  pool: TipoPool,
  d: Desafio,
  sessaoMfa: string,
  codigo: string,
  buscar?: typeof fetch,
): Promise<ResultadoLogin> {
  const v = await chamar<{ Session: string }>(
    "VerifySoftwareToken",
    { Session: sessaoMfa, UserCode: codigo.trim(), FriendlyDeviceName: "Revenda" },
    buscar,
  );
  return responder(pool, { ...d, sessao: v.Session }, {}, buscar);
}

export async function renovarToken(
  pool: TipoPool,
  refreshToken: string,
  buscar?: typeof fetch,
): Promise<Sessao> {
  const r = await chamar<RespostaAuth>(
    "InitiateAuth",
    {
      AuthFlow: "REFRESH_TOKEN_AUTH",
      ClientId: clientId(pool),
      AuthParameters: { REFRESH_TOKEN: refreshToken },
    },
    buscar,
  );
  const a = r.AuthenticationResult;
  if (!a)
    throw new ErroCognito(
      "NotAuthorizedException",
      MENSAGENS.NotAuthorizedException ?? "Sessão expirada.",
    );
  return montarSessao(pool, a, refreshToken);
}

export async function revogar(
  pool: TipoPool,
  refreshToken: string,
  buscar?: typeof fetch,
): Promise<void> {
  await chamar("RevokeToken", { ClientId: clientId(pool), Token: refreshToken }, buscar).catch(
    () => undefined,
  );
}

export const cadastrar = (email: string, senha: string, buscar?: typeof fetch) =>
  chamar(
    "SignUp",
    {
      ClientId: clientId("clientes"),
      Username: email.trim(),
      Password: senha,
      UserAttributes: [{ Name: "email", Value: email.trim() }],
    },
    buscar,
  );

export const confirmarCadastro = (email: string, codigo: string, buscar?: typeof fetch) =>
  chamar(
    "ConfirmSignUp",
    { ClientId: clientId("clientes"), Username: email.trim(), ConfirmationCode: codigo.trim() },
    buscar,
  );

export const reenviarCodigo = (email: string, buscar?: typeof fetch) =>
  chamar(
    "ResendConfirmationCode",
    { ClientId: clientId("clientes"), Username: email.trim() },
    buscar,
  );

export const esqueciSenha = (pool: TipoPool, email: string, buscar?: typeof fetch) =>
  chamar("ForgotPassword", { ClientId: clientId(pool), Username: email.trim() }, buscar);

export const redefinirSenha = (
  pool: TipoPool,
  email: string,
  codigo: string,
  senha: string,
  buscar?: typeof fetch,
) =>
  chamar(
    "ConfirmForgotPassword",
    {
      ClientId: clientId(pool),
      Username: email.trim(),
      ConfirmationCode: codigo.trim(),
      Password: senha,
    },
    buscar,
  );

function respostaInvalida(): ErroCognito {
  return new ErroCognito("RespostaInvalida", "O serviço de login retornou uma resposta inválida.");
}

function montarSessao(pool: TipoPool, valor: unknown, refreshToken?: string): Sessao {
  if (
    !ehObjeto(valor) ||
    typeof valor.AccessToken !== "string" ||
    !valor.AccessToken ||
    typeof valor.ExpiresIn !== "number" ||
    !Number.isFinite(valor.ExpiresIn) ||
    valor.ExpiresIn <= 0 ||
    (valor.IdToken !== undefined && typeof valor.IdToken !== "string") ||
    (valor.RefreshToken !== undefined && typeof valor.RefreshToken !== "string")
  )
    throw respostaInvalida();
  const renovacao = typeof valor.RefreshToken === "string" ? valor.RefreshToken : refreshToken;
  return {
    accessToken: valor.AccessToken,
    expiraEm: Date.now() + valor.ExpiresIn * 1000,
    pool,
    ...(typeof valor.IdToken === "string" ? { idToken: valor.IdToken } : {}),
    ...(renovacao ? { refreshToken: renovacao } : {}),
  };
}

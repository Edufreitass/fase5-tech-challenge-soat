import { renovarToken, revogar } from "./cognito";
import { config } from "./config";
import { ehListaDeTextos, ehObjeto } from "./json";

export type TipoPool = "clientes" | "funcionarios";

export interface Sessao {
  accessToken: string;
  idToken?: string;
  refreshToken?: string;
  expiraEm: number;
  pool: TipoPool;
}

const CHAVE_SESSAO = "revenda.sessao";

function guardar(chave: string, valor: unknown | null): void {
  try {
    if (valor === null) sessionStorage.removeItem(chave);
    else sessionStorage.setItem(chave, JSON.stringify(valor));
  } catch {
    /* armazenamento indisponivel: a sessao dura so a aba */
  }
}

function ler(chave: string): unknown {
  try {
    const bruto = sessionStorage.getItem(chave);
    return bruto ? (JSON.parse(bruto) as unknown) : null;
  } catch {
    return null;
  }
}

export function lerSessao(): Sessao | null {
  const valor = ler(CHAVE_SESSAO);
  if (
    !ehObjeto(valor) ||
    typeof valor.accessToken !== "string" ||
    !valor.accessToken ||
    typeof valor.expiraEm !== "number" ||
    !Number.isFinite(valor.expiraEm) ||
    (valor.pool !== "clientes" && valor.pool !== "funcionarios") ||
    (valor.refreshToken !== undefined && typeof valor.refreshToken !== "string") ||
    (valor.idToken !== undefined && typeof valor.idToken !== "string")
  )
    return null;
  return {
    accessToken: valor.accessToken,
    expiraEm: valor.expiraEm,
    pool: valor.pool,
    ...(typeof valor.refreshToken === "string" ? { refreshToken: valor.refreshToken } : {}),
    ...(typeof valor.idToken === "string" ? { idToken: valor.idToken } : {}),
  };
}

const CHAVE_AVISO = "revenda.aviso-login";

/** Recado de uma vez para a tela de login (ex.: conta excluida). Sobrevive ao redirecionamento das rotas protegidas. */
export const avisarNoLogin = (texto: string): void => guardar(CHAVE_AVISO, texto);

export function consumirAvisoDoLogin(): string | null {
  const texto = ler(CHAVE_AVISO);
  guardar(CHAVE_AVISO, null);
  return typeof texto === "string" ? texto : null;
}
export const salvarSessao = (s: Sessao | null): void => guardar(CHAVE_SESSAO, s);

/** Renova o access token com o refresh token; null se nao for possivel (o usuario precisa entrar de novo). */
export async function renovar(sessao: Sessao, buscar?: typeof fetch): Promise<Sessao | null> {
  if (!sessao.refreshToken) return null;
  try {
    const nova = await renovarToken(sessao.pool, sessao.refreshToken, buscar);
    salvarSessao(nova);
    return nova;
  } catch {
    return null;
  }
}

/** Encerra a sessao local e revoga o refresh token no Cognito. */
export async function sair(sessao: Sessao | null): Promise<void> {
  salvarSessao(null);
  if (sessao?.refreshToken) await revogar(sessao.pool, sessao.refreshToken);
}

export interface Claims {
  sub?: string;
  "cognito:groups"?: string[];
  username?: string;
  email?: string;
  name?: string;
}

/** Decodifica dados de exibicao; autorizacao e assinatura sao verificadas pela API. */
export function claims(token: string): Claims {
  try {
    const segmento = token.split(".")[1];
    if (!segmento) return {};
    const carga = segmento.replaceAll("-", "+").replaceAll("_", "/");
    const bytes = Uint8Array.from(atob(carga), (caractere) => caractere.charCodeAt(0));
    const valor: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    if (!ehObjeto(valor)) return {};
    const resultado: Claims = {};
    for (const campo of ["sub", "username", "email", "name"] as const) {
      if (typeof valor[campo] === "string") resultado[campo] = valor[campo];
    }
    if (ehListaDeTextos(valor["cognito:groups"]))
      resultado["cognito:groups"] = valor["cognito:groups"];
    return resultado;
  } catch {
    return {};
  }
}

export type Papel = "cliente" | "vendedor" | "admin";

export function papelDe(sessao: Sessao | null): Papel | null {
  if (!sessao) return null;
  if (sessao.pool === "clientes") return "cliente";
  const grupos = claims(sessao.accessToken)["cognito:groups"] ?? [];
  if (grupos.includes("admin")) return "admin";
  return grupos.includes("vendedor") ? "vendedor" : null;
}

export const poolDe = (pool: TipoPool) => config()[pool];

/** Nome para exibir: `name` do ID token (funcionarios) ou a parte local do e-mail. */
export function identificacaoDe(sessao: Sessao | null): { nome: string; email: string } | null {
  if (!sessao) return null;
  const c = sessao.idToken ? claims(sessao.idToken) : {};
  const email = c.email ?? "";
  return { nome: c.name?.trim() || (email ? (email.split("@")[0] ?? "") : ""), email };
}

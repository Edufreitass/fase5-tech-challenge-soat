import { avisarNoLogin, lerSessao, renovar, type Sessao, salvarSessao } from "./auth";
import { config } from "./config";
import { ehObjeto } from "./json";

export class ErroApi extends Error {
  constructor(
    public status: number,
    public titulo: string,
    public detalhe?: string,
    public campos: { campo?: string; mensagem?: string }[] = [],
    public retryAfter?: number,
    public tipo?: string,
  ) {
    super(detalhe ?? titulo);
  }
}

export interface Resposta<T> {
  dados: T;
  etag: string | null;
}

export interface Contexto {
  sessao: () => Sessao | null;
  atualizar: (s: Sessao | null) => void;
  buscar?: typeof fetch;
}

// O padrao ja le a sessao guardada: efeitos das paginas rodam antes do efeito do AuthProvider que chama definirContexto,
// e sem isso a primeira requisicao de um carregamento completo sairia sem token.
let contexto: Contexto = { sessao: lerSessao, atualizar: salvarSessao };
export const definirContexto = (c: Contexto): void => {
  contexto = c;
};

interface Opcoes {
  metodo?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  corpo?: unknown;
  consulta?: Record<string, string | number | undefined | null>;
  ifMatch?: string | null;
  autenticado?: boolean;
}

export function montarUrl(caminho: string, consulta: Opcoes["consulta"] = {}): string {
  const q = new URLSearchParams();
  Object.entries(consulta).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  });
  const s = q.toString();
  return `${config().apiBase}${caminho}${s ? `?${s}` : ""}`;
}

export const SEM_CONEXAO =
  "Não foi possível conectar ao servidor. Verifique sua conexão e tente de novo.";
export const SERVICO_INDISPONIVEL =
  "O serviço está indisponível no momento. Tente de novo em instantes.";

async function enviar(url: string, o: Opcoes, token: string | null): Promise<Response> {
  try {
    return await buscarSemTratar(url, o, token);
  } catch {
    // fetch so rejeita em falha de rede (offline, DNS, CORS): a mensagem do navegador ("Failed to fetch") nao serve.
    throw new ErroApi(0, "Sem conexão", SEM_CONEXAO);
  }
}

function buscarSemTratar(url: string, o: Opcoes, token: string | null): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (o.corpo !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  if (o.ifMatch) headers["If-Match"] = o.ifMatch;
  return (contexto.buscar ?? fetch)(url, {
    method: o.metodo ?? "GET",
    headers,
    body: o.corpo === undefined ? undefined : JSON.stringify(o.corpo),
  });
}

/** Renova o token; se nao der, encerra a sessao e deixa o motivo para a tela de login (para onde a rota leva). */
async function renovarOuSair(sessao: Sessao): Promise<Sessao | null> {
  const nova = await renovar(sessao, contexto.buscar);
  if (!nova) avisarNoLogin("Sua sessão expirou. Entre novamente para continuar.");
  contexto.atualizar(nova);
  return nova;
}

export async function chamar<T>(caminho: string, o: Opcoes = {}): Promise<Resposta<T>> {
  const url = montarUrl(caminho, o.consulta);
  let sessao = o.autenticado === false ? null : contexto.sessao();
  if (sessao && sessao.expiraEm - Date.now() < 30_000) {
    const nova = await renovarOuSair(sessao);
    sessao = nova;
    if (!nova) throw new ErroApi(401, "Sessão expirada", "Entre novamente.");
  }
  let r = await enviar(url, o, sessao?.accessToken ?? null);
  if (r.status === 401 && sessao) {
    const nova = await renovarOuSair(sessao);
    if (nova) r = await enviar(url, o, nova.accessToken);
  }
  if (!r.ok) throw await converterErro(r);
  const texto = await r.text();
  try {
    return { dados: (texto ? JSON.parse(texto) : null) as T, etag: r.headers.get("ETag") };
  } catch {
    throw new ErroApi(
      502,
      "Resposta inválida",
      "O servidor retornou uma resposta inválida. Tente novamente.",
    );
  }
}

interface ErroCampo {
  campo?: string;
  mensagem?: string;
}

function ehErroCampo(valor: unknown): valor is ErroCampo {
  return (
    ehObjeto(valor) &&
    (valor.campo === undefined || typeof valor.campo === "string") &&
    (valor.mensagem === undefined || typeof valor.mensagem === "string")
  );
}

async function converterErro(r: Response): Promise<ErroApi> {
  const bruto: unknown = await r.json().catch(() => null);
  const problema = ehObjeto(bruto) ? bruto : {};
  const titulo = typeof problema.title === "string" ? problema.title : undefined;
  const detalhe =
    typeof problema.detail === "string"
      ? problema.detail
      : r.status >= 500 && !titulo
        ? SERVICO_INDISPONIVEL
        : undefined;
  const erros = problema.erros ?? problema.errors;
  const campos = Array.isArray(erros) ? erros.filter(ehErroCampo) : [];
  const espera = Number(r.headers.get("Retry-After"));
  const tipo = typeof problema.type === "string" ? problema.type.split(":").pop() : undefined;
  return new ErroApi(
    r.status,
    titulo ?? `Erro ${r.status}`,
    detalhe,
    campos,
    Number.isFinite(espera) && espera > 0 ? espera : undefined,
    tipo,
  );
}

export const obter = <T>(c: string, consulta?: Opcoes["consulta"], autenticado = true) =>
  chamar<T>(c, { consulta, autenticado });
export const enviarJson = <T>(
  c: string,
  corpo: unknown,
  metodo: "POST" | "PATCH" = "POST",
  ifMatch?: string | null,
) => chamar<T>(c, { metodo, corpo, ifMatch });
export const remover = <T>(c: string) => chamar<T>(c, { metodo: "DELETE" });

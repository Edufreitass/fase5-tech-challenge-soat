import { ehObjeto } from "./json";

export interface PoolConfig {
  clientId: string;
  dominio: string;
}

export interface Config {
  apiBase: string;
  versaoTermo: string;
  regiao: string;
  clientes: PoolConfig;
  funcionarios: PoolConfig;
}

let atual: Config | null = null;

/** Le /config.json (gerado pelo Terraform, so com IDs publicos). */
export async function carregarConfig(
  buscar: typeof fetch = (...a) => fetch(...a),
): Promise<Config> {
  const r = await buscar("/config.json", { cache: "no-store" });
  if (!r.ok) throw new Error("Configuração do ambiente indisponível.");
  const dados: unknown = await r.json();
  if (
    !ehObjeto(dados) ||
    typeof dados.apiBase !== "string" ||
    typeof dados.versaoTermo !== "string" ||
    typeof dados.regiao !== "string" ||
    !ehPool(dados.clientes) ||
    !ehPool(dados.funcionarios)
  ) {
    throw new Error("Configuração do ambiente inválida.");
  }
  atual = {
    apiBase: dados.apiBase,
    versaoTermo: dados.versaoTermo,
    regiao: dados.regiao,
    clientes: dados.clientes,
    funcionarios: dados.funcionarios,
  };
  return atual;
}

export function config(): Config {
  if (!atual) throw new Error("Configuracao ainda nao carregada.");
  return atual;
}

export function definirConfig(c: Config | null): void {
  atual = c;
}

function ehPool(valor: unknown): valor is PoolConfig {
  return ehObjeto(valor) && typeof valor.clientId === "string" && typeof valor.dominio === "string";
}

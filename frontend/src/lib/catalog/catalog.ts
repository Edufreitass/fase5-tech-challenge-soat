import { obter } from "../api";
import type { Pagina, Veiculo } from "../types";

export const POR_PAGINA = 10;

export interface Filtros {
  busca: string;
  marca: string;
  modelo: string;
  cor: string;
  combustivel: string;
  cambio: string;
  anoMin: string;
  anoMax: string;
  precoMin: string;
  precoMax: string;
  ordem: "preco_asc" | "preco_desc" | "ano_desc" | "km_asc";
}

export const FILTROS_VAZIOS: Filtros = {
  busca: "",
  marca: "",
  modelo: "",
  cor: "",
  combustivel: "",
  cambio: "",
  anoMin: "",
  anoMax: "",
  precoMin: "",
  precoMax: "",
  ordem: "preco_asc",
};

/** Le todas as paginas de uma listagem (50 por chamada, ate 10 chamadas); a tela pagina em memoria. */
export async function lerTodas<T>(
  caminho: string,
  consulta: Record<string, string | number | undefined> = {},
  autenticado = true,
): Promise<T[]> {
  const todos: T[] = [];
  let token: string | null = null;
  for (let i = 0; i < 10; i++) {
    const { dados }: { dados: Pagina<T> } = await obter<Pagina<T>>(
      caminho,
      { ...consulta, limit: 50, nextToken: token },
      autenticado,
    );
    todos.push(...dados.itens);
    token = dados.nextToken ?? null;
    if (!token) break;
  }
  return todos;
}

export const carregarTodos = (): Promise<Veiculo[]> => lerTodas<Veiculo>("/veiculos", {}, false);

const unicos = <T>(v: T[]): T[] => [...new Set(v)];
const ordenarTexto = (v: string[]) => v.sort((a, b) => a.localeCompare(b, "pt-BR"));

export interface Opcoes {
  marcas: string[];
  modelos: string[];
  cores: string[];
  combustiveis: string[];
  cambios: string[];
  anos: number[];
  precos: number[];
}

/** Opcoes das listas de selecao, derivadas do estoque. Marca vem de todo o estoque; modelo depende da marca; as demais
 * listas so trazem o que existe na marca/modelo escolhidos (sem combinacoes que dariam zero resultados). */
export function opcoesDe(veiculos: Veiculo[], marca = "", modelo = ""): Opcoes {
  const daMarca = marca ? veiculos.filter((v) => v.marca === marca) : veiculos;
  const base = modelo ? daMarca.filter((v) => v.modelo === modelo) : daMarca;
  const anos = unicos(base.map((v) => v.anoModelo)).sort((a, b) => a - b);
  const maior = Math.max(0, ...base.map((v) => Number(v.preco)));
  const passo = maior > 300_000 ? 50_000 : 10_000;
  const precos: number[] = [];
  for (let p = passo; p <= Math.ceil(maior / passo) * passo; p += passo) precos.push(p);
  return {
    marcas: ordenarTexto(unicos(veiculos.map((v) => v.marca))),
    modelos: ordenarTexto(unicos(daMarca.map((v) => v.modelo))),
    cores: ordenarTexto(unicos(base.map((v) => v.cor))),
    combustiveis: ordenarTexto(unicos(base.map((v) => v.combustivel ?? "").filter(Boolean))),
    cambios: ordenarTexto(unicos(base.map((v) => v.cambio ?? "").filter(Boolean))),
    anos,
    precos,
  };
}

const ORDENS: Filtros["ordem"][] = ["preco_asc", "preco_desc", "ano_desc", "km_asc"];

/** Descarta valores que nao existem nas listas (URL editada a mao, estoque que mudou, marca trocada): o filtro aplicado
 * e sempre o que o select mostra. Sem estoque carregado, so a ordem e validada. */
export function normalizar(f: Filtros, veiculos: Veiculo[] | null): Filtros {
  const ordem = ORDENS.includes(f.ordem) ? f.ordem : FILTROS_VAZIOS.ordem;
  if (!veiculos) return { ...f, ordem };
  const em = (valor: string, lista: (string | number)[]) =>
    lista.map(String).includes(valor) ? valor : "";
  const marca = em(f.marca, opcoesDe(veiculos).marcas);
  const modelo = em(f.modelo, opcoesDe(veiculos, marca).modelos);
  const o = opcoesDe(veiculos, marca, modelo);
  return {
    busca: f.busca,
    marca,
    modelo,
    ordem,
    cor: em(f.cor, o.cores),
    combustivel: em(f.combustivel, o.combustiveis),
    cambio: em(f.cambio, o.cambios),
    anoMin: em(f.anoMin, o.anos),
    anoMax: em(f.anoMax, o.anos),
    precoMin: em(f.precoMin, o.precos),
    precoMax: em(f.precoMax, o.precos),
  };
}

/** Filtros + pagina <-> query string (so o que difere do padrao). */
export function paraQuery(f: Filtros, numero = 1): URLSearchParams {
  const q = new URLSearchParams();
  (Object.entries(f) as [keyof Filtros, string][]).forEach(([k, v]) => {
    if (v && v !== FILTROS_VAZIOS[k]) q.set(k, v);
  });
  if (numero > 1) q.set("pagina", String(numero));
  return q;
}

export function daQuery(q: URLSearchParams): { filtros: Filtros; numero: number } {
  const filtros = { ...FILTROS_VAZIOS };
  (Object.keys(filtros) as (keyof Filtros)[]).forEach((k) => {
    const v = q.get(k);
    if (v) (filtros as Record<string, string>)[k] = v;
  });
  return { filtros, numero: Math.max(1, Math.floor(Number(q.get("pagina"))) || 1) };
}

/** Erros de coerencia entre filtros (faixas invertidas ou valores negativos). */
export function validarFiltros(f: Filtros): string | null {
  const num = (t: string) => (t === "" ? null : Number(t));
  const pMin = num(f.precoMin);
  const pMax = num(f.precoMax);
  const aMin = num(f.anoMin);
  const aMax = num(f.anoMax);
  if ([pMin, pMax, aMin, aMax].some((n) => n !== null && (!Number.isFinite(n) || n < 0)))
    return "Os valores dos filtros não podem ser negativos.";
  if (pMin !== null && pMax !== null && pMin > pMax)
    return "O preço mínimo não pode ser maior que o máximo.";
  if (aMin !== null && aMax !== null && aMin > aMax)
    return "O ano mínimo não pode ser maior que o máximo.";
  return null;
}

export function filtrar(veiculos: Veiculo[], f: Filtros): Veiculo[] {
  const termo = (f.busca ?? "")
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR");
  const lista = veiculos.filter(
    (v) =>
      (!termo ||
        `${v.marca} ${v.modelo} ${v.cor}`
          .normalize("NFD")
          .replace(/[\u0300-\u036f]/g, "")
          .toLocaleLowerCase("pt-BR")
          .includes(termo)) &&
      (!f.marca || v.marca === f.marca) &&
      (!f.modelo || v.modelo === f.modelo) &&
      (!f.cor || v.cor === f.cor) &&
      (!f.combustivel || v.combustivel === f.combustivel) &&
      (!f.cambio || v.cambio === f.cambio) &&
      (!f.anoMin || v.anoModelo >= Number(f.anoMin)) &&
      (!f.anoMax || v.anoModelo <= Number(f.anoMax)) &&
      (!f.precoMin || Number(v.preco) >= Number(f.precoMin)) &&
      (!f.precoMax || Number(v.preco) <= Number(f.precoMax)),
  );
  const chave: Record<Filtros["ordem"], (a: Veiculo, b: Veiculo) => number> = {
    preco_asc: (a, b) => Number(a.preco) - Number(b.preco),
    preco_desc: (a, b) => Number(b.preco) - Number(a.preco),
    ano_desc: (a, b) => b.anoModelo - a.anoModelo || Number(a.preco) - Number(b.preco),
    km_asc: (a, b) => a.quilometragem - b.quilometragem,
  };
  return [...lista].sort(chave[f.ordem]);
}

export function pagina<T>(
  itens: T[],
  numero: number,
  tamanho = POR_PAGINA,
): { itens: T[]; total: number; paginas: number; atual: number } {
  const paginas = Math.max(1, Math.ceil(itens.length / tamanho));
  const atual = Math.min(Math.max(1, numero), paginas);
  return {
    itens: itens.slice((atual - 1) * tamanho, atual * tamanho),
    total: itens.length,
    paginas,
    atual,
  };
}

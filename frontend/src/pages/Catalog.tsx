import { Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { Aviso, Carregando, Paginacao, Selecao, Titulo } from "../components/ui";
import { VeiculoCard } from "../components/VehicleCard";
import {
  carregarTodos,
  daQuery,
  FILTROS_VAZIOS,
  type Filtros,
  filtrar,
  normalizar,
  opcoesDe,
  POR_PAGINA,
  pagina,
  paraQuery,
  validarFiltros,
} from "../lib/catalog/catalog";
import { moeda, titulo } from "../lib/formatters/format";
import { mensagemDe } from "../lib/hooks/use";
import type { Veiculo } from "../lib/types";

const ORDENS = [
  { valor: "preco_asc", rotulo: "Menor preço" },
  { valor: "preco_desc", rotulo: "Maior preço" },
  { valor: "ano_desc", rotulo: "Mais novos" },
  { valor: "km_asc", rotulo: "Menor quilometragem" },
];

export function Catalogo() {
  // A URL e a fonte da verdade dos filtros e da pagina: links, voltar/avancar e F5 mostram sempre o mesmo resultado.
  const [q, setQ] = useSearchParams();
  const [todos, setTodos] = useState<Veiculo[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [abertos, setAbertos] = useState(false);
  const chave = q.toString();
  const { filtros, numero } = useMemo(() => {
    const lido = daQuery(new URLSearchParams(chave));
    return { filtros: normalizar(lido.filtros, todos), numero: lido.numero };
  }, [chave, todos]);

  useEffect(() => {
    let ativo = true;
    void carregarTodos()
      .then((dados) => {
        if (ativo) setTodos(dados);
      })
      .catch((e: unknown) => {
        if (ativo) setErro(mensagemDe(e));
      });
    return () => {
      ativo = false;
    };
  }, []);

  const opcoes = useMemo(
    () => opcoesDe(todos ?? [], filtros.marca, filtros.modelo),
    [todos, filtros.marca, filtros.modelo],
  );
  const problema = validarFiltros(filtros);
  const resultado = useMemo(
    () => pagina(problema ? [] : filtrar(todos ?? [], filtros), numero),
    [todos, filtros, numero, problema],
  );

  // Valores da URL que nao existem nas listas (e pagina alem da ultima) sao corrigidos tambem na URL.
  useEffect(() => {
    const limpa = paraQuery(filtros, resultado.atual).toString();
    if (todos && limpa !== chave) setQ(new URLSearchParams(limpa), { replace: true });
  }, [todos, filtros, resultado.atual, chave, setQ]);

  function mudar(parcial: Partial<Filtros>) {
    const novo = { ...filtros, ...parcial };
    if ("marca" in parcial) novo.modelo = ""; // o modelo depende da marca
    setQ(paraQuery(normalizar(novo, todos)), { replace: true });
  }

  function irParaPagina(p: number) {
    setQ(paraQuery(filtros, p));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const lista = (valores: string[]) => valores.map((v) => ({ valor: v, rotulo: v }));
  const ativos = (Object.keys(FILTROS_VAZIOS) as (keyof Filtros)[]).filter(
    (k) => k !== "ordem" && filtros[k],
  ).length;
  const alterados = ativos + (filtros.ordem !== FILTROS_VAZIOS.ordem ? 1 : 0);
  const avancados = (Object.keys(FILTROS_VAZIOS) as (keyof Filtros)[]).filter(
    (k) => ["modelo", "cor", "anoMin", "anoMax", "combustivel", "cambio"].includes(k) && filtros[k],
  ).length;
  const nomes: Record<keyof Filtros, string> = {
    busca: "Busca",
    marca: "Marca",
    modelo: "Modelo",
    cor: "Cor",
    combustivel: "Combustível",
    cambio: "Câmbio",
    anoMin: "Ano desde",
    anoMax: "Ano até",
    precoMin: "Preço desde",
    precoMax: "Preço até",
    ordem: "Ordenação",
  };
  const rotuloFiltro = (k: keyof Filtros) => {
    if (k === "precoMin" || k === "precoMax") return moeda(Number(filtros[k])).replace(",00", "");
    return filtros[k];
  };
  const faixa = (id: string, rotulo: string, k: "precoMin" | "precoMax") => (
    <Selecao
      id={id}
      rotulo={rotulo}
      valor={filtros[k]}
      aoMudar={(v) => mudar({ [k]: v })}
      opcoes={opcoes.precos.map((p) => ({ valor: String(p), rotulo: moeda(p).replace(",00", "") }))}
      vazio="Qualquer"
    />
  );
  const anos = (id: string, rotulo: string, k: "anoMin" | "anoMax") => (
    <Selecao
      id={id}
      rotulo={rotulo}
      valor={filtros[k]}
      aoMudar={(v) => mudar({ [k]: v })}
      opcoes={opcoes.anos.map((a) => ({ valor: String(a), rotulo: String(a) }))}
      vazio="Qualquer"
    />
  );

  return (
    <>
      <Titulo sub="Encontre um veículo pelo modelo, marca ou pelos filtros. Os resultados aparecem em páginas de 10.">
        Veículos disponíveis
      </Titulo>
      <button
        type="button"
        className="botao-contorno mb-4 w-full sm:hidden"
        onClick={() => setAbertos((a) => !a)}
        aria-expanded={abertos}
      >
        <SlidersHorizontal className="size-4" aria-hidden /> Filtros {ativos > 0 && `(${ativos})`}
      </button>
      <form
        className={`cartao mb-4 grid-cols-2 gap-4 p-5 lg:grid-cols-5 ${abertos ? "grid" : "hidden sm:grid"}`}
        onSubmit={(e) => e.preventDefault()}
        aria-label="Filtros"
      >
        <div className="col-span-2 lg:col-span-1">
          <label className="rotulo" htmlFor="f-busca">
            Modelo ou marca
          </label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ultrassonico"
              aria-hidden
            />
            <input
              id="f-busca"
              type="search"
              className="campo pl-10"
              value={filtros.busca}
              onChange={(e) => mudar({ busca: e.target.value })}
              placeholder="Ex.: Corolla, Honda"
              autoComplete="off"
            />
          </div>
        </div>
        <Selecao
          id="f-marca"
          rotulo="Marca"
          valor={filtros.marca}
          aoMudar={(v) => mudar({ marca: v })}
          opcoes={lista(opcoes.marcas)}
        />
        {faixa("f-preco-min", "Preço a partir de", "precoMin")}
        {faixa("f-preco-max", "Preço até", "precoMax")}
        <Selecao
          id="f-ordem"
          rotulo="Ordenar por"
          valor={filtros.ordem}
          aoMudar={(v) => mudar({ ordem: v as Filtros["ordem"] })}
          opcoes={ORDENS}
          vazio={null}
        />
        <details className="col-span-2 border-t border-white/10 pt-3 lg:col-span-5">
          <summary className="min-h-11 cursor-pointer list-none rounded-lg py-2 text-sm font-bold text-ultrassonico marker:hidden hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fiap">
            <span className="inline-flex items-center gap-2">
              <SlidersHorizontal className="size-4" aria-hidden /> Mais filtros
              {avancados > 0 ? ` (${avancados} ativos)` : ""}
            </span>
          </summary>
          <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Selecao
              id="f-modelo"
              rotulo="Modelo"
              valor={filtros.modelo}
              aoMudar={(v) => mudar({ modelo: v })}
              opcoes={lista(opcoes.modelos)}
              desabilitado={!opcoes.modelos.length}
            />
            <Selecao
              id="f-cor"
              rotulo="Cor"
              valor={filtros.cor}
              aoMudar={(v) => mudar({ cor: v })}
              opcoes={lista(opcoes.cores)}
            />
            {anos("f-ano-min", "Ano a partir de", "anoMin")}
            {anos("f-ano-max", "Ano até", "anoMax")}
            <Selecao
              id="f-comb"
              rotulo="Combustível"
              valor={filtros.combustivel}
              aoMudar={(v) => mudar({ combustivel: v })}
              opcoes={opcoes.combustiveis.map((c) => ({ valor: c, rotulo: titulo(c) }))}
            />
            <Selecao
              id="f-cambio"
              rotulo="Câmbio"
              valor={filtros.cambio}
              aoMudar={(v) => mudar({ cambio: v })}
              opcoes={opcoes.cambios.map((c) => ({ valor: c, rotulo: titulo(c) }))}
            />
          </div>
        </details>
      </form>
      {problema && (
        <div className="mb-6">
          <Aviso>{problema}</Aviso>
        </div>
      )}
      {erro && <Aviso>{erro}</Aviso>}
      {!todos && !erro && <Carregando />}
      {todos && (
        <div aria-live="polite" className="mb-4 flex flex-wrap items-center justify-between gap-3">
          {!problema && (
            <p className="text-sm font-semibold text-ultrassonico">
              {resultado.total}{" "}
              {resultado.total === 1 ? "veículo encontrado" : "veículos encontrados"}
            </p>
          )}
          <fieldset className="flex flex-wrap items-center gap-2" aria-label="Filtros ativos">
            {ativos > 0 &&
              (Object.keys(FILTROS_VAZIOS) as (keyof Filtros)[])
                .filter((k) => k !== "ordem" && filtros[k])
                .map((k) => (
                  <button
                    key={k}
                    type="button"
                    className="inline-flex min-h-11 items-center gap-2 rounded-full border border-white/20 bg-white/5 px-3 text-xs font-semibold text-white hover:border-fiap"
                    onClick={() => mudar({ [k]: "" } as Partial<Filtros>)}
                    aria-label={`Remover filtro ${nomes[k]}: ${rotuloFiltro(k)}`}
                  >
                    {nomes[k]}: {rotuloFiltro(k)} <X className="size-3.5" aria-hidden />
                  </button>
                ))}
            <button
              type="button"
              className="botao-fantasma min-h-11"
              disabled={alterados === 0}
              onClick={() => setQ({}, { replace: true })}
            >
              <X className="size-4" aria-hidden /> Limpar filtros
            </button>
          </fieldset>
        </div>
      )}
      {todos && !problema && resultado.total === 0 && (
        <Aviso tipo="info">
          Nenhum veículo encontrado com esses filtros. Remova um filtro ou tente outro modelo ou
          marca.
        </Aviso>
      )}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3" aria-live="polite">
        {resultado.itens.map((v, i) => (
          <VeiculoCard key={v.id} veiculo={v} indice={i} />
        ))}
      </div>
      <Paginacao
        atual={resultado.atual}
        paginas={resultado.paginas}
        total={resultado.total}
        tamanho={POR_PAGINA}
        aoMudar={irParaPagina}
      />
    </>
  );
}

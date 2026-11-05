import {
  ArrowRight,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  FileLock2,
  KeyRound,
  QrCode,
  Search,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { motion } from "motion/react";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { CarroSvg } from "../components/CarSvg";
import { Carregando, Reveal, Selecao } from "../components/ui";
import { VeiculoCard } from "../components/VehicleCard";
import { carregarTodos, opcoesDe } from "../lib/catalog/catalog";
import { moeda } from "../lib/formatters/format";
import type { Veiculo } from "../lib/types";

const PASSOS = [
  {
    icone: Search,
    t: "Escolha",
    d: "Catálogo com filtros por marca, modelo, cor, ano e faixa de preço.",
  },
  {
    icone: CalendarClock,
    t: "Reserve",
    d: "Reserva atômica por 48 horas: se duas pessoas querem o mesmo carro, só uma conclui.",
  },
  {
    icone: QrCode,
    t: "Pague com Pix",
    d: "Código copia-e-cola e confirmação automática do pagamento.",
  },
  {
    icone: KeyRound,
    t: "Retire",
    d: "Acompanhe cada etapa e retire o veículo na loja em até 7 dias.",
  },
];

const GARANTIAS = [
  {
    icone: ShieldCheck,
    t: "Compra protegida",
    d: "Desistiu antes da retirada? O estorno do Pix é integral e o carro volta ao estoque.",
  },
  {
    icone: FileLock2,
    t: "Privacidade dos dados",
    d: "Seus documentos têm acesso restrito. Exporte seus dados ou solicite a exclusão quando não houver compra em andamento.",
  },
  {
    icone: Zap,
    t: "Tempo real",
    d: "A linha do tempo da compra mostra cada etapa da reserva até a entrega das chaves.",
  },
];

export function Home() {
  const [todos, setTodos] = useState<Veiculo[] | null>(null);
  const [marca, setMarca] = useState("");
  const [precoMax, setPrecoMax] = useState("");
  const [anoMin, setAnoMin] = useState("");
  const [destaque, setDestaque] = useState(0);
  const navegar = useNavigate();

  useEffect(() => {
    let ativo = true;
    void carregarTodos()
      .then((dados) => {
        if (ativo) setTodos(dados);
      })
      .catch(() => {
        if (ativo) setTodos([]);
      });
    return () => {
      ativo = false;
    };
  }, []);

  const baratos = useMemo(
    () => [...(todos ?? [])].sort((a, b) => Number(a.preco) - Number(b.preco)),
    [todos],
  );
  const vitrine = baratos.slice(0, 4);
  const opcoes = useMemo(() => opcoesDe(todos ?? []), [todos]);
  const atual = vitrine[destaque % Math.max(vitrine.length, 1)];

  const moverDestaque = (direcao: -1 | 1) =>
    setDestaque((d) => (d + direcao + vitrine.length) % vitrine.length);

  function buscar(e: FormEvent) {
    e.preventDefault();
    const q = new URLSearchParams();
    if (marca) q.set("marca", marca);
    if (precoMax) q.set("precoMax", precoMax);
    if (anoMin) q.set("anoMin", anoMin);
    navegar(`/veiculos${q.size ? `?${q}` : ""}`);
  }

  return (
    <div className="grid gap-20">
      <section
        className="relative grid items-center gap-10 pt-4 lg:grid-cols-[1.05fr_.95fr]"
        aria-labelledby="titulo-home"
      >
        <div>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mb-4 inline-flex items-center gap-2 rounded-full border border-fiap/40 bg-fiap/10 px-4 py-1 text-xs font-bold uppercase tracking-widest text-fiap-claro"
          >
            <span className="size-1.5 animate-brilho rounded-full bg-fiap" /> Seminovos com compra
            100% online
          </motion.p>
          <motion.h1
            id="titulo-home"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-6xl"
          >
            Seu próximo carro,
            <br />
            <span className="bg-gradient-to-r from-fiap via-fiap-claro to-white bg-clip-text text-transparent">
              do clique à chave.
            </span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.25 }}
            className="mt-6 max-w-xl text-base text-ultrassonico sm:text-lg"
          >
            Reserve, pague com Pix e acompanhe a compra etapa por etapa. Sem filas, sem surpresas.
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="mt-8 flex flex-wrap items-center gap-4"
          >
            <Link to="/veiculos" className="botao-primario !px-8 !py-3">
              Explorar veículos <ArrowRight className="size-4" aria-hidden />
            </Link>
            <a
              href="#como-funciona"
              className="text-sm font-bold text-ultrassonico underline-offset-4 hover:text-white hover:underline"
            >
              Como funciona
            </a>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.94 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.7 }}
          className="relative mx-auto w-full max-w-xl"
        >
          <div
            aria-hidden
            className="absolute inset-x-6 top-10 h-3/4 rounded-full bg-fiap/30 blur-[90px]"
          />
          <div className="cartao relative overflow-hidden px-4 pb-6 pt-10">
            <div
              aria-hidden
              className="absolute inset-0 bg-[radial-gradient(circle_at_50%_30%,rgba(237,20,91,.18),transparent_60%)]"
            />
            {atual ? (
              <motion.div
                key={atual.id}
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.25 }}
                aria-live="polite"
                aria-label={`Veículo em destaque ${destaque + 1} de ${vitrine.length}`}
              >
                <div className="relative">
                  <CarroSvg
                    cor={atual.cor}
                    modelo={atual.modelo}
                    className="relative mx-auto w-full"
                  />
                  <span className="absolute right-2 top-2 rounded-full border border-white/20 bg-tinta/90 px-2.5 py-1 text-[11px] font-semibold text-ultrassonico">
                    Ilustração de referência
                  </span>
                </div>
                <div className="relative mt-4 flex items-end justify-between gap-3 px-2">
                  <div className="min-w-0 wrap-anywhere">
                    <p className="text-[11px] font-bold uppercase tracking-widest text-ultrassonico">
                      {atual.marca} · {atual.cor}
                    </p>
                    <p className="text-lg font-extrabold">{atual.modelo}</p>
                  </div>
                  <Link
                    to={`/veiculos/${atual.id}`}
                    className="botao-contorno !px-4 !py-1.5 text-xs whitespace-nowrap"
                  >
                    {moeda(atual.preco)}
                  </Link>
                </div>
                {vitrine.length > 1 && (
                  <div className="relative mt-4 flex items-center justify-end gap-2 px-2">
                    <span className="mr-auto text-xs text-ultrassonico">
                      {destaque + 1} de {vitrine.length} destaques
                    </span>
                    <button
                      type="button"
                      className="grid size-11 place-items-center rounded-full border border-white/20 text-white transition hover:border-fiap hover:text-fiap-claro focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fiap"
                      aria-label="Veículo em destaque anterior"
                      onClick={() => moverDestaque(-1)}
                    >
                      <ChevronLeft className="size-5" aria-hidden />
                    </button>
                    <button
                      type="button"
                      className="grid size-11 place-items-center rounded-full border border-white/20 text-white transition hover:border-fiap hover:text-fiap-claro focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fiap"
                      aria-label="Próximo veículo em destaque"
                      onClick={() => moverDestaque(1)}
                    >
                      <ChevronRight className="size-5" aria-hidden />
                    </button>
                  </div>
                )}
              </motion.div>
            ) : (
              <div className="h-56" aria-hidden />
            )}
          </div>
        </motion.div>
      </section>

      <section aria-label="Busca rápida" className="-mt-6">
        <form
          onSubmit={buscar}
          className="cartao grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_auto] lg:items-end"
        >
          <Selecao
            id="h-marca"
            rotulo="Marca"
            valor={marca}
            aoMudar={setMarca}
            opcoes={opcoes.marcas.map((m) => ({ valor: m, rotulo: m }))}
            vazio="Todas as marcas"
          />
          <Selecao
            id="h-preco"
            rotulo="Preço até"
            valor={precoMax}
            aoMudar={setPrecoMax}
            opcoes={opcoes.precos.map((p) => ({
              valor: String(p),
              rotulo: moeda(p).replace(",00", ""),
            }))}
            vazio="Qualquer"
          />
          <Selecao
            id="h-ano"
            rotulo="Ano a partir de"
            valor={anoMin}
            aoMudar={setAnoMin}
            opcoes={opcoes.anos.map((a) => ({ valor: String(a), rotulo: String(a) }))}
            vazio="Qualquer"
          />
          <button type="submit" className="botao-primario sm:col-span-2 lg:col-span-1">
            <Search className="size-4" aria-hidden /> Buscar
          </button>
        </form>
      </section>

      <section aria-labelledby="destaques">
        <div className="mb-8 flex items-end justify-between gap-4">
          <Reveal>
            <h2 id="destaques" className="text-2xl font-extrabold sm:text-3xl">
              Melhores preços<span className="text-fiap">.</span>
            </h2>
          </Reveal>
          <Link
            to="/veiculos"
            className="inline-flex items-center gap-1 text-sm font-bold text-fiap-claro hover:underline"
          >
            Ver todos <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
        {!todos && <Carregando linhas={1} />}
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {baratos.slice(0, 3).map((v, i) => (
            <VeiculoCard key={v.id} veiculo={v} indice={i} />
          ))}
        </div>
      </section>

      <section id="como-funciona" aria-labelledby="como" className="scroll-mt-24">
        <Reveal>
          <h2 id="como" className="mb-8 text-2xl font-extrabold sm:text-3xl">
            Como funciona<span className="text-fiap">.</span>
          </h2>
        </Reveal>
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PASSOS.map((p, i) => (
            <Reveal key={p.t} atraso={i * 0.08}>
              <li className="cartao relative h-full p-6 transition hover:-translate-y-1 hover:border-fiap/50">
                <span className="absolute right-5 top-4 text-4xl font-extrabold text-white/[0.06]">
                  0{i + 1}
                </span>
                <span className="grid size-11 place-items-center rounded-xl bg-fiap/15 text-fiap-claro">
                  <p.icone className="size-5" aria-hidden />
                </span>
                <h3 className="mt-4 text-lg font-extrabold">{p.t}</h3>
                <p className="mt-2 text-sm text-ultrassonico">{p.d}</p>
              </li>
            </Reveal>
          ))}
        </ol>
      </section>

      <section
        aria-labelledby="garantias"
        className="cartao bg-gradient-to-br from-fiap/10 via-transparent to-transparent p-6 sm:p-10"
      >
        <Reveal>
          <h2 id="garantias" className="mb-8 text-2xl font-extrabold sm:text-3xl">
            Compre com tranquilidade<span className="text-fiap">.</span>
          </h2>
        </Reveal>
        <div className="grid gap-8 md:grid-cols-3">
          {GARANTIAS.map((g, i) => (
            <Reveal key={g.t} atraso={i * 0.08}>
              <div className="flex gap-4">
                <span className="grid size-11 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/5 text-fiap-claro">
                  <g.icone className="size-5" aria-hidden />
                </span>
                <div>
                  <h3 className="font-extrabold">{g.t}</h3>
                  <p className="mt-1 text-sm text-ultrassonico">{g.d}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>
    </div>
  );
}

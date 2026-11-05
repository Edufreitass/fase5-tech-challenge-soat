import { motion } from "motion/react";
import { Link, useLocation } from "react-router";
import { km, moeda, titulo } from "../lib/formatters/format";
import type { Veiculo } from "../lib/types";
import { CarroSvg } from "./CarSvg";
import { StatusBadge } from "./ui";

export function VeiculoCard({
  veiculo,
  indice = 0,
  base = "/veiculos",
}: {
  veiculo: Veiculo;
  indice?: number;
  base?: string;
}) {
  // O detalhe volta para onde o card estava (catalogo com filtros e pagina, ou a home).
  const local = useLocation();
  const de = { de: `${local.pathname}${local.search}` };
  return (
    <motion.article
      initial={{ opacity: 0, y: 28 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: Math.min(indice, 8) * 0.05 }}
      whileHover={{ y: -6 }}
      className="group cartao relative overflow-hidden p-5 transition-colors hover:border-fiap/60"
    >
      <Link
        to={`${base}/${veiculo.id}`}
        state={de}
        tabIndex={-1}
        aria-hidden
        className="relative -mx-5 -mt-5 mb-4 block overflow-hidden bg-gradient-to-b from-white/[0.07] to-transparent px-4 pb-1 pt-6"
      >
        <span className="absolute right-3 top-3 z-10 rounded-full border border-white/20 bg-tinta/90 px-2.5 py-1 text-[11px] font-semibold text-ultrassonico">
          Ilustração de referência
        </span>
        <div
          aria-hidden
          className="absolute inset-x-8 bottom-2 h-10 rounded-full bg-fiap/20 blur-2xl transition-opacity group-hover:opacity-100 sm:opacity-60"
        />
        <CarroSvg
          cor={veiculo.cor}
          modelo={veiculo.modelo}
          className="relative mx-auto w-full max-w-[19rem] transition duration-500 group-hover:scale-105"
        />
      </Link>
      <div className="relative flex items-start justify-between gap-2">
        <div className="min-w-0 wrap-anywhere">
          <p className="text-xs font-bold uppercase tracking-widest text-ultrassonico">
            {veiculo.marca}
          </p>
          <h3 className="mt-1 text-lg font-extrabold leading-tight">{veiculo.modelo}</h3>
        </div>
        <StatusBadge status={veiculo.status} />
      </div>
      <dl className="relative mt-4 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-prata">
        <div>
          <dt className="sr-only">Ano</dt>
          {veiculo.anoFabricacao}/{veiculo.anoModelo}
        </div>
        <div>
          <dt className="sr-only">Quilometragem</dt>
          {km(veiculo.quilometragem)}
        </div>
        <div>
          <dt className="sr-only">Cor</dt>
          {veiculo.cor}
        </div>
        <div>
          <dt className="sr-only">Combustível</dt>
          {veiculo.combustivel ? titulo(veiculo.combustivel) : "-"} ·{" "}
          {veiculo.cambio ? titulo(veiculo.cambio) : "-"}
        </div>
      </dl>
      <div className="relative mt-5 flex items-end justify-between">
        <p className="text-2xl font-extrabold text-white">{moeda(veiculo.preco)}</p>
        <Link
          to={`${base}/${veiculo.id}`}
          state={de}
          className="botao-contorno !px-4 !py-1.5 text-xs whitespace-nowrap"
          aria-label={`Ver ${veiculo.marca} ${veiculo.modelo}`}
        >
          Ver detalhes
        </Link>
      </div>
    </motion.article>
  );
}

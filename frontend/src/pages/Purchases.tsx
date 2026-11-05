import { motion } from "motion/react";
import { Link } from "react-router";
import { Aviso, Carregando, StatusBadge, Titulo } from "../components/ui";
import { obter } from "../lib/api";
import { dataHora, moeda } from "../lib/formatters/format";
import { mensagemDe, useBusca } from "../lib/hooks/use";
import type { Pagina, Venda } from "../lib/types";

export function Compras() {
  const { dados, erro, carregando } = useBusca(() =>
    obter<Pagina<Venda>>("/clientes/meu-perfil/vendas", { limit: 50 }),
  );
  return (
    <>
      <Titulo sub="Acompanhe a reserva, o pagamento e a retirada de cada veículo.">
        Minhas compras
      </Titulo>
      {carregando && <Carregando />}
      {erro && <Aviso>{mensagemDe(erro)}</Aviso>}
      {dados && dados.dados.itens.length === 0 && (
        <Aviso tipo="info">
          Você ainda não tem compras.{" "}
          <Link className="font-bold underline" to="/veiculos">
            Veja o catálogo
          </Link>
          .
        </Aviso>
      )}
      <ul className="grid gap-4">
        {dados?.dados.itens.map((v, i) => (
          <motion.li
            key={v.id}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
          >
            <Link
              to={`/compras/${v.id}`}
              className="cartao flex flex-wrap items-center justify-between gap-4 p-5 transition hover:border-fiap/60"
            >
              <div className="min-w-0 wrap-anywhere">
                <p className="text-xs font-bold uppercase tracking-widest text-ultrassonico">
                  {v.veiculo.marca}
                </p>
                <p className="text-lg font-extrabold">{v.veiculo.modelo}</p>
                <p className="text-xs text-ardosia">{dataHora(v.criadoEm)}</p>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-lg font-extrabold">{moeda(v.precoNegociado)}</span>
                <StatusBadge status={v.status} />
              </div>
            </Link>
          </motion.li>
        ))}
      </ul>
    </>
  );
}

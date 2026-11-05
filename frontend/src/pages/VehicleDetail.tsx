import { ArrowLeft } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { CarroSvg } from "../components/CarSvg";
import { Aviso, Carregando, StatusBadge, Titulo } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ErroApi, enviarJson, obter } from "../lib/api";
import { km, moeda, pendencias, titulo } from "../lib/formatters/format";
import { mensagemDe, useBusca, useEnvio } from "../lib/hooks/use";
import { retornoInterno } from "../lib/navigation";
import type { Cliente, Veiculo, Venda } from "../lib/types";

/** Link de volta: para a lista de onde o card foi aberto (com filtros e pagina) ou para o catalogo. */
function Voltar() {
  const de = retornoInterno(useLocation().state) ?? "/veiculos";
  return (
    <Link
      to={de}
      className="relative inline-flex items-center gap-1 text-xs font-bold text-ultrassonico hover:text-white"
    >
      <ArrowLeft className="size-3.5" aria-hidden />{" "}
      {de.startsWith("/veiculos") ? "Voltar ao catálogo" : "Voltar"}
    </Link>
  );
}

export function VeiculoDetalhe() {
  const { id = "" } = useParams();
  const { papel } = useAuth();
  const navegar = useNavigate();
  const local = useLocation();
  const { dados, erro, carregando, recarregar } = useBusca(
    () => obter<Veiculo>(`/veiculos/${id}`, undefined, false),
    id,
  );
  // So o cliente precisa do cadastro completo para reservar; descobrimos antes de oferecer o botao.
  const cadastro = useBusca(
    () =>
      obter<Cliente>("/clientes/meu-perfil")
        .then((r) => r.dados)
        .catch((e) =>
          e instanceof ErroApi && e.tipo === "perfil-cliente-inexistente"
            ? null
            : Promise.reject(e),
        ),
    papel ?? "anonimo",
    { ativo: papel === "cliente" },
  );
  const [confirmando, setConfirmando] = useState(false);
  const { enviando: comprando, executar } = useEnvio();
  const [falha, setFalha] = useState<string | null>(null);
  // Outro cliente reservou antes: o status do veiculo e atualizado pela saga e pode demorar a refletir na leitura.
  const [tomado, setTomado] = useState(false);
  const [compraAberta, setCompraAberta] = useState(false);

  async function comprar() {
    await executar(async () => {
      setFalha(null);
      try {
        const { dados: venda } = await enviarJson<Venda>("/vendas", { veiculoId: id });
        navegar(`/compras/${venda.id}`);
      } catch (e) {
        const semCadastro =
          e instanceof ErroApi &&
          ["perfil-cliente-inexistente", "cadastro-incompleto"].includes(e.tipo ?? "");
        setFalha(
          semCadastro
            ? "Complete seu cadastro (incluindo o RG) para reservar um veículo."
            : mensagemDe(e),
        );
        setConfirmando(false);
        setCompraAberta(e instanceof ErroApi && e.tipo === "reserva-ativa-existente");
        if (e instanceof ErroApi && e.tipo === "veiculo-indisponivel") {
          setTomado(true);
          recarregar();
        }
      }
    });
  }

  if (carregando) return <Carregando linhas={2} />;
  if (erro || !dados) {
    const naoExiste = !erro || (erro instanceof ErroApi && erro.status === 404);
    return (
      <div className="grid gap-4">
        <Titulo>
          {naoExiste ? "Veículo não encontrado" : "Não foi possível carregar o veículo"}
        </Titulo>
        <Aviso>
          {naoExiste ? "Ele pode ter sido vendido ou retirado do catálogo." : mensagemDe(erro)}
        </Aviso>
        <div>
          <Link to="/veiculos" className="botao-contorno">
            Ver veículos disponíveis
          </Link>
        </div>
      </div>
    );
  }
  const v = dados.dados;
  const disponivel = v.status === "DISPONIVEL" && !tomado;
  const ficha: [string, string][] = [
    ["Ano", `${v.anoFabricacao}/${v.anoModelo}`],
    ["Quilometragem", km(v.quilometragem)],
    ["Cor", v.cor],
    ["Combustível", v.combustivel ? titulo(v.combustivel) : "-"],
    ["Câmbio", v.cambio ? titulo(v.cambio) : "-"],
    ["Placa", v.placa ?? "-"],
  ];
  const c = cadastro.dados;
  const acoesReserva = () => (
    <div className="grid gap-3">
      {falha && (
        <Aviso>
          {falha}
          {compraAberta && (
            <>
              {" "}
              <Link to="/compras" className="font-bold underline">
                Ver minhas compras
              </Link>
            </>
          )}
        </Aviso>
      )}
      {!disponivel && (
        <Aviso tipo="info">Este veículo não está disponível para compra no momento.</Aviso>
      )}
      {disponivel && !papel && (
        <Link
          to="/entrar"
          state={{ de: `${local.pathname}${local.search}` }}
          className="botao-primario w-full"
        >
          Entrar para comprar
        </Link>
      )}
      {disponivel && (papel === "vendedor" || papel === "admin") && (
        <Aviso tipo="info">Funcionários não realizam compras. Use o painel.</Aviso>
      )}
      {disponivel && papel === "cliente" && cadastro.carregando && (
        <p role="status" className="text-sm text-ultrassonico">
          Verificando seu cadastro…
        </p>
      )}
      {disponivel && papel === "cliente" && !cadastro.carregando && cadastro.erro && (
        <>
          <Aviso>Não foi possível verificar seu cadastro: {mensagemDe(cadastro.erro)}</Aviso>
          <button type="button" className="botao-contorno w-full" onClick={cadastro.recarregar}>
            Tentar de novo
          </button>
        </>
      )}
      {disponivel &&
        papel === "cliente" &&
        !cadastro.carregando &&
        !cadastro.erro &&
        (c === null || (c && !c.cadastroCompleto)) && (
          <>
            <Aviso tipo="info">
              {c
                ? `Para reservar, falta informar: ${pendencias(c.camposPendentes)}.`
                : "Para reservar, primeiro faça seu cadastro."}
            </Aviso>
            <Link to="/perfil" className="botao-primario w-full">
              Completar cadastro
            </Link>
          </>
        )}
      {disponivel &&
        papel === "cliente" &&
        !cadastro.carregando &&
        !cadastro.erro &&
        c?.cadastroCompleto &&
        !confirmando && (
          <button
            type="button"
            className="botao-primario w-full"
            onClick={() => setConfirmando(true)}
          >
            Reservar e comprar
          </button>
        )}
      {disponivel && papel === "cliente" && c?.cadastroCompleto && confirmando && (
        <fieldset
          aria-label="Confirmar reserva"
          className="grid gap-3 rounded-xl border border-fiap/40 bg-fiap/10 p-4 text-sm"
        >
          <p>
            Reservar o{" "}
            <b>
              {v.marca} {v.modelo}
            </b>{" "}
            por <b>{moeda(v.preco)}</b>? O veículo fica reservado por 48 horas enquanto você paga o
            Pix.
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="botao-primario" onClick={comprar} disabled={comprando}>
              {comprando ? "Reservando…" : "Confirmar reserva"}
            </button>
            <button
              type="button"
              className="botao-fantasma"
              onClick={() => setConfirmando(false)}
              disabled={comprando}
            >
              Cancelar
            </button>
          </div>
        </fieldset>
      )}
    </div>
  );
  return (
    <div className="grid gap-8 pb-40 lg:grid-cols-[1.2fr_.8fr] lg:pb-0">
      <motion.div
        initial={{ opacity: 0, x: -24 }}
        animate={{ opacity: 1, x: 0 }}
        className="cartao relative overflow-hidden p-5 sm:p-8"
      >
        <div
          aria-hidden
          className="absolute -right-16 -top-16 size-64 rounded-full bg-fiap/25 blur-3xl"
        />
        <Voltar />
        <div className="relative mx-auto mt-6 w-full max-w-xl">
          <CarroSvg cor={v.cor} modelo={v.modelo} className="w-full" />
          <span className="absolute right-2 top-2 rounded-full border border-white/20 bg-tinta/90 px-3 py-1 text-xs font-semibold text-ultrassonico">
            Ilustração de referência
          </span>
        </div>
        <p className="relative mt-6 text-xs font-bold uppercase tracking-[.2em] text-fiap-claro">
          {v.marca} · {v.cor}
        </p>
        <h1 className="relative mt-1 text-3xl font-extrabold wrap-anywhere sm:text-5xl">
          {v.modelo}
        </h1>
        <div className="relative mt-4">
          <StatusBadge status={tomado && v.status === "DISPONIVEL" ? "RESERVADO" : v.status} />
        </div>
        <dl className="relative mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3">
          {ficha.map(([k, val]) => (
            <div key={k} className="rounded-xl border border-white/10 bg-black/30 p-4">
              <dt className="text-xs font-bold uppercase tracking-wider text-ultrassonico">{k}</dt>
              <dd className="mt-1 text-sm font-bold">{val}</dd>
            </div>
          ))}
        </dl>
      </motion.div>
      <motion.aside
        initial={{ opacity: 1, x: 0 }}
        animate={{ opacity: 1, x: 0 }}
        aria-label="Comprar veículo"
        className="fixed inset-x-0 bottom-0 z-40 border-t border-white/15 bg-tinta/95 px-4 pb-[calc(env(safe-area-inset-bottom)+0.75rem)] pt-3 shadow-[0_-12px_32px_rgba(0,0,0,.35)] backdrop-blur-xl lg:sticky lg:top-24 lg:h-fit lg:border lg:border-white/10 lg:p-8 lg:shadow-none"
      >
        <div className="mx-auto grid max-w-7xl gap-2 lg:max-w-none lg:gap-0">
          <p className="hidden text-xs font-bold uppercase tracking-wider text-ultrassonico lg:block">
            Preço
          </p>
          <p className="flex items-center justify-between gap-3 text-lg font-extrabold lg:mt-1 lg:block lg:text-4xl">
            <span className="text-xs font-semibold uppercase tracking-wider text-ultrassonico lg:hidden">
              Preço
            </span>
            {moeda(v.preco)}
          </p>
          <p className="text-xs text-ardosia">
            Pagamento integral via Pix. A reserva vale por 48 horas.
          </p>
          <div className="lg:mt-6">{acoesReserva()}</div>
        </div>
      </motion.aside>
    </div>
  );
}

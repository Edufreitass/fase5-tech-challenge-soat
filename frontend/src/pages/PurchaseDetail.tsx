import { useState } from "react";
import { Link, useParams } from "react-router";
import { SagaFlow } from "../components/SagaFlow";
import { Aviso, Carregando, StatusBadge, Titulo } from "../components/ui";
import { chamar, ErroApi, obter } from "../lib/api";
import { dataHora, titulo as formatar, moeda, restante } from "../lib/formatters/format";
import { mensagemDe, useBusca, useEnvio } from "../lib/hooks/use";
import { VENDA_FINAL } from "../lib/saga";
import type { Venda } from "../lib/types";

export function CompraDetalhe() {
  const { id = "" } = useParams();
  const [copiado, setCopiado] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);
  const { enviando, executar } = useEnvio();
  const busca = useBusca(() => obter<Venda>(`/vendas/${id}`), id, {
    intervaloMs: 4000,
    continuar: (resposta, erro) => {
      const erroPermanente =
        erro instanceof ErroApi && erro.status >= 400 && erro.status < 500 && erro.status !== 429;
      return !erroPermanente && (!resposta || !VENDA_FINAL(resposta.dados.status));
    },
  });

  async function desistir() {
    await executar(async () => {
      if (!confirm("Tem certeza que deseja desistir desta compra?")) return;
      try {
        await chamar(`/vendas/${id}/desistencia`, { metodo: "POST" });
        setAviso({
          tipo: "ok",
          texto: "Desistência em processamento. Se houve pagamento, o estorno é integral.",
        });
        busca.recarregar();
      } catch (e) {
        setAviso({ tipo: "erro", texto: mensagemDe(e) });
      }
    });
  }

  async function copiar(codigo: string) {
    try {
      await navigator.clipboard.writeText(codigo);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      setAviso({ tipo: "erro", texto: "Não foi possível copiar; selecione o código manualmente." });
    }
  }

  if (busca.carregando && !busca.dados) return <Carregando linhas={2} />;
  if (busca.erro || !busca.dados) {
    const naoExiste = busca.erro instanceof ErroApi && busca.erro.status === 404;
    return (
      <div className="grid gap-4">
        <Titulo>
          {naoExiste ? "Compra não encontrada" : "Não foi possível carregar a compra"}
        </Titulo>
        <Aviso>
          {naoExiste
            ? "Confira o link ou abra a compra pela lista das suas compras."
            : mensagemDe(busca.erro)}
        </Aviso>
        <div>
          <Link to="/compras" className="botao-contorno">
            Ver minhas compras
          </Link>
        </div>
      </div>
    );
  }
  const v = busca.dados.dados;
  const pix = v.pagamento?.pixCopiaECola;
  const podeDesistir =
    v.status === "AGUARDANDO_PAGAMENTO" || v.status === "PAGO" || v.status === "RESERVADO";

  return (
    <>
      <Link to="/compras" className="text-xs font-bold text-ultrassonico hover:text-white">
        ← Minhas compras
      </Link>
      <div className="mt-4">
        <Titulo sub={`Compra iniciada em ${dataHora(v.criadoEm)}`}>
          {v.veiculo.marca} {v.veiculo.modelo}
        </Titulo>
      </div>
      <div className="grid gap-6">
        <SagaFlow status={v.status} />
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="cartao p-6" aria-label="Resumo">
            <div className="flex items-center justify-between">
              <h2 className="font-extrabold">Resumo</h2>
              <StatusBadge status={v.status} />
            </div>
            <p className="mt-4 text-3xl font-extrabold">{moeda(v.precoNegociado)}</p>
            <dl className="mt-4 grid gap-1 text-sm text-prata">
              {v.status === "AGUARDANDO_PAGAMENTO" && (
                <div>
                  Expira em{" "}
                  <b className="text-white">
                    {restante(v.pagamento?.expiraEm ?? v.reservaExpiraEm)}
                  </b>
                </div>
              )}
              {v.retiradaLimiteEm && v.status === "PAGO" && (
                <div>
                  Retirar até <b className="text-white">{dataHora(v.retiradaLimiteEm)}</b>
                </div>
              )}
              {v.motivoCancelamento && (
                <div>
                  Motivo: <b className="text-white">{formatar(v.motivoCancelamento)}</b>
                </div>
              )}
            </dl>
            {podeDesistir && (
              <button
                type="button"
                className="botao-contorno mt-6"
                onClick={desistir}
                disabled={enviando}
              >
                Desistir da compra
              </button>
            )}
          </section>
          <section className="cartao p-6" aria-label="Pagamento">
            <h2 className="font-extrabold">Pagamento via Pix</h2>
            {pix && v.status === "AGUARDANDO_PAGAMENTO" ? (
              <>
                <p className="mt-3 text-xs text-ultrassonico">
                  Copie o código e pague no app do seu banco. A confirmação é automática.
                </p>
                <textarea
                  readOnly
                  rows={4}
                  value={pix}
                  aria-label="Código Pix copia e cola"
                  className="campo mt-3 font-mono text-xs"
                  onFocus={(e) => e.currentTarget.select()}
                />
                <button type="button" className="botao-primario mt-3" onClick={() => copiar(pix)}>
                  {copiado ? "Copiado ✓" : "Copiar código"}
                </button>
              </>
            ) : (
              <p className="mt-3 text-sm text-ultrassonico">
                {v.status === "CRIADO" || v.status === "RESERVADO"
                  ? "Gerando seu código de pagamento…"
                  : v.pagamento
                    ? `Pagamento: ${formatar(v.pagamento.status)}.`
                    : "Sem cobrança ativa."}
              </p>
            )}
          </section>
        </div>
        {VENDA_FINAL(v.status) && (
          <section
            className="cartao flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between"
            aria-live="polite"
          >
            <div>
              <h2 className="font-extrabold">Compra encerrada: {formatar(v.status)}.</h2>
              <p className="mt-1 text-sm text-ultrassonico">
                Acompanhe o histórico acima ou explore outros veículos disponíveis.
              </p>
            </div>
            <Link to="/veiculos" className="botao-primario shrink-0">
              Ver outros veículos
            </Link>
          </section>
        )}
        {/* O aviso de processamento sai quando a atualização mostra o desfecho final. */}
        {aviso && !(aviso.tipo === "ok" && VENDA_FINAL(v.status)) && (
          <Aviso tipo={aviso.tipo}>{aviso.texto}</Aviso>
        )}
        {v.historico && v.historico.length > 0 && (
          <section className="cartao p-6" aria-label="Histórico">
            <h2 className="mb-4 font-extrabold">Histórico</h2>
            <ol className="relative grid gap-4 border-l border-white/15 pl-6">
              {v.historico.map((e) => (
                <li key={`${e.ocorridoEm}:${e.para}:${e.ator}`} className="relative text-sm">
                  <span className="absolute -left-[31px] top-1 size-2.5 rounded-full bg-fiap" />
                  <b>{formatar(e.para)}</b>{" "}
                  <span className="text-ardosia">· {dataHora(e.ocorridoEm)}</span>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
    </>
  );
}

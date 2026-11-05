import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { Aviso, Carregando, Paginacao, Selecao, StatusBadge } from "../../components/ui";
import { enviarJson, obter } from "../../lib/api";
import { POR_PAGINA, pagina } from "../../lib/catalog/catalog";
import { dataHora, moeda, titulo } from "../../lib/formatters/format";
import { textoDoFormulario } from "../../lib/forms";
import { mensagemDe, useEnvio } from "../../lib/hooks/use";
import { useLista } from "../../lib/hooks/useList";
import { transacaoDoPix } from "../../lib/pix";
import type { StatusVenda, Venda } from "../../lib/types";
import { Campo, type Mensagem, useEmFoco } from "./shared";

const STATUS_VENDA: StatusVenda[] = [
  "PAGO",
  "AGUARDANDO_PAGAMENTO",
  "CONCLUIDO",
  "CANCELADO",
  "ESTORNADO",
];

function Retirada({
  venda,
  aoFechar,
  aoConcluir,
}: {
  venda: Venda;
  aoFechar: () => void;
  aoConcluir: () => void;
}) {
  const [erro, setErro] = useState<string | null>(null);
  const { enviando, executar } = useEnvio();
  const foco = useEmFoco<HTMLFormElement>();
  function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = textoDoFormulario(e.currentTarget);
    const agora = new Date().toISOString();
    void executar(async () => {
      try {
        await enviarJson(`/vendas/${venda.id}/retirada`, {
          retiradaEm: agora,
          documentacao: { protocolo: f("protocolo").trim(), emitidaEm: agora },
          conferencia: { documentoApresentado: f("documento") },
        });
        aoConcluir();
      } catch (x) {
        setErro(mensagemDe(x));
      }
    });
  }
  return (
    <form
      ref={foco}
      onSubmit={enviar}
      className="cartao mb-6 grid scroll-mt-24 gap-4 border-fiap/40 p-5 sm:grid-cols-3"
      aria-label="Registrar retirada"
    >
      <p className="text-sm font-bold sm:col-span-3">
        Retirada de {venda.veiculo.marca} {venda.veiculo.modelo}
      </p>
      <div>
        <label className="rotulo" htmlFor="r-doc">
          Documento apresentado
        </label>
        <select id="r-doc" name="documento" className="campo" required defaultValue="">
          <option value="" disabled>
            Selecione
          </option>
          {["CNH", "RG", "Passaporte"].map((d) => (
            <option key={d}>{d}</option>
          ))}
        </select>
      </div>
      <Campo
        id="r-proto"
        rotulo="Protocolo da documentação"
        name="protocolo"
        required
        minLength={3}
        maxLength={60}
      />
      <div className="flex items-end gap-2">
        <button type="submit" className="botao-primario" disabled={enviando}>
          {enviando ? "Registrando…" : "Confirmar retirada"}
        </button>
        <button type="button" className="botao-fantasma" onClick={aoFechar}>
          Cancelar
        </button>
      </div>
      {erro && (
        <div className="sm:col-span-3">
          <Aviso>{erro}</Aviso>
        </div>
      )}
    </form>
  );
}

/** Faz o papel do banco: o gateway Pix e simulado, entao a equipe confirma ou recusa o pagamento aqui. */
function SimularPagamento({
  venda,
  aoFechar,
  aoConcluir,
}: {
  venda: Venda;
  aoFechar: () => void;
  aoConcluir: (aprovado: boolean) => void;
}) {
  const [erro, setErro] = useState<string | null>(null);
  const { enviando, executar } = useEnvio();
  const foco = useEmFoco<HTMLFormElement>();
  function enviar(resultado: "APROVADO" | "RECUSADO") {
    void executar(async () => {
      try {
        const detalhe = await obter<Venda>(`/vendas/${venda.id}`);
        const tx = transacaoDoPix(detalhe.dados.pagamento?.pixCopiaECola);
        if (!tx) {
          setErro("Esta venda ainda não tem um código Pix válido para o gateway simulado.");
          return;
        }
        await enviarJson(`/_simulacao/pagamentos/cobrancas/${tx}/simular`, { resultado });
        aoConcluir(resultado === "APROVADO");
      } catch (x) {
        setErro(mensagemDe(x));
      }
    });
  }
  return (
    <form
      ref={foco}
      onSubmit={(e) => e.preventDefault()}
      className="cartao mb-6 grid scroll-mt-24 gap-3 border-fiap/40 p-5"
      aria-label="Simular pagamento"
    >
      <p className="text-sm font-bold">
        Gateway Pix simulado: {venda.veiculo.marca} {venda.veiculo.modelo} ·{" "}
        {moeda(venda.precoNegociado)}
      </p>
      <p className="text-xs text-ultrassonico">
        Em produção, o banco confirmaria o pagamento sozinho. Aqui a equipe escolhe o resultado, e o
        sistema o recebe pelo mesmo webhook assinado.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="botao-primario"
          disabled={enviando}
          onClick={() => enviar("APROVADO")}
        >
          Aprovar pagamento
        </button>
        <button
          type="button"
          className="botao-contorno"
          disabled={enviando}
          onClick={() => enviar("RECUSADO")}
        >
          Recusar pagamento
        </button>
        <button type="button" className="botao-fantasma" onClick={aoFechar}>
          Cancelar
        </button>
      </div>
      {erro && <Aviso>{erro}</Aviso>}
    </form>
  );
}

export function Vendas() {
  // GET /vendas exige o status: por padrao mostra as pagas, que aguardam retirada.
  const [status, setStatus] = useState<StatusVenda>("PAGO");
  const [numero, setNumero] = useState(1);
  const lista = useLista<Venda>("/vendas", { status });
  const [retirando, setRetirando] = useState<Venda | null>(null);
  const [pagando, setPagando] = useState<Venda | null>(null);
  // A conclusao e assincrona (saga): a venda segue "PAGO" por instantes; marcamos para nao oferecer a retirada de novo.
  const [retiradas, setRetiradas] = useState<Set<string>>(() => new Set());
  const [msg, setMsg] = useState<Mensagem>(null);
  const p = useMemo(() => pagina(lista.itens ?? [], numero), [lista.itens, numero]);
  const { recarregar } = lista;
  useEffect(() => {
    if (!retiradas.size) return;
    const id = setTimeout(recarregar, 3000);
    return () => clearTimeout(id);
  }, [retiradas, recarregar]);
  return (
    <>
      <div className="mb-4 max-w-xs">
        <Selecao
          id="filtro-status"
          rotulo="Status da venda"
          valor={status}
          aoMudar={(v) => {
            setStatus(v as StatusVenda);
            setNumero(1);
            setRetirando(null);
            setPagando(null);
            setMsg(null);
          }}
          opcoes={STATUS_VENDA.map((s) => ({ valor: s, rotulo: titulo(s) }))}
          vazio={null}
        />
      </div>
      {msg && (
        <div className="mb-4">
          <Aviso tipo={msg.tipo}>{msg.texto}</Aviso>
        </div>
      )}
      {retirando && (
        <Retirada
          key={retirando.id}
          venda={retirando}
          aoFechar={() => setRetirando(null)}
          aoConcluir={() => {
            setRetiradas((r) => new Set(r).add(retirando.id));
            setRetirando(null);
            setMsg({
              tipo: "ok",
              texto: "Retirada registrada; a venda será concluída em instantes.",
            });
          }}
        />
      )}
      {pagando && (
        <SimularPagamento
          key={pagando.id}
          venda={pagando}
          aoFechar={() => setPagando(null)}
          aoConcluir={(aprovado) => {
            setPagando(null);
            setMsg({
              tipo: "ok",
              texto: aprovado
                ? "Pagamento aprovado; a venda seguirá para a retirada em instantes."
                : "Pagamento recusado; o veículo será liberado em instantes.",
            });
            setTimeout(recarregar, 3000);
          }}
        />
      )}
      {lista.erro ? (
        <Aviso>{lista.erro}</Aviso>
      ) : !lista.itens ? (
        <Carregando />
      ) : (
        <>
          <ul className="grid gap-3">
            {p.itens.map((v) => (
              <li
                key={v.id}
                className="cartao flex flex-wrap items-center justify-between gap-3 p-4"
              >
                <div className="min-w-0 wrap-anywhere">
                  <p className="font-bold">
                    {v.veiculo.id ? (
                      <Link to={`/veiculos/${v.veiculo.id}`} className="hover:underline">
                        {v.veiculo.marca} {v.veiculo.modelo}
                      </Link>
                    ) : (
                      `${v.veiculo.marca} ${v.veiculo.modelo}`
                    )}
                  </p>
                  <p className="text-xs text-ardosia">
                    {dataHora(v.criadoEm)} · {moeda(v.precoNegociado)} · venda {v.id.slice(-8)}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {v.status === "PAGO" && retiradas.has(v.id) ? (
                    <span className="text-xs font-bold text-emerald-300">Retirada registrada</span>
                  ) : (
                    <StatusBadge status={v.status} />
                  )}
                  {v.status === "AGUARDANDO_PAGAMENTO" && (
                    <button
                      type="button"
                      className="botao-contorno !py-1 text-xs"
                      onClick={() => {
                        setRetirando(null);
                        setPagando(v);
                      }}
                      aria-label={`Simular pagamento de ${v.veiculo.marca} ${v.veiculo.modelo}`}
                    >
                      Simular pagamento
                    </button>
                  )}
                  {v.status === "PAGO" && !retiradas.has(v.id) && (
                    <button
                      type="button"
                      className="botao-contorno !py-1 text-xs"
                      onClick={() => {
                        setPagando(null);
                        setRetirando(v);
                      }}
                      aria-label={`Registrar retirada de ${v.veiculo.marca} ${v.veiculo.modelo}`}
                    >
                      Registrar retirada
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {p.total === 0 && <Aviso tipo="info">Nenhuma venda com este status.</Aviso>}
          <Paginacao
            atual={p.atual}
            paginas={p.paginas}
            total={p.total}
            tamanho={POR_PAGINA}
            aoMudar={setNumero}
          />
        </>
      )}
    </>
  );
}

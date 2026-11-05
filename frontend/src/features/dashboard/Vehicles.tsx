import { Pencil } from "lucide-react";
import { useMemo, useState } from "react";
import { Aviso, Carregando, Paginacao, Selecao, StatusBadge } from "../../components/ui";
import { chamar } from "../../lib/api";
import { POR_PAGINA, pagina } from "../../lib/catalog/catalog";
import { moeda, titulo } from "../../lib/formatters/format";
import { mensagemDe, useEnvio } from "../../lib/hooks/use";
import { useLista } from "../../lib/hooks/useList";
import type { Veiculo } from "../../lib/types";
import type { Mensagem } from "./shared";
import { EditarVeiculo, Marcas, NovoVeiculo, type VeiculoCompleto } from "./VehicleForms";

const STATUS_VEICULO = ["DISPONIVEL", "RESERVADO", "AGUARDANDO_RETIRADA", "VENDIDO", "INATIVO"];

export function Veiculos() {
  const [status, setStatus] = useState("DISPONIVEL");
  const [numero, setNumero] = useState(1);
  const lista = useLista<VeiculoCompleto>("/gestao/veiculos", { status });
  const [msg, setMsg] = useState<Mensagem>(null);
  const [editando, setEditando] = useState<VeiculoCompleto | null>(null);
  const p = useMemo(() => pagina(lista.itens ?? [], numero), [lista.itens, numero]);
  const { enviando: alternando, executar } = useEnvio();
  const alternar = (v: Veiculo) =>
    executar(async () => {
      const inativar = v.status !== "INATIVO";
      if (
        inativar &&
        !confirm(`Inativar ${v.marca} ${v.modelo}? Ele sai do catálogo até ser reativado.`)
      )
        return;
      setMsg(null);
      try {
        // Concorrencia otimista: a API exige a versao lida no If-Match.
        await chamar(`/veiculos/${v.id}/${inativar ? "inativacao" : "reativacao"}`, {
          metodo: "POST",
          ifMatch: `"v${v.versao ?? 1}"`,
        });
        setMsg({
          tipo: "ok",
          texto: `${v.marca} ${v.modelo} ${inativar ? "inativado: saiu do catálogo" : "reativado: voltou ao catálogo"}.`,
        });
        lista.recarregar();
      } catch (e) {
        setMsg({ tipo: "erro", texto: mensagemDe(e) });
      }
    });
  return (
    <>
      <Marcas />
      <NovoVeiculo
        aoCriar={(nome) => {
          setMsg({ tipo: "ok", texto: `${nome} cadastrado e disponível no catálogo.` });
          setStatus("DISPONIVEL");
          setNumero(1);
          lista.recarregar();
        }}
      />
      {editando && (
        <EditarVeiculo
          key={editando.id}
          veiculo={editando}
          aoFechar={() => setEditando(null)}
          aoSalvar={() => {
            setMsg({ tipo: "ok", texto: `${editando.marca} ${editando.modelo} atualizado.` });
            setEditando(null);
            lista.recarregar();
          }}
        />
      )}
      <div className="mb-4 max-w-xs">
        <Selecao
          id="g-status"
          rotulo="Status"
          valor={status}
          aoMudar={(v) => {
            setStatus(v);
            setNumero(1);
            setMsg(null);
            setEditando(null);
          }}
          opcoes={STATUS_VEICULO.map((s) => ({ valor: s, rotulo: titulo(s) }))}
          vazio={null}
        />
      </div>
      {msg && (
        <div className="mb-4">
          <Aviso tipo={msg.tipo}>{msg.texto}</Aviso>
        </div>
      )}
      {lista.erro ? (
        <Aviso>{lista.erro}</Aviso>
      ) : !lista.itens ? (
        <Carregando />
      ) : (
        <>
          <ul className="grid gap-3 md:hidden" aria-label="Estoque de veículos">
            {p.itens.map((v) => (
              <li key={v.id} className="cartao grid gap-3 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-bold">
                      {v.marca} {v.modelo}
                    </h2>
                    <p className="mt-1 text-sm text-ultrassonico">
                      {v.cor} · {v.anoModelo}
                    </p>
                  </div>
                  <StatusBadge status={v.status} />
                </div>
                <p className="text-lg font-extrabold">{moeda(v.preco)}</p>
                {(v.status === "DISPONIVEL" || v.status === "INATIVO") && (
                  <button
                    type="button"
                    className="botao-contorno w-full"
                    onClick={() => alternar(v)}
                  >
                    {v.status === "INATIVO" ? "Reativar veículo" : "Inativar veículo"}
                  </button>
                )}
              </li>
            ))}
          </ul>
          <div className="cartao hidden overflow-x-auto md:block">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-ultrassonico">
                <tr>
                  <th className="p-4">Veículo</th>
                  <th>Cor</th>
                  <th>Ano</th>
                  <th>Preço</th>
                  <th>Status</th>
                  <th>
                    <span className="sr-only">Ações</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {p.itens.map((v) => (
                  <tr key={v.id} className="border-t border-white/10 transition hover:bg-white/5">
                    <td className="p-4 font-bold">
                      {v.marca} {v.modelo}
                    </td>
                    <td>{v.cor}</td>
                    <td>{v.anoModelo}</td>
                    <td>{moeda(v.preco)}</td>
                    <td>
                      <StatusBadge status={v.status} />
                    </td>
                    <td className="whitespace-nowrap pr-4 text-right">
                      {v.status !== "VENDIDO" && (
                        <button
                          type="button"
                          className="botao-fantasma !py-1 text-xs"
                          onClick={() => setEditando(v)}
                          aria-label={`Editar ${v.marca} ${v.modelo}`}
                        >
                          <Pencil className="size-3.5" aria-hidden /> Editar
                        </button>
                      )}
                      {(v.status === "DISPONIVEL" || v.status === "INATIVO") && (
                        <button
                          type="button"
                          className="botao-fantasma !py-1 text-xs"
                          disabled={alternando}
                          onClick={() => void alternar(v)}
                          aria-label={`${v.status === "INATIVO" ? "Reativar" : "Inativar"} ${v.marca} ${v.modelo}`}
                        >
                          {v.status === "INATIVO" ? "Reativar" : "Inativar"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {p.total === 0 && (
            <div className="mt-4">
              <Aviso tipo="info">Nenhum veículo neste status.</Aviso>
            </div>
          )}
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

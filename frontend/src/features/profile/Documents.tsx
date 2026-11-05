import { type FormEvent, useState } from "react";
import { Aviso, CampoForm, SelecaoUf } from "../../components/ui";
import { chamar } from "../../lib/api";
import { apenasDigitos } from "../../lib/formatters/format";
import { mensagemDe, useEnvio } from "../../lib/hooks/use";
import type { Cliente } from "../../lib/types";

import { rgIncompleto } from "./shared";

export function Documentos({
  cliente,
  etag,
  aoSalvar,
}: {
  cliente: Cliente;
  etag: string | null;
  aoSalvar: () => void;
}) {
  const [rg, setRg] = useState({ numero: "", orgao: "", uf: "" });
  const [cnh, setCnh] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const { enviando, executar } = useEnvio();
  function enviar(e: FormEvent) {
    e.preventDefault();
    void executar(salvar);
  }
  async function salvar() {
    setErro(null);
    setOk(false);
    if (rgIncompleto(rg.numero, rg.orgao, rg.uf))
      return setErro("Para informar o RG, preencha número, órgão emissor e UF do RG.");
    if (cnh && cnh.length !== 11) return setErro("A CNH deve ter 11 dígitos.");
    const corpo: Record<string, unknown> = {};
    if (rg.numero) corpo.rg = { numero: rg.numero, orgaoEmissor: rg.orgao, uf: rg.uf };
    if (cnh) corpo.cnh = cnh;
    if (!Object.keys(corpo).length) return setErro("Informe o RG ou a CNH para salvar.");
    try {
      await chamar("/clientes/meu-perfil", { metodo: "PATCH", corpo, ifMatch: etag });
      setOk(true);
      setRg({ numero: "", orgao: "", uf: "" });
      setCnh("");
      aoSalvar();
    } catch (x) {
      setErro(mensagemDe(x));
    }
  }
  // RG obrigatorio enquanto faltar (ou quando um campo dele for preenchido); quem so informa a CNH pode salva-la sozinha.
  const rgEmEdicao = Boolean(rg.numero || rg.orgao || rg.uf) || (!cliente.rg && !cnh);
  return (
    <form
      onSubmit={enviar}
      className="cartao mt-6 grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-4"
      aria-label="Documentos"
    >
      <p className="text-sm font-extrabold sm:col-span-2 lg:col-span-4">
        Documentos
        <span className="mt-0.5 block text-xs font-medium text-ultrassonico">
          {cliente.rg
            ? "Atualize seu RG ou informe a CNH (opcional)."
            : "Informe o RG para poder reservar veículos. A CNH é opcional."}
        </span>
      </p>
      <CampoForm
        id="d-rg"
        rotulo="Número do RG"
        obrigatorio={rgEmEdicao}
        value={rg.numero}
        onChange={(e) => setRg({ ...rg, numero: e.target.value })}
        maxLength={20}
      />
      <CampoForm
        id="d-orgao"
        rotulo="Órgão emissor"
        obrigatorio={rgEmEdicao}
        value={rg.orgao}
        onChange={(e) => setRg({ ...rg, orgao: e.target.value })}
        maxLength={10}
        placeholder="SSP"
      />
      <SelecaoUf
        id="d-uf"
        rotulo="UF do RG"
        obrigatorio={rgEmEdicao}
        valor={rg.uf}
        aoMudar={(v) => setRg({ ...rg, uf: v })}
      />
      <CampoForm
        id="d-cnh"
        rotulo="CNH"
        value={cnh}
        onChange={(e) => setCnh(apenasDigitos(e.target.value))}
        maxLength={11}
        minLength={11}
        inputMode="numeric"
        title="11 dígitos"
        placeholder="11 dígitos (opcional)"
      />
      {erro && (
        <div className="sm:col-span-2 lg:col-span-4">
          <Aviso>{erro}</Aviso>
        </div>
      )}
      {ok && (
        <div className="sm:col-span-2 lg:col-span-4">
          <Aviso tipo="ok">Documentos salvos.</Aviso>
        </div>
      )}
      <div className="sm:col-span-2 lg:col-span-4">
        <button type="submit" className="botao-primario" disabled={enviando}>
          {enviando ? "Salvando…" : "Salvar documentos"}
        </button>
      </div>
    </form>
  );
}

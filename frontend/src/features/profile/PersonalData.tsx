import { type FormEvent, useState } from "react";
import { Aviso, CampoForm, SelecaoUf } from "../../components/ui";
import { chamar } from "../../lib/api";
import { apenasDigitos, telefoneE164, telefoneFormatado } from "../../lib/formatters/format";
import { mensagemDe, useEnvio } from "../../lib/hooks/use";
import type { Cliente } from "../../lib/types";

import { Secao } from "./shared";

export function DadosPessoais({
  cliente,
  etag,
  aoSalvar,
}: {
  cliente: Cliente;
  etag: string | null;
  aoSalvar: () => void;
}) {
  const inicial = () => ({
    nomeCompleto: cliente.nomeCompleto,
    telefone: telefoneFormatado(cliente.telefone),
    cep: apenasDigitos(cliente.endereco.cep).replace(/^(\d{5})(\d{3})$/, "$1-$2"),
    logradouro: cliente.endereco.logradouro,
    numero: cliente.endereco.numero,
    complemento: cliente.endereco.complemento ?? "",
    bairro: cliente.endereco.bairro,
    cidade: cliente.endereco.cidade,
    uf: cliente.endereco.uf,
  });
  const [editando, setEditando] = useState(false);
  const [f, setF] = useState(inicial);
  const [erro, setErro] = useState<string | null>(null);
  const { enviando, executar } = useEnvio();
  const mudar = (k: keyof ReturnType<typeof inicial>) => (e: { target: { value: string } }) =>
    setF({ ...f, [k]: e.target.value });

  async function salvar(e: FormEvent) {
    e.preventDefault();
    await executar(async () => {
      setErro(null);
      const telefone = telefoneE164(f.telefone);
      if (!telefone) return setErro("Telefone inválido: informe DDD e número.");
      const end = cliente.endereco;
      const endereco = {
        cep: f.cep,
        logradouro: f.logradouro.trim(),
        numero: f.numero.trim(),
        complemento: f.complemento.trim() || null,
        bairro: f.bairro.trim(),
        cidade: f.cidade.trim(),
        uf: f.uf,
      };
      const corpo: Record<string, unknown> = {};
      if (f.nomeCompleto.trim() !== cliente.nomeCompleto)
        corpo.nomeCompleto = f.nomeCompleto.trim();
      if (telefone !== cliente.telefone) corpo.telefone = telefone;
      // Endereco so vai se mudou: com compra em andamento a API recusa qualquer endereco no PATCH.
      if (
        apenasDigitos(endereco.cep) !== apenasDigitos(end.cep) ||
        (["logradouro", "numero", "bairro", "cidade", "uf"] as const).some(
          (k) => endereco[k] !== end[k],
        ) ||
        endereco.complemento !== (end.complemento ?? null)
      )
        corpo.endereco = endereco;
      if (!Object.keys(corpo).length) return setEditando(false);
      try {
        await chamar("/clientes/meu-perfil", { metodo: "PATCH", corpo, ifMatch: etag });
        setEditando(false);
        aoSalvar();
      } catch (x) {
        setErro(mensagemDe(x));
      }
    });
  }

  const c = cliente;
  const itens: [string, string][] = [
    ["Nome", c.nomeCompleto],
    ["CPF", c.cpf],
    ["E-mail", c.email],
    ["Telefone", telefoneFormatado(c.telefone)],
    ["RG", c.rg ? `${c.rg.numero} · ${c.rg.orgaoEmissor}/${c.rg.uf}` : "não informado"],
    ["CNH", c.cnh ?? "não informada"],
    [
      "Endereço",
      `${c.endereco.logradouro}, ${c.endereco.numero}${c.endereco.complemento ? ` (${c.endereco.complemento})` : ""} · ${c.endereco.bairro}, ${c.endereco.cidade}/${c.endereco.uf}`,
    ],
  ];
  if (!editando) {
    return (
      <div className="cartao grid gap-4 p-6">
        <dl className="grid gap-4 sm:grid-cols-2">
          {itens.map(([k, v]) => (
            <div key={k} className="min-w-0">
              <dt className="rotulo">{k}</dt>
              <dd className="text-sm font-semibold wrap-anywhere">{v}</dd>
            </div>
          ))}
        </dl>
        <div>
          <button
            type="button"
            className="botao-contorno"
            onClick={() => {
              setF(inicial());
              setErro(null);
              setEditando(true);
            }}
          >
            Editar dados
          </button>
        </div>
      </div>
    );
  }
  return (
    <form onSubmit={salvar} className="cartao grid gap-6 p-6" aria-label="Editar dados">
      <p className="text-sm text-ultrassonico">
        CPF, e-mail e data de nascimento não podem ser alterados. Com uma compra em andamento, o
        endereço fica bloqueado.
      </p>
      <Secao titulo="Dados pessoais">
        <CampoForm
          id="e-nome"
          rotulo="Nome completo"
          obrigatorio
          value={f.nomeCompleto}
          onChange={mudar("nomeCompleto")}
          maxLength={120}
          minLength={3}
          autoComplete="name"
        />
        <CampoForm
          id="e-tel"
          rotulo="Telefone com DDD"
          obrigatorio
          value={f.telefone}
          onChange={mudar("telefone")}
          maxLength={20}
          inputMode="tel"
          autoComplete="tel"
        />
      </Secao>
      <Secao titulo="Endereço">
        <CampoForm
          id="e-cep"
          rotulo="CEP"
          obrigatorio
          value={f.cep}
          onChange={mudar("cep")}
          maxLength={9}
          inputMode="numeric"
          pattern="\d{5}-?\d{3}"
          title="8 dígitos"
          autoComplete="postal-code"
        />
        <CampoForm
          id="e-logradouro"
          rotulo="Logradouro"
          obrigatorio
          value={f.logradouro}
          onChange={mudar("logradouro")}
          maxLength={120}
        />
        <CampoForm
          id="e-numero"
          rotulo="Número"
          obrigatorio
          value={f.numero}
          onChange={mudar("numero")}
          maxLength={10}
        />
        <CampoForm
          id="e-compl"
          rotulo="Complemento"
          value={f.complemento}
          onChange={mudar("complemento")}
          maxLength={60}
          placeholder="Apto, bloco… (opcional)"
        />
        <CampoForm
          id="e-bairro"
          rotulo="Bairro"
          obrigatorio
          value={f.bairro}
          onChange={mudar("bairro")}
          maxLength={80}
        />
        <CampoForm
          id="e-cidade"
          rotulo="Cidade"
          obrigatorio
          value={f.cidade}
          onChange={mudar("cidade")}
          maxLength={80}
        />
        <SelecaoUf
          id="e-uf"
          rotulo="Estado (UF)"
          obrigatorio
          valor={f.uf}
          aoMudar={(v) => setF({ ...f, uf: v })}
        />
      </Secao>
      {erro && <Aviso>{erro}</Aviso>}
      <div className="flex flex-wrap gap-2">
        <button type="submit" className="botao-primario" disabled={enviando}>
          {enviando ? "Salvando…" : "Salvar alterações"}
        </button>
        <button
          type="button"
          className="botao-fantasma"
          onClick={() => setEditando(false)}
          disabled={enviando}
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}

import { type FormEvent, useState } from "react";
import { Aviso, CampoForm, Etapas, SelecaoUf } from "../../components/ui";
import { enviarJson } from "../../lib/api";
import { config } from "../../lib/config";
import { telefoneE164 } from "../../lib/formatters/format";
import { mensagemDe, useEnvio } from "../../lib/hooks/use";
import { cpfValido } from "../../lib/validators/validation";

import { rgIncompleto, Secao } from "./shared";

const vazio = {
  nomeCompleto: "",
  cpf: "",
  dataNascimento: "",
  telefone: "",
  cep: "",
  logradouro: "",
  numero: "",
  complemento: "",
  bairro: "",
  cidade: "",
  uf: "",
  rgNumero: "",
  rgOrgao: "",
  rgUf: "",
  marketing: false,
};
type Form = typeof vazio;

export function Cadastro({ aoCriar }: { aoCriar: () => void }) {
  const [f, setF] = useState<Form>(vazio);
  const [etapa, setEtapa] = useState(1);
  const [aceito, setAceito] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const { enviando, executar } = useEnvio();
  const mudar = (k: keyof Form) => (e: { target: { value: string } }) => {
    setErro(null);
    setF({ ...f, [k]: e.target.value });
  };
  const hoje = new Date().toISOString().slice(0, 10);
  // A API exige titular com 18 anos ou mais: o campo ja limita a data e o envio explica.
  const maioridade = `${Number(hoje.slice(0, 4)) - 18}${hoje.slice(4)}`;

  async function enviar(e: FormEvent) {
    e.preventDefault();
    await executar(async () => {
      setErro(null);
      if (!cpfValido(f.cpf)) return setErro("CPF inválido. Confira os dígitos.");
      if (f.dataNascimento > hoje) return setErro("A data de nascimento não pode ser futura.");
      if (f.dataNascimento > maioridade)
        return setErro("É preciso ter 18 anos ou mais para se cadastrar.");
      const telefone = telefoneE164(f.telefone);
      if (!telefone) return setErro("Telefone inválido: informe DDD e número.");
      if (etapa === 1) {
        setEtapa(2);
        return;
      }
      if (etapa === 2) {
        setEtapa(3);
        return;
      }
      if (rgIncompleto(f.rgNumero, f.rgOrgao, f.rgUf))
        return setErro("Para informar o RG, preencha número, órgão emissor e UF do RG.");
      try {
        await enviarJson("/clientes", {
          nomeCompleto: f.nomeCompleto.trim(),
          cpf: f.cpf,
          dataNascimento: f.dataNascimento,
          telefone,
          endereco: {
            cep: f.cep,
            logradouro: f.logradouro.trim(),
            numero: f.numero.trim(),
            complemento: f.complemento.trim() || null,
            bairro: f.bairro.trim(),
            cidade: f.cidade.trim(),
            uf: f.uf,
          },
          rg: f.rgNumero ? { numero: f.rgNumero, orgaoEmissor: f.rgOrgao, uf: f.rgUf } : null,
          consentimento: {
            versaoTermo: config().versaoTermo,
            aceito: true,
            finalidades: f.marketing ? ["EXECUCAO_CONTRATO", "MARKETING"] : ["EXECUCAO_CONTRATO"],
          },
        });
        aoCriar();
      } catch (x) {
        setErro(mensagemDe(x));
      }
    });
  }

  return (
    <form onSubmit={enviar} className="cartao grid gap-6 p-5 sm:gap-8 sm:p-6">
      <Etapas atual={etapa} itens={["Dados pessoais", "Endereço", "Documentos e termos"]} />
      <div className="-mt-4">
        <p className="text-sm font-semibold text-white">Etapa {etapa} de 3</p>
        <p className="mt-1 text-sm text-ultrassonico">
          Usamos seus dados para emitir o pagamento e a documentação. CPF e RG são cifrados e
          aparecem mascarados.
        </p>
      </div>
      {etapa === 1 && (
        <Secao titulo="Dados pessoais">
          <CampoForm
            id="c-nome"
            rotulo="Nome completo"
            obrigatorio
            value={f.nomeCompleto}
            onChange={mudar("nomeCompleto")}
            maxLength={120}
            minLength={3}
            autoComplete="name"
          />
          <CampoForm
            id="c-cpf"
            rotulo="CPF"
            obrigatorio
            value={f.cpf}
            onChange={mudar("cpf")}
            maxLength={14}
            inputMode="numeric"
            placeholder="000.000.000-00"
          />
          <CampoForm
            id="c-nasc"
            rotulo="Data de nascimento"
            obrigatorio
            type="date"
            value={f.dataNascimento}
            onChange={mudar("dataNascimento")}
            max={maioridade}
            min="1900-01-01"
            autoComplete="bday"
          />
          <CampoForm
            id="c-tel"
            rotulo="Telefone com DDD"
            obrigatorio
            value={f.telefone}
            onChange={mudar("telefone")}
            maxLength={20}
            inputMode="tel"
            placeholder="(11) 98765-4321"
            autoComplete="tel"
          />
        </Secao>
      )}
      {etapa === 2 && (
        <Secao titulo="Endereço" texto="Necessário para a emissão do pagamento e da documentação.">
          <CampoForm
            id="c-cep"
            rotulo="CEP"
            obrigatorio
            value={f.cep}
            onChange={mudar("cep")}
            maxLength={9}
            inputMode="numeric"
            placeholder="01310-100"
            pattern="\d{5}-?\d{3}"
            title="Informe 8 dígitos, com ou sem hífen."
            autoComplete="postal-code"
          />
          <CampoForm
            id="c-logradouro"
            rotulo="Logradouro"
            obrigatorio
            value={f.logradouro}
            onChange={mudar("logradouro")}
            maxLength={120}
            autoComplete="address-line1"
          />
          <CampoForm
            id="c-numero"
            rotulo="Número"
            obrigatorio
            value={f.numero}
            onChange={mudar("numero")}
            maxLength={10}
          />
          <CampoForm
            id="c-compl"
            rotulo="Complemento"
            value={f.complemento}
            onChange={mudar("complemento")}
            maxLength={60}
            placeholder="Apto, bloco… (opcional)"
          />
          <CampoForm
            id="c-bairro"
            rotulo="Bairro"
            obrigatorio
            value={f.bairro}
            onChange={mudar("bairro")}
            maxLength={80}
          />
          <CampoForm
            id="c-cidade"
            rotulo="Cidade"
            obrigatorio
            value={f.cidade}
            onChange={mudar("cidade")}
            maxLength={80}
            autoComplete="address-level2"
          />
          <SelecaoUf
            id="c-uf"
            rotulo="Estado (UF)"
            obrigatorio
            valor={f.uf}
            aoMudar={(v) => {
              setErro(null);
              setF({ ...f, uf: v });
            }}
          />
        </Secao>
      )}
      {etapa === 3 && (
        <>
          <Secao
            titulo="Documento (RG)"
            texto="Opcional para concluir o cadastro; obrigatório para reservar. Você também pode informar depois no perfil."
          >
            <CampoForm
              id="c-rg"
              rotulo="Número do RG"
              value={f.rgNumero}
              onChange={mudar("rgNumero")}
              maxLength={20}
            />
            <CampoForm
              id="c-rg-orgao"
              rotulo="Órgão emissor"
              value={f.rgOrgao}
              onChange={mudar("rgOrgao")}
              maxLength={10}
              placeholder="SSP (opcional)"
            />
            <SelecaoUf
              id="c-rg-uf"
              rotulo="UF do RG"
              valor={f.rgUf}
              aoMudar={(v) => {
                setErro(null);
                setF({ ...f, rgUf: v });
              }}
            />
          </Secao>
          <div className="grid gap-3">
            <label className="flex min-h-11 items-start gap-3 text-sm">
              <input
                type="checkbox"
                required
                checked={aceito}
                onChange={(e) => setAceito(e.target.checked)}
                className="mt-1 size-5 shrink-0 accent-fiap"
              />
              <span>
                Aceito os termos (versão {config().versaoTermo}) para tratamento dos meus dados na
                execução do contrato de compra{" "}
                <span className="text-fiap-claro" aria-hidden>
                  *
                </span>
              </span>
            </label>
            <label className="flex min-h-11 items-start gap-3 text-sm text-prata">
              <input
                type="checkbox"
                checked={f.marketing}
                onChange={(e) => setF({ ...f, marketing: e.target.checked })}
                className="mt-1 size-5 shrink-0 accent-fiap"
              />
              Quero receber ofertas (opcional).
            </label>
          </div>
        </>
      )}
      {erro && <Aviso>{erro}</Aviso>}
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
        {etapa > 1 ? (
          <button
            type="button"
            className="botao-contorno"
            onClick={() => {
              setErro(null);
              setEtapa(etapa - 1);
            }}
          >
            Voltar
          </button>
        ) : (
          <span />
        )}
        <button
          type="submit"
          className="botao-primario"
          disabled={enviando || (etapa === 3 && !aceito)}
        >
          {etapa < 3 ? "Continuar" : enviando ? "Salvando…" : "Concluir cadastro"}
        </button>
      </div>
    </form>
  );
}

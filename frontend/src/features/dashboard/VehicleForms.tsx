import { Plus } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Aviso } from "../../components/ui";
import { chamar, enviarJson } from "../../lib/api";
import { titulo } from "../../lib/formatters/format";
import { textoDoFormulario } from "../../lib/forms";
import { mensagemDe, useEnvio } from "../../lib/hooks/use";
import type { Veiculo } from "../../lib/types";
import { validarVeiculo } from "../../lib/validators/validation";
import { Campo, Opcoes, useEmFoco } from "./shared";

// Sugestoes (datalist): a API aceita qualquer marca de ate 60 caracteres.
const MARCAS = [
  "Audi",
  "BMW",
  "BYD",
  "Caoa Chery",
  "Chevrolet",
  "Citroën",
  "Fiat",
  "Ford",
  "GWM",
  "Honda",
  "Hyundai",
  "Jeep",
  "Kia",
  "Mercedes-Benz",
  "Mitsubishi",
  "Nissan",
  "Peugeot",
  "Ram",
  "Renault",
  "Toyota",
  "Volkswagen",
  "Volvo",
];
const COMBUSTIVEIS = ["FLEX", "GASOLINA", "ETANOL", "DIESEL", "HIBRIDO", "ELETRICO", "GNV"];
const CAMBIOS = ["MANUAL", "AUTOMATICO", "CVT", "AUTOMATIZADO"];
// A API lista um status por vez (padrao DISPONIVEL): nao ha opcao "Todos".
const ANO_MAX = new Date().getFullYear() + 1;

export const Marcas = () => (
  <datalist id="marcas-sugeridas">
    {MARCAS.map((m) => (
      <option key={m} value={m} />
    ))}
  </datalist>
);

export function NovoVeiculo({ aoCriar }: { aoCriar: (modelo: string) => void }) {
  const [erro, setErro] = useState<string | null>(null);
  const [fab, setFab] = useState("");
  const { enviando, executar } = useEnvio();
  function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    void executar(() => salvar(form));
  }
  async function salvar(form: HTMLFormElement) {
    const f = textoDoFormulario(form);
    const problemas = validarVeiculo({
      renavam: f("renavam"),
      chassi: f("chassi"),
      placa: f("placa"),
      anoFabricacao: Number(f("anoFabricacao")),
      anoModelo: Number(f("anoModelo")),
      preco: Number(f("preco")),
      quilometragem: Number(f("quilometragem")),
    });
    if (problemas.length) {
      setErro(problemas.join(" "));
      return;
    }
    try {
      await enviarJson("/veiculos", {
        marca: f("marca").trim(),
        modelo: f("modelo").trim(),
        anoFabricacao: Number(f("anoFabricacao")),
        anoModelo: Number(f("anoModelo")),
        cor: f("cor").trim(),
        preco: Number(f("preco")).toFixed(2),
        quilometragem: Number(f("quilometragem")),
        placa: f("placa") ? f("placa").toUpperCase() : null,
        renavam: f("renavam"),
        chassi: f("chassi").toUpperCase(),
        combustivel: f("combustivel") || null,
        cambio: f("cambio") || null,
      });
      form.reset();
      setFab("");
      setErro(null);
      aoCriar(`${f("marca").trim()} ${f("modelo").trim()}`);
    } catch (x) {
      setErro(mensagemDe(x));
    }
  }
  return (
    <details className="cartao mb-6 p-5">
      <summary className="flex min-h-11 cursor-pointer items-center gap-2 text-sm font-bold text-fiap-claro">
        <Plus className="size-4" aria-hidden /> Cadastrar veículo
      </summary>
      <form onSubmit={enviar} className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Campo
          id="v-marca"
          rotulo="Marca"
          name="marca"
          required
          minLength={2}
          maxLength={60}
          list="marcas-sugeridas"
          autoComplete="off"
          placeholder="Ex.: Peugeot"
        />
        <Campo id="v-modelo" rotulo="Modelo" name="modelo" required minLength={2} maxLength={80} />
        <Campo
          id="v-fab"
          rotulo="Ano de fabricação"
          name="anoFabricacao"
          type="number"
          required
          min={1950}
          max={ANO_MAX}
          step={1}
          value={fab}
          onChange={(e) => setFab(e.target.value)}
        />
        <Campo
          id="v-ano"
          rotulo="Ano do modelo"
          name="anoModelo"
          type="number"
          required
          min={fab ? Number(fab) : 1950}
          max={fab ? Number(fab) + 1 : ANO_MAX + 1}
          step={1}
        />
        <Campo
          id="v-cor"
          rotulo="Cor"
          name="cor"
          required
          minLength={3}
          maxLength={30}
          placeholder="Ex.: Prata Bari"
        />
        <Campo
          id="v-preco"
          rotulo="Preço (R$)"
          name="preco"
          type="number"
          required
          min={0.01}
          max={9999999.99}
          step={0.01}
        />
        <Campo
          id="v-km"
          rotulo="Quilometragem"
          name="quilometragem"
          type="number"
          required
          min={0}
          max={1000000}
          step={1}
        />
        <Campo
          id="v-placa"
          rotulo="Placa (opcional)"
          name="placa"
          pattern="[A-Za-z]{3}[0-9][A-Za-z0-9][0-9]{2}"
          maxLength={7}
          title="Formato ABC1234 ou ABC1D23"
        />
        <Campo
          id="v-renavam"
          rotulo="RENAVAM"
          name="renavam"
          required
          pattern="[0-9]{11}"
          inputMode="numeric"
          maxLength={11}
          title="11 dígitos"
        />
        <Campo
          id="v-chassi"
          rotulo="Chassi"
          name="chassi"
          required
          pattern="[A-HJ-NPR-Za-hj-npr-z0-9]{17}"
          maxLength={17}
          title="17 caracteres alfanuméricos, sem I, O e Q"
        />
        <Opcoes id="v-combustivel" rotulo="Combustível" nome="combustivel" valores={COMBUSTIVEIS} />
        <Opcoes id="v-cambio" rotulo="Câmbio" nome="cambio" valores={CAMBIOS} />
        <div className="sm:col-span-2 lg:col-span-4">
          {erro && (
            <div className="mb-3">
              <Aviso>{erro}</Aviso>
            </div>
          )}
          <button type="submit" className="botao-primario" disabled={enviando}>
            {enviando ? "Salvando…" : "Salvar veículo"}
          </button>
        </div>
      </form>
    </details>
  );
}

export type VeiculoCompleto = Veiculo & { renavam?: string; chassi?: string };

/** Edita um veiculo. Reservado/aguardando retirada nao muda preco, chassi nem RENAVAM; vendido nao edita. */
export function EditarVeiculo({
  veiculo,
  aoFechar,
  aoSalvar,
}: {
  veiculo: VeiculoCompleto;
  aoFechar: () => void;
  aoSalvar: () => void;
}) {
  const [erro, setErro] = useState<string | null>(null);
  const [fab, setFab] = useState(String(veiculo.anoFabricacao));
  const travado = veiculo.status === "RESERVADO" || veiculo.status === "AGUARDANDO_RETIRADA";
  const foco = useEmFoco<HTMLFormElement>();
  const { enviando, executar } = useEnvio();
  function enviar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    void executar(() => salvar(form));
  }
  async function salvar(form: HTMLFormElement) {
    const f = textoDoFormulario(form);
    const preco = travado ? Number(veiculo.preco) : Number(f("preco"));
    const problemas = validarVeiculo({
      renavam: travado ? (veiculo.renavam ?? "") : f("renavam"),
      chassi: travado ? (veiculo.chassi ?? "") : f("chassi"),
      placa: f("placa"),
      anoFabricacao: Number(f("anoFabricacao")),
      anoModelo: Number(f("anoModelo")),
      preco,
      quilometragem: Number(f("quilometragem")),
    }).filter((p) => !travado || !/RENAVAM|Chassi/.test(p));
    if (problemas.length) return setErro(problemas.join(" "));
    const novo: Record<string, unknown> = {
      marca: f("marca").trim(),
      modelo: f("modelo").trim(),
      anoFabricacao: Number(f("anoFabricacao")),
      anoModelo: Number(f("anoModelo")),
      cor: f("cor").trim(),
      quilometragem: Number(f("quilometragem")),
      placa: f("placa") ? f("placa").toUpperCase() : null,
      combustivel: f("combustivel") || null,
      cambio: f("cambio") || null,
      ...(travado
        ? {}
        : { preco: preco.toFixed(2), renavam: f("renavam"), chassi: f("chassi").toUpperCase() }),
    };
    const atual: Record<string, unknown> = { ...veiculo, preco: Number(veiculo.preco).toFixed(2) };
    // So o que mudou vai no PATCH (campos nulos nao sao enviados: a API os ignora).
    const corpo = Object.fromEntries(
      Object.entries(novo).filter(([k, v]) => v !== null && v !== (atual[k] ?? null)),
    );
    if (!Object.keys(corpo).length) return aoFechar();
    try {
      await chamar(`/veiculos/${veiculo.id}`, {
        metodo: "PATCH",
        corpo,
        ifMatch: `"v${veiculo.versao ?? 1}"`,
      });
      aoSalvar();
    } catch (x) {
      setErro(mensagemDe(x));
    }
  }
  return (
    <form
      ref={foco}
      onSubmit={enviar}
      className="cartao mb-6 grid scroll-mt-24 gap-4 border-fiap/40 p-5 sm:grid-cols-2 lg:grid-cols-4"
      aria-label="Editar veículo"
    >
      <p className="text-sm font-bold sm:col-span-2 lg:col-span-4">
        Editar {veiculo.marca} {veiculo.modelo}
        {travado && (
          <span className="mt-0.5 block text-xs font-medium text-ultrassonico">
            Veículo {titulo(veiculo.status).toLowerCase()}: preço, chassi e RENAVAM não podem mudar.
          </span>
        )}
      </p>
      <Campo
        id="ed-marca"
        rotulo="Marca"
        name="marca"
        required
        minLength={2}
        maxLength={60}
        list="marcas-sugeridas"
        defaultValue={veiculo.marca}
      />
      <Campo
        id="ed-modelo"
        rotulo="Modelo"
        name="modelo"
        required
        minLength={2}
        maxLength={80}
        defaultValue={veiculo.modelo}
      />
      <Campo
        id="ed-fab"
        rotulo="Ano de fabricação"
        name="anoFabricacao"
        type="number"
        required
        min={1950}
        max={ANO_MAX}
        step={1}
        value={fab}
        onChange={(e) => setFab(e.target.value)}
      />
      <Campo
        id="ed-ano"
        rotulo="Ano do modelo"
        name="anoModelo"
        type="number"
        required
        min={Number(fab) || 1950}
        max={(Number(fab) || ANO_MAX) + 1}
        step={1}
        defaultValue={veiculo.anoModelo}
      />
      <Campo
        id="ed-cor"
        rotulo="Cor"
        name="cor"
        required
        minLength={3}
        maxLength={30}
        defaultValue={veiculo.cor}
      />
      <Campo
        id="ed-preco"
        rotulo="Preço (R$)"
        name="preco"
        type="number"
        required
        min={0.01}
        max={9999999.99}
        step={0.01}
        defaultValue={Number(veiculo.preco)}
        disabled={travado}
      />
      <Campo
        id="ed-km"
        rotulo="Quilometragem"
        name="quilometragem"
        type="number"
        required
        min={0}
        max={1000000}
        step={1}
        defaultValue={veiculo.quilometragem}
      />
      <Campo
        id="ed-placa"
        rotulo="Placa (opcional)"
        name="placa"
        pattern="[A-Za-z]{3}[0-9][A-Za-z0-9][0-9]{2}"
        maxLength={7}
        title="Formato ABC1234 ou ABC1D23"
        defaultValue={veiculo.placa ?? ""}
      />
      <Campo
        id="ed-renavam"
        rotulo="RENAVAM"
        name="renavam"
        required={!travado}
        pattern="[0-9]{11}"
        inputMode="numeric"
        maxLength={11}
        title="11 dígitos"
        defaultValue={veiculo.renavam ?? ""}
        disabled={travado}
      />
      <Campo
        id="ed-chassi"
        rotulo="Chassi"
        name="chassi"
        required={!travado}
        pattern="[A-HJ-NPR-Za-hj-npr-z0-9]{17}"
        maxLength={17}
        title="17 caracteres alfanuméricos, sem I, O e Q"
        defaultValue={veiculo.chassi ?? ""}
        disabled={travado}
      />
      <Opcoes
        id="ed-combustivel"
        rotulo="Combustível"
        nome="combustivel"
        valores={COMBUSTIVEIS}
        valor={veiculo.combustivel}
      />
      <Opcoes
        id="ed-cambio"
        rotulo="Câmbio"
        nome="cambio"
        valores={CAMBIOS}
        valor={veiculo.cambio}
      />
      <div className="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-4">
        {erro && (
          <div className="w-full">
            <Aviso>{erro}</Aviso>
          </div>
        )}
        <button type="submit" className="botao-primario" disabled={enviando}>
          {enviando ? "Salvando…" : "Salvar alterações"}
        </button>
        <button type="button" className="botao-fantasma" onClick={aoFechar}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

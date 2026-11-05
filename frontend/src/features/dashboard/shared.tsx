import { type InputHTMLAttributes, useEffect, useRef } from "react";
import { titulo } from "../../lib/formatters/format";

export type Mensagem = { tipo: "ok" | "erro"; texto: string } | null;

export function Campo({
  id,
  rotulo,
  ...resto
}: { id: string; rotulo: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <label className="rotulo" htmlFor={id}>
        {rotulo}
      </label>
      <input id={id} className="campo" {...resto} />
    </div>
  );
}

export function Opcoes({
  id,
  rotulo,
  nome,
  valores,
  valor,
}: {
  id: string;
  rotulo: string;
  nome: string;
  valores: string[];
  valor?: string | null;
}) {
  return (
    <div>
      <label className="rotulo" htmlFor={id}>
        {rotulo}
      </label>
      <select id={id} name={nome} className="campo" defaultValue={valor ?? ""}>
        <option value="">Não informado</option>
        {valores.map((o) => (
          <option key={o} value={o}>
            {titulo(o)}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Formulario aberto a partir de uma linha da lista: aparece acima dela, entao rola ate ele e foca o primeiro campo. */
export function useEmFoco<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    ref.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    ref.current?.querySelector<HTMLElement>("input, select")?.focus({ preventScroll: true });
  }, []);
  return ref;
}

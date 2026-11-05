import type { ReactNode } from "react";
export const Secao = ({
  titulo,
  texto,
  children,
}: {
  titulo: string;
  texto?: string;
  children: ReactNode;
}) => (
  <fieldset className="grid min-w-0 gap-4 sm:grid-cols-2 lg:grid-cols-3">
    <legend className="mb-3 w-full text-sm font-extrabold">
      {titulo}
      {texto && <span className="mt-0.5 block text-xs font-medium text-ultrassonico">{texto}</span>}
    </legend>
    {children}
  </fieldset>
);

/** RG: opcional no cadastro, obrigatorio para comprar; se um campo for preenchido, os tres sao necessarios. */
export function rgIncompleto(n: string, o: string, u: string): boolean {
  const preenchidos = [n, o, u].filter(Boolean).length;
  return preenchidos > 0 && preenchidos < 3;
}

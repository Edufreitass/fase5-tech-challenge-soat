import { ehObjeto } from "./json";

/** Estado de navegacao pode vir de historico ou de links anteriores. */
export function retornoInterno(estado: unknown): string | undefined {
  if (!ehObjeto(estado) || typeof estado.de !== "string") return undefined;
  const caminho = estado.de;
  return caminho.startsWith("/") && !caminho.startsWith("//") && !caminho.includes("\\")
    ? caminho
    : undefined;
}

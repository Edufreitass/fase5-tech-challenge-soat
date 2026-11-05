/** JSON externo precisa ser refinado antes de acessar suas propriedades. */
export function ehObjeto(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

export function ehListaDeTextos(valor: unknown): valor is string[] {
  return Array.isArray(valor) && valor.every((item: unknown) => typeof item === "string");
}

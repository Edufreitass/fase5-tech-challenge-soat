import { lerTodas } from "../catalog/catalog";
import { mensagemDe, useBusca } from "./use";

type Consulta = Record<string, string | number | undefined>;

/** Compartilha cancelamento e recarga com as buscas pontuais. */
export function useLista<T>(caminho: string, consulta: Consulta) {
  const chave = `${caminho}:${JSON.stringify(Object.entries(consulta).sort(([a], [b]) => a.localeCompare(b)))}`;
  const busca = useBusca(() => lerTodas<T>(caminho, consulta), chave);
  return {
    itens: busca.dados,
    erro: busca.erro ? mensagemDe(busca.erro) : null,
    recarregar: busca.recarregar,
  };
}

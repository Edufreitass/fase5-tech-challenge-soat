import type { StatusVenda } from "./types";

export type EstadoNo = "feito" | "atual" | "pendente" | "falha";

export interface NoSaga {
  id: string;
  rotulo: string;
  estado: EstadoNo;
}

const CAMINHO_FELIZ: { id: string; rotulo: string; status: StatusVenda[] }[] = [
  { id: "reserva", rotulo: "Veículo reservado", status: ["CRIADO", "RESERVADO"] },
  { id: "pagamento", rotulo: "Aguardando Pix", status: ["AGUARDANDO_PAGAMENTO"] },
  { id: "pago", rotulo: "Pagamento confirmado", status: ["PAGO"] },
  { id: "retirada", rotulo: "Retirada concluída", status: ["CONCLUIDO"] },
];

const FINAIS_RUINS: Record<string, string> = {
  CANCELADO: "Compra cancelada",
  ESTORNADO: "Pagamento estornado",
};

/** Traduz o status da venda nos nos do fluxo exibido (React Flow). */
export function montarFluxo(status: StatusVenda): NoSaga[] {
  const ruim = FINAIS_RUINS[status];
  const nos: NoSaga[] = [];
  if (ruim) {
    // Antes de falhar a venda passou ao menos pela reserva (e, se estornada, pelo pagamento).
    const percorridos = status === "ESTORNADO" ? 3 : 1;
    CAMINHO_FELIZ.slice(0, percorridos).forEach((e) => {
      nos.push({ id: e.id, rotulo: e.rotulo, estado: "feito" });
    });
    nos.push({ id: "fim", rotulo: ruim, estado: "falha" });
    return nos;
  }
  const indice = CAMINHO_FELIZ.findIndex((e) => e.status.includes(status));
  CAMINHO_FELIZ.forEach((e, i) => {
    const concluido = status === "CONCLUIDO" || i < indice;
    nos.push({
      id: e.id,
      rotulo: e.rotulo,
      estado: concluido ? "feito" : i === indice ? "atual" : "pendente",
    });
  });
  return nos;
}

export const VENDA_FINAL = (s: StatusVenda): boolean =>
  s === "CONCLUIDO" || s === "CANCELADO" || s === "ESTORNADO";

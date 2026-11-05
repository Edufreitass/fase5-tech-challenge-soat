/** O gateway simulado embute o identificador da cobranca (`tx_<16 hex>`) no payload Pix copia e cola. */
const TRANSACAO = /BR\.GOV\.BCB\.PIX0136(tx_[0-9a-f]{16})/;

export function transacaoDoPix(codigo: string | null | undefined): string | null {
  return codigo?.match(TRANSACAO)?.[1] ?? null;
}

import { configure } from "@testing-library/react";
import "@testing-library/jest-dom";

// Renderizacoes com varias listas (lucide, formularios) podem passar de 1 s em maquinas lentas de CI.
configure({ asyncUtilTimeout: 4000 });
window.scrollTo = () => undefined;

import { TextDecoder, TextEncoder } from "node:util";

Object.assign(globalThis, { TextEncoder, TextDecoder });
if (!globalThis.crypto?.subtle) {
  Object.defineProperty(globalThis, "crypto", { value: require("node:crypto").webcrypto });
}

// jsdom nao traz fetch/Response: versao minima para os testes do cliente HTTP.
class RespostaFalsa {
  readonly ok: boolean;
  readonly status: number;
  readonly headers: { get: (k: string) => string | null };
  constructor(
    private corpo: string | null,
    init: { status?: number; headers?: Record<string, string> } = {},
  ) {
    this.status = init.status ?? 200;
    this.ok = this.status >= 200 && this.status < 300;
    const h = Object.fromEntries(
      Object.entries(init.headers ?? {}).map(([k, v]) => [k.toLowerCase(), v]),
    );
    this.headers = { get: (k) => h[k.toLowerCase()] ?? null };
  }
  async text() {
    return this.corpo ?? "";
  }
  async json() {
    return JSON.parse(this.corpo ?? "null");
  }
}
Object.assign(globalThis, { Response: RespostaFalsa });

import { opcoesDev } from "./environment";

describe("ambiente do vite dev", () => {
  it("cria proxy para a API quando API_ALVO esta configurada", () => {
    const o = opcoesDev({ API_ALVO: "https://x.execute-api.us-east-1.amazonaws.com" });
    expect(Object.keys(o.proxy ?? {})).toEqual(["/api"]);
    expect(o.proxy?.["/api"]?.target).toBe("https://x.execute-api.us-east-1.amazonaws.com");
    expect(o.proxy?.["/api"]?.rewrite("/api/veiculos")).toBe("/v1/veiculos");
  });

  it("sem API_ALVO nao cria proxy", () => {
    expect(opcoesDev({}).proxy).toBeUndefined();
  });
});

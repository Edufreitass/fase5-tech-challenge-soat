export interface Proxy {
  target: string;
  changeOrigin: boolean;
  rewrite: (caminho: string) => string;
}

export interface OpcoesDev {
  proxy: Record<string, Proxy> | undefined;
}

export function opcoesDev(env: Record<string, string | undefined>): OpcoesDev {
  return {
    proxy: env.API_ALVO
      ? {
          "/api": {
            target: env.API_ALVO,
            changeOrigin: true,
            rewrite: (p) => p.replace(/^\/api/, "/v1"),
          },
        }
      : undefined,
  };
}

import { useCallback, useEffect, useRef, useState } from "react";
import { ErroApi } from "../api";
import { acentuar, rotuloDoCampo } from "../formatters/format";

export interface Estado<T> {
  dados: T | null;
  erro: Error | null;
  carregando: boolean;
  recarregar: () => void;
}

interface Recurso<T> {
  chave: string;
  dados: T | null;
  erro: Error | null;
  carregando: boolean;
}

interface OpcoesBusca<T> {
  intervaloMs?: number;
  ativo?: boolean;
  continuar?: (dados: T | null, erro: Error | null) => boolean;
}

/** A chave identifica o recurso; respostas de buscas antigas sao descartadas. */
export function useBusca<T>(
  buscar: () => Promise<T>,
  chave = "",
  { intervaloMs, ativo = true, continuar }: OpcoesBusca<T> = {},
): Estado<T> {
  const [recurso, setRecurso] = useState<Recurso<T>>({
    chave,
    dados: null,
    erro: null,
    carregando: ativo,
  });
  const fn = useRef(buscar);
  const requisicao = useRef(0);
  useEffect(() => {
    fn.current = buscar;
  }, [buscar]);

  const carregar = useCallback(async () => {
    if (!ativo) return;
    const numero = ++requisicao.current;
    setRecurso((anterior) =>
      anterior.chave === chave
        ? { ...anterior, erro: null, carregando: anterior.dados === null }
        : { chave, dados: null, erro: null, carregando: true },
    );
    try {
      const dados = await fn.current();
      if (numero === requisicao.current)
        setRecurso({ chave, dados, erro: null, carregando: false });
    } catch (falha) {
      if (numero === requisicao.current)
        setRecurso((anterior) => ({
          ...anterior,
          erro: falha instanceof Error ? falha : new Error("Erro inesperado."),
          carregando: false,
        }));
    }
  }, [ativo, chave]);

  useEffect(() => {
    void carregar();
    return () => {
      requisicao.current += 1;
    };
  }, [carregar]);

  const atual =
    ativo && recurso.chave === chave ? recurso : { dados: null, erro: null, carregando: ativo };
  const monitorar = ativo && (continuar?.(atual.dados, atual.erro) ?? true);
  useEffect(() => {
    if (!intervaloMs || intervaloMs <= 0 || !monitorar) return;
    const id = setInterval(() => {
      void carregar();
    }, intervaloMs);
    return () => clearInterval(id);
  }, [intervaloMs, monitorar, carregar]);

  return {
    ...atual,
    recarregar: useCallback(() => {
      void carregar();
    }, [carregar]),
  };
}

export function mensagemDe(e: unknown): string {
  if (e instanceof ErroApi) {
    const campos = e.campos.length
      ? ` (${e.campos.map((c) => [rotuloDoCampo(c.campo), c.mensagem ?? ""].filter(Boolean).join(": ")).join("; ")})`
      : "";
    const espera = e.retryAfter ? ` Tente de novo em ${e.retryAfter}s.` : "";
    return acentuar(`${e.detalhe ?? e.titulo}${campos}${espera}`);
  }
  return e instanceof Error ? e.message : "Erro inesperado.";
}

/** Envio que nao repete: enquanto `executar` roda, novas chamadas (duplo clique, Enter repetido) sao ignoradas.
 * O ref barra na hora; `enviando` desabilita o botao na proxima renderizacao. */
export function useEnvio(): {
  enviando: boolean;
  executar: (fn: () => Promise<void>) => Promise<void>;
} {
  const emCurso = useRef(false);
  const [enviando, setEnviando] = useState(false);
  const executar = useCallback(async (fn: () => Promise<void>) => {
    if (emCurso.current) return;
    emCurso.current = true;
    setEnviando(true);
    try {
      await fn();
    } finally {
      emCurso.current = false;
      setEnviando(false);
    }
  }, []);
  return { enviando, executar };
}

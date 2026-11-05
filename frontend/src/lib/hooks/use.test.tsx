import { act, renderHook, waitFor } from "@testing-library/react";
import { useBusca, useEnvio } from "./use";

function pendente<T>() {
  let resolver: (valor: T) => void = () => {
    throw new Error("Promise nao inicializada");
  };
  const promise = new Promise<T>((resolve) => {
    resolver = resolve;
  });
  return { promise, resolver };
}

describe("useBusca", () => {
  it("limpa o recurso anterior ao trocar a chave", async () => {
    // Arrange
    const segunda = pendente<string>();
    const buscar = jest.fn((chave: string) =>
      chave === "a" ? Promise.resolve("A") : segunda.promise,
    );
    const { result, rerender } = renderHook(({ chave }) => useBusca(() => buscar(chave), chave), {
      initialProps: { chave: "a" },
    });
    await waitFor(() => expect(result.current.dados).toBe("A"));

    // Act
    rerender({ chave: "b" });

    // Assert
    expect(result.current.dados).toBeNull();
    expect(result.current.carregando).toBe(true);
    await act(async () => {
      segunda.resolver("B");
    });
    expect(result.current.dados).toBe("B");
  });

  it("descarta resposta antiga que chega depois da nova", async () => {
    const primeira = pendente<string>();
    const segunda = pendente<string>();
    const { result, rerender } = renderHook(
      ({ chave }) => useBusca(() => (chave === "a" ? primeira.promise : segunda.promise), chave),
      { initialProps: { chave: "a" } },
    );

    rerender({ chave: "b" });
    await act(async () => {
      segunda.resolver("B");
    });
    await act(async () => {
      primeira.resolver("A");
    });

    expect(result.current.dados).toBe("B");
    expect(result.current.erro).toBeNull();
  });

  it("nao chama uma busca desativada e oculta os dados ao desativar", async () => {
    const buscar = jest.fn().mockResolvedValue("perfil");
    const { result, rerender } = renderHook(({ ativo }) => useBusca(buscar, "perfil", { ativo }), {
      initialProps: { ativo: false },
    });
    expect(buscar).not.toHaveBeenCalled();

    rerender({ ativo: true });
    await waitFor(() => expect(result.current.dados).toBe("perfil"));
    rerender({ ativo: false });

    expect(result.current.dados).toBeNull();
    expect(result.current.carregando).toBe(false);
  });

  it("normaliza falhas desconhecidas e permite nova tentativa", async () => {
    const buscar = jest.fn().mockRejectedValueOnce("falha").mockResolvedValue("recuperado");
    const { result } = renderHook(() => useBusca<string>(buscar));
    await waitFor(() => expect(result.current.erro?.message).toBe("Erro inesperado."));

    act(() => {
      result.current.recarregar();
    });

    await waitFor(() => expect(result.current.dados).toBe("recuperado"));
    expect(result.current.erro).toBeNull();
  });

  it("para o polling quando a condicao de acompanhamento termina", async () => {
    jest.useFakeTimers();
    try {
      const buscar = jest.fn().mockResolvedValueOnce("PENDENTE").mockResolvedValue("CONCLUIDO");
      const { result, unmount } = renderHook(() =>
        useBusca<string>(buscar, "venda", {
          intervaloMs: 1000,
          continuar: (dados) => dados !== "CONCLUIDO",
        }),
      );
      await act(async () => {});

      await act(async () => {
        jest.advanceTimersByTime(1000);
      });
      await act(async () => {
        jest.advanceTimersByTime(5000);
      });

      expect(result.current.dados).toBe("CONCLUIDO");
      expect(buscar).toHaveBeenCalledTimes(2);
      unmount();
    } finally {
      jest.useRealTimers();
    }
  });
});

describe("useEnvio", () => {
  it("bloqueia duplo envio e libera depois da conclusao", async () => {
    const operacao = pendente<void>();
    const salvar = jest.fn(() => operacao.promise);
    const { result } = renderHook(useEnvio);

    let envio: Promise<void> | undefined;
    act(() => {
      envio = result.current.executar(salvar);
      void result.current.executar(salvar);
    });

    expect(salvar).toHaveBeenCalledTimes(1);
    expect(result.current.enviando).toBe(true);
    await act(async () => {
      operacao.resolver();
      await envio;
    });
    expect(result.current.enviando).toBe(false);
  });
});

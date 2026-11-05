import { CarFront, RefreshCw } from "lucide-react";

/** Tela de quando nem a configuracao do ambiente carrega (sem rede, servidor fora do ar): explica e deixa tentar de novo. */
export function FalhaInicial({
  aoTentar = () => window.location.reload(),
}: {
  aoTentar?: () => void;
}) {
  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <div role="alert" className="cartao grid max-w-md gap-4 p-8 text-center">
        <span className="mx-auto grid size-12 place-items-center rounded-xl bg-fiap text-white">
          <CarFront className="size-6" aria-hidden />
        </span>
        <h1 className="text-2xl font-extrabold">
          Não foi possível abrir a loja<span className="text-fiap">.</span>
        </h1>
        <p className="text-sm text-ultrassonico">
          O serviço não respondeu. Verifique sua conexão com a internet e tente de novo em
          instantes.
        </p>
        <button type="button" className="botao-primario mx-auto" onClick={aoTentar}>
          <RefreshCw className="size-4" aria-hidden /> Tentar de novo
        </button>
      </div>
    </main>
  );
}

import { CarFront, LogOut, Menu, TriangleAlert, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useAuth } from "../context/AuthContext";
import { pendencias } from "../lib/formatters/format";

function Marca() {
  return (
    <Link
      to="/"
      className="flex items-center gap-2 text-lg font-extrabold tracking-tight"
      aria-label="Revenda, página inicial"
    >
      <span className="grid size-8 place-items-center rounded-lg bg-fiap text-white shadow-lg shadow-fiap/40">
        <CarFront className="size-5" aria-hidden />
      </span>
      Revenda<span className="text-fiap">.</span>
    </Link>
  );
}

function Usuario({ nome, papel }: { nome: string; papel: string | null }) {
  const primeiro = nome.split(" ")[0] || "Minha conta";
  return (
    <span
      className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 py-1 pl-1 pr-3"
      title={nome}
    >
      <span
        aria-hidden
        className="grid size-7 place-items-center rounded-full bg-fiap text-xs font-extrabold uppercase text-white"
      >
        {primeiro[0] ?? "?"}
      </span>
      <span className="flex flex-col leading-tight">
        <span data-testid="usuario-nome" className="max-w-[10rem] truncate text-sm font-bold">
          {primeiro}
        </span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-fiap-claro">
          {papel}
        </span>
      </span>
    </span>
  );
}

export function Layout() {
  const { sessao, papel, sair, nome, cadastro } = useAuth();
  const [aberto, setAberto] = useState(false);
  const local = useLocation();
  const link = ({ isActive }: { isActive: boolean }) =>
    `inline-flex min-h-11 items-center rounded-full px-4 py-2 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fiap ${isActive ? "bg-white/10 text-white" : "text-ultrassonico hover:text-white"}`;
  const itens = [
    { para: "/veiculos", rotulo: "Veículos", mostrar: true },
    { para: "/compras", rotulo: "Minhas compras", mostrar: papel === "cliente" },
    { para: "/perfil", rotulo: "Meu perfil", mostrar: papel === "cliente" },
    { para: "/painel", rotulo: "Painel", mostrar: papel === "vendedor" || papel === "admin" },
  ].filter((i) => i.mostrar);

  return (
    <div className="relative isolate flex min-h-dvh flex-col overflow-x-clip">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -left-32 top-0 size-[28rem] animate-flutuar rounded-full bg-fiap/25 blur-[110px]" />
        <div className="absolute -right-24 top-1/3 size-[24rem] animate-flutuar rounded-full bg-ultrassonico/10 blur-[110px] [animation-delay:-4s]" />
        <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,.035)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.035)_1px,transparent_1px)] bg-[size:56px_56px] [mask-image:radial-gradient(ellipse_at_top,black,transparent_75%)]" />
      </div>

      <header className="sticky top-0 z-40 border-b border-white/10 bg-tinta/75 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
          <Marca />
          <nav aria-label="Principal" className="hidden items-center gap-1 md:flex">
            {itens.map((i) => (
              <NavLink key={i.para} to={i.para} className={link}>
                {i.rotulo}
              </NavLink>
            ))}
          </nav>
          <div className="hidden items-center gap-2 md:flex">
            {sessao ? (
              <>
                <Usuario nome={nome} papel={papel} />
                <button type="button" className="botao-contorno !py-1.5" onClick={sair}>
                  <LogOut className="size-4" aria-hidden /> Sair
                </button>
              </>
            ) : (
              <Link to="/entrar" className="botao-primario !py-2">
                Entrar
              </Link>
            )}
          </div>
          <button
            type="button"
            className="grid size-11 place-items-center rounded-full border border-white/20 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fiap md:hidden"
            aria-expanded={aberto}
            aria-label={aberto ? "Fechar menu" : "Abrir menu"}
            onClick={() => setAberto((a) => !a)}
          >
            {aberto ? (
              <X className="size-5" aria-hidden />
            ) : (
              <Menu className="size-5" aria-hidden />
            )}
          </button>
        </div>
        <AnimatePresence>
          {aberto && (
            <motion.nav
              aria-label="Menu móvel"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-t border-white/10 md:hidden"
              onClick={() => setAberto(false)}
            >
              <div className="flex flex-col gap-1 p-4">
                {itens.map((i) => (
                  <NavLink key={i.para} to={i.para} className={link}>
                    {i.rotulo}
                  </NavLink>
                ))}
                {sessao && (
                  <div className="px-2 py-2">
                    <Usuario nome={nome} papel={papel} />
                  </div>
                )}
                {sessao ? (
                  <button type="button" className="botao-contorno mt-2" onClick={sair}>
                    Sair
                  </button>
                ) : (
                  <Link to="/entrar" className="botao-primario mt-2">
                    Entrar
                  </Link>
                )}
              </div>
            </motion.nav>
          )}
        </AnimatePresence>
      </header>

      {papel === "cliente" &&
        cadastro &&
        local.pathname !== "/perfil" &&
        (cadastro === "novo" || !cadastro.completo) && (
          <div role="status" className="border-b border-amber-400/30 bg-amber-400/10">
            <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-sm text-amber-100 sm:px-6">
              <p className="flex items-center gap-2">
                <TriangleAlert className="size-4 shrink-0" aria-hidden />
                {cadastro === "novo"
                  ? "Falta pouco: complete seu cadastro para poder reservar um veículo."
                  : `Complete seu cadastro para comprar (falta: ${pendencias(cadastro.pendentes)}).`}
              </p>
              <Link to="/perfil" className="botao-primario !px-4 !py-1.5 text-xs">
                Completar cadastro
              </Link>
            </div>
          </div>
        )}

      <motion.main
        key={local.pathname}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="mx-auto w-full max-w-7xl flex-1 px-4 py-10 sm:px-6"
      >
        <Outlet />
      </motion.main>

      <footer className="border-t border-white/10 py-8 text-center text-xs text-ardosia">
        Revenda · Tech Challenge Fase 5 · Pagamentos em ambiente simulado (Pix de demonstração).
      </footer>
    </div>
  );
}

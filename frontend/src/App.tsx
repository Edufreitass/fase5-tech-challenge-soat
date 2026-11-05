import { lazy, type ReactNode, Suspense, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";
import { Layout } from "./components/Layout";
import { Carregando } from "./components/ui";
import { useAuth } from "./context/AuthContext";
import type { Papel } from "./lib/auth";
import { Catalogo } from "./pages/Catalog";
import { Home } from "./pages/Home";
import { ConfiguracaoInicial } from "./pages/InitialSetup";
import { Entrar } from "./pages/SignIn";
import { VeiculoDetalhe } from "./pages/VehicleDetail";

// Paginas autenticadas (e o React Flow) carregam sob demanda.
const Compras = lazy(() => import("./pages/Purchases").then((m) => ({ default: m.Compras })));
const CompraDetalhe = lazy(() =>
  import("./pages/PurchaseDetail").then((m) => ({ default: m.CompraDetalhe })),
);
const Perfil = lazy(() => import("./pages/Profile").then((m) => ({ default: m.Perfil })));
const Painel = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.Painel })));

export function Protegida({ papeis, children }: { papeis: Papel[]; children: ReactNode }) {
  const { papel } = useAuth();
  const local = useLocation();
  if (!papel)
    return <Navigate to="/entrar" replace state={{ de: `${local.pathname}${local.search}` }} />;
  if (!papeis.includes(papel)) return <Navigate to="/" replace />;
  return <Suspense fallback={<Carregando />}>{children}</Suspense>;
}

/** Quem ja chega logado em /entrar vai para a tela do seu papel (o login em andamento navega sozinho). */
export function SoAnonimo({ children }: { children: ReactNode }) {
  const { papel } = useAuth();
  const [logadoAoAbrir] = useState(papel);
  if (logadoAoAbrir)
    return <Navigate to={logadoAoAbrir === "cliente" ? "/compras" : "/painel"} replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="veiculos" element={<Catalogo />} />
        <Route path="veiculos/:id" element={<VeiculoDetalhe />} />
        <Route
          path="entrar"
          element={
            <SoAnonimo>
              <Entrar />
            </SoAnonimo>
          }
        />
        <Route path="configuracao-inicial" element={<ConfiguracaoInicial />} />
        <Route
          path="compras"
          element={
            <Protegida papeis={["cliente"]}>
              <Compras />
            </Protegida>
          }
        />
        <Route
          path="compras/:id"
          element={
            <Protegida papeis={["cliente"]}>
              <CompraDetalhe />
            </Protegida>
          }
        />
        <Route
          path="perfil"
          element={
            <Protegida papeis={["cliente"]}>
              <Perfil />
            </Protegida>
          }
        />
        <Route
          path="painel"
          element={
            <Protegida papeis={["vendedor", "admin"]}>
              <Painel />
            </Protegida>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

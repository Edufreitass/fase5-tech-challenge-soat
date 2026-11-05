// react-router 8 e so ESM e o Jest roda em CJS: este mock cobre o subconjunto usado pelo app.
import {
  Children,
  createContext,
  isValidElement,
  type ReactElement,
  type ReactNode,
  useContext,
  useState,
} from "react";

interface Ctx {
  caminho: string;
  estado: unknown;
  ir: (c: string, o?: { state?: unknown }) => void;
}
const Roteador = createContext<Ctx>({ caminho: "/", estado: null, ir: () => undefined });
const Params = createContext<Record<string, string>>({});
const Saida = createContext<ReactNode>(null);

export const MemoryRouter = ({
  initialEntries = ["/"],
  children,
}: {
  initialEntries?: string[];
  children?: ReactNode;
}) => {
  const [atual, setAtual] = useState<{ caminho: string; estado: unknown }>({
    caminho: initialEntries[0] ?? "/",
    estado: null,
  });
  const ir = (caminho: string, o?: { state?: unknown }) =>
    setAtual({ caminho, estado: o?.state ?? null });
  return <Roteador.Provider value={{ ...atual, ir }}>{children}</Roteador.Provider>;
};
export const BrowserRouter = MemoryRouter;

type Rota = ReactElement<{
  path?: string;
  index?: boolean;
  element?: ReactNode;
  children?: ReactNode;
}>;

function casar(padrao: string, caminho: string): Record<string, string> | null {
  const a = padrao.split("/").filter(Boolean);
  const b = (caminho.split("?")[0] ?? "/").split("/").filter(Boolean);
  if (a.length !== b.length && a.at(-1) !== "*") return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < a.length; i++) {
    const segmento = a[i];
    const valor = b[i];
    if (segmento === "*") return params;
    if (segmento === undefined || valor === undefined) return null;
    if (segmento.startsWith(":")) params[segmento.slice(1)] = valor;
    else if (segmento !== valor) return null;
  }
  return params;
}

function resolver(rotas: ReactNode, caminho: string, pai: ReactNode = null): ReactNode {
  for (const r of Children.toArray(rotas) as Rota[]) {
    if (!isValidElement(r)) continue;
    const { path, index, element, children } = r.props;
    if (children) {
      const dentro = resolver(children, caminho, null);
      if (dentro) return <Saida.Provider value={dentro}>{element}</Saida.Provider>;
      continue;
    }
    const params = index ? (casar("/", caminho) ?? null) : casar(`/${path ?? ""}`, caminho);
    if (params) return <Params.Provider value={params}>{pai ?? element}</Params.Provider>;
  }
  return null;
}

export const Routes = ({ children }: { children?: ReactNode }) => {
  const { caminho } = useContext(Roteador);
  return <>{resolver(children, caminho)}</>;
};
export const Route = (_: {
  path?: string;
  index?: boolean;
  element?: ReactNode;
  children?: ReactNode;
}) => null;
export const Outlet = () => <>{useContext(Saida)}</>;
export const useParams = () => useContext(Params);
export const useLocation = () => {
  const { caminho, estado } = useContext(Roteador);
  const [pathname, busca] = caminho.split("?");
  return { pathname, search: busca ? `?${busca}` : "", state: estado };
};
export const useNavigate = () => useContext(Roteador).ir;
export const Navigate = ({ to, state }: { to: string; replace?: boolean; state?: unknown }) => {
  const { caminho, ir } = useContext(Roteador);
  if (caminho !== to) queueMicrotask(() => ir(to, { state }));
  return null;
};
export const Link = ({
  to,
  children,
  state,
  ...resto
}: { to: string; children?: ReactNode; state?: unknown } & Record<string, unknown>) => {
  const { ir } = useContext(Roteador);
  return (
    <a
      href={to}
      data-state={state ? JSON.stringify(state) : undefined}
      onClick={(e) => {
        e.preventDefault();
        ir(to, { state });
      }}
      {...resto}
    >
      {children}
    </a>
  );
};
export const NavLink = ({
  to,
  children,
  className,
  ...resto
}: { to: string; children?: ReactNode; className?: unknown } & Record<string, unknown>) => (
  <a
    href={to}
    className={
      typeof className === "function"
        ? (className as (a: { isActive: boolean }) => string)({ isActive: false })
        : (className as string)
    }
    {...resto}
  >
    {children}
  </a>
);
export const useSearchParams = (): [
  URLSearchParams,
  (p: URLSearchParams | Record<string, string>, o?: unknown) => void,
] => {
  const { caminho, ir } = useContext(Roteador);
  const [, forcar] = useState(0);
  const q = new URLSearchParams(caminho.split("?")[1] ?? "");
  return [
    q,
    (p) => {
      ir(`${caminho.split("?")[0]}?${new URLSearchParams(p as Record<string, string>)}`);
      forcar((n) => n + 1);
    },
  ];
};

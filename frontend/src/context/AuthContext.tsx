import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { definirContexto, ErroApi, obter } from "../lib/api";
import {
  identificacaoDe,
  lerSessao,
  type Papel,
  papelDe,
  type Sessao,
  sair,
  salvarSessao,
} from "../lib/auth";
import { useBusca } from "../lib/hooks/use";
import type { Cliente } from "../lib/types";

/** Situacao do cadastro do comprador: `novo` = ainda sem POST /clientes. */
export type Cadastro = "novo" | { nome: string; completo: boolean; pendentes: string[] };

interface Auth {
  sessao: Sessao | null;
  papel: Papel | null;
  /** Nome exibido no menu: nome do cadastro (cliente) ou do ID token (funcionario). */
  nome: string;
  cadastro: Cadastro | null;
  recarregarCadastro: () => void;
  definirSessao: (s: Sessao | null) => void;
  sair: () => void;
}

const Ctx = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [sessao, setSessao] = useState<Sessao | null>(() => lerSessao());
  const [versao, setVersao] = useState(0);

  const definirSessao = useCallback((s: Sessao | null) => {
    salvarSessao(s);
    setSessao(s);
  }, []);

  // Liga a renovacao de token ao estado React. Os efeitos dos filhos rodam antes deste; ate aqui o api.ts usa a
  // sessao guardada (lerSessao), entao as primeiras buscas ja saem autenticadas.
  useEffect(() => {
    definirContexto({ sessao: () => lerSessao(), atualizar: definirSessao });
  }, [definirSessao]);

  const papel = papelDe(sessao);
  const token = sessao?.accessToken ?? "";
  const perfil = useBusca(() => obter<Cliente>("/clientes/meu-perfil"), `${token}:${versao}`, {
    ativo: papel === "cliente",
  });
  const dados = perfil.dados?.dados;
  const cadastro: Cadastro | null = dados
    ? {
        nome: dados.nomeCompleto,
        completo: dados.cadastroCompleto,
        pendentes: dados.camposPendentes,
      }
    : perfil.erro instanceof ErroApi && perfil.erro.tipo === "perfil-cliente-inexistente"
      ? "novo"
      : null;

  const valor = useMemo<Auth>(() => {
    const id = identificacaoDe(sessao);
    const nome = typeof cadastro === "object" && cadastro ? cadastro.nome : (id?.nome ?? "");
    return {
      sessao,
      papel,
      nome,
      cadastro,
      recarregarCadastro: () => setVersao((v) => v + 1),
      definirSessao,
      sair: () => {
        const atual = sessao;
        setSessao(null);
        void sair(atual);
      },
    };
  }, [sessao, papel, cadastro, definirSessao]);
  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useAuth(): Auth {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth fora do AuthProvider");
  return c;
}

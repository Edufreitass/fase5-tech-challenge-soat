import { Users } from "lucide-react";
import { type FormEvent, useMemo, useState } from "react";
import { Aviso, Carregando, Paginacao, StatusBadge } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { chamar, enviarJson } from "../../lib/api";
import { identificacaoDe } from "../../lib/auth";
import { POR_PAGINA, pagina } from "../../lib/catalog/catalog";
import { textoDoFormulario } from "../../lib/forms";
import { mensagemDe, useEnvio } from "../../lib/hooks/use";
import { useLista } from "../../lib/hooks/useList";
import type { Funcionario } from "../../lib/types";
import { Campo, type Mensagem } from "./shared";

export function Equipe() {
  const { sessao } = useAuth();
  const eu = identificacaoDe(sessao)?.email ?? "";
  const lista = useLista<Funcionario>("/administracao/funcionarios", {});
  const [msg, setMsg] = useState<Mensagem>(null);
  const [numero, setNumero] = useState(1);
  const p = useMemo(() => pagina(lista.itens ?? [], numero), [lista.itens, numero]);
  const { enviando, executar } = useEnvio();
  function criar(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = textoDoFormulario(form);
    void executar(async () => {
      try {
        await enviarJson("/administracao/funcionarios", {
          nome: f("nome").trim(),
          email: f("email").trim(),
          grupo: f("grupo"),
        });
        setMsg({ tipo: "ok", texto: `Convite enviado para ${f("email").trim()}.` });
        form.reset();
        lista.recarregar();
      } catch (x) {
        setMsg({ tipo: "erro", texto: mensagemDe(x) });
      }
    });
  }
  const atualizar = (
    f: Funcionario,
    nome: string,
    corpo: { ativo?: boolean; grupo?: string },
    texto: string,
  ) =>
    executar(async () => {
      if (
        corpo.ativo === false &&
        !confirm(`Desativar ${nome}? O acesso é bloqueado e as sessões abertas são encerradas.`)
      )
        return;
      try {
        await chamar(`/administracao/funcionarios/${f.id}`, { metodo: "PATCH", corpo });
        setMsg({ tipo: "ok", texto });
        lista.recarregar();
      } catch (x) {
        setMsg({ tipo: "erro", texto: mensagemDe(x) });
      }
    });
  return (
    <>
      <form onSubmit={criar} className="cartao mb-6 grid gap-4 p-5 sm:grid-cols-4">
        <Campo id="fn-nome" rotulo="Nome" name="nome" required minLength={2} maxLength={120} />
        <Campo id="fn-email" rotulo="E-mail" name="email" type="email" required maxLength={254} />
        <div>
          <label className="rotulo" htmlFor="fn-grupo">
            Perfil
          </label>
          <select id="fn-grupo" name="grupo" className="campo" defaultValue="vendedor">
            <option value="vendedor">Vendedor</option>
            <option value="admin">Administrador</option>
          </select>
        </div>
        <div className="flex items-end">
          <button type="submit" className="botao-primario w-full" disabled={enviando}>
            {enviando ? "Enviando…" : "Convidar"}
          </button>
        </div>
      </form>
      {msg && (
        <div className="mb-4">
          <Aviso tipo={msg.tipo}>{msg.texto}</Aviso>
        </div>
      )}
      {lista.erro ? (
        <Aviso>{lista.erro}</Aviso>
      ) : !lista.itens ? (
        <Carregando />
      ) : (
        <>
          <ul className="grid gap-3">
            {p.itens.map((f) => {
              const admin = f.grupos.includes("admin");
              // Contas criadas fora do app (ex.: console do Cognito) podem nao ter o atributo `name`.
              const nome = f.nome?.trim() || (f.email.split("@")[0] ?? f.email);
              const proprio = f.email === eu;
              return (
                <li
                  key={f.id}
                  className="cartao flex flex-wrap items-center justify-between gap-3 p-4"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="grid size-10 shrink-0 place-items-center rounded-full bg-fiap/15 text-fiap-claro">
                      <Users className="size-4" aria-hidden />
                    </span>
                    <div className="min-w-0 wrap-anywhere">
                      <p className="font-bold">
                        {nome}
                        {proprio && (
                          <span className="ml-2 text-xs font-medium text-ardosia">(você)</span>
                        )}
                      </p>
                      <p className="text-xs text-ardosia">{f.email}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {f.grupos.map((g) => (
                      <StatusBadge key={g} status={g.toUpperCase()} />
                    ))}
                    <StatusBadge status={f.ativo ? "ATIVO" : "INATIVO"} />
                    <span className="text-xs text-ardosia">
                      {f.mfaConfigurado ? "MFA ativo" : "MFA pendente"}
                    </span>
                    {!proprio && (
                      <>
                        <button
                          type="button"
                          className="botao-fantasma !py-1 text-xs"
                          disabled={enviando}
                          onClick={() =>
                            void atualizar(
                              f,
                              nome,
                              { grupo: admin ? "vendedor" : "admin" },
                              `${nome} agora é ${admin ? "vendedor" : "administrador"}.`,
                            )
                          }
                        >
                          {admin ? "Tornar vendedor" : "Tornar administrador"}
                        </button>
                        <button
                          type="button"
                          className={`botao-fantasma !py-1 text-xs ${f.ativo ? "!text-red-300" : ""}`}
                          disabled={enviando}
                          onClick={() =>
                            void atualizar(
                              f,
                              nome,
                              { ativo: !f.ativo },
                              `${nome} ${f.ativo ? "desativado" : "reativado"}.`,
                            )
                          }
                        >
                          {f.ativo ? "Desativar" : "Reativar"}
                        </button>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          {p.total === 0 && <Aviso tipo="info">Nenhum funcionário cadastrado.</Aviso>}
          <Paginacao
            atual={p.atual}
            paginas={p.paginas}
            total={p.total}
            tamanho={POR_PAGINA}
            aoMudar={setNumero}
          />
        </>
      )}
    </>
  );
}

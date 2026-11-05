import { useState } from "react";
import { Link } from "react-router";
import { Aviso, Carregando, Titulo } from "../components/ui";
import { chamar, obter } from "../lib/api";
import { mensagemDe, useBusca, useEnvio } from "../lib/hooks/use";

/** Convida o administrador declarado na implantacao. Fecha sozinha quando ja existe um: a API recusa nova tentativa. */
export function ConfiguracaoInicial() {
  const situacao = useBusca(() =>
    obter<{ necessaria: boolean }>("/configuracao-inicial", undefined, false),
  );
  const { enviando, executar } = useEnvio();
  const [erro, setErro] = useState<string | null>(null);
  const [enviado, setEnviado] = useState(false);

  function convidar() {
    void executar(async () => {
      try {
        await chamar("/configuracao-inicial", { metodo: "POST", autenticado: false });
        setErro(null);
        setEnviado(true);
      } catch (x) {
        setErro(mensagemDe(x));
      }
    });
  }

  if (situacao.carregando && !situacao.dados) return <Carregando linhas={2} />;
  if (situacao.erro || !situacao.dados) return <Aviso>{mensagemDe(situacao.erro)}</Aviso>;

  if (enviado)
    return (
      <div className="mx-auto grid max-w-xl gap-4">
        <Titulo>Convite enviado</Titulo>
        <Aviso tipo="ok">
          Enviamos a senha temporária para o e-mail do administrador. No primeiro acesso, ele define
          a nova senha e configura o MFA.
        </Aviso>
        <div>
          <Link to="/entrar" className="botao-primario">
            Entrar como funcionário
          </Link>
        </div>
      </div>
    );

  if (!situacao.dados.dados.necessaria)
    return (
      <div className="mx-auto grid max-w-xl gap-4">
        <Titulo>Configuração concluída</Titulo>
        <Aviso tipo="info">
          Esta loja já tem um administrador. Novos funcionários são convidados por ele, na aba
          Equipe do painel.
        </Aviso>
        <div>
          <Link to="/entrar" className="botao-contorno">
            Ir para o login
          </Link>
        </div>
      </div>
    );

  return (
    <div className="mx-auto grid max-w-xl gap-4">
      <Titulo sub="A loja ainda não tem administrador. Depois do primeiro, a equipe é gerida pelo painel.">
        Configuração inicial
      </Titulo>
      <Aviso tipo="info">
        O convite vai para o e-mail do administrador definido na implantação. Só essa pessoa recebe
        a senha temporária.
      </Aviso>
      {erro && <Aviso>{erro}</Aviso>}
      <div>
        <button type="button" className="botao-primario" disabled={enviando} onClick={convidar}>
          {enviando ? "Enviando…" : "Enviar convite ao administrador"}
        </button>
      </div>
    </div>
  );
}

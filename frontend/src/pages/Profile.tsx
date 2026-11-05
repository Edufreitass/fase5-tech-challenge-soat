import { CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Aviso, Carregando, Titulo } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { Documentos } from "../features/profile/Documents";
import { DadosPessoais } from "../features/profile/PersonalData";
import { Cadastro } from "../features/profile/Registration";
import { chamar, ErroApi, obter, remover } from "../lib/api";
import { avisarNoLogin } from "../lib/auth";
import { pendencias } from "../lib/formatters/format";
import { mensagemDe, useBusca, useEnvio } from "../lib/hooks/use";
import type { Cliente } from "../lib/types";

export function Perfil() {
  const { sair, recarregarCadastro } = useAuth();
  const busca = useBusca(() => obter<Cliente>("/clientes/meu-perfil"));
  const [aviso, setAviso] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);
  const [recemCadastrado, setRecemCadastrado] = useState(false);
  const [dadosSalvos, setDadosSalvos] = useState(false);
  // A API responde 403 (perfil-cliente-inexistente) para quem ainda nao fez POST /clientes.
  const naoCadastrado =
    busca.erro instanceof ErroApi &&
    (busca.erro.tipo === "perfil-cliente-inexistente" || busca.erro.status === 404);

  const atualizar = () => {
    busca.recarregar();
    recarregarCadastro();
  };

  const exportacao = useEnvio();
  const exportar = () =>
    exportacao.executar(async () => {
      try {
        const r = await chamar<unknown>("/clientes/meu-perfil/exportacao");
        const url = URL.createObjectURL(
          new Blob([JSON.stringify(r.dados, null, 2)], { type: "application/json" }),
        );
        const a = Object.assign(document.createElement("a"), {
          href: url,
          download: "meus-dados.json",
        });
        document.body.append(a);
        a.click();
        a.remove();
        // Revogar na hora pode cancelar o download (Safari/Firefox): espera o navegador comecar a baixar.
        setTimeout(() => URL.revokeObjectURL(url), 10_000);
        setAviso({
          tipo: "ok",
          texto: "Exportação gerada: o arquivo meus-dados.json foi baixado.",
        });
      } catch (e) {
        setAviso({ tipo: "erro", texto: mensagemDe(e) });
      }
    });

  async function excluir() {
    if (
      !confirm("Isto anonimiza seu cadastro e remove seu login. Não pode ser desfeito. Continuar?")
    )
      return;
    try {
      await remover("/clientes/meu-perfil");
      // Sem sessao, a rota protegida leva ao login; o recado vai junto pelo sessionStorage.
      avisarNoLogin("Sua conta foi excluída e seus dados pessoais foram anonimizados.");
      sair();
    } catch (e) {
      setAviso({ tipo: "erro", texto: mensagemDe(e) });
    }
  }

  if (busca.carregando && !busca.dados && !busca.erro) return <Carregando linhas={2} />;
  if (naoCadastrado)
    return (
      <>
        <Titulo sub="Bem-vindo! Falta só completar seus dados para comprar.">Cadastro</Titulo>
        <Cadastro
          aoCriar={() => {
            setRecemCadastrado(true);
            atualizar();
          }}
        />
      </>
    );
  if (busca.erro || !busca.dados)
    return (
      <>
        <Titulo>Meu perfil</Titulo>
        <Aviso>{mensagemDe(busca.erro)}</Aviso>
      </>
    );
  const c = busca.dados.dados;
  return (
    <>
      <Titulo sub="Seus documentos aparecem mascarados por segurança.">Meu perfil</Titulo>
      {recemCadastrado && (
        <div className="mb-6">
          <Aviso tipo="ok">
            <span className="flex flex-wrap items-center gap-3">
              <CheckCircle2 className="size-4" aria-hidden /> Cadastro concluído!
              {c.cadastroCompleto && (
                <Link to="/veiculos" className="font-bold underline">
                  Escolher um veículo
                </Link>
              )}
            </span>
          </Aviso>
        </div>
      )}
      {!c.cadastroCompleto && (
        <div className="mb-6">
          <Aviso tipo="info">Para comprar, falta informar: {pendencias(c.camposPendentes)}.</Aviso>
        </div>
      )}
      {dadosSalvos && (
        <div className="mb-6">
          <Aviso tipo="ok">Dados atualizados.</Aviso>
        </div>
      )}
      <DadosPessoais
        key={busca.dados.etag ?? c.id}
        cliente={c}
        etag={busca.dados.etag}
        aoSalvar={() => {
          setDadosSalvos(true);
          atualizar();
        }}
      />
      <Documentos cliente={c} etag={busca.dados.etag} aoSalvar={atualizar} />
      <h2 className="mb-3 mt-10 text-lg font-extrabold">Seus direitos (LGPD)</h2>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          className="botao-contorno"
          onClick={() => void exportar()}
          disabled={exportacao.enviando}
        >
          {exportacao.enviando ? "Gerando…" : "Exportar meus dados"}
        </button>
        <button
          type="button"
          className="botao-fantasma !text-red-300 hover:!bg-red-500/10"
          onClick={excluir}
        >
          Excluir minha conta
        </button>
      </div>
      {aviso && (
        <div className="mt-4">
          <Aviso tipo={aviso.tipo}>{aviso.texto}</Aviso>
        </div>
      )}
    </>
  );
}

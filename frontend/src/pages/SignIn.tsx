import {
  ArrowLeft,
  Check,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Mail,
  ShieldCheck,
  UserRound,
  Wrench,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { QRCodeSVG } from "qrcode.react";
import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { Link as LinkRota, useLocation, useNavigate } from "react-router";
import { CarroSvg } from "../components/CarSvg";
import { Aviso, Etapas } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ErroApi, obter } from "../lib/api";
import { consumirAvisoDoLogin, papelDe, type Sessao, type TipoPool } from "../lib/auth";
import * as cognito from "../lib/cognito";
import { mensagemDe, useEnvio } from "../lib/hooks/use";
import { retornoInterno } from "../lib/navigation";
import { emailValido, requisitosDaSenha, senhaValida } from "../lib/validators/password";

type Etapa =
  | "login"
  | "cadastro"
  | "confirmar"
  | "esqueci"
  | "redefinir"
  | "novaSenha"
  | "mfaSetup"
  | "mfaCodigo";

const TITULOS: Record<Etapa, { t: string; d: string }> = {
  login: { t: "Entrar", d: "Use o e-mail e a senha da sua conta." },
  cadastro: {
    t: "Criar conta",
    d: "Leva menos de um minuto. Enviaremos um código para confirmar seu e-mail.",
  },
  confirmar: {
    t: "Confirme seu e-mail",
    d: "Digite o código de 6 dígitos que enviamos para você.",
  },
  esqueci: { t: "Recuperar senha", d: "Informe seu e-mail para receber um código de redefinição." },
  redefinir: {
    t: "Nova senha",
    d: "Digite o código recebido por e-mail e escolha uma nova senha.",
  },
  novaSenha: {
    t: "Defina sua senha",
    d: "Este é seu primeiro acesso: troque a senha temporária por uma só sua.",
  },
  mfaSetup: {
    t: "Ative a verificação em duas etapas",
    d: "Escaneie o QR code no seu aplicativo autenticador e digite o código gerado.",
  },
  mfaCodigo: {
    t: "Verificação em duas etapas",
    d: "Digite o código de 6 dígitos do seu aplicativo autenticador.",
  },
};

function Senha({
  id,
  rotulo,
  valor,
  aoMudar,
  novo = false,
}: {
  id: string;
  rotulo: string;
  valor: string;
  aoMudar: (v: string) => void;
  novo?: boolean;
}) {
  const [visivel, setVisivel] = useState(false);
  return (
    <div>
      <label className="rotulo" htmlFor={id}>
        {rotulo}
      </label>
      <div className="relative">
        <input
          id={id}
          className="campo pr-11"
          type={visivel ? "text" : "password"}
          value={valor}
          onChange={(e) => aoMudar(e.target.value)}
          autoComplete={novo ? "new-password" : "current-password"}
          required
        />
        <button
          type="button"
          className="absolute right-3 top-1/2 -translate-y-1/2 text-ardosia transition hover:text-white"
          onClick={() => setVisivel((v) => !v)}
          aria-label={visivel ? "Ocultar senha" : "Mostrar senha"}
        >
          {visivel ? (
            <EyeOff className="size-4" aria-hidden />
          ) : (
            <Eye className="size-4" aria-hidden />
          )}
        </button>
      </div>
      {novo && (
        <ul
          className="mt-2 grid grid-cols-1 gap-1 text-xs sm:grid-cols-2"
          aria-label="Requisitos da senha"
        >
          {requisitosDaSenha(valor).map((r) => (
            <li
              key={r.id}
              className={`flex items-center gap-1.5 transition ${r.ok ? "text-emerald-300" : "text-ardosia"}`}
            >
              <Check className={`size-3.5 ${r.ok ? "opacity-100" : "opacity-30"}`} aria-hidden />{" "}
              {r.rotulo}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Codigo({
  valor,
  aoMudar,
  rotulo = "Código",
}: {
  valor: string;
  aoMudar: (v: string) => void;
  rotulo?: string;
}) {
  return (
    <div>
      <label className="rotulo" htmlFor="codigo">
        {rotulo}
      </label>
      <input
        id="codigo"
        className="campo text-center font-mono text-2xl tracking-[.5em]"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        pattern="[0-9]{6}"
        required
        value={valor}
        onChange={(e) => aoMudar(e.target.value.replace(/\D/g, ""))}
        placeholder="000000"
      />
    </div>
  );
}

function Botao({ carregando, children }: { carregando: boolean; children: ReactNode }) {
  return (
    <button type="submit" className="botao-primario w-full !py-3" disabled={carregando}>
      {carregando && <Loader2 className="size-4 animate-spin" aria-hidden />} {children}
    </button>
  );
}

const Link = ({ onClick, children }: { onClick: () => void; children: ReactNode }) => (
  <button
    type="button"
    onClick={onClick}
    className="text-sm font-bold text-fiap-claro underline-offset-4 hover:underline"
  >
    {children}
  </button>
);

/** Destino depois do login: a pagina que pediu login, se o papel puder abri-la; senao a tela inicial do papel. */
export function destinoAposLogin(papel: string | null, de?: string): string {
  const inicial = papel === "cliente" ? "/compras" : "/painel";
  const caminho = retornoInterno({ de });
  if (!caminho || caminho === "/entrar") return inicial;
  const deFuncionario = caminho.startsWith("/painel");
  const deCliente = caminho.startsWith("/compras") || caminho.startsWith("/perfil");
  return (papel === "cliente" ? !deFuncionario : !deCliente) ? caminho : inicial;
}

export function Entrar() {
  const { definirSessao } = useAuth();
  const navegar = useNavigate();
  const destino = retornoInterno(useLocation().state);
  const [pool, setPool] = useState<TipoPool>("clientes");
  const [etapa, setEtapa] = useState<Etapa>("login");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [codigo, setCodigo] = useState("");
  const [desafio, setDesafio] = useState<cognito.Desafio | null>(null);
  const [mfa, setMfa] = useState<{ segredo: string; sessao: string } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(consumirAvisoDoLogin);
  const { enviando: carregando, executar } = useEnvio();

  function ir(e: Etapa, mensagem: string | null = null) {
    setEtapa(e);
    setErro(null);
    setInfo(mensagem);
    setCodigo("");
    // So a confirmacao do cadastro reaproveita a senha (para entrar sozinha); nas demais telas ela nao pode "vazar".
    if (e !== "confirmar") setSenha("");
  }

  function cancelarDesafio() {
    setDesafio(null);
    setMfa(null);
    ir("login");
  }

  async function reenviar() {
    setErro(null);
    setInfo(null);
    try {
      await cognito.reenviarCodigo(email);
      setInfo("Código reenviado. Confira sua caixa de entrada.");
    } catch (e) {
      setErro(mensagemDe(e));
    }
  }

  function trocarPool(p: TipoPool) {
    setPool(p);
    setDesafio(null);
    setMfa(null);
    ir("login");
  }

  // Cliente sem cadastro (conta recem-criada) segue direto para completar os dados; os demais vao para suas telas.
  async function concluir(sessao: Sessao) {
    definirSessao(sessao);
    const papel = papelDe(sessao);
    if (papel !== "cliente") return navegar(destinoAposLogin(papel, destino), { replace: true });
    const semCadastro = await obter("/clientes/meu-perfil")
      .then(() => false)
      .catch((e) => e instanceof ErroApi && e.tipo === "perfil-cliente-inexistente");
    navegar(semCadastro ? "/perfil" : destinoAposLogin(papel, destino), { replace: true });
  }

  function aposResultado(r: cognito.ResultadoLogin) {
    if ("sessao" in r) return void concluir(r.sessao);
    setDesafio(r.desafio);
    setSenha("");
    ir(r.desafio.tipo);
  }

  // Ao chegar no MFA_SETUP, gera a chave do autenticador.
  useEffect(() => {
    if (etapa !== "mfaSetup" || !desafio || mfa) return;
    let ativo = true;
    void cognito
      .iniciarMfa(desafio)
      .then((dados) => {
        if (ativo) setMfa(dados);
      })
      .catch((erro: unknown) => {
        if (ativo) setErro(mensagemDe(erro));
      });
    return () => {
      ativo = false;
    };
  }, [etapa, desafio, mfa]);

  async function enviar(evento: FormEvent, acao: () => Promise<void>) {
    evento.preventDefault();
    await executar(async () => {
      setErro(null);
      if (!emailValido(email) && ["login", "cadastro", "esqueci"].includes(etapa))
        return setErro("Informe um e-mail válido.");
      try {
        await acao();
      } catch (e) {
        if (e instanceof cognito.ErroCognito && e.codigo === "UserNotConfirmedException")
          return ir(
            "confirmar",
            "Sua conta ainda não foi confirmada. Digite o código enviado por e-mail.",
          );
        if (e instanceof cognito.ErroCognito && e.codigo === "PasswordResetRequiredException") {
          await cognito.esqueciSenha(pool, email).catch(() => undefined);
          return ir("redefinir", "Enviamos um código para redefinir sua senha.");
        }
        setErro(mensagemDe(e));
      }
    });
  }

  const tituloEtapa = TITULOS[etapa];
  const rotuloEmail = (
    <div>
      <label className="rotulo" htmlFor="email">
        E-mail
      </label>
      <div className="relative">
        <Mail
          className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-ardosia"
          aria-hidden
        />
        <input
          id="email"
          className="campo pl-10"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="voce@exemplo.com"
          disabled={["confirmar", "redefinir"].includes(etapa)}
        />
      </div>
    </div>
  );

  return (
    <div className="mx-auto grid max-w-5xl overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] backdrop-blur-sm lg:grid-cols-[.9fr_1.1fr]">
      <aside
        className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-fiap via-fiap-escuro to-black p-10 lg:flex"
        aria-hidden
      >
        <div className="absolute -right-24 -top-24 size-72 rounded-full bg-white/10 blur-3xl" />
        <div className="relative">
          <p className="text-xs font-bold uppercase tracking-[.25em] text-white/70">Revenda</p>
          <h2 className="mt-4 text-3xl font-extrabold leading-tight">
            Compre seu carro
            <br />
            sem sair de casa.
          </h2>
        </div>
        <motion.div
          animate={{ y: [0, -8, 0] }}
          transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
          className="relative"
        >
          <CarroSvg cor="Branco" modelo="Corolla" className="w-full drop-shadow-2xl" />
        </motion.div>
        <ul className="relative grid gap-2 text-sm text-white/90">
          {[
            "Reserva garantida por 48 horas",
            "Pagamento por Pix",
            "Seus dados protegidos pela LGPD",
          ].map((t) => (
            <li key={t} className="flex items-center gap-2">
              <ShieldCheck className="size-4" /> {t}
            </li>
          ))}
        </ul>
      </aside>

      <section className="p-6 sm:p-10" aria-labelledby="titulo-login">
        <div
          role="tablist"
          aria-label="Tipo de conta"
          className="mb-8 grid grid-cols-2 gap-1 rounded-full border border-white/10 bg-black/30 p-1"
        >
          {(
            [
              ["clientes", "Sou cliente", UserRound],
              ["funcionarios", "Sou funcionário", Wrench],
            ] as const
          ).map(([id, rotulo, Icone]) => (
            <button
              type="button"
              key={id}
              role="tab"
              aria-selected={pool === id}
              onClick={() => trocarPool(id)}
              className={`flex items-center justify-center gap-2 rounded-full px-3 py-2.5 text-sm font-bold transition ${pool === id ? "bg-fiap text-white shadow-lg shadow-fiap/30" : "text-ultrassonico hover:text-white"}`}
            >
              <Icone className="size-4" aria-hidden /> {rotulo}
            </button>
          ))}
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={`${pool}-${etapa}`}
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            transition={{ duration: 0.2 }}
          >
            {etapa !== "login" && !["novaSenha", "mfaSetup", "mfaCodigo"].includes(etapa) && (
              <button
                type="button"
                onClick={() => ir("login")}
                className="mb-4 inline-flex items-center gap-1 text-xs font-bold text-ultrassonico hover:text-white"
              >
                <ArrowLeft className="size-3.5" aria-hidden /> Voltar ao login
              </button>
            )}
            <h1 id="titulo-login" className="text-3xl font-extrabold tracking-tight">
              {tituloEtapa.t}
              <span className="text-fiap">.</span>
            </h1>
            <p className="mt-2 text-sm text-ultrassonico">{tituloEtapa.d}</p>
            <div className="mt-6 grid gap-4">
              {(etapa === "cadastro" || etapa === "confirmar") && (
                <Etapas
                  atual={etapa === "cadastro" ? 1 : 2}
                  itens={["Conta", "E-mail confirmado", "Seus dados"]}
                />
              )}
              {info && <Aviso tipo="info">{info}</Aviso>}
              {erro && <Aviso>{erro}</Aviso>}

              {etapa === "login" && (
                <form
                  className="grid gap-4"
                  onSubmit={(e) =>
                    enviar(e, async () => aposResultado(await cognito.entrar(pool, email, senha)))
                  }
                >
                  {rotuloEmail}
                  <Senha id="senha" rotulo="Senha" valor={senha} aoMudar={setSenha} />
                  <Botao carregando={carregando}>Entrar</Botao>
                  {pool === "funcionarios" && (
                    <LinkRota
                      to="/configuracao-inicial"
                      className="text-xs font-bold text-ultrassonico hover:text-white"
                    >
                      Primeira vez na loja? Configure o administrador
                    </LinkRota>
                  )}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Link onClick={() => ir("esqueci")}>Esqueci minha senha</Link>
                    {pool === "clientes" && <Link onClick={() => ir("cadastro")}>Criar conta</Link>}
                  </div>
                </form>
              )}

              {etapa === "cadastro" && (
                <form
                  className="grid gap-4"
                  onSubmit={(e) =>
                    enviar(e, async () => {
                      if (!senhaValida(senha))
                        throw new Error("A senha não atende a todos os requisitos.");
                      await cognito.cadastrar(email, senha);
                      ir("confirmar", `Enviamos um código para ${email.trim()}.`);
                    })
                  }
                >
                  {rotuloEmail}
                  <Senha id="senha-nova" rotulo="Senha" valor={senha} aoMudar={setSenha} novo />
                  <Botao carregando={carregando}>Criar conta</Botao>
                </form>
              )}

              {etapa === "confirmar" && (
                <form
                  className="grid gap-4"
                  onSubmit={(e) =>
                    enviar(e, async () => {
                      await cognito.confirmarCadastro(email, codigo);
                      // Jornada continua: entra com a senha recem-criada e segue para o cadastro dos dados.
                      if (senha) {
                        try {
                          return aposResultado(await cognito.entrar(pool, email, senha));
                        } catch {
                          /* cai no login manual */
                        }
                      }
                      ir("login", "E-mail confirmado! Entre com sua senha.");
                    })
                  }
                >
                  {rotuloEmail}
                  <Codigo valor={codigo} aoMudar={setCodigo} />
                  <Botao carregando={carregando}>Confirmar</Botao>
                  <Link onClick={() => void reenviar()}>Reenviar código</Link>
                </form>
              )}

              {etapa === "esqueci" && (
                <form
                  className="grid gap-4"
                  onSubmit={(e) =>
                    enviar(e, async () => {
                      await cognito.esqueciSenha(pool, email);
                      ir(
                        "redefinir",
                        `Se houver uma conta para ${email.trim()}, enviamos um código.`,
                      );
                    })
                  }
                >
                  {rotuloEmail}
                  <Botao carregando={carregando}>Enviar código</Botao>
                </form>
              )}

              {etapa === "redefinir" && (
                <form
                  className="grid gap-4"
                  onSubmit={(e) =>
                    enviar(e, async () => {
                      if (!senhaValida(senha))
                        throw new Error("A senha não atende a todos os requisitos.");
                      await cognito.redefinirSenha(pool, email, codigo, senha);
                      setSenha("");
                      ir("login", "Senha redefinida! Entre com a nova senha.");
                    })
                  }
                >
                  {rotuloEmail}
                  <Codigo valor={codigo} aoMudar={setCodigo} />
                  <Senha
                    id="senha-redefinida"
                    rotulo="Nova senha"
                    valor={senha}
                    aoMudar={setSenha}
                    novo
                  />
                  <Botao carregando={carregando}>Redefinir senha</Botao>
                </form>
              )}

              {etapa === "novaSenha" && desafio && (
                <form
                  className="grid gap-4"
                  onSubmit={(e) =>
                    enviar(e, async () => {
                      if (!senhaValida(senha))
                        throw new Error("A senha não atende a todos os requisitos.");
                      aposResultado(await cognito.responderNovaSenha(pool, desafio, senha));
                    })
                  }
                >
                  <Senha
                    id="senha-primeiro-acesso"
                    rotulo="Nova senha"
                    valor={senha}
                    aoMudar={setSenha}
                    novo
                  />
                  <Botao carregando={carregando}>Salvar e continuar</Botao>
                  <Link onClick={cancelarDesafio}>Cancelar e voltar ao login</Link>
                </form>
              )}

              {etapa === "mfaSetup" && desafio && (
                <form
                  className="grid gap-4"
                  onSubmit={(e) =>
                    enviar(e, async () => {
                      if (!mfa) throw new Error("Aguarde a geração da chave.");
                      aposResultado(await cognito.concluirMfa(pool, desafio, mfa.sessao, codigo));
                    })
                  }
                >
                  {mfa ? (
                    <div className="grid place-items-center gap-3 rounded-2xl border border-white/10 bg-white p-4 text-tinta">
                      <QRCodeSVG
                        value={`otpauth://totp/Revenda:${encodeURIComponent(email.trim())}?secret=${mfa.segredo}&issuer=Revenda`}
                        size={168}
                        aria-label="QR code do autenticador"
                      />
                    </div>
                  ) : (
                    <p role="status" className="py-6 text-center text-sm text-ultrassonico">
                      Gerando chave…
                    </p>
                  )}
                  {mfa && (
                    <p className="flex items-start gap-2 text-xs text-ultrassonico">
                      <KeyRound className="mt-0.5 size-3.5 shrink-0" aria-hidden /> Sem câmera?
                      Digite a chave manualmente:
                      <code
                        data-testid="chave-mfa"
                        className="break-all rounded bg-black/40 px-2 py-0.5 font-mono text-white"
                      >
                        {mfa.segredo}
                      </code>
                    </p>
                  )}
                  <Codigo valor={codigo} aoMudar={setCodigo} rotulo="Código do aplicativo" />
                  <Botao carregando={carregando}>Ativar e entrar</Botao>
                  <Link onClick={cancelarDesafio}>Cancelar e voltar ao login</Link>
                </form>
              )}

              {etapa === "mfaCodigo" && desafio && (
                <form
                  className="grid gap-4"
                  onSubmit={(e) =>
                    enviar(e, async () =>
                      aposResultado(await cognito.responderMfa(pool, desafio, codigo)),
                    )
                  }
                >
                  <Codigo valor={codigo} aoMudar={setCodigo} rotulo="Código do aplicativo" />
                  <Botao carregando={carregando}>Verificar</Botao>
                  <Link onClick={cancelarDesafio}>Cancelar e voltar ao login</Link>
                </form>
              )}
            </div>
          </motion.div>
        </AnimatePresence>
      </section>
    </div>
  );
}

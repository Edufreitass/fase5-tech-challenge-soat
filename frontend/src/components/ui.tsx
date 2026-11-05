import { motion } from "motion/react";
import type { ReactNode } from "react";
import { titulo } from "../lib/formatters/format";
import { UFS } from "../lib/states";

const CORES: Record<string, string> = {
  DISPONIVEL: "bg-emerald-400/15 text-emerald-300 ring-emerald-400/30",
  RESERVADO: "bg-amber-400/15 text-amber-300 ring-amber-400/30",
  AGUARDANDO_RETIRADA: "bg-sky-400/15 text-sky-300 ring-sky-400/30",
  AGUARDANDO_PAGAMENTO: "bg-amber-400/15 text-amber-300 ring-amber-400/30",
  PAGO: "bg-sky-400/15 text-sky-300 ring-sky-400/30",
  CONCLUIDO: "bg-emerald-400/15 text-emerald-300 ring-emerald-400/30",
  VENDIDO: "bg-prata/15 text-prata ring-prata/30",
  INATIVO: "bg-ardosia/20 text-ultrassonico ring-ardosia/40",
  ATIVO: "bg-emerald-400/15 text-emerald-300 ring-emerald-400/30",
  CANCELADO: "bg-red-500/15 text-red-300 ring-red-400/30",
  ESTORNADO: "bg-red-500/15 text-red-300 ring-red-400/30",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex min-h-7 items-center rounded-full px-3 py-1 text-xs font-bold ring-1 ring-inset ${CORES[status] ?? "bg-white/10 text-white ring-white/20"}`}
    >
      {titulo(status)}
    </span>
  );
}

export function Reveal({
  children,
  atraso = 0,
  className = "",
}: {
  children: ReactNode;
  atraso?: number;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.55, delay: atraso, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

export function Aviso({
  tipo = "erro",
  children,
}: {
  tipo?: "erro" | "info" | "ok";
  children: ReactNode;
}) {
  const cor = {
    erro: "border-red-400/40 bg-red-500/10 text-red-200",
    info: "border-sky-400/40 bg-sky-500/10 text-sky-200",
    ok: "border-emerald-400/40 bg-emerald-500/10 text-emerald-200",
  }[tipo];
  return (
    <motion.div
      role={tipo === "erro" ? "alert" : "status"}
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-xl border px-4 py-3 text-sm ${cor}`}
    >
      {children}
    </motion.div>
  );
}

export function Carregando({ linhas = 3 }: { linhas?: number }) {
  return (
    <div role="status" aria-label="Carregando" className="grid gap-3">
      {Array.from({ length: linhas }, (_, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: Esqueletos decorativos nao possuem identidade ou estado.
        <div key={i} className="h-24 animate-pulse rounded-2xl bg-white/5" />
      ))}
    </div>
  );
}

export function Titulo({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-8">
      <h1 className="text-3xl font-extrabold tracking-tight wrap-anywhere sm:text-4xl">
        {children}
        <span className="text-fiap">.</span>
      </h1>
      {sub && <p className="mt-2 max-w-2xl text-sm text-ultrassonico">{sub}</p>}
    </div>
  );
}

export function Selecao({
  id,
  rotulo,
  valor,
  aoMudar,
  opcoes,
  vazio = "Todos",
  desabilitado = false,
}: {
  id: string;
  rotulo: string;
  valor: string;
  aoMudar: (v: string) => void;
  opcoes: { valor: string; rotulo: string }[];
  vazio?: string | null;
  desabilitado?: boolean;
}) {
  return (
    <div>
      <label className="rotulo" htmlFor={id}>
        {rotulo}
      </label>
      <select
        id={id}
        className="campo appearance-none bg-[length:1rem] bg-[right_.9rem_center] bg-no-repeat pr-9 [background-image:url(&quot;data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23acc1cc' stroke-width='2.5'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E&quot;)]"
        value={valor}
        disabled={desabilitado}
        onChange={(e) => aoMudar(e.target.value)}
      >
        {vazio !== null && <option value="">{vazio}</option>}
        {opcoes.map((o) => (
          <option key={o.valor} value={o.valor}>
            {o.rotulo}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Paginacao({
  atual,
  paginas,
  total,
  aoMudar,
  tamanho,
}: {
  atual: number;
  paginas: number;
  total: number;
  aoMudar: (p: number) => void;
  tamanho: number;
}) {
  if (total === 0) return null;
  const de = (atual - 1) * tamanho + 1;
  const ate = Math.min(atual * tamanho, total);
  const janela = Array.from({ length: paginas }, (_, i) => i + 1).filter(
    (p) => p === 1 || p === paginas || Math.abs(p - atual) <= 1,
  );
  return (
    <nav
      aria-label="Paginação"
      className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-between"
    >
      <p className="text-xs text-ultrassonico" aria-live="polite">
        Mostrando {de}–{ate} de {total}
      </p>
      <ul className="flex items-center gap-1">
        <li>
          <button
            type="button"
            className="botao-fantasma !px-3 !py-2"
            disabled={atual === 1}
            onClick={() => aoMudar(atual - 1)}
            aria-label="Página anterior"
          >
            ‹
          </button>
        </li>
        {janela.map((p, i) => (
          <li key={p} className="flex items-center">
            {i > 0 && janela[i - 1] !== p - 1 && (
              <span className="px-1 text-ardosia" aria-hidden>
                …
              </span>
            )}
            <button
              type="button"
              onClick={() => aoMudar(p)}
              aria-current={p === atual ? "page" : undefined}
              aria-label={`Página ${p}`}
              className={`grid size-11 place-items-center rounded-full text-sm font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fiap ${p === atual ? "bg-fiap text-white" : "text-ultrassonico hover:bg-white/10"}`}
            >
              {p}
            </button>
          </li>
        ))}
        <li>
          <button
            type="button"
            className="botao-fantasma !px-3 !py-2"
            disabled={atual === paginas}
            onClick={() => aoMudar(atual + 1)}
            aria-label="Próxima página"
          >
            ›
          </button>
        </li>
      </ul>
    </nav>
  );
}

/** Campo de formulario: obrigatorios levam `*`; opcionais dizem "(opcional)" no rotulo e no placeholder. */
export function CampoForm({
  id,
  rotulo,
  obrigatorio = false,
  dica,
  ...resto
}: {
  id: string;
  rotulo: string;
  obrigatorio?: boolean;
  dica?: string;
} & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <label className="rotulo" htmlFor={id}>
        {rotulo}
        {obrigatorio ? (
          <span className="ml-0.5 text-fiap-claro" aria-hidden>
            {" "}
            *
          </span>
        ) : (
          <span className="ml-1 font-medium normal-case tracking-normal text-ardosia">
            {" "}
            (opcional)
          </span>
        )}
      </label>
      <input
        id={id}
        className="campo"
        required={obrigatorio}
        aria-required={obrigatorio}
        placeholder={resto.placeholder ?? (obrigatorio ? undefined : "(opcional)")}
        {...resto}
      />
      {dica && <p className="mt-1 text-[11px] text-ardosia">{dica}</p>}
    </div>
  );
}

export function SelecaoUf({
  id,
  rotulo,
  valor,
  aoMudar,
  obrigatorio = false,
}: {
  id: string;
  rotulo: string;
  valor: string;
  aoMudar: (v: string) => void;
  obrigatorio?: boolean;
}) {
  return (
    <div>
      <label className="rotulo" htmlFor={id}>
        {rotulo}
        {obrigatorio ? (
          <span className="ml-0.5 text-fiap-claro" aria-hidden>
            {" "}
            *
          </span>
        ) : (
          <span className="ml-1 font-medium normal-case tracking-normal text-ardosia">
            {" "}
            (opcional)
          </span>
        )}
      </label>
      <select
        id={id}
        className="campo"
        required={obrigatorio}
        value={valor}
        onChange={(e) => aoMudar(e.target.value)}
      >
        <option value="">{obrigatorio ? "Selecione" : "(opcional)"}</option>
        {UFS.map((u) => (
          <option key={u} value={u}>
            {u}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Etapas({ atual, itens }: { atual: number; itens: string[] }) {
  return (
    <ol
      className="mb-6 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-2 text-xs font-bold"
      aria-label="Etapas do cadastro"
    >
      {itens.map((t, i) => (
        <li
          key={t}
          aria-current={i + 1 === atual ? "step" : undefined}
          className="flex items-center gap-2"
        >
          <span
            className={`grid size-6 place-items-center rounded-full text-[11px] ${i + 1 < atual ? "bg-emerald-400/20 text-emerald-300" : i + 1 === atual ? "bg-fiap text-white" : "bg-white/10 text-ardosia"}`}
          >
            {i + 1 < atual ? "✓" : i + 1}
          </span>
          <span className={i + 1 === atual ? "text-white" : "text-ardosia"}>{t}</span>
          {i < itens.length - 1 && <span aria-hidden className="mx-1 h-px w-6 bg-white/15" />}
        </li>
      ))}
    </ol>
  );
}

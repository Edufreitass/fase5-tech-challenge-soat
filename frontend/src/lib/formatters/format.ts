const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

/** "129900.00" -> "R$ 129.900,00". */
export function moeda(valor: string | number): string {
  const n = typeof valor === "number" ? valor : Number(valor);
  return Number.isFinite(n) ? brl.format(n) : "-";
}

export function km(valor: number): string {
  return `${new Intl.NumberFormat("pt-BR").format(valor)} km`;
}

export function dataHora(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "-"
    : new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(d);
}

// Enums da API (ASCII) cujo rotulo nao sai da regra geral de `titulo`: acentos e siglas.
const ROTULOS: Record<string, string> = {
  DISPONIVEL: "Disponível",
  CONCLUIDO: "Concluído",
  ELETRICO: "Elétrico",
  HIBRIDO: "Híbrido",
  AUTOMATICO: "Automático",
  CVT: "CVT",
  GNV: "GNV",
  DESISTENCIA: "Desistência",
  NAO_RETIRADO: "Não retirado",
  FALHA_SISTEMICA: "Falha sistêmica",
  CONFLITO_RESERVA: "Conflito de reserva",
  ADMIN: "Administrador",
};

/** "AGUARDANDO_PAGAMENTO" -> "Aguardando pagamento" (com acentos e siglas dos enums conhecidos). */
export function titulo(texto: string): string {
  return ROTULOS[texto] ?? texto.charAt(0) + texto.slice(1).toLowerCase().replaceAll("_", " ");
}

const PENDENCIAS: Record<string, string> = {
  rg: "RG",
  email: "e-mail confirmado",
  consentimento: "aceite dos termos vigentes",
  cadastro: "cadastro",
};

/** `camposPendentes` da API em texto: ["rg", "email"] -> "RG e e-mail confirmado". */
export function pendencias(campos: string[]): string {
  const nomes = campos.map((c) => PENDENCIAS[c] ?? c);
  return nomes.length > 1 ? `${nomes.slice(0, -1).join(", ")} e ${nomes.at(-1)}` : (nomes[0] ?? "");
}

// A API e ASCII por convencao; as mensagens dela ganham acento so na exibicao (palavras inteiras, sem ambiguidade).
const ACENTOS: Record<string, string> = {
  nao: "não",
  so: "só",
  ja: "já",
  codigo: "código",
  configuracao: "configuração",
  ha: "há",
  voce: "você",
  veiculo: "veículo",
  veiculos: "veículos",
  documentacao: "documentação",
  validacao: "validação",
  requisicao: "requisição",
  cabecalho: "cabeçalho",
  digito: "dígito",
  digitos: "dígitos",
  invalido: "inválido",
  invalida: "inválida",
  obrigatorio: "obrigatório",
  obrigatoria: "obrigatória",
  funcionario: "funcionário",
  usuario: "usuário",
  endereco: "endereço",
  editaveis: "editáveis",
  servico: "serviço",
  indisponivel: "indisponível",
  disponivel: "disponível",
  concluida: "concluída",
  desistencia: "desistência",
  faca: "faça",
  exclusao: "exclusão",
  exportacao: "exportação",
  possivel: "possível",
  cobranca: "cobrança",
  execucao: "execução",
  parametro: "parâmetro",
  migracao: "migração",
  migracoes: "migrações",
  versoes: "versões",
  preco: "preço",
  propria: "própria",
  operacao: "operação",
  recuperavel: "recuperável",
  sessao: "sessão",
};

/** Acentua uma mensagem da API ("Veiculo nao encontrado." -> "Veículo não encontrado."), preservando a maiuscula inicial. */
export function acentuar(texto: string): string {
  return texto
    .replace(/[A-Za-z_]+/g, (p) => {
      const a = ACENTOS[p.toLowerCase()];
      if (!a) return p;
      return p.charAt(0) === p.charAt(0).toUpperCase() ? a.charAt(0).toUpperCase() + a.slice(1) : a;
    })
    .replace(/([Ss]ó|[Nn]ão) esta\b/g, "$1 está")
    .replace(/([Ss]ó) e possível/g, "$1 é possível")
    .replace(/\b([A-Z_]+) e obrigatória/g, "$1 é obrigatória");
}

// Campos de `erros[]` da API (caminho JSON) com o rotulo usado nos formularios.
const CAMPOS: Record<string, string> = {
  nomeCompleto: "Nome completo",
  cpf: "CPF",
  dataNascimento: "Data de nascimento",
  telefone: "Telefone",
  cnh: "CNH",
  "endereco.cep": "CEP",
  "endereco.logradouro": "Logradouro",
  "endereco.numero": "Número",
  "endereco.complemento": "Complemento",
  "endereco.bairro": "Bairro",
  "endereco.cidade": "Cidade",
  "endereco.uf": "Estado (UF)",
  "rg.numero": "Número do RG",
  "rg.orgaoEmissor": "Órgão emissor",
  "rg.uf": "UF do RG",
  "consentimento.aceito": "Aceite dos termos",
  "consentimento.finalidades": "Finalidades",
  "consentimento.versaoTermo": "Versão do termo",
  marca: "Marca",
  modelo: "Modelo",
  anoFabricacao: "Ano de fabricação",
  anoModelo: "Ano do modelo",
  cor: "Cor",
  preco: "Preço",
  quilometragem: "Quilometragem",
  placa: "Placa",
  renavam: "RENAVAM",
  chassi: "Chassi",
  combustivel: "Combustível",
  cambio: "Câmbio",
  nome: "Nome",
  email: "E-mail",
};

/** "endereco.cep" -> "CEP"; caminho desconhecido fica como veio (e "." vira vazio). */
export function rotuloDoCampo(campo?: string): string {
  // Erros do validador do corpo vem como "body.nomeCompleto"; os do dominio, como "nomeCompleto".
  const caminho = (campo ?? "").replace(/^body\./, "");
  return caminho && caminho !== "." ? (CAMPOS[caminho] ?? caminho) : "";
}

/** "+5511987654321" -> "(11) 98765-4321"; outros formatos voltam como vieram. */
export function telefoneFormatado(e164: string): string {
  const m = /^\+55(\d{2})(\d{4,5})(\d{4})$/.exec(e164);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : e164;
}

/** Tempo restante ate `iso` em "1h 05min" (ou "expirado"). */
export function restante(iso: string | null | undefined, agora: number = Date.now()): string {
  if (!iso) return "-";
  const ms = new Date(iso).getTime() - agora;
  if (!Number.isFinite(ms) || ms <= 0) return "expirado";
  const min = Math.floor(ms / 60000);
  const h = Math.floor(min / 60);
  return h > 0 ? `${h}h ${String(min % 60).padStart(2, "0")}min` : `${min}min`;
}

export function apenasDigitos(texto: string): string {
  return texto.replace(/\D/g, "");
}

/** Telefone em E.164 (+55 + DDD + numero) ou null. So remove o 55 do pais quando sobra DDD + numero: "(55) 9..." e DDD. */
export function telefoneE164(texto: string): string | null {
  const d = apenasDigitos(texto);
  const nacional = (d.length === 12 || d.length === 13) && d.startsWith("55") ? d.slice(2) : d;
  return nacional.length === 10 || nacional.length === 11 ? `+55${nacional}` : null;
}

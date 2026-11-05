export type StatusVeiculo =
  | "DISPONIVEL"
  | "RESERVADO"
  | "AGUARDANDO_RETIRADA"
  | "VENDIDO"
  | "INATIVO";
export type StatusVenda =
  | "CRIADO"
  | "RESERVADO"
  | "AGUARDANDO_PAGAMENTO"
  | "PAGO"
  | "CONCLUIDO"
  | "CANCELADO"
  | "ESTORNADO";

export interface Veiculo {
  id: string;
  marca: string;
  modelo: string;
  anoFabricacao: number;
  anoModelo: number;
  cor: string;
  preco: string;
  quilometragem: number;
  placa?: string | null;
  combustivel?: string | null;
  cambio?: string | null;
  status: StatusVeiculo;
  versao?: number;
}

export interface Pagina<T> {
  itens: T[];
  nextToken?: string | null;
}

export interface Pagamento {
  id: string;
  metodo: string;
  status: string;
  pixCopiaECola: string | null;
  valor: string;
  expiraEm: string;
}

export interface EventoVenda {
  para: StatusVenda;
  ocorridoEm: string;
  ator: string;
}

export interface Venda {
  id: string;
  status: StatusVenda;
  veiculo: Partial<Veiculo> & { marca?: string; modelo?: string };
  precoNegociado: string;
  reservaExpiraEm?: string | null;
  pagamento: Pagamento | null;
  criadoEm: string;
  clienteId?: string;
  retiradaLimiteEm?: string | null;
  retiradaEm?: string | null;
  motivoCancelamento?: string | null;
  historico?: EventoVenda[];
}

export interface Endereco {
  cep: string;
  logradouro: string;
  numero: string;
  complemento?: string | null;
  bairro: string;
  cidade: string;
  uf: string;
}

export interface Cliente {
  id: string;
  nomeCompleto: string;
  cpf: string;
  dataNascimento: string;
  email: string;
  telefone: string;
  endereco: Endereco;
  rg: { numero: string; orgaoEmissor: string; uf: string } | null;
  cnh: string | null;
  cadastroCompleto: boolean;
  camposPendentes: string[];
  status: string;
}

export interface Funcionario {
  id: string;
  nome: string;
  email: string;
  grupos: string[];
  ativo: boolean;
  mfaConfigurado: boolean;
}

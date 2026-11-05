// Validacoes espelhadas das regras da API: o formulario avisa antes de enviar, a API continua a fonte da verdade.

const PESOS_RENAVAM = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3];

export function digitoRenavam(primeirosDez: string): number {
  const soma = [...primeirosDez]
    .reverse()
    .reduce((s, d, i) => s + Number(d) * (PESOS_RENAVAM[i] ?? 0), 0);
  const resto = (soma * 10) % 11;
  return resto === 10 ? 0 : resto;
}

export function renavamValido(renavam: string): boolean {
  return /^\d{11}$/.test(renavam) && digitoRenavam(renavam.slice(0, 10)) === Number(renavam[10]);
}

export const chassiValido = (chassi: string): boolean =>
  /^[A-HJ-NPR-Z0-9]{17}$/.test(chassi.toUpperCase());

export const placaValida = (placa: string): boolean =>
  /^[A-Z]{3}\d[A-Z0-9]\d{2}$/.test(placa.toUpperCase());

export function cpfValido(cpf: string): boolean {
  const n = cpf.replace(/\D/g, "");
  if (n.length !== 11 || /^(\d)\1{10}$/.test(n)) return false;
  const dv = (base: string) => {
    const soma = [...base].reduce((s, d, i) => s + Number(d) * (base.length + 1 - i), 0);
    const r = (soma * 10) % 11;
    return r === 10 ? 0 : r;
  };
  return dv(n.slice(0, 9)) === Number(n[9]) && dv(n.slice(0, 10)) === Number(n[10]);
}

/** Erros de campo do cadastro de veiculo (vazio = valido). */
export function validarVeiculo(
  f: {
    renavam: string;
    chassi: string;
    placa: string;
    anoFabricacao: number;
    anoModelo: number;
    preco: number;
    quilometragem: number;
  },
  anoAtual = new Date().getFullYear(),
): string[] {
  const erros: string[] = [];
  if (!renavamValido(f.renavam))
    erros.push("RENAVAM inválido (11 dígitos com dígito verificador correto).");
  if (!chassiValido(f.chassi))
    erros.push("Chassi deve ter 17 caracteres alfanuméricos, sem as letras I, O e Q.");
  if (f.placa && !placaValida(f.placa)) erros.push("Placa inválida (ex.: ABC1234 ou BRA2E19).");
  if (
    !Number.isInteger(f.anoFabricacao) ||
    f.anoFabricacao < 1950 ||
    f.anoFabricacao > anoAtual + 1
  )
    erros.push(`Ano de fabricação deve estar entre 1950 e ${anoAtual + 1}.`);
  if (
    !Number.isInteger(f.anoModelo) ||
    f.anoModelo < f.anoFabricacao ||
    f.anoModelo > f.anoFabricacao + 1
  )
    erros.push("Ano do modelo deve ser o de fabricação ou o seguinte.");
  if (!(f.preco > 0) || f.preco >= 1e10) erros.push("Preço deve ser positivo.");
  if (!Number.isInteger(f.quilometragem) || !(f.quilometragem >= 0))
    erros.push("Quilometragem não pode ser negativa.");
  return erros;
}

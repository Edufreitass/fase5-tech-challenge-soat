import {
  chassiValido,
  cpfValido,
  digitoRenavam,
  placaValida,
  renavamValido,
  validarVeiculo,
} from "./validation";

const base = {
  renavam: "",
  chassi: "9BWZZZ377VT004251",
  placa: "",
  anoFabricacao: 2022,
  anoModelo: 2023,
  preco: 1000,
  quilometragem: 0,
};
const renavamOk = (() => {
  const b = "1234567890";
  return `${b}${digitoRenavam(b)}`;
})();

describe("validacao", () => {
  it("RENAVAM: 11 digitos com digito verificador", () => {
    expect(renavamValido(renavamOk)).toBe(true);
    expect(renavamValido(`${renavamOk.slice(0, 10)}${(Number(renavamOk[10]) + 1) % 10}`)).toBe(
      false,
    );
    expect(renavamValido("123")).toBe(false);
  });
  it("chassi sem I, O e Q e placa antiga ou Mercosul", () => {
    expect(chassiValido("9BWZZZ377VT004251")).toBe(true);
    expect(chassiValido("9BWZZZ377VT00425I")).toBe(false);
    expect(placaValida("abc1d23")).toBe(true);
    expect(placaValida("ABC1234")).toBe(true);
    expect(placaValida("AB12345")).toBe(false);
  });
  it("CPF com digitos verificadores", () => {
    expect(cpfValido("529.982.247-25")).toBe(true);
    expect(cpfValido("529.982.247-24")).toBe(false);
    expect(cpfValido("111.111.111-11")).toBe(false);
  });
  it("reune os erros do veiculo", () => {
    expect(validarVeiculo({ ...base, renavam: renavamOk })).toEqual([]);
    const erros = validarVeiculo(
      {
        ...base,
        renavam: "1",
        chassi: "x",
        placa: "zz",
        anoFabricacao: 1900,
        anoModelo: 1899,
        preco: -1,
        quilometragem: -5,
      },
      2026,
    );
    expect(erros).toHaveLength(7);
    expect(validarVeiculo({ ...base, renavam: renavamOk, anoModelo: 2025 })).toEqual([
      "Ano do modelo deve ser o de fabricação ou o seguinte.",
    ]);
  });
});

it.each([
  { anoFabricacao: Number.NaN },
  { anoFabricacao: 2022.5 },
  { anoModelo: Number.NaN },
  { anoModelo: 2022.5 },
  { quilometragem: Number.POSITIVE_INFINITY },
  { quilometragem: 10.5 },
])("rejeita valor numerico fora do contrato: %j", (alteracao) => {
  const entrada = { ...base, renavam: renavamOk, ...alteracao };

  const erros = validarVeiculo(entrada, 2026);

  expect(erros).not.toHaveLength(0);
});

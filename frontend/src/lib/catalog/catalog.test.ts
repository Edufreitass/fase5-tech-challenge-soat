import type { Veiculo } from "../types";
import { ajustar, carroceriaDe, corParaHex } from "../vehicles/cars";
import type { Filtros } from "./catalog";
import {
  daQuery,
  FILTROS_VAZIOS,
  filtrar,
  normalizar,
  opcoesDe,
  pagina,
  paraQuery,
  validarFiltros,
} from "./catalog";

const v = (id: string, extra: Partial<Veiculo> = {}): Veiculo => ({
  id,
  marca: "Fiat",
  modelo: "Argo",
  anoFabricacao: 2020,
  anoModelo: 2021,
  cor: "Prata Bari",
  preco: "50000.00",
  quilometragem: 1000,
  combustivel: "FLEX",
  cambio: "MANUAL",
  status: "DISPONIVEL",
  ...extra,
});
const estoque = [
  v("1"),
  v("2", {
    marca: "Honda",
    modelo: "Fit",
    preco: "90000.00",
    anoModelo: 2023,
    cor: "Preto Cristal",
  }),
  v("3", { modelo: "Mobi", preco: "30000.00", quilometragem: 50 }),
];

describe("catalogo", () => {
  it("deriva opcoes do estoque e restringe modelos pela marca", () => {
    const o = opcoesDe(estoque);
    expect(o.marcas).toEqual(["Fiat", "Honda"]);
    expect(o.anos).toEqual([2021, 2023]);
    expect(o.precos[0]).toBe(10000);
    expect(opcoesDe(estoque, "Honda").modelos).toEqual(["Fit"]);
  });

  it("restringe cor, ano, preco, combustivel e cambio a marca/modelo escolhidos", () => {
    const honda = opcoesDe(estoque, "Honda");
    expect(honda.marcas).toEqual(["Fiat", "Honda"]);
    expect(honda.cores).toEqual(["Preto Cristal"]);
    expect(honda.anos).toEqual([2023]);
    expect(honda.precos.at(-1)).toBe(90000);
    expect(opcoesDe(estoque, "Fiat", "Mobi").precos).toEqual([10000, 20000, 30000]);
  });

  it("normaliza filtros vindos da URL: descarta o que nao existe nas listas", () => {
    const sujo = {
      ...FILTROS_VAZIOS,
      marca: "Inexistente",
      precoMin: "45000",
      anoMin: "-5",
      cor: "Prata Bari",
      ordem: "xyz" as Filtros["ordem"],
    };
    expect(normalizar(sujo, estoque)).toEqual({ ...FILTROS_VAZIOS, cor: "Prata Bari" });
    // Cor que nao existe na marca escolhida cai fora; modelo de outra marca tambem.
    expect(
      normalizar({ ...FILTROS_VAZIOS, marca: "Honda", modelo: "Argo", cor: "Prata Bari" }, estoque),
    ).toEqual({ ...FILTROS_VAZIOS, marca: "Honda" });
    expect(normalizar({ ...FILTROS_VAZIOS, marca: "Fiat", precoMax: "50000" }, estoque)).toEqual({
      ...FILTROS_VAZIOS,
      marca: "Fiat",
      precoMax: "50000",
    });
    // Sem estoque carregado, so a ordem e validada.
    expect(
      normalizar({ ...FILTROS_VAZIOS, marca: "X", ordem: "xyz" as Filtros["ordem"] }, null),
    ).toEqual({
      ...FILTROS_VAZIOS,
      marca: "X",
    });
  });

  it("converte filtros e pagina de/para a query string", () => {
    const q = paraQuery({ ...FILTROS_VAZIOS, marca: "Fiat", ordem: "preco_desc" }, 3);
    expect(q.toString()).toBe("marca=Fiat&ordem=preco_desc&pagina=3");
    expect(paraQuery(FILTROS_VAZIOS, 1).toString()).toBe("");
    expect(daQuery(q)).toEqual({
      filtros: { ...FILTROS_VAZIOS, marca: "Fiat", ordem: "preco_desc" },
      numero: 3,
    });
    expect(daQuery(new URLSearchParams("pagina=-2")).numero).toBe(1);
    expect(daQuery(new URLSearchParams("pagina=abc")).numero).toBe(1);
  });

  it("filtra, ordena e valida", () => {
    expect(filtrar(estoque, { ...FILTROS_VAZIOS, marca: "Fiat" }).map((x) => x.id)).toEqual([
      "3",
      "1",
    ]);
    expect(
      filtrar(estoque, { ...FILTROS_VAZIOS, precoMin: "40000", cor: "Preto Cristal" }).map(
        (x) => x.id,
      ),
    ).toEqual(["2"]);
    expect(filtrar(estoque, { ...FILTROS_VAZIOS, ordem: "preco_desc" })[0]?.id).toBe("2");
    expect(filtrar(estoque, { ...FILTROS_VAZIOS, ordem: "km_asc" })[0]?.id).toBe("3");
    expect(filtrar(estoque, { ...FILTROS_VAZIOS, ordem: "ano_desc" })[0]?.id).toBe("2");
    expect(validarFiltros({ ...FILTROS_VAZIOS, precoMin: "-1" })).toMatch(/negativos/);
    expect(validarFiltros({ ...FILTROS_VAZIOS, anoMin: "2024", anoMax: "2020" })).toMatch(
      /ano mínimo/,
    );
    expect(validarFiltros(FILTROS_VAZIOS)).toBeNull();
  });

  it("pagina em blocos de 10 e limita a pagina", () => {
    const itens = Array.from({ length: 25 }, (_, i) => i);
    expect(pagina(itens, 1).itens).toHaveLength(10);
    expect(pagina(itens, 3)).toMatchObject({ itens: [20, 21, 22, 23, 24], paginas: 3, atual: 3 });
    expect(pagina(itens, 99).atual).toBe(3);
    expect(pagina([], 1)).toMatchObject({ paginas: 1, total: 0 });
  });
});

describe("carros", () => {
  it("mapeia cor comercial para tom e carroceria", () => {
    expect(corParaHex("Vermelho Alpine")).toBe("#d3122f");
    expect(corParaHex("Cinza Grafite")).toBe("#7c838d");
    expect(corParaHex("Laranja Atacama")).toBe("#ee6a12");
    expect(corParaHex("Xyz")).toBe("#8a929c");
    expect(carroceriaDe("Hilux SRV 2.8 Diesel")).toBe("pickup");
    expect(carroceriaDe("T-Cross Highline")).toBe("suv");
    expect(carroceriaDe("Corolla XEi 2.0")).toBe("sedan");
    expect(carroceriaDe("Mobi Like 1.0")).toBe("hatch");
    expect(ajustar("#000000", 0.5)).toBe("#808080");
  });
});

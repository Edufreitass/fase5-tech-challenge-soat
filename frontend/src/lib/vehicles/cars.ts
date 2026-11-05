export type Carroceria = "hatch" | "sedan" | "suv" | "pickup";

const SEM_ACENTO = (t: string) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// Primeira palavra da cor comercial ("Vermelho Alpine", "Cinza Platinum") define o tom base.
const CORES: [string, string][] = [
  ["branco", "#f4f5f7"],
  ["preto", "#16181c"],
  ["prata", "#c3c8d0"],
  ["cinza", "#7c838d"],
  ["grafite", "#3e444c"],
  ["vermelho", "#d3122f"],
  ["vinho", "#6e0f26"],
  ["azul", "#1f5fd1"],
  ["verde", "#1f8a52"],
  ["laranja", "#ee6a12"],
  ["amarelo", "#f2c300"],
  ["marrom", "#6a4328"],
  ["bege", "#cdb594"],
  ["dourado", "#c39a3a"],
  ["roxo", "#6a3aa8"],
  ["rosa", "#e0558b"],
];

/** Cor comercial em portugues -> cor CSS (cinza medio se desconhecida). */
export function corParaHex(cor: string): string {
  const alvo = SEM_ACENTO(cor);
  return CORES.find(([nome]) => alvo.includes(nome))?.[1] ?? "#8a929c";
}

const PICKUPS = [
  "strada",
  "toro",
  "saveiro",
  "hilux",
  "s10",
  "ranger",
  "montana",
  "frontier",
  "amarok",
  "ram",
];
const SUVS = [
  "t-cross",
  "tcross",
  "nivus",
  "tracker",
  "hr-v",
  "hrv",
  "creta",
  "duster",
  "kicks",
  "renegade",
  "compass",
  "pulse",
  "fastback",
  "taos",
  "tiguan",
  "sw4",
  "corolla cross",
  "dolphin",
  "yuan",
  "song",
  "captur",
  "ecosport",
];
const SEDANS = [
  "corolla",
  "civic",
  "virtus",
  "cronos",
  "voyage",
  "prisma",
  "logan",
  "sentra",
  "versa",
  "cruze",
  "jetta",
  "city",
  "yaris sedan",
  "onix plus",
  "hb20s",
  "etios sedan",
];

export function carroceriaDe(modelo: string): Carroceria {
  const m = SEM_ACENTO(modelo);
  if (PICKUPS.some((p) => m.includes(p))) return "pickup";
  if (SUVS.some((p) => m.includes(p))) return "suv";
  if (SEDANS.some((p) => m.includes(p))) return "sedan";
  return "hatch";
}

function canais(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Mistura a cor com branco (fator > 0) ou preto (fator < 0). */
export function ajustar(hex: string, fator: number): string {
  const alvo = fator >= 0 ? 255 : 0;
  const f = Math.abs(fator);
  return `#${canais(hex)
    .map((c) =>
      Math.round(c + (alvo - c) * f)
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}

export function luminosidade(hex: string): number {
  const [r, g, b] = canais(hex);
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}

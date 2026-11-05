import { useId } from "react";
import {
  ajustar,
  type Carroceria,
  carroceriaDe,
  corParaHex,
  luminosidade,
} from "../lib/vehicles/cars";

// Silhuetas laterais (viewBox 410x170, chao em y=150): corpo, vidros, rodas, porta e faroletes por carroceria.
interface Forma {
  corpo: string;
  vidros: string[];
  rodas: [number, number];
  raio: number;
  porta: [number, number, number];
  frente: number;
  traseira: number;
}
const FORMAS: Record<Carroceria, Forma> = {
  hatch: {
    corpo:
      "M52 130 L50 106 Q50 94 62 90 L70 88 Q76 56 100 36 Q112 26 140 26 L226 26 Q256 28 274 52 L292 76 Q300 82 316 84 L346 90 Q358 94 360 108 L360 130 Z",
    vidros: [
      "M96 76 Q104 46 122 36 L150 34 L150 76 Z",
      "M158 34 L224 34 Q246 36 260 56 L270 76 L158 76 Z",
    ],
    rodas: [104, 308],
    raio: 24,
    porta: [154, 76, 130],
    frente: 360,
    traseira: 50,
  },
  sedan: {
    corpo:
      "M32 130 L30 108 Q30 96 42 93 L84 88 Q92 78 104 74 L122 70 Q140 36 176 30 L238 30 Q268 34 286 62 L296 74 Q304 80 320 83 L366 90 Q380 94 380 108 L380 130 Z",
    vidros: [
      "M138 70 Q150 44 176 38 L196 38 L196 70 Z",
      "M204 38 L236 38 Q256 42 270 70 L204 70 Z",
    ],
    rodas: [92, 322],
    raio: 24,
    porta: [200, 70, 130],
    frente: 380,
    traseira: 30,
  },
  suv: {
    corpo:
      "M46 132 L44 104 Q44 90 58 86 L70 84 Q74 40 108 24 Q118 18 140 18 L248 18 Q276 22 292 50 L304 78 Q312 84 330 86 L350 90 Q364 94 366 108 L366 132 Z",
    vidros: [
      "M92 76 Q96 42 118 30 L150 28 L150 76 Z",
      "M158 28 L244 28 Q262 32 274 54 L284 76 L158 76 Z",
    ],
    rodas: [104, 308],
    raio: 28,
    porta: [154, 76, 132],
    frente: 366,
    traseira: 44,
  },
  pickup: {
    corpo:
      "M36 132 L36 104 Q36 92 50 88 L84 82 Q96 44 126 36 L186 36 Q206 38 218 62 L228 84 L370 84 Q382 86 384 100 L386 132 Z",
    vidros: [
      "M104 76 Q112 52 130 44 L160 44 L160 76 Z",
      "M168 44 L184 44 Q198 48 206 76 L168 76 Z",
    ],
    rodas: [94, 322],
    raio: 28,
    porta: [164, 76, 132],
    frente: 386,
    traseira: 36,
  },
};

interface Props {
  cor: string;
  modelo: string;
  className?: string;
  titulo?: string;
}

/** Ilustracao do veiculo na cor real do anuncio (a cor comercial vira o tom da lataria). */
export function CarroSvg({ cor, modelo, className = "", titulo }: Props) {
  const id = useId().replaceAll(":", "");
  const f = FORMAS[carroceriaDe(modelo)];
  const base = corParaHex(cor);
  const clara = luminosidade(base) > 0.7;
  return (
    <svg
      viewBox="0 0 410 170"
      role="img"
      aria-label={
        titulo ??
        `Ilustração de referência de ${modelo} na cor ${cor}; não é uma fotografia do veículo anunciado`
      }
      className={className}
    >
      <defs>
        <linearGradient id={`lat${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={ajustar(base, 0.28)} />
          <stop offset=".55" stopColor={base} />
          <stop offset="1" stopColor={ajustar(base, -0.28)} />
        </linearGradient>
        <linearGradient id={`vid${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8fb3d6" />
          <stop offset="1" stopColor="#1d2a38" />
        </linearGradient>
        <radialGradient id={`sombra${id}`}>
          <stop offset="0" stopColor="#000" stopOpacity=".55" />
          <stop offset="1" stopColor="#000" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`brilho${id}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#fff" stopOpacity="0" />
          <stop offset=".5" stopColor="#fff" stopOpacity=".5" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <ellipse cx="205" cy="152" rx="175" ry="10" fill={`url(#sombra${id})`} />
      <path
        d={f.corpo}
        fill={`url(#lat${id})`}
        stroke={clara ? "#9aa1ab" : ajustar(base, -0.45)}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      {f.vidros.map((d) => (
        <path
          key={d}
          d={d}
          fill={`url(#vid${id})`}
          stroke="#0b0f14"
          strokeWidth="1"
          opacity=".95"
        />
      ))}
      <path
        d={`M${f.porta[0]} ${f.porta[1]} V${f.porta[2]}`}
        stroke={ajustar(base, -0.4)}
        strokeWidth="1.2"
        opacity=".7"
      />
      <rect
        x={f.porta[0] + 8}
        y={f.porta[1] + 10}
        width="16"
        height="3.5"
        rx="1.7"
        fill={ajustar(base, -0.35)}
      />
      <path
        d={`M${f.traseira + 4} 124 H${f.frente - 4} V132 H${f.traseira + 4} Z`}
        fill="#0b0d10"
        opacity=".55"
      />
      <path d={f.corpo} fill={`url(#brilho${id})`} opacity=".25" />
      <rect x={f.frente - 20} y="97" width="16" height="7" rx="3" fill="#fff3c4" />
      <rect x={f.traseira + 2} y="98" width="9" height="7" rx="2" fill="#e0243c" />
      {f.rodas.map((x) => (
        <g key={x}>
          <circle cx={x} cy="130" r={f.raio + 6} fill="#0a0b0d" />
          <circle cx={x} cy="130" r={f.raio} fill="#1a1c20" stroke="#2c2f35" strokeWidth="2" />
          <circle cx={x} cy="130" r={f.raio * 0.62} fill="#c9ced6" />
          {[0, 72, 144, 216, 288].map((a) => (
            <rect
              key={a}
              x={x - 1.8}
              y={130 - f.raio * 0.6}
              width="3.6"
              height={f.raio * 0.45}
              rx="1.5"
              fill="#6b717b"
              transform={`rotate(${a} ${x} 130)`}
            />
          ))}
          <circle cx={x} cy="130" r="3.5" fill="#4a4f57" />
        </g>
      ))}
    </svg>
  );
}

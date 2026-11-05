import { useState } from "react";
import { Titulo } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { Vendas } from "../features/dashboard/Sales";
import { Equipe } from "../features/dashboard/Team";
import { Veiculos } from "../features/dashboard/Vehicles";

type Aba = "veiculos" | "vendas" | "equipe";

export function Painel() {
  const { papel } = useAuth();
  const [aba, setAba] = useState<Aba>("veiculos");
  const abas: { id: Aba; rotulo: string }[] = [
    { id: "veiculos", rotulo: "Veículos" },
    { id: "vendas", rotulo: "Vendas" },
    ...(papel === "admin" ? [{ id: "equipe" as Aba, rotulo: "Equipe" }] : []),
  ];
  return (
    <>
      <Titulo sub="Gestão de estoque, vendas e equipe da loja.">Painel</Titulo>
      <div role="tablist" aria-label="Seções do painel" className="mb-6 flex flex-wrap gap-2">
        {abas.map((a) => (
          <button
            type="button"
            key={a.id}
            role="tab"
            aria-selected={aba === a.id}
            onClick={() => setAba(a.id)}
            className={`min-h-11 rounded-full px-5 py-2 text-sm font-bold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fiap ${aba === a.id ? "bg-fiap text-white" : "bg-white/5 text-ultrassonico hover:text-white"}`}
          >
            {a.rotulo}
          </button>
        ))}
      </div>
      {aba === "veiculos" && <Veiculos />}
      {aba === "vendas" && <Vendas />}
      {aba === "equipe" && papel === "admin" && <Equipe />}
    </>
  );
}

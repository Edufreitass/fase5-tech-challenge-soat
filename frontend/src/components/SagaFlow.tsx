import { Background, type Edge, type Node, Position, ReactFlow } from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { montarFluxo } from "../lib/saga";
import type { StatusVenda } from "../lib/types";

const LARGA = "(min-width: 640px)";

/** Tela larga o bastante para a linha do tempo horizontal (sem matchMedia, como nos testes, assume que sim). */
function useTelaLarga(): boolean {
  const [larga, setLarga] = useState(() => window.matchMedia?.(LARGA).matches ?? true);
  useEffect(() => {
    const m = window.matchMedia?.(LARGA);
    if (!m) return;
    const mudar = () => setLarga(m.matches);
    m.addEventListener("change", mudar);
    return () => m.removeEventListener("change", mudar);
  }, []);
  return larga;
}

/** Linha do tempo da saga de compra desenhada com React Flow (somente leitura). No celular fica na vertical: na
 * horizontal as 4 etapas precisariam de zoom abaixo do minimo e as pontas eram cortadas. */
export function SagaFlow({ status }: { status: StatusVenda }) {
  const larga = useTelaLarga();
  const { nodes, edges } = useMemo(() => {
    const etapas = montarFluxo(status);
    const nodes: Node[] = etapas.map((e, i) => ({
      id: e.id,
      position: larga ? { x: i * 210, y: 20 } : { x: 0, y: i * 90 },
      data: { rotulo: e.rotulo, label: e.rotulo },
      className: e.estado,
      draggable: false,
      selectable: false,
      sourcePosition: larga ? Position.Right : Position.Bottom,
      targetPosition: larga ? Position.Left : Position.Top,
    }));
    const edges: Edge[] = etapas.flatMap((origem, indice) => {
      const destino = etapas[indice + 1];
      if (!destino) return [];
      return [
        {
          id: `${origem.id}-${destino.id}`,
          source: origem.id,
          target: destino.id,
          animated: destino.estado === "atual",
          className: origem.estado === "feito" ? "feito" : "",
        },
      ];
    });
    return { nodes, edges };
  }, [status, larga]);

  return (
    <div
      className={`${larga ? "h-36" : "h-96"} w-full overflow-hidden rounded-2xl border border-white/10 bg-black/30`}
      role="img"
      aria-label={`Etapas da compra: ${status}`}
    >
      <ReactFlow
        key={larga ? "horizontal" : "vertical"}
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        panOnScroll={false}
        preventScrolling={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#75838b" gap={22} size={1} />
      </ReactFlow>
    </div>
  );
}

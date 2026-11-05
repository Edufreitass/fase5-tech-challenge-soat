// Mock de `@xyflow/react`: lista os nos para que os testes verifiquem o conteudo.
import type { ReactNode } from "react";

type No = {
  id: string;
  data: { rotulo: string };
  className?: string;
  position?: { x: number; y: number };
};
export const ReactFlow = ({ nodes }: { nodes: No[] }) => (
  <ul data-testid="fluxo">
    {nodes.map((n) => (
      <li key={n.id} data-estado={n.className} data-x={n.position?.x} data-y={n.position?.y}>
        {n.data.rotulo}
      </li>
    ))}
  </ul>
);
export const Background = () => null;
export const Controls = () => null;
export const Handle = () => null;
export const Position = { Left: "left", Right: "right", Top: "top", Bottom: "bottom" };
export const ReactFlowProvider = ({ children }: { children?: ReactNode }) => children;
export type Node = No;
export type Edge = { id: string; source: string; target: string };

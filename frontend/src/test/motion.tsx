// Mock de `motion/react` para os testes: renderiza o elemento puro, sem animacao.
import { createElement, type ReactNode } from "react";

const limpar = ({
  initial,
  animate,
  exit,
  transition,
  whileHover,
  whileTap,
  whileInView,
  viewport,
  layout,
  variants,
  ...resto
}: Record<string, unknown>) => {
  void [
    initial,
    animate,
    exit,
    transition,
    whileHover,
    whileTap,
    whileInView,
    viewport,
    layout,
    variants,
  ];
  return resto;
};

// Um componente estavel por tag: criar a funcao a cada acesso remontaria a arvore a cada render.
const cache: Record<string, (p: Record<string, unknown>) => ReactNode> = {};
export const motion = new Proxy(
  {},
  {
    get: (_, tag: string) =>
      (cache[tag] ??= (props: Record<string, unknown>) => createElement(tag, limpar(props))),
  },
) as Record<string, (p: Record<string, unknown>) => ReactNode>;
export const AnimatePresence = ({ children }: { children?: ReactNode }) => children;
export const useReducedMotion = () => true;

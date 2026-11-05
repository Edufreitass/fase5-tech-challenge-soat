export interface Requisito {
  id: string;
  rotulo: string;
  ok: boolean;
}

/** Politica dos dois pools: 12+ caracteres com maiuscula, minuscula, numero e simbolo. */
export function requisitosDaSenha(senha: string): Requisito[] {
  return [
    { id: "tamanho", rotulo: "12 ou mais caracteres", ok: senha.length >= 12 },
    { id: "maiuscula", rotulo: "Uma letra maiúscula", ok: /[A-Z]/.test(senha) },
    { id: "minuscula", rotulo: "Uma letra minúscula", ok: /[a-z]/.test(senha) },
    { id: "numero", rotulo: "Um número", ok: /\d/.test(senha) },
    { id: "simbolo", rotulo: "Um símbolo (ex.: ! @ # $)", ok: /[^A-Za-z0-9]/.test(senha) },
  ];
}

export const senhaValida = (senha: string): boolean => requisitosDaSenha(senha).every((r) => r.ok);

export const emailValido = (email: string): boolean =>
  /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());

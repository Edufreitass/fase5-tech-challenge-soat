/** Le somente campos textuais; arquivos e campos ausentes nao viram strings falsas. */
export function textoDoFormulario(formulario: HTMLFormElement): (campo: string) => string {
  const dados = new FormData(formulario);
  return (campo) => {
    const valor = dados.get(campo);
    return typeof valor === "string" ? valor : "";
  };
}

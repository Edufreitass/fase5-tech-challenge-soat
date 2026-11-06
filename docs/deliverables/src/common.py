import pathlib, subprocess, sys
HERE = pathlib.Path(__file__).parent
DIAG = HERE.parent.parent / "diagrams"
DATA = "05/11/2026"
REPO = "github.com/Edufreitass/fase5-tech-challenge-soat"
NOTA = ("Esta entrega descreve código e infraestrutura declarada. <code>infra/config/dev.yml</code> contém "
        "<code>destroy: true</code>: o ambiente foi implantado e validado em 05/11/2026 e depois removido, e não há implantação ativa. Testes locais não comprovam latência, custos, "
        "achados de segurança ou comportamento E2E na AWS.")
def page(titulo, corpo):
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{titulo}</title>'
            f'<link rel="stylesheet" href="style.css"></head><body>{corpo}</body></html>')
def cab(titulo):
    return (f'<h1>{titulo}</h1><div class="sub">Revenda de veículos · Tech Challenge SOAT · Fase 5 · '
            f'{DATA}</div><div class="nota">{NOTA}</div>')
def tabela(cab_, linhas):
    h = "".join(f"<th>{c}</th>" for c in cab_)
    r = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>" for l in linhas)
    return f"<table><tr>{h}</tr>{r}</table>"
def pdf(html_name, pdf_path):
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", (HERE / html_name).as_uri()], check=True,
                   capture_output=True)

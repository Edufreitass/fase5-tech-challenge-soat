from sections import *
OUT = HERE.parent
docs = {
 "architecture-design": ("Desenho da arquitetura", lambda: arquitetura(True)),
 "data-security-report": ("Relatório de segurança dos dados", seguranca),
 "saga-report": ("Relatório SAGA", saga),
}
for nome, (t, f) in docs.items():
    (HERE / f"{nome}.html").write_text(page(t, f()))
    pdf(f"{nome}.html", OUT / f"{nome}.pdf")
capa = (f"<h1>Tech Challenge — Fase 5</h1><div class='sub'>Revenda de veículos · Arquitetura de software · Entrega técnica consolidada · {DATA}</div>"
        f"<p>Arquitetura serverless/gerenciada, segurança dos dados, SAGA e rastreabilidade dos requisitos.</p>"
        f"<ol><li>Desenho da arquitetura e cinco diagramas AWS</li><li>Relatório de segurança dos dados</li><li>Relatório SAGA</li><li>Matriz de requisitos</li></ol>"
        f"<p>Repositório: <code>{REPO}</code> (se privado, o avaliador precisa receber acesso).</p><div class='nota'>{NOTA} Gateway Pix simulado.</div>")
corpo = capa + "".join(f'<div class="pg">{f()}</div>' for _, f in [(0, lambda: arquitetura(True)), (0, seguranca), (0, saga), (0, matriz)])
(HERE / "tech-challenge-fase5.html").write_text(page("Tech Challenge Fase 5", corpo))
pdf("tech-challenge-fase5.html", OUT / "tech-challenge-fase5.pdf")
print("ok")

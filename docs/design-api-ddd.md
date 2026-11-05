# Design da API orientado a domínio

O contrato HTTP publica capacidades do negócio e mantém os limites de domínio do backend. A estrutura por contexto em `backend/src` é a referência para as responsabilidades; a API não expõe tabelas, chaves de persistência, nomes de funções Lambda ou passos internos de saga.

## Contextos delimitados

| Contexto | Responsabilidade | Recursos públicos |
| --- | --- | --- |
| Clientes | Perfil do comprador, consentimentos, proteção de dados e direitos LGPD | `/clientes`, `/clientes/meu-perfil`, consentimentos, exportação, vendas do cliente |
| Veículos | Catálogo e ciclo de vida dos anúncios | `/veiculos`, `/veiculos/{veiculo_id}`, `/gestao/veiculos` |
| Vendas | Compra, reserva, pagamento, desistência, documentação e retirada | `/vendas`, `/vendas/{venda_id}` e operações de ciclo de vida |
| Administração | Operação restrita, funcionários, auditoria, segredos e reprocessamento | `/administracao/*`, `/configuracao-inicial` |
| Adaptador de pagamento simulado | Apoio de desenvolvimento para simular callbacks do provedor | `/_simulacao/pagamentos/*` (rotas técnicas, fora dos recursos de negócio) |

## Linguagem e modelagem dos recursos

- Caminhos de negócio usam substantivos no plural e em português, como `clientes`, `veiculos` e `vendas`; identificadores ficam em segmentos `{..._id}`.
- `GET`, `POST`, `PATCH` e `DELETE` representam consulta, criação/início de ação, alteração parcial e encerramento, respectivamente. Ações de ciclo de vida inevitáveis são sub-recursos em português (`/inativacao`, `/reativacao`, `/desistencia`, `/retirada`).
- `/clientes/meu-perfil` representa o cliente autenticado. O identificador do titular é obtido da identidade, evitando que o consumidor escolha outro cliente no caminho.
- `/veiculos` é a leitura pública do catálogo; `/gestao/veiculos` é uma projeção operacional autorizada. As duas visões pertencem ao contexto Veículos e não expõem o modelo de armazenamento.
- `/vendas` inicia a compra e a reserva. O processamento distribuído permanece uma saga interna; `/administracao/vendas/{venda_id}/fluxo/reprocessamento` é uma capacidade operacional restrita, não parte do fluxo de compra do cliente.
- Atualizações concorrentes de perfil, anúncio e funcionário usam `If-Match`/ETag quando definidos pela implementação. O cliente deve reenviar a versão observada para evitar sobrescrever alterações concorrentes.

## Colaboração entre contextos

Cada contexto mantém suas regras e casos de uso em `domain` e `application`; adaptadores HTTP, DynamoDB, eventos e AWS ficam nas bordas. Vendas coordena a compra e integra com Clientes e Pagamentos por portas/adaptadores e eventos, sem importar detalhes de infraestrutura para o domínio. As notificações de domínio e a saga permitem desfazer ou continuar o processo sem transformar os passos internos em endpoints públicos.

## Regras do contrato OpenAPI

- A especificação versionada é OpenAPI 3.1.2, JSON Schema alinhado à família 3.1 e compatível com a validação e o Swagger UI usados pelo projeto.
- Resumos, descrições, tags e mensagens documentais são pt-BR. Termos normativos de protocolo (`ETag`, `If-Match`, `OAuth2`, `HTTP`) e identificadores de código permanecem conforme os padrões técnicos.
- Cada operação tem `operationId` estável, tag de contexto, parâmetros de caminho descritos, formato de sucesso e resposta de validação. Mudanças no contrato são geradas a partir dos handlers e verificadas contra o arquivo versionado pelo teste de contrato.
- Erros HTTP da aplicação usam `application/problem+json`; autenticação e autorização são declaradas na operação conforme os papéis aceitos.

## Evolução

Uma capacidade nova deve ser atribuída ao contexto dono da regra, usar a linguagem ubíqua desse contexto, preservar autorização e documentar os efeitos observáveis. Se uma alteração mudar caminho, método, cabeçalho ou formato de payload, atualize consumidor e produtor na mesma mudança e mantenha teste de contrato e testes unitários cobrindo a transição.

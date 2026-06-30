# devoz-automations

Automações operacionais da DevOZ — código executável + agendamento (GitHub Actions).
Cada automação tem uma **skill correspondente** no repo `devoz-skills` (instruções/"como rodar"),
que aponta pra cá. Aqui mora o **código** e os **secrets**; lá moram as instruções.

## Automações

| Automação | O que faz | Agendamento | Skill (instruções) |
|---|---|---|---|
| `directory-sync` | Atualiza o Diretório (Quem é Quem) da intranet a partir do Google Workspace | diário 05:00 BRT | devoz-skills: workspace-directory-sync |
| `org-chart` | Gera o Organograma (PNG, hierarquia por gestor) a partir do **Feedz** e publica no Confluence | diário 05:30 BRT | devoz-skills: workspace-directory-sync |

## Estrutura
```
scripts/            # código das automações
.github/workflows/  # agendamentos (Actions)
docs/               # setup/provisionamento (service accounts, tokens, secrets)
```

## Setup
Ver `docs/SETUP-directory-sync.md`. Secrets ficam em Settings → Secrets and variables → Actions.
Nenhum segredo no código.

## Token do Feedz (para o org-chart)
Gere em **Configurações → Integrações → Chave de Integração API v2** (admin do Feedz) e cadastre como secret `FEEDZ_API_TOKEN`. Endpoint usado: `GET /v2/integracao/employees` (somente leitura). A remuneração retornada pela API é **ignorada** de propósito.

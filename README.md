# devoz-automations

Automações operacionais da DevOZ — código executável + agendamento (GitHub Actions).
Cada automação tem uma **skill correspondente** no repo `devoz-skills` (instruções/"como rodar"),
que aponta pra cá. Aqui mora o **código** e os **secrets**; lá moram as instruções.

## Automações

| Automação | O que faz | Agendamento | Skill (instruções) |
|---|---|---|---|
| `org-chart` | Gera o **Organograma estrutural** (Área › Time › Grupo) a partir do **Feedz** e publica no Confluence | **pausado** (disparo manual) até a limpeza do Feedz | devoz-skills: org-chart |

> O agendamento diário está **pausado** (bloco `schedule` comentado no workflow) até o Feedz estar limpo. Religar = descomentar o `schedule`.

## Estrutura
```
scripts/            # código das automações
.github/workflows/  # agendamentos (Actions)
```

## org-chart — como roda

Fonte de dados via env `ORG_SOURCE`:
- `feedz` (padrão): lê da API do Feedz (departamento→Time, groups→Grupo, área via `taxonomy.json`, papel via subordinados). Requer Feedz limpo.
- `csv`: lê `ORG_CSV` (pipe `nome|area|time|grupo|papel`) — uso interino a partir da planilha de correção (`scripts/org_rows_interino.csv`).

`DRY_RUN=1` gera só o PNG (artifact), sem publicar.

## Token do Feedz
Gere em **Configurações → Integrações → Chave de Integração API v2** (admin do Feedz) e cadastre como secret `FEEDZ_API_TOKEN`. Endpoint usado: `GET /v2/integracao/employees` (somente leitura). A remuneração retornada pela API é **ignorada** de propósito. Secrets ficam em Settings → Secrets and variables → Actions; nenhum segredo no código.

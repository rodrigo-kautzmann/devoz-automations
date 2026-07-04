# devoz-automations

Automações operacionais da DevOZ — código executável + agendamento (GitHub Actions).
Cada automação tem uma **skill correspondente** no repo `devoz-skills` (instruções/"como rodar"),
que aponta pra cá. Aqui mora o **código** e os **secrets**; lá moram as instruções.

## Automações

| Automação | O que faz | Agendamento | Skill (instruções) |
|---|---|---|---|
| `org-chart` | Gera o **Organograma estrutural** (Área › Time › Grupo) a partir do **Feedz** e publica no Confluence | **pausado** (disparo manual) até a limpeza do Feedz | devoz-skills: org-chart |
| `ozmap-metrics` | Extrai histórico de métricas de clientes do OZmap (usuários, caixas, projetos, limites) do Prometheus interno via proxy do Grafana | sob demanda / CLI | `README_ozmap_metrics.md` |
| `audit-amarracao` | Auditoria da **amarração de clientes** entre financeiro (Supabase), CRM (Zoho), Totango e monitoramento (OZmap), por `ozid`; e-mail no achado de gaps/divergências | semanal (seg 06:00 BRT) | (skill a criar em devoz-skills) |

> O agendamento diário do `org-chart` está **pausado** (bloco `schedule` comentado no workflow) até o Feedz estar limpo. Religar = descomentar o `schedule`.

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

## audit-amarracao — como roda

Cruza clientes pela chave canônica `ozid` (UUID) entre quatro fontes e reporta
**gaps de presença** e **IDs divergentes**. Fonte da verdade = financeiro (quem fatura).

Chave unificada descoberta: `monitoramento.userID` = `CRM.ozid` = `Xero.AccountNumber`
= `Superlógica.st_sincro_sac`; `monitoramento.host` ≈ `CRM.domain`.

Fontes e secrets (GitHub Actions):
- **Financeiro** (Supabase/cockpit): `PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE` (SSL require, Session Pooler).
- **CRM** (Zoho OAuth): `ZOHO_CLIENT_ID ZOHO_CLIENT_SECRET ZOHO_REFRESH_TOKEN` (+ `ZOHO_ACCOUNTS_URL`/`ZOHO_API_URL` se não for `.com`).
- **Monitoramento** (Grafana proxy): `GRAFANA_TOKEN` (service account Viewer). `GRAFANA_URL`/`GRAFANA_DS_UID` são literais no workflow.
- **Totango** (opcional): `TOTANGO_APP_TOKEN` (+ `TOTANGO_ID_FIELD`, default `account_id`). Sem token, é ignorado.
- **E-mail**: `SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASSWORD ALERT_FROM ALERT_TO`.

Rodar/depurar:
```
python3 scripts/audit_amarracao.py                 # auditoria completa (gera audit_out/ + e-mail)
python3 scripts/audit_amarracao.py --no-email      # só relatório, sem e-mail
python3 scripts/audit_amarracao.py --probe-totango # dumpa amostra do Totango p/ descobrir o campo do ozid
```
Cada fonte é lida em modo tolerante: se uma falhar (menos o financeiro), a auditoria segue e
marca a falha no resumo. Saída em `audit_out/` (`gaps.csv`, `divergencias.csv`, `resumo.md`).

> ⚠️ Totango: o campo que guarda o `ozid`/`domain` ainda **não foi confirmado**. Rode
> `--probe-totango` uma vez e ajuste `TOTANGO_ID_FIELD` conforme a amostra.

## Token do Feedz
Gere em **Configurações → Integrações → Chave de Integração API v2** (admin do Feedz) e cadastre como secret `FEEDZ_API_TOKEN`. Endpoint usado: `GET /v2/integracao/employees` (somente leitura). A remuneração retornada pela API é **ignorada** de propósito. Secrets ficam em Settings → Secrets and variables → Actions; nenhum segredo no código.

# devoz-automations

Automações operacionais da DevOZ — código executável + agendamento (GitHub Actions).
Cada automação tem uma **skill correspondente** no repo `devoz-skills` (instruções/"como rodar"),
que aponta pra cá. Aqui mora o **código** e os **secrets**; lá moram as instruções.

## Automações

| Automação | O que faz | Agendamento | Skill (instruções) |
|---|---|---|---|
| `org-chart` | Gera o **Organograma estrutural** (Área › Time › Grupo) a partir do **Feedz** e publica no Confluence | diário (~06:00 BRT) + disparo manual | devoz-skills: org-chart |
| `ozmap-metrics` | Extrai histórico de métricas de clientes do OZmap (usuários, caixas, projetos, limites) do Prometheus interno via proxy do Grafana | sob demanda / CLI | `README_ozmap_metrics.md` |
| `audit-ozid` | Auditoria do **ozid**: consistência da chave canônica entre financeiro (Supabase), CRM (Zoho) e Totango; e-mail no achado de gaps/divergências. Nada que exija VPN | semanal (seg 06:00 BRT) | (skill a criar em devoz-skills) |

> O agendamento diário do `org-chart` está **ativo** desde o commit `67b9852` (cron `07 9 * * *` = 06:07 BRT).
> O GitHub enfileira jobs agendados, então o disparo real costuma atrasar — minuto quebrado reduz o atraso, mas não zera.

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

## audit-ozid — como roda

Cruza clientes pela chave canônica `ozid` (UUID) e reporta **gaps de presença** e
**IDs divergentes**. Fonte da verdade = financeiro (quem fatura).

Chave unificada: `CRM.ozid` = `Xero.AccountNumber` = `Superlógica.st_sincro_sac`
= `Totango.Identifier` = `Freshdesk.custom_fields.identificador`
= `Jira.customfield_10101` = `Chargebee.customer_id`.

> **Nada que exija VPN entra nesta auditoria** (decisão de 2026-08-24). Ver "Fora do escopo".

Fontes e secrets (GitHub Actions):
- **Financeiro** (Supabase/cockpit): `PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE` (SSL require, Session Pooler).
- **CRM** (Zoho OAuth): `ZOHO_CLIENT_ID ZOHO_CLIENT_SECRET ZOHO_REFRESH_TOKEN` (+ `ZOHO_ACCOUNTS_URL`/`ZOHO_API_URL` se não for `.com`).
- **Totango** (opcional): `TOTANGO_APP_TOKEN` — token da **Search API**, formato `{v2}<uuid>` (o token do `int-hub`, usado para escrita, **não** serve). `TOTANGO_ID_FIELD` default `identifier`. Sem token, a fonte é marcada como falha no resumo.
- **E-mail**: `SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASSWORD ALERT_FROM ALERT_TO`.

Rodar/depurar:
```
python3 scripts/audit_ozid.py                 # auditoria completa (gera audit_out/ + e-mail)
python3 scripts/audit_ozid.py --no-email      # só relatório, sem e-mail
python3 scripts/audit_ozid.py --probe-totango # dumpa amostra do Totango p/ descobrir o campo do ozid
```
Cada fonte é lida em modo tolerante: se uma falhar (menos o financeiro), a auditoria segue e
marca a falha no resumo. Saída em `audit_out/` (`gaps.csv`, `divergencias.csv`, `resumo.md`).

### Totango — onde vive o ozid (confirmado)

Validado contra a API e contra o subflow `Totango | createAccount` do Node-RED (CSM):

| Campo no Totango | Conteúdo | Serve de chave? |
|---|---|---|
| atributo `Identifier` | o `ozid` | ✅ **é a chave canônica** (1492/1512 contas) |
| atributo `Identificador` | o `ozid` (duplicata legada, mesmo valor) | fallback |
| account id (`hits[].name`) | `ozid` só nas contas novas; nas legadas é slug (`wayiranet`) | ❌ 364 contas com slug |
| atributo `Company Domain` | URL completa `https://<slug>.ozmap.com.br` | último recurso (normalizar: CRM.domain é só o slug) |

A Search API é **`/api/v1/search/accounts`** — `v2` não existe (404). Os campos pedidos
voltam **posicionalmente** em `hits[].selected_fields`, na ordem de `fields` (não em
`display_fields`). Era isso que fazia a auditoria reportar `Totango=0`.

Pendências de limpeza no Totango (levantadas em 2026-08-24, 1512 contas):
- 3 contas lixo sem nenhum atributo: `fake-user-id-para-ambiente-local-nao-e-credencial-real`, `PLACEHOLDER_USER_ID`, `import-beltra3`.
- 1 cliente duplicado: `fastnetsystem` tem conta legada (slug) **e** conta nova (UUID), ambas `Churn`.
- 2 `Identifier` fora do padrão UUID (batem com o CRM, mas quebram a validação): `bayconnecttelecom`, `nari`.
- 20 contas sem `Identifier`; 18 sem `Status`.

### Freshdesk — tem ozid sim (e é a fonte mais suja)

`Freshdesk.company.custom_fields.identificador` guarda o `ozid`. Quem grava é o subflow
`Freshdesk | createCompany` (CSM); a busca é `Freshdesk | searchCompaniesByUserId`
(`GET /api/v2/search/companies?query="identificador:'<ozid>'"`).

Estado em 2026-08-24 — **624 companies**:

| `custom_fields.identificador` | Contas | % |
|---|---|---|
| UUID válido (ozid de verdade) | 252 | 40% |
| slug do domínio (`maisnet`, `360net`) | 322 | 52% |
| vazio | 50 | 8% |

Dos 322 com slug, **275 (85%) são resolvíveis** cruzando o slug com o `Company Domain`
do Totango; **47 não resolvem** por si só (grafia divergente: `redeserrado` vs `redecerrado`,
`nasciemtoinfornet`, `mtelecom` vs `MateusTelecom`) — esses precisam de correção manual.
Incluir Freshdesk na auditoria exige, portanto, **fallback por slug de domínio**, não só
match direto por UUID.

**Freshchat: não existe integração.** Zero referências nos 3 pilares do Node-RED.

## Escopo da auditoria de ozid

O escopo é **cliente**, e **sem VPN**: os 8 sistemas que carregam o ozid num campo próprio
e respondem da internet pública. Hoje o script lê 3. Mapa visual completo: `Mapa do ozid` (artifact).

| Fonte | Campo do ozid | Situação |
|---|---|---|
| Cockpit / Supabase | `core.dim_cliente_ozid` | ✅ implementado (fonte da verdade atual) |
| Zoho CRM | `Senha` ("identificador") → `ozid` (fórmula) | ✅ implementado |
| Totango | atributo `Identifier` | ✅ código corrigido — falta o secret do token |
| Freshdesk | `company.custom_fields.identificador` | ❌ mapeado, não implementado (exige fallback por slug) |
| Jira Suporte (JSM) | `customfield_10101` — rótulo "Client ID" | ❌ mapeado, não implementado |
| Chargebee | o próprio `customer_id` **é** o ozid | ❌ mapeado, não implementado (aba WiP) |
| Superlógica | `st_sincro_sac` | ⚠️ só indireto, agregado no "financeiro" do cockpit |
| Xero | `Contact.AccountNumber` | ⚠️ só indireto, agregado no "financeiro" do cockpit |

Superlógica e Xero alimentam o `fct_faturamento`. Lê-los direto separa erro de ingestão
do cockpit de erro de amarração na ponta.

**Dois eixos de reconciliação, não um.** O ozid resolve os casos novos; o **slug de
domínio** (`CRM.domain` = `silcomnet`) recupera o registro legado
que ficou com slug no lugar do UUID — 322 das 624 companies do Freshdesk e 364 das 1512
contas do Totango. Sem o segundo eixo, o Freshdesk entra pela metade.

### Fora do escopo — não será tratado aqui

**Por exigir VPN** (decisão de 2026-08-24). A auditoria roda no GitHub Actions, que não tem
acesso à rede interna. Verificado: `isismanager.devoz.com.br:1337` dá timeout e
`monitoz.ozmap.com` não responde nem do container em nuvem nem de um Mac fora da VPN.

| Fonte | Campo do ozid | Consequência de ficar fora |
|---|---|---|
| Manager / OZmachine | `user_id` | A fonte da verdade continua sendo o **financeiro** ("quem fatura"), não o Manager ("quem existe"). A auditoria não valida se um ozid é legítimo. |
| Monitoramento (Prometheus/Grafana) | label `userID` | Deixa de existir a verificação "o cliente está de pé". Some a divergência `host_x_domain` e os gaps `fatura_sem_monitoramento` / `monitorado_sem_faturar` — que eram **342 dos 543 achados** da última rodada local. |

**Por serem camada de infra.** **AWX, AWS/EC2, Teleport, SigNoz, Skycloak/Keycloak e
Wasabi** enxergam *máquina*, não *cliente*: não têm ozid nem deveriam ter. A chave deles é
hostname e o ciclo de vida é o da instância. Se a amarração de infra precisar de auditoria,
ela é **outra auditoria**.

### Descartados

- **Zabbix — não vamos olhar: está em descontinuação.** Não faz sentido investir em
  amarração de um sistema que vai sair. Além disso nunca foi sistema interno da DevOZ: nos
  flows aparece como *integração do produto OZmap* (componente Jira `10886`, ao lado de
  SGP, IXC, Wispro, MK Solutions, SmartOLT).
- **Freshchat — não existe.** Zero ocorrências de `freshchat`/`freshworks`/`freshsales`/
  `freshcaller` nos 4 exports do Node-RED, nenhum host `*.freshchat.com`. O único Fresh\* na
  infra é o Freshdesk. Chat hoje é JetSales, MessageBird e Zenvia (chatbot de cobrança).

## Token do Feedz
Gere em **Configurações → Integrações → Chave de Integração API v2** (admin do Feedz) e cadastre como secret `FEEDZ_API_TOKEN`. Endpoint usado: `GET /v2/integracao/employees` (somente leitura). A remuneração retornada pela API é **ignorada** de propósito. Secrets ficam em Settings → Secrets and variables → Actions; nenhum segredo no código.

# Extração headless de métricas dos clientes (OZmap)

Puxa histórico por cliente (usuários, caixas, projetos, limites) **sem navegador e sem VPN**,
falando com o proxy de datasource do Grafana usando um token de service account.

## Por que funciona

- As métricas de negócio (`hc_*`) ficam num Prometheus **interno** (`http://devoz-prometheus:9090`),
  que não é acessível pela internet.
- Mas o Grafana (`https://monitoz.ozmap.com`) **é público** e reencaminha a query para esse
  Prometheus interno pelo endpoint de proxy:
  `/api/datasources/uid/<uid>/resources/api/v1/query_range`.
- Basta um **token** com permissão de leitura. Qualquer máquina/CI com acesso à internet consegue.

## Métricas disponíveis (datasource `prometheus`, uid `cdx3t7vrk9khse`)

| Métrica | Significado |
|---|---|
| `hc_numUsers` | número de usuários |
| `hc_numOZmobUsers` | usuários do OZmob (mobile) |
| `hc_numBoxes` | número de caixas |
| `hc_numJunctionBoxes` | caixas de emenda |
| `hc_numClients` | clientes finais |
| `hc_numProjects` | projetos |
| `limitUsers` / `limitBoxes` / `limitClients` / `limitProjects` | limites contratados do plano |

Labels em cada série: `host` (nome do cliente) e `userID` (UUID da instância — provável ligação
com o `ozid` do cockpit). Histórico disponível desde ~set/2024.

## 1. Criar o token (você faz isso, uma vez)

O token é uma credencial — crie você mesmo no Grafana, não cole aqui no chat.

1. No Grafana: **Administration → Users and access → Service accounts → Add service account**.
2. Nome: `cockpit-metrics-reader`. Role: **Viewer** (só leitura).
3. Abra a service account criada → **Add service account token** → copie o token (`glsa_...`).
   Guarde num gerenciador de secrets; ele só aparece uma vez.

> Viewer basta para consultar via proxy. Não conceda Editor/Admin.

## 2. Configurar e rodar (local)

```bash
export GRAFANA_URL="https://monitoz.ozmap.com"
export GRAFANA_DS_UID="cdx3t7vrk9khse"
export GRAFANA_TOKEN="glsa_...."        # o token do passo 1

# lista os clientes que têm a métrica
python3 ozmap_metrics.py clients

# histórico de 1 cliente (todas as métricas), 365 dias, passo diário -> CSV
python3 ozmap_metrics.py history --host guarovision --days 365 --out guarovision.csv

# uma métrica, todos os clientes, 90 dias -> CSV  (mais pesado)
python3 ozmap_metrics.py history --metric hc_numUsers --all --days 90 --step 1d --out users_90d.csv

# snapshot atual de todas as métricas / todos os clientes -> CSV
python3 ozmap_metrics.py snapshot --out snapshot.csv
```

Saída CSV (formato longo): `timestamp, datetime, host, userID, metric, value`.
Sem dependências externas — só Python 3.

## Filtrar instâncias que não são clientes (demo/teste/interno)

A base tem ~30 hosts que não são clientes de produção (demo, testes, tickets, clones,
`data-manipulation-*`, instâncias internas da DevOZ). O script detecta isso:

```bash
# lista TODOS os hosts com a categoria detectada -> CSV (host,producao,categoria)
python3 ozmap_metrics.py classify --out hosts_classificados.csv

# snapshot / histórico já excluindo não-produção:
python3 ozmap_metrics.py snapshot --exclude-tests --out snapshot_prod.csv
python3 ozmap_metrics.py history --all --exclude-tests --days 365 --out hist_prod.csv
```

Categorias detectadas: `demo`, `teste`, `homolog`, `clone_backup`, `ticket`, `requestlog`,
`manipulacao`, `interno_devoz`, `uuid_host`. O CSV de snapshot/history ganha a coluna
`categoria` (vazia = produção), então você pode filtrar depois também.

> A heurística é conservadora (por nome do host) para não marcar cliente real como teste.
> Casos de borda (ex.: `academia*`) ficam como produção — a classificação definitiva sai
> cruzando `userID` ↔ `ozid` com o estágio do Zoho CRM (Rodando/Churn).

## 3. Deploy no pipeline (GitHub Actions)

Encaixa no pipeline diário do cockpit:

1. Salve o token como secret do repositório: `GRAFANA_TOKEN`.
2. Passo no workflow:

```yaml
- name: Ingest OZmap health-check metrics
  env:
    GRAFANA_URL: https://monitoz.ozmap.com
    GRAFANA_DS_UID: cdx3t7vrk9khse
    GRAFANA_TOKEN: ${{ secrets.GRAFANA_TOKEN }}
  run: |
    python3 ozmap_metrics.py history --metric hc_numUsers --metric hc_numBoxes \
      --all --days 2 --step 1d --out ozmap_daily.csv
```

Depois é só carregar o CSV no Supabase (`fct_*` ou uma tabela nova de uso do produto) e
cruzar com o faturamento por `host`/`userID` ↔ `ozid`.

## Cuidado com carga (pedido do time)

- Prefira `--host` a `--all` quando puder.
- Use `--step 1d` (ou maior) para históricos longos — evita milhões de pontos.
- Para backfill único e grande, rode fora do horário de pico.
```

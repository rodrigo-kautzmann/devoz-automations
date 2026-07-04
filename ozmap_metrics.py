#!/usr/bin/env python3
"""
Extrai histórico de métricas de clientes do OZmap direto do Grafana, sem navegador.

Fala com o proxy de datasource do Grafana (que alcança o Prometheus interno por baixo),
autenticando com um token de service account. Só precisa de rede pública para
https://monitoz.ozmap.com — nada de VPN.

Uso das credenciais (NUNCA hardcode o token):
    export GRAFANA_URL="https://monitoz.ozmap.com"
    export GRAFANA_TOKEN="glsa_xxx..."          # token de service account (read-only)
    export GRAFANA_DS_UID="cdx3t7vrk9khse"       # datasource 'prometheus' (métricas hc_*)

Exemplos:
    # listar todos os clientes (label host) que têm a métrica
    python3 ozmap_metrics.py clients

    # histórico de 1 cliente, várias métricas, últimos 365 dias, passo diário -> CSV
    python3 ozmap_metrics.py history --host guarovision --days 365 --out guarovision.csv

    # histórico de TODOS os clientes para uma métrica (cuidado: pesado) -> CSV
    python3 ozmap_metrics.py history --metric hc_numUsers --all --days 90 --step 1d --out users_90d.csv

    # snapshot atual (valor mais recente) de todas as métricas, todos os clientes -> CSV
    python3 ozmap_metrics.py snapshot --out snapshot.csv
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

# Métricas de negócio do health check (label host = cliente, userID = instância)
DEFAULT_METRICS = [
    "hc_numUsers",        # usuários
    "hc_numOZmobUsers",   # usuários OZmob (mobile)
    "hc_numBoxes",        # caixas
    "hc_numJunctionBoxes",# caixas de emenda
    "hc_numClients",      # clientes finais
    "hc_numProjects",     # projetos
    "limitUsers",         # limite do plano
    "limitBoxes",
    "limitClients",
    "limitProjects",
]

STEP_SECONDS = {"1m": 60, "5m": 300, "1h": 3600, "6h": 21600, "1d": 86400}

# Padrões que identificam instâncias NÃO-produção (demo, teste, interno DevOZ, etc.).
# Ordem importa: a primeira que casar define a categoria.
import re as _re
NON_PROD_PATTERNS = [
    ("demo",         _re.compile(r"(^|[-_])demo", _re.I)),
    ("teste",        _re.compile(r"(^|[-_])(test|teste)", _re.I)),
    ("homolog",      _re.compile(r"homolog", _re.I)),
    ("clone_backup", _re.compile(r"clone|backup|copia|restaur", _re.I)),
    ("ticket",       _re.compile(r"tkt|ticket", _re.I)),
    ("requestlog",   _re.compile(r"requestlog", _re.I)),
    ("manipulacao",  _re.compile(r"manipulation|manipulacao", _re.I)),
    ("interno_devoz",_re.compile(r"(^|[-_])(oz|devoz)|ozneutral|ozmap|centraozconfig|amidevops|sandbox", _re.I)),
    ("uuid_host",    _re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-", _re.I)),
]


def classify_host(host):
    """Retorna (is_producao, categoria). categoria='' quando é produção."""
    for cat, rx in NON_PROD_PATTERNS:
        if rx.search(host or ""):
            return (False, cat)
    return (True, "")


def env(name, required=True, default=None):
    v = os.environ.get(name, default)
    if v:
        # remove espaços e aspas (retas ou "curvas") que entram ao copiar/colar
        v = v.strip().strip('"\'“”‘’').strip()
    if required and not v:
        sys.exit(f"ERRO: variável de ambiente {name} não definida.")
    return v


def api_get(path, params=None):
    base = env("GRAFANA_URL").rstrip("/")
    uid = env("GRAFANA_DS_UID")
    token = env("GRAFANA_TOKEN")
    url = f"{base}/api/datasources/uid/{uid}/resources{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        sys.exit(f"ERRO HTTP {e.code} em {path}: {body}")
    except Exception as e:
        sys.exit(f"ERRO de rede em {path}: {e}")


def list_clients(metric="hc_numUsers"):
    # valores do label 'host' para a métrica
    data = api_get(f"/api/v1/label/host/values", {"match[]": metric})
    return sorted(data.get("data", []))


def instant(query):
    data = api_get("/api/v1/query", {"query": query})
    return data["data"]["result"]


def range_query(query, start, end, step):
    data = api_get("/api/v1/query_range", {
        "query": query, "start": start, "end": end, "step": step,
    })
    return data["data"]["result"]


def cmd_clients(args):
    clients = list_clients(args.metric)
    print(f"# {len(clients)} clientes com a métrica {args.metric}:", file=sys.stderr)
    for c in clients:
        print(c)


def cmd_snapshot(args):
    rows = []
    for m in args.metrics:
        for s in instant(m):
            met = s["metric"]
            host = met.get("host", "")
            is_prod, cat = classify_host(host)
            if args.exclude_tests and not is_prod:
                continue
            ts, val = s["value"]
            rows.append({
                "timestamp": int(float(ts)),
                "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(float(ts))),
                "host": host,
                "userID": met.get("userID", ""),
                "categoria": cat,
                "metric": m,
                "value": val,
            })
    write_csv(args.out, rows)


def cmd_classify(args):
    """Lista todos os hosts com a categoria detectada (produção vs teste/demo/interno)."""
    hosts = list_clients(args.metric)
    rows = []
    for h in hosts:
        is_prod, cat = classify_host(h)
        rows.append({"host": h, "producao": "sim" if is_prod else "nao", "categoria": cat})
    n_test = sum(1 for r in rows if r["producao"] == "nao")
    print(f"# {len(rows)} hosts | producao={len(rows)-n_test} | nao-producao={n_test}", file=sys.stderr)
    cols = ["host", "producao", "categoria"]
    _write_csv_cols(args.out, rows, cols)


def cmd_history(args):
    step = STEP_SECONDS.get(args.step, None)
    if step is None:
        try:
            step = int(args.step)
        except ValueError:
            sys.exit(f"--step inválido: {args.step} (use 1m/5m/1h/6h/1d ou segundos)")
    end = int(time.time())
    start = end - args.days * 86400

    metrics = args.metrics
    # seletor por host
    if args.all:
        selector = ""  # todas as séries
    elif args.host:
        selector = '{host="%s"}' % args.host
    else:
        sys.exit("Informe --host <cliente> ou --all")

    rows = []
    for m in metrics:
        query = m + selector
        series = range_query(query, start, end, step)
        for s in series:
            met = s["metric"]
            host = met.get("host", "")
            is_prod, cat = classify_host(host)
            if args.exclude_tests and not is_prod:
                continue
            uid = met.get("userID", "")
            for ts, val in s["values"]:
                rows.append({
                    "timestamp": int(float(ts)),
                    "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(float(ts))),
                    "host": host,
                    "userID": uid,
                    "categoria": cat,
                    "metric": m,
                    "value": val,
                })
    write_csv(args.out, rows)


def write_csv(path, rows):
    cols = ["timestamp", "datetime", "host", "userID", "categoria", "metric", "value"]
    _write_csv_cols(path, rows, cols)


def _write_csv_cols(path, rows, cols):
    if not path or path == "-":
        w = csv.DictWriter(sys.stdout, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    else:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"OK: {len(rows)} linhas escritas em {path}", file=sys.stderr)


def build_parser():
    p = argparse.ArgumentParser(description="Extrai métricas do OZmap via Grafana (headless).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("clients", help="lista clientes (label host)")
    pc.add_argument("--metric", default="hc_numUsers")
    pc.set_defaults(func=cmd_clients)

    ps = sub.add_parser("snapshot", help="valor atual de todas as métricas")
    ps.add_argument("--metrics", nargs="+", default=DEFAULT_METRICS)
    ps.add_argument("--exclude-tests", dest="exclude_tests", action="store_true",
                    help="ignora instâncias demo/teste/interno DevOZ")
    ps.add_argument("--out", default="-")
    ps.set_defaults(func=cmd_snapshot)

    pcl = sub.add_parser("classify", help="lista hosts com categoria (produção vs teste/demo/interno)")
    pcl.add_argument("--metric", default="hc_numUsers")
    pcl.add_argument("--out", default="-")
    pcl.set_defaults(func=cmd_classify)

    ph = sub.add_parser("history", help="histórico via query_range")
    ph.add_argument("--host", help="cliente específico (label host)")
    ph.add_argument("--all", action="store_true", help="todos os clientes")
    ph.add_argument("--metric", dest="metrics", action="append",
                    help="métrica (repita para várias); default = todas hc_/limit")
    ph.add_argument("--days", type=int, default=365)
    ph.add_argument("--step", default="1d", help="1m/5m/1h/6h/1d ou segundos")
    ph.add_argument("--exclude-tests", dest="exclude_tests", action="store_true",
                    help="ignora instâncias demo/teste/interno DevOZ")
    ph.add_argument("--out", default="-")
    ph.set_defaults(func=cmd_history)
    return p


def main():
    args = build_parser().parse_args()
    if getattr(args, "cmd", None) == "history" and not args.metrics:
        args.metrics = DEFAULT_METRICS
    args.func(args)


if __name__ == "__main__":
    main()

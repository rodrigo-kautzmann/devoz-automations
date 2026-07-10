#!/usr/bin/env python3
"""
Auditoria de amarração de clientes entre sistemas — DevOZ.

Cruza, pela chave canônica `ozid` (UUID), quatro fontes:
  1. FINANCEIRO  (Supabase / cockpit)  -> fonte da verdade ("quem fatura")
  2. CRM         (Zoho, deals c/ ozid)
  3. MONITORAMENTO (Prometheus via proxy do Grafana; label userID = ozid)
  4. TOTANGO     (API Search v2)  -> módulo configurável (ver TOTANGO_* / --probe)

Detecta:
  - GAPS DE PRESENÇA: fatura mas falta em CRM/Totango/monitoramento (e o reverso).
  - IDs DIVERGENTES: host(monitor) != domain(CRM) p/ o mesmo ozid; ozid malformado;
    conta Totango sem ozid correspondente.

Saída: CSVs por categoria + resumo (markdown) em OUT_DIR. Se houver inconsistências
e SMTP_* estiver configurado, dispara e-mail com o resumo.

Roda no GitHub Actions (tem rede pro Supabase). NUNCA hardcode segredo — tudo via env.

Variáveis de ambiente
  Financeiro (Postgres/Supabase):  PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE  (SSL require)
  Zoho:      ZOHO_CLIENT_ID ZOHO_CLIENT_SECRET ZOHO_REFRESH_TOKEN
             [ZOHO_ACCOUNTS_URL=https://accounts.zoho.com] [ZOHO_API_URL=https://www.zohoapis.com]
  Grafana:   GRAFANA_URL GRAFANA_TOKEN GRAFANA_DS_UID
  Totango:   TOTANGO_APP_TOKEN [TOTANGO_BASE=https://api.totango.com]
             [TOTANGO_ID_FIELD=account_id]  (campo do Totango que guarda o ozid; ou 'domain')
  E-mail:    SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASSWORD ALERT_FROM ALERT_TO
  Ajustes:   AUDIT_LOOKBACK_MONTHS=3   OUT_DIR=audit_out

Uso:
  python3 scripts/audit_amarracao.py            # roda auditoria completa
  python3 scripts/audit_amarracao.py --probe-totango   # só dumpa amostra do Totango
  python3 scripts/audit_amarracao.py --no-email        # não envia e-mail
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# reaproveita a classificação de host (produção vs teste/demo/interno) do ozmap_metrics.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from ozmap_metrics import classify_host
except Exception:
    def classify_host(h):
        return (True, "")


def env(name, default=None, required=False):
    v = os.environ.get(name, default)
    if isinstance(v, str):
        v = v.strip().strip('"\'“”‘’').strip()
    if required and not v:
        sys.exit(f"ERRO: variável de ambiente obrigatória ausente: {name}")
    return v


def _http_json(url, data=None, headers=None, method=None, timeout=60):
    body = None
    if data is not None:
        body = json.dumps(data).encode() if not isinstance(data, (bytes, str)) else (
            data.encode() if isinstance(data, str) else data)
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ----------------------------------------------------------------------------
# 1. FINANCEIRO (fonte da verdade) — Supabase / Postgres
# ----------------------------------------------------------------------------
FINANCEIRO_SQL = """
SELECT d.ozid,
       max(f.cliente_nome)               AS nome,
       max(f.pais)                       AS pais,
       f.empresa_id                      AS empresa_id,
       max(f.mes_competencia)            AS ultima_competencia
FROM core.fct_faturamento f
JOIN core.dim_cliente_ozid d
  ON d.empresa_id = f.empresa_id
 AND d.id_cliente_ext = f.id_cliente_ext
WHERE f.tratamento = 'receita'
  AND f.mes_competencia >= (date_trunc('month', now()) - make_interval(months => %(lookback)s))
GROUP BY d.ozid, f.empresa_id
"""


def get_financeiro(lookback_months):
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        sys.exit("ERRO: psycopg2 não instalado (pip install psycopg2-binary).")
    conn = psycopg2.connect(
        host=env("PGHOST", required=True), port=env("PGPORT", "5432"),
        user=env("PGUSER", required=True), password=env("PGPASSWORD", required=True),
        dbname=env("PGDATABASE", "postgres"), sslmode="require",
    )
    out = {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(FINANCEIRO_SQL, {"lookback": lookback_months})
        for r in cur.fetchall():
            oz = (r["ozid"] or "").strip().lower()
            if not oz:
                continue
            out[oz] = {
                "nome": r["nome"], "pais": r["pais"],
                "empresa": "LLC/US" if r["empresa_id"] == 1 else "LTDA/BR",
                "ultima_competencia": str(r["ultima_competencia"]),
            }
    conn.close()
    return out


# ----------------------------------------------------------------------------
# 2. CRM — Zoho (deals com ozid)
# ----------------------------------------------------------------------------
def _zoho_access_token():
    accounts = env("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.com")
    data = urllib.parse.urlencode({
        "refresh_token": env("ZOHO_REFRESH_TOKEN", required=True),
        "client_id": env("ZOHO_CLIENT_ID", required=True),
        "client_secret": env("ZOHO_CLIENT_SECRET", required=True),
        "grant_type": "refresh_token",
    }).encode()
    resp = _http_json(f"{accounts}/oauth/v2/token", data=data,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    if "access_token" not in resp:
        sys.exit(f"ERRO Zoho OAuth: {resp}")
    return resp["access_token"]


def get_crm():
    api = env("ZOHO_API_URL", "https://www.zohoapis.com")
    token = _zoho_access_token()
    hdr = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}
    out = {}
    offset, page = 0, 200
    while True:
        q = (f"select ozid, Stage, Deal_Name, domain, Pipeline from Deals "
             f"where ozid is not null limit {offset},{page}")
        resp = _http_json(f"{api}/crm/v7/coql", data={"select_query": q}, headers=hdr)
        rows = (resp or {}).get("data", [])
        for r in rows:
            oz = (r.get("ozid") or "").strip().lower()
            if not oz:
                continue
            stage = (r.get("Stage") or "").strip()
            pipe = (r.get("Pipeline") or "").strip()
            sl, is_ozn = stage.lower(), pipe.lower() == "ozneutral"
            # Regra pipeline-aware: no OZneutral, "Fechado Ganho" = rodando e
            # "Fechado perdido" = churn. Nos demais (OZmap/Projetos): Rodando/Churn.
            is_active = sl == "rodando" or (is_ozn and sl == "fechado ganho")
            is_churn = sl == "churn" or (is_ozn and sl == "fechado perdido")
            out[oz] = {
                "deal_name": r.get("Deal_Name"), "domain": (r.get("domain") or "").strip(),
                "pipeline": pipe, "stage": stage, "is_active": is_active, "is_churn": is_churn,
            }
        if not (resp or {}).get("info", {}).get("more_records"):
            break
        offset += page
        time.sleep(0.3)
    return out


# ----------------------------------------------------------------------------
# 3. MONITORAMENTO — Prometheus via proxy do Grafana (label userID = ozid)
# ----------------------------------------------------------------------------
def get_monitoramento():
    base = env("GRAFANA_URL", required=True).rstrip("/")
    uid = env("GRAFANA_DS_UID", required=True)
    token = env("GRAFANA_TOKEN", required=True)
    url = (f"{base}/api/datasources/uid/{uid}/resources/api/v1/query"
           f"?query={urllib.parse.quote('hc_numUsers')}")
    resp = _http_json(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    out = {}
    for s in resp.get("data", {}).get("result", []):
        m = s.get("metric", {})
        oz = (m.get("userID") or "").strip().lower()
        host = m.get("host", "")
        if not oz:
            continue
        is_prod, _cat = classify_host(host)
        if not is_prod:
            continue  # ignora demo/teste/interno DevOZ
        out[oz] = {"host": host}
    return out


# ----------------------------------------------------------------------------
# 4. TOTANGO — API Search v2 (módulo configurável)
# ----------------------------------------------------------------------------
def _totango_fetch_accounts():
    base = env("TOTANGO_BASE", "https://api.totango.com").rstrip("/")
    token = env("TOTANGO_APP_TOKEN", required=True)
    # Search API: paginação por offset; retorna display_name + campos.
    accounts, offset, page = [], 0, 1000
    while True:
        query = {"terms": [], "count": page, "offset": offset,
                 "fields": [{"type": "string_attribute", "attribute": "domain", "field_display_name": "domain"}],
                 "scope": "all"}
        data = urllib.parse.urlencode({"query": json.dumps(query)}).encode()
        resp = _http_json(f"{base}/api/v2/search/accounts", data=data,
                          headers={"app-token": token,
                                   "Content-Type": "application/x-www-form-urlencoded"})
        hits = (((resp or {}).get("response") or {}).get("accounts") or {}).get("hits", [])
        if not hits:
            break
        accounts.extend(hits)
        if len(hits) < page:
            break
        offset += page
    return accounts


def get_totango():
    """Retorna dict ozid_ou_domain -> {name, raw_id}. O campo identificador é
    configurável via TOTANGO_ID_FIELD (default 'account_id'). Em Totango, o id da
    conta costuma vir em hit['name']; atributos extras em hit['display_fields']."""
    id_field = env("TOTANGO_ID_FIELD", "account_id")
    out = {}
    for h in _totango_fetch_accounts():
        raw_id = h.get("name")  # account_id do Totango
        disp = h.get("display_name") or raw_id
        df = h.get("display_fields", {}) or {}
        # chave de match: tenta o campo configurado, senão o próprio account_id, senão domain
        key = df.get(id_field) or raw_id or df.get("domain")
        if not key:
            continue
        out[str(key).strip().lower()] = {"name": disp, "raw_id": raw_id,
                                         "domain": (df.get("domain") or "").strip().lower()}
    return out


def probe_totango():
    accts = _totango_fetch_accounts()
    print(f"# Totango: {len(accts)} contas. Amostra (pra confirmar qual campo é o ozid):")
    for h in accts[:8]:
        print(json.dumps({"name": h.get("name"), "display_name": h.get("display_name"),
                          "display_fields": h.get("display_fields")}, ensure_ascii=False))


# ----------------------------------------------------------------------------
# Reconciliação
# ----------------------------------------------------------------------------
def reconcile(fin, crm, mon, tot):
    gaps, diverg = [], []
    all_ozids = set(fin) | set(crm) | set(mon) | set(tot)

    for oz in sorted(all_ozids):
        f, c, m = fin.get(oz), crm.get(oz), mon.get(oz)
        nome = (f or {}).get("nome") or (c or {}).get("deal_name") or (m or {}).get("host") or ""

        # só reporta ozid malformado quando o registro importa (fatura ou está ativo no CRM);
        # evita o ruído de deals legados/perdidos com slug no campo ozid.
        if not UUID_RE.match(oz) and (f or (c and c["is_active"])):
            diverg.append({"ozid": oz, "cliente": nome, "tipo": "ozid_malformado",
                           "detalhe": f"ozid fora do padrão UUID (stage={(c or {}).get('stage','-')})"})

        if f:  # fonte da verdade: fatura
            if not c:
                gaps.append({"ozid": oz, "cliente": nome, "gap": "fatura_sem_CRM",
                             "detalhe": f"{f['empresa']} / {f['pais']}"})
            elif not c["is_active"]:
                gaps.append({"ozid": oz, "cliente": nome, "gap": "fatura_CRM_nao_rodando",
                             "detalhe": f"stage={c['stage']}"})
            if not m:
                gaps.append({"ozid": oz, "cliente": nome, "gap": "fatura_sem_monitoramento",
                             "detalhe": f"{f['empresa']}"})
            if tot and oz not in tot and (c or {}).get("domain", "") not in tot:
                gaps.append({"ozid": oz, "cliente": nome, "gap": "fatura_sem_Totango",
                             "detalhe": ""})
        else:  # não fatura, mas aparece em algum sistema
            if c and c["is_active"]:
                gaps.append({"ozid": oz, "cliente": nome, "gap": "CRM_rodando_sem_faturar",
                             "detalhe": "ativo no CRM mas sem faturamento recente"})
            if m and not (c and c["is_churn"]):
                gaps.append({"ozid": oz, "cliente": nome, "gap": "monitorado_sem_faturar",
                             "detalhe": f"host={m['host']}"})

        # divergência host x domain
        if c and m and c["domain"] and m["host"] and c["domain"] != m["host"]:
            diverg.append({"ozid": oz, "cliente": nome, "tipo": "host_x_domain",
                           "detalhe": f"CRM.domain={c['domain']} != monitor.host={m['host']}"})

    # contas Totango sem ozid correspondente
    for key, t in (tot or {}).items():
        if key not in fin and key not in crm and key not in mon:
            diverg.append({"ozid": key, "cliente": t["name"], "tipo": "totango_sem_amarracao",
                           "detalhe": "conta no Totango não bate com ozid/domain de nenhum sistema"})

    return gaps, diverg


def write_report(out_dir, fin, crm, mon, tot, gaps, diverg, sources_ok):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "gaps.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ozid", "cliente", "gap", "detalhe"])
        w.writeheader(); w.writerows(gaps)
    with open(os.path.join(out_dir, "divergencias.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ozid", "cliente", "tipo", "detalhe"])
        w.writeheader(); w.writerows(diverg)

    import collections
    g = collections.Counter(x["gap"] for x in gaps)
    d = collections.Counter(x["tipo"] for x in diverg)
    lines = [f"# Auditoria de amarração — {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", ""]
    lines.append(f"Fontes lidas: financeiro={len(fin)} | CRM={len(crm)} | "
                 f"monitoramento={len(mon)} | Totango={len(tot)}")
    falhas = [s for s, ok in sources_ok.items() if not ok]
    if falhas:
        lines.append(f"⚠️ Fontes que FALHARAM (ignoradas): {', '.join(falhas)}")
    lines += ["", f"## Gaps de presença ({len(gaps)})"]
    lines += [f"- {k}: {v}" for k, v in g.most_common()] or ["- nenhum"]
    lines += ["", f"## IDs divergentes ({len(diverg)})"]
    lines += [f"- {k}: {v}" for k, v in d.most_common()] or ["- nenhum"]
    summary = "\n".join(lines)
    with open(os.path.join(out_dir, "resumo.md"), "w", encoding="utf-8") as f:
        f.write(summary + "\n")
    return summary


def send_email(summary, out_dir):
    host = env("SMTP_HOST"); to = env("ALERT_TO")
    if not host or not to:
        print("(e-mail não enviado: SMTP_HOST/ALERT_TO ausentes)", file=sys.stderr)
        return
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    msg = MIMEMultipart()
    msg["Subject"] = "[DevOZ] Auditoria de amarração — inconsistências encontradas"
    msg["From"] = env("ALERT_FROM", env("SMTP_USER"))
    msg["To"] = to
    msg.attach(MIMEText(summary, "plain", "utf-8"))
    for fn in ("gaps.csv", "divergencias.csv"):
        p = os.path.join(out_dir, fn)
        if os.path.exists(p):
            from email.mime.base import MIMEBase
            from email import encoders
            part = MIMEBase("text", "csv")
            part.set_payload(open(p, "rb").read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={fn}")
            msg.attach(part)
    port = int(env("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port) as s:
        s.starttls()
        if env("SMTP_USER"):
            s.login(env("SMTP_USER"), env("SMTP_PASSWORD", required=True))
        s.send_message(msg)
    print(f"E-mail enviado para {to}", file=sys.stderr)


def safe(fn, name, sources_ok):
    try:
        r = fn()
        sources_ok[name] = True
        print(f"  {name}: OK ({len(r)} registros)", file=sys.stderr)
        return r
    except SystemExit:
        raise
    except Exception as e:
        sources_ok[name] = False
        print(f"  {name}: FALHOU -> {e}", file=sys.stderr)
        return {}


def main():
    ap = argparse.ArgumentParser(description="Auditoria de amarração de clientes DevOZ.")
    ap.add_argument("--probe-totango", action="store_true", help="só dumpa amostra do Totango")
    ap.add_argument("--no-email", action="store_true", help="não envia e-mail")
    ap.add_argument("--out", default=env("OUT_DIR", "audit_out"))
    args = ap.parse_args()

    if args.probe_totango:
        probe_totango()
        return

    lookback = int(env("AUDIT_LOOKBACK_MONTHS", "3"))
    sources_ok = {}
    print("Lendo fontes...", file=sys.stderr)
    fin = safe(lambda: get_financeiro(lookback), "financeiro", sources_ok)
    crm = safe(get_crm, "CRM", sources_ok)
    mon = safe(get_monitoramento, "monitoramento", sources_ok)
    tot = safe(get_totango, "Totango", sources_ok) if env("TOTANGO_APP_TOKEN") else {}

    if not sources_ok.get("financeiro"):
        sys.exit("ERRO: financeiro (fonte da verdade) falhou — abortando auditoria.")

    gaps, diverg = reconcile(fin, crm, mon, tot)
    summary = write_report(args.out, fin, crm, mon, tot, gaps, diverg, sources_ok)
    print("\n" + summary)

    if (gaps or diverg) and not args.no_email:
        send_email(summary, args.out)


if __name__ == "__main__":
    main()

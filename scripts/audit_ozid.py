#!/usr/bin/env python3
"""
Auditoria de ozid — consistência da chave canônica entre os sistemas da DevOZ.

Cruza, pela chave canônica `ozid` (UUID), quatro fontes:
  1. FINANCEIRO  (Supabase / cockpit)  -> fonte da verdade ("quem fatura")
  2. CRM         (Zoho, deals c/ ozid)
  3. TOTANGO     (Search API v1; ozid no atributo "Identifier" — ver TOTANGO_* / --probe)

FORA DE ESCOPO por decisão (2026-08-24): Manager/OZmachine e Monitoramento (Prometheus via
Grafana). Ambos só respondem dentro da rede — exigiriam VPN, que o GitHub Actions não tem.
Consequência aceita: a fonte da verdade continua sendo o FINANCEIRO ("quem fatura"), não o
Manager ("quem existe"), e a auditoria não verifica mais se o cliente está de pé.

Detecta:
  - GAPS DE PRESENÇA: fatura mas falta em CRM/Totango (e o reverso).
  - IDs DIVERGENTES: ozid malformado; conta Totango sem ozid correspondente.

Saída: CSVs por categoria + resumo (markdown) em OUT_DIR. Se houver inconsistências
e SMTP_* estiver configurado, dispara e-mail com o resumo.

Roda no GitHub Actions (tem rede pro Supabase). NUNCA hardcode segredo — tudo via env.

Variáveis de ambiente
  Financeiro (Postgres/Supabase):  PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE  (SSL require)
  Zoho:      ZOHO_CLIENT_ID ZOHO_CLIENT_SECRET ZOHO_REFRESH_TOKEN
             [ZOHO_ACCOUNTS_URL=https://accounts.zoho.com] [ZOHO_API_URL=https://www.zohoapis.com]
  Totango:   TOTANGO_APP_TOKEN  (token da Search API, formato "{v2}<uuid>" — NÃO o token
                                 do int-hub usado para escrita) [TOTANGO_BASE=https://api.totango.com]
             [TOTANGO_ID_FIELD=identifier]  (alias do campo que guarda o ozid;
                                 opções: identifier | identificador | company_domain)
  E-mail:    SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASSWORD ALERT_FROM ALERT_TO
  Ajustes:   AUDIT_LOOKBACK_MONTHS=3   OUT_DIR=audit_out

Uso:
  python3 scripts/audit_ozid.py            # roda auditoria completa
  python3 scripts/audit_ozid.py --probe-totango   # só dumpa amostra do Totango
  python3 scripts/audit_ozid.py --no-email        # não envia e-mail
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
# 3. TOTANGO — Search API v1
# ----------------------------------------------------------------------------
# Onde vive o ozid no Totango (confirmado contra a API + subflow "Totango | createAccount"):
#   - atributo string "Identifier"    = ozid   <- chave canônica
#   - atributo string "Identificador" = ozid   (duplicata legada, mesmo valor)
#   - account id (hits[].name)        = ozid SÓ nas contas novas; nas legadas é slug
#                                      ("wayiranet", "giganet"), então NÃO serve de chave
#   - atributo "Company Domain"       = URL completa (https://<slug>.ozmap.com.br),
#                                      enquanto CRM.domain é só o slug -> normalizar
# A Search API é /api/v1/ (v2 não existe: 404) e devolve os campos pedidos
# posicionalmente em hits[].selected_fields, na ordem de "fields" — NÃO em display_fields.
TOTANGO_FIELDS = [
    ("Identifier", "identifier"),
    ("Identificador", "identificador"),
    ("Company Domain", "company_domain"),
    ("Status", "status"),
]


def _totango_norm_domain(v):
    """'https://silcomnet.ozmap.com.br/' -> 'silcomnet' (formato do CRM.domain)."""
    if not v:
        return ""
    v = str(v).strip().lower().rstrip("/")
    v = re.sub(r"^https?://", "", v)
    return v.split(".")[0]


def _totango_fetch_accounts():
    base = env("TOTANGO_BASE", "https://api.totango.com").rstrip("/")
    token = env("TOTANGO_APP_TOKEN", required=True)
    accounts, offset, page = [], 0, 1000
    while True:
        query = {"terms": [], "count": page, "offset": offset, "scope": "all",
                 "fields": [{"type": "string_attribute", "attribute": a,
                             "field_display_name": d} for a, d in TOTANGO_FIELDS]}
        data = urllib.parse.urlencode({"query": json.dumps(query)}).encode()
        resp = _http_json(f"{base}/api/v1/search/accounts", data=data,
                          headers={"app-token": token,
                                   "Content-Type": "application/x-www-form-urlencoded"})
        block = (((resp or {}).get("response") or {}).get("accounts") or {})
        hits = block.get("hits", [])
        total = block.get("total_hits", 0)
        for h in hits:
            sel = h.get("selected_fields") or []
            rec = {"raw_id": h.get("name"),
                   "display_name": h.get("display_name") or h.get("name")}
            for i, (_attr, alias) in enumerate(TOTANGO_FIELDS):
                rec[alias] = sel[i] if i < len(sel) else None
            accounts.append(rec)
        offset += len(hits)
        if not hits or offset >= total:
            break
    return accounts


def get_totango():
    """Retorna dict chave -> {name, raw_id, domain}, onde a chave é o ozid.

    Ordem de preferência da chave (TOTANGO_ID_FIELD sobrescreve a primeira):
      1. atributo "Identifier"        (o ozid de verdade)
      2. atributo "Identificador"     (duplicata legada)
      3. account id, se for UUID      (contas novas: id == ozid)
      4. domain normalizado           (último recurso, casa com CRM.domain)
    """
    id_field = (env("TOTANGO_ID_FIELD", "identifier") or "identifier").strip().lower()
    out = {}
    for r in _totango_fetch_accounts():
        raw_id = (r.get("raw_id") or "").strip()
        cand = [r.get(id_field), r.get("identifier"), r.get("identificador")]
        key = next((str(c).strip() for c in cand if c and str(c).strip()), "")
        if not key and UUID_RE.match(raw_id):
            key = raw_id
        dom = _totango_norm_domain(r.get("company_domain"))
        if not key:
            key = dom
        if not key:
            continue
        out[key.lower()] = {"name": r.get("display_name") or raw_id,
                            "raw_id": raw_id, "domain": dom,
                            "status": (r.get("status") or "")}
    return out


def probe_totango():
    accts = _totango_fetch_accounts()
    ident = sum(1 for a in accts if a.get("identifier"))
    id_uuid = sum(1 for a in accts if UUID_RE.match((a.get("raw_id") or "")))
    print(f"# Totango: {len(accts)} contas | com atributo Identifier: {ident} "
          f"| account id em formato UUID: {id_uuid}")
    print("# (Identifier é a chave; account id só é ozid nas contas novas.)")
    for a in accts[:8]:
        print(json.dumps(a, ensure_ascii=False))


# ----------------------------------------------------------------------------
# Reconciliação
# ----------------------------------------------------------------------------
def reconcile(fin, crm, tot):
    gaps, diverg = [], []
    all_ozids = set(fin) | set(crm) | set(tot)

    for oz in sorted(all_ozids):
        f, c = fin.get(oz), crm.get(oz)
        nome = (f or {}).get("nome") or (c or {}).get("deal_name") or ""

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
            if tot and oz not in tot and (c or {}).get("domain", "") not in tot:
                gaps.append({"ozid": oz, "cliente": nome, "gap": "fatura_sem_Totango",
                             "detalhe": ""})
        else:  # não fatura, mas aparece em algum sistema
            if c and c["is_active"]:
                gaps.append({"ozid": oz, "cliente": nome, "gap": "CRM_rodando_sem_faturar",
                             "detalhe": "ativo no CRM mas sem faturamento recente"})

    # contas Totango sem ozid correspondente
    for key, t in (tot or {}).items():
        if key not in fin and key not in crm:
            diverg.append({"ozid": key, "cliente": t["name"], "tipo": "totango_sem_ozid",
                           "detalhe": "conta no Totango não bate com ozid/domain de nenhum sistema"})

    return gaps, diverg


def write_report(out_dir, fin, crm, tot, gaps, diverg, sources_ok):
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
    lines = [f"# Auditoria de ozid — {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", ""]
    lines.append(f"Fontes lidas: financeiro={len(fin)} | CRM={len(crm)} | "
                 f"Totango={len(tot)}")
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
    msg["Subject"] = "[DevOZ] Auditoria de ozid — inconsistências encontradas"
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
    ap = argparse.ArgumentParser(description="Auditoria de ozid: consistência da chave canônica entre os sistemas da DevOZ.")
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
    if env("TOTANGO_APP_TOKEN"):
        tot = safe(get_totango, "Totango", sources_ok)
    else:
        tot = {}
        sources_ok["Totango"] = False
        print("  Totango: FALHOU -> TOTANGO_APP_TOKEN ausente", file=sys.stderr)

    if not sources_ok.get("financeiro"):
        sys.exit("ERRO: financeiro (fonte da verdade) falhou — abortando auditoria.")

    gaps, diverg = reconcile(fin, crm, tot)
    summary = write_report(args.out, fin, crm, tot, gaps, diverg, sources_ok)
    print("\n" + summary)

    if (gaps or diverg) and not args.no_email:
        send_email(summary, args.out)


if __name__ == "__main__":
    main()

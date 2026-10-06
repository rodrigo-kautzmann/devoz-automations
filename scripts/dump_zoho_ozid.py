#!/usr/bin/env python3
"""Dump de todos os Deals com ozid para CSV — insumo do cruzamento entre sistemas.

Uso (na pasta do repo, com as mesmas env do audit_ozid.py):
    export ZOHO_CLIENT_ID=...  ZOHO_CLIENT_SECRET=...  ZOHO_REFRESH_TOKEN=...
    python3 scripts/dump_zoho_ozid.py

Gera: audit_out/zoho_deals_ozid.csv  (ozid, deal_id, deal_name, stage, domain, pipeline)
Somente leitura. Nenhum segredo é gravado no arquivo.
"""
import csv, json, os, sys, urllib.parse, urllib.request

ACCOUNTS = os.environ.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.com").rstrip("/")
API = os.environ.get("ZOHO_API_URL", "https://www.zohoapis.com").rstrip("/")
OUT = os.path.join("audit_out", "zoho_deals_ozid.csv")


def env(name):
    v = (os.environ.get(name) or "").strip().strip('"\'')
    if not v:
        sys.exit(f"ERRO: variável de ambiente obrigatória ausente: {name}")
    return v


def token():
    data = urllib.parse.urlencode({
        "refresh_token": env("ZOHO_REFRESH_TOKEN"),
        "client_id": env("ZOHO_CLIENT_ID"),
        "client_secret": env("ZOHO_CLIENT_SECRET"),
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(f"{ACCOUNTS}/oauth/v2/token", data=data)
    with urllib.request.urlopen(req, timeout=60) as r:
        t = json.load(r).get("access_token")
    if not t:
        sys.exit("ERRO: não veio access_token — confira o refresh token e o data center.")
    return t


def coql(tok, q):
    req = urllib.request.Request(
        f"{API}/crm/v2/coql",
        data=json.dumps({"select_query": q}).encode(),
        headers={"Authorization": f"Zoho-oauthtoken {tok}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 204:          # sem mais registros
            return {"data": []}
        sys.exit(f"ERRO HTTP {e.code}: {e.read()[:300].decode('utf-8','ignore')}")


def main():
    tok = token()
    rows, last = [], "0"
    # paginação por keyset: mais barata e estável que offset em base grande
    while True:
        q = ("select id, ozid, Deal_Name, Stage, domain, Pipeline from Deals "
             f"where ozid is not null and id > {last} order by id limit 200")
        d = coql(tok, q).get("data") or []
        if not d:
            break
        for x in d:
            rows.append({
                "ozid": x.get("ozid") or "",
                "deal_id": x.get("id") or "",
                "deal_name": x.get("Deal_Name") or "",
                "stage": x.get("Stage") or "",
                "domain": x.get("domain") or "",
                "pipeline": (x.get("Pipeline") or {}).get("name")
                            if isinstance(x.get("Pipeline"), dict) else (x.get("Pipeline") or ""),
            })
        last = d[-1]["id"]
        print(f"  ... {len(rows)} deals", file=sys.stderr)

    os.makedirs("audit_out", exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ozid", "deal_id", "deal_name",
                                          "stage", "domain", "pipeline"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nOK: {len(rows)} deals com ozid -> {OUT}")


if __name__ == "__main__":
    main()

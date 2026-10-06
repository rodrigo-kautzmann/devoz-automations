#!/usr/bin/env python3
"""Dump das fontes que só o seu terminal alcança — insumo do cruzamento do ozid.

Roda os dumps que faltam (Zoho e Xero) usando as env que você já tem exportadas.
Somente leitura. Nenhum segredo é gravado nos CSVs.

Monitoramento e Manager NÃO entram: só respondem dentro da rede (VPN), e a auditoria
roda no GitHub Actions. Decisão de 2026-08-24.

    cd ~/Claude/Projects/iafirstitizacao\\ devoz/devoz-automations
    python3 scripts/dump_fontes.py                 # roda os dois
    python3 scripts/dump_fontes.py zoho            # só um

Saída em audit_out/:  zoho_deals_ozid.csv | xero_contacts_ozid.csv

Cada fonte é independente: se uma falhar, as outras seguem e o erro aparece no fim.
"""
import base64, csv, json, os, sys, urllib.error, urllib.parse, urllib.request

OUTDIR = "audit_out"


def env(name, default=None, required=False):
    v = (os.environ.get(name) or default or "").strip().strip('"\'')
    if required and not v:
        raise RuntimeError(f"variável de ambiente ausente: {name}")
    return v


def grava(nome, campos, rows):
    os.makedirs(OUTDIR, exist_ok=True)
    p = os.path.join(OUTDIR, nome)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(rows)
    return p


# ------------------------------------------------------------------ ZOHO
def zoho():
    acc = env("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.com").rstrip("/")
    api = env("ZOHO_API_URL", "https://www.zohoapis.com").rstrip("/")
    data = urllib.parse.urlencode({
        "refresh_token": env("ZOHO_REFRESH_TOKEN", required=True),
        "client_id": env("ZOHO_CLIENT_ID", required=True),
        "client_secret": env("ZOHO_CLIENT_SECRET", required=True),
        "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen(
            urllib.request.Request(f"{acc}/oauth/v2/token", data=data), timeout=60) as r:
        tok = json.load(r).get("access_token")
    if not tok:
        raise RuntimeError("Zoho não devolveu access_token (confira o data center)")

    rows, last = [], "0"
    while True:
        q = ("select id, ozid, Deal_Name, Stage, domain from Deals "
             f"where ozid is not null and id > {last} order by id limit 200")
        req = urllib.request.Request(f"{api}/crm/v2/coql",
                                     data=json.dumps({"select_query": q}).encode(),
                                     headers={"Authorization": f"Zoho-oauthtoken {tok}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                # ATENÇÃO: o Zoho encerra a paginação com 204 + corpo VAZIO.
                # 204 é 2xx, então NÃO vira HTTPError — cai aqui com body em branco.
                body = r.read()
                if r.status == 204 or not body.strip():
                    break
                d = json.loads(body).get("data") or []
        except urllib.error.HTTPError as e:
            if e.code == 204:
                break
            raise
        if not d:
            break
        for x in d:
            rows.append({"ozid": x.get("ozid") or "", "deal_id": x.get("id") or "",
                         "deal_name": x.get("Deal_Name") or "", "stage": x.get("Stage") or "",
                         "domain": x.get("domain") or ""})
        last = d[-1]["id"]
        print(f"  zoho ... {len(rows)}", file=sys.stderr)
    return grava("zoho_deals_ozid.csv",
                 ["ozid", "deal_id", "deal_name", "stage", "domain"], rows), len(rows)


# ------------------------------------------------------------------ XERO
def xero():
    basic = base64.b64encode(
        f"{env('XERO_CLIENT_ID', required=True)}:{env('XERO_CLIENT_SECRET', required=True)}"
        .encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "refresh_token",
                                   "refresh_token": env("XERO_REFRESH_TOKEN", required=True)}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://identity.xero.com/connect/token", data=data,
                headers={"Authorization": f"Basic {basic}",
                         "Content-Type": "application/x-www-form-urlencoded"}), timeout=60) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        det = e.read()[:300].decode("utf-8", "ignore")
        if "invalid_grant" in det:
            raise RuntimeError(
                "refresh token do Xero inválido/já usado. O token do Xero é de USO ÚNICO e "
                "rotaciona a cada refresh — se o pipeline do cockpit rodou depois de você "
                "exportar a env, a sua cópia morreu. Refaça o consent (xero_auth.py) e "
                "reexporte XERO_REFRESH_TOKEN.") from None
        raise RuntimeError(f"HTTP {e.code} no token do Xero: {det}") from None
    if not body.get("access_token"):
        raise RuntimeError("Xero não devolveu access_token")
    novo = body.get("refresh_token")
    if novo:
        with open(".xero_refresh_token.novo", "w") as f:
            f.write(novo)

    H = {"Authorization": f"Bearer {body['access_token']}",
         "Xero-tenant-id": env("XERO_TENANT_ID", required=True),
         "Accept": "application/json"}
    rows, page = [], 1
    while True:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://api.xero.com/api.xro/2.0/Contacts?page={page}&includeArchived=true",
                headers=H), timeout=120) as r:
            batch = json.load(r).get("Contacts") or []
        if not batch:
            break
        for c in batch:
            rows.append({"ozid": (c.get("AccountNumber") or "").strip(),
                         "contact_id": c.get("ContactID") or "",
                         "nome": c.get("Name") or "",
                         "status": c.get("ContactStatus") or ""})
        print(f"  xero ... {len(rows)}", file=sys.stderr)
        if len(batch) < 100:
            break
        page += 1
        if page > 60:
            break
    return grava("xero_contacts_ozid.csv",
                 ["ozid", "contact_id", "nome", "status"], rows), len(rows)


FONTES = {"zoho": zoho, "xero": xero}

if __name__ == "__main__":
    alvo = [a.lower() for a in sys.argv[1:]] or list(FONTES)
    ok, erro = [], []
    for nome in alvo:
        if nome not in FONTES:
            erro.append((nome, "fonte desconhecida"))
            continue
        try:
            p, n = FONTES[nome]()
            ok.append((nome, p, n))
        except Exception as e:
            erro.append((nome, f"{type(e).__name__}: {e}"))
    print()
    for nome, p, n in ok:
        print(f"OK   {nome:8s} {n:6d} registros -> {p}")
    for nome, msg in erro:
        print(f"FALHA {nome:8s} {msg}")
    if os.path.exists(".xero_refresh_token.novo"):
        print("\nAVISO: o refresh token do Xero rotacionou. O novo está em "
              ".xero_refresh_token.novo — atualize a env, senão a próxima execução falha.")

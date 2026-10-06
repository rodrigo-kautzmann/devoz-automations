#!/usr/bin/env python3
"""Dump dos contatos do Xero com o ozid (AccountNumber) — insumo do cruzamento.

Este é o pedaço que hoje falta no cruzamento: a base faturada em USD (LLC/LatAm).
Sem ele não se distingue "cliente faturado fora do BR" de "cliente não faturado".

Uso (com as mesmas env do xero_ingest.py do cockpit):
    export XERO_CLIENT_ID=... XERO_CLIENT_SECRET=... XERO_REFRESH_TOKEN=... XERO_TENANT_ID=...
    python3 dump_xero_ozid.py

Gera: audit_out/xero_contacts_ozid.csv  (ozid, contact_id, nome, status)
Somente leitura (escopo accounting.contacts.read).
"""
import base64, csv, json, os, sys, urllib.parse, urllib.request

OUT = os.path.join("audit_out", "xero_contacts_ozid.csv")


def env(name):
    v = (os.environ.get(name) or "").strip().strip('"\'')
    if not v:
        sys.exit(f"ERRO: variável de ambiente obrigatória ausente: {name}")
    return v


def token():
    basic = base64.b64encode(
        f"{env('XERO_CLIENT_ID')}:{env('XERO_CLIENT_SECRET')}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "refresh_token",
                                   "refresh_token": env("XERO_REFRESH_TOKEN")}).encode()
    req = urllib.request.Request("https://identity.xero.com/connect/token", data=data,
                                 headers={"Authorization": f"Basic {basic}",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if not body.get("access_token"):
        sys.exit("ERRO: não veio access_token do Xero.")
    # o refresh token do Xero ROTACIONA a cada uso — guarde o novo
    novo = body.get("refresh_token")
    if novo:
        with open(".xero_refresh_token.novo", "w") as f:
            f.write(novo)
        print("AVISO: o refresh token rotacionou. O novo está em .xero_refresh_token.novo "
              "— atualize seu segredo, senão a próxima execução falha.", file=sys.stderr)
    return body["access_token"]


def main():
    tok = token()
    H = {"Authorization": f"Bearer {tok}",
         "Xero-tenant-id": env("XERO_TENANT_ID"),
         "Accept": "application/json"}
    rows, page = [], 1
    while True:
        req = urllib.request.Request(
            f"https://api.xero.com/api.xro/2.0/Contacts?page={page}&includeArchived=true", headers=H)
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.load(r)
        batch = d.get("Contacts") or []
        if not batch:
            break
        for c in batch:
            rows.append({"ozid": (c.get("AccountNumber") or "").strip(),
                         "contact_id": c.get("ContactID") or "",
                         "nome": c.get("Name") or "",
                         "status": c.get("ContactStatus") or ""})
        print(f"  ... {len(rows)} contatos", file=sys.stderr)
        if len(batch) < 100:
            break
        page += 1
        if page > 60:
            break

    os.makedirs("audit_out", exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ozid", "contact_id", "nome", "status"])
        w.writeheader()
        w.writerows(rows)
    com = sum(1 for r in rows if r["ozid"])
    print(f"\nOK: {len(rows)} contatos ({com} com AccountNumber preenchido) -> {OUT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Busca no Feedz a relação Colaborador → Gestor direto (líder) via API.

Sem dependências externas (usa só a biblioteca padrão do Python).
Gera 'feedz_relacao.csv' e imprime um resumo (líder → liderados + quem está sem gestor).
NÃO usa nem grava remuneração.

Como rodar (o token fica só na sua máquina):
    export FEEDZ_API_TOKEN="SEU_TOKEN"      # Configurações → Integrações → Chave de Integração API v2
    python3 scripts/feedz_relacao.py

Opcional (sandbox):  export FEEDZ_BASE="https://sandbox.feedz.dev"
"""
import os, sys, csv, json, urllib.request, urllib.error
from collections import defaultdict

BASE = os.environ.get("FEEDZ_BASE", "https://app.feedz.com.br").rstrip("/")
TOKEN = os.environ.get("FEEDZ_API_TOKEN")
if not TOKEN:
    sys.exit('Defina o token:  export FEEDZ_API_TOKEN="..."')


def dig(d, *ks):
    for k in ks:
        d = d.get(k) if isinstance(d, dict) else None
        if d is None:
            return None
    return d


def fetch():
    req = urllib.request.Request(
        f"{BASE}/v2/integracao/employees",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.load(resp)
    except urllib.error.HTTPError as ex:
        body = ex.read().decode("utf-8", "ignore")[:300]
        sys.exit(f"Erro HTTP {ex.code} ao chamar a API do Feedz.\n{body}\n"
                 "Dica: 401 = token inválido/sem permissão; 403/1010 = bloqueio Cloudflare (User-Agent).")
    except urllib.error.URLError as ex:
        sys.exit(f"Falha de conexão: {ex}")
    return d if isinstance(d, list) else d.get("data", [])


def norm(e):
    dept = dig(e, "department_data", "name") or (e.get("department") if isinstance(e.get("department"), str) else dig(e, "department", "name")) or ""
    return {
        "nome": (e.get("full_name") or e.get("name") or "").strip(),
        "email": (e.get("email") or "").strip().lower(),
        "cargo": (dig(e, "job_description", "title") or "").strip(),
        "department": dept.strip(),
        "gestor": (dig(e, "direct_manager", "name") or (e.get("manager") if isinstance(e.get("manager"), str) else "") or "").strip(),
        "gestor_email": (dig(e, "direct_manager", "email") or "").strip().lower(),
        "papel": (dig(e, "role", "name") or (e.get("role") if isinstance(e.get("role"), str) else "") or "").strip(),
        "grupos": ", ".join(e.get("groups", []) if isinstance(e.get("groups"), list) else []),
        "status": e.get("status", ""),
    }


def main():
    emps = [norm(e) for e in fetch()]
    ativos = [p for p in emps if str(p["status"]).lower().startswith("ativ") or p["status"] in (0, "0", "")]
    cols = ["nome", "email", "cargo", "department", "gestor", "gestor_email", "papel", "grupos", "status"]
    hdr = ["Colaborador", "E-mail", "Cargo", "Department (Time)", "Gestor direto (líder)",
           "E-mail do gestor", "Papel (role)", "Grupos", "Status"]
    with open("feedz_relacao.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(hdr)
        for p in sorted(emps, key=lambda x: (x["gestor"] or "~", x["nome"])):
            w.writerow([p[c] for c in cols])
    print(f"OK: {len(emps)} colaboradores ({len(ativos)} ativos) -> feedz_relacao.csv\n")

    liderados = defaultdict(list)
    sem = []
    for p in ativos:
        (liderados[p["gestor"]].append(p["nome"]) if p["gestor"] else sem.append(p["nome"]))
    print("== Líder → liderados ==")
    for lider in sorted(liderados):
        print(f"\n{lider} ({len(liderados[lider])}):")
        for n in sorted(liderados[lider]):
            print(f"   - {n}")
    if sem:
        print("\n== Sem gestor direto (topo ou faltando) ==")
        for n in sorted(sem):
            print(f"   - {n}")


if __name__ == "__main__":
    main()

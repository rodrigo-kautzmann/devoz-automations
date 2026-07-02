#!/usr/bin/env python3
"""Tabela completa das pessoas no Feedz (pra auditar o cadastro).

Usa só a biblioteca padrão. Token na sua máquina (env FEEDZ_API_TOKEN).
Gera 'feedz_pessoas.csv' (abre no Excel/Numbers) e imprime um resumo.
IGNORA remuneração.

Rodar:  python3 scripts/feedz_tabela.py
"""
import os, sys, csv, json, urllib.request, urllib.error
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("FEEDZ_BASE", "https://app.feedz.com.br").rstrip("/")
TOKEN = os.environ.get("FEEDZ_API_TOKEN")
if not TOKEN:
    sys.exit('Defina o token:  export FEEDZ_API_TOKEN="..."')
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def dig(d, *ks):
    for k in ks:
        d = d.get(k) if isinstance(d, dict) else None
        if d is None:
            return None
    return d


def time_area_map():
    with open(os.path.join(HERE, "taxonomy.json"), encoding="utf-8") as f:
        tx = json.load(f)
    return {t["time"]: t["area"] for t in tx["times"]}, {t["area"] for t in tx["times"]}


def fetch():
    req = urllib.request.Request(f"{BASE}/v2/integracao/employees",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.load(resp)
    except urllib.error.HTTPError as ex:
        sys.exit(f"Erro HTTP {ex.code}: {ex.read().decode('utf-8','ignore')[:300]}")
    return d if isinstance(d, list) else d.get("data", [])


def main():
    t2a, areas = time_area_map()
    emps = fetch()
    rows = []
    for e in emps:
        dept = (dig(e, "department_data", "name") or (e.get("department") if isinstance(e.get("department"), str) else "") or "").strip()
        area = t2a.get(dept, dept if dept in areas else "⚠ fora da taxonomia")
        groups = e.get("groups") or []
        grupos = ", ".join((g.get("name") if isinstance(g, dict) else str(g)) for g in groups) if isinstance(groups, list) else ""
        rows.append({
            "Nome": (e.get("full_name") or e.get("name") or "").strip(),
            "E-mail": (e.get("email") or "").strip().lower(),
            "Cargo": (dig(e, "job_description", "title") or "").strip(),
            "Time (department Feedz)": dept,
            "Área (derivada)": area,
            "Grupos (Feedz)": grupos,
            "Gestor direto": (dig(e, "direct_manager", "name") or (e.get("manager") if isinstance(e.get("manager"), str) else "") or "").strip(),
            "Papel (role)": (dig(e, "role", "name") or (e.get("role") if isinstance(e.get("role"), str) else "") or "").strip(),
            "Unidade (branch)": (dig(e, "branch", "name") or "").strip(),
            "Admissão": (e.get("admission_at") or "")[:10],
            "Status": str(e.get("status", "")),
        })
    cols = list(rows[0].keys())
    with open("feedz_pessoas.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["Área (derivada)"], x["Time (department Feedz)"], x["Nome"])):
            w.writerow(r)
    print(f"OK: {len(rows)} pessoas -> feedz_pessoas.csv\n")
    print("Por Unidade:", dict(Counter(r["Unidade (branch)"] or "(vazio)" for r in rows)))
    print("Por Time:   ", dict(Counter(r["Time (department Feedz)"] or "(vazio)" for r in rows)))
    fora = [r["Nome"] for r in rows if r["Área (derivada)"].startswith("⚠")]
    if fora:
        print("Fora da taxonomia (department não-canônico):", fora)


if __name__ == "__main__":
    main()

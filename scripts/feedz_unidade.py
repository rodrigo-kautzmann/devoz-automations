#!/usr/bin/env python3
"""Lista Colaborador -> Unidade (entidade jurídica) no Feedz, pra conferir LLC/LTDA.

Usa só a biblioteca padrão. Token fica na sua máquina (env FEEDZ_API_TOKEN).
Como o nome exato do campo "unidade" no Feedz não está confirmado, o script:
  1) imprime as CHAVES do 1º colaborador (pra vermos o schema);
  2) tenta campos candidatos (unit/company/unidade/filial/business_unit/...);
  3) imprime nome + unidade e um resumo por unidade.

Rodar:  python3 scripts/feedz_unidade.py
"""
import os, sys, json, urllib.request, urllib.error
from collections import Counter

BASE = os.environ.get("FEEDZ_BASE", "https://app.feedz.com.br").rstrip("/")
TOKEN = os.environ.get("FEEDZ_API_TOKEN")
if not TOKEN:
    sys.exit('Defina o token:  export FEEDZ_API_TOKEN="..."')

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def fetch():
    req = urllib.request.Request(
        f"{BASE}/v2/integracao/employees",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.load(resp)
    except urllib.error.HTTPError as ex:
        sys.exit(f"Erro HTTP {ex.code}: {ex.read().decode('utf-8','ignore')[:300]}")
    return d if isinstance(d, list) else d.get("data", [])


def unidade_de(e):
    # tenta vários formatos possíveis; retorna (valor, de_onde)
    cands = [
        ("branch.name", ("branch", "name")),
        ("unit.name", ("unit", "name")), ("unit", ("unit",)),
        ("unidade.name", ("unidade", "name")), ("unidade", ("unidade",)),
        ("company.name", ("company", "name")), ("company", ("company",)),
        ("company_data.name", ("company_data", "name")),
        ("business_unit.name", ("business_unit", "name")), ("business_unit", ("business_unit",)),
        ("filial.name", ("filial", "name")), ("filial", ("filial",)),
        ("branch.name", ("branch", "name")), ("establishment.name", ("establishment", "name")),
    ]
    for label, path in cands:
        v = e
        for k in path:
            v = v.get(k) if isinstance(v, dict) else None
            if v is None:
                break
        if isinstance(v, str) and v.strip():
            return v.strip(), label
    return "", ""


def main():
    emps = fetch()
    if not emps:
        sys.exit("Nenhum colaborador retornado.")
    print("== chaves do 1º colaborador ==")
    print(sorted(emps[0].keys()))
    print("\n== estrutura crua dos campos candidatos (1º colaborador) ==")
    for k in ("branch", "company", "company_data", "situation", "registration"):
        print(f"  {k}: {json.dumps(emps[0].get(k), ensure_ascii=False)}")
    print("\n== valores distintos de branch / company (contagem) ==")
    cb = Counter(json.dumps(e.get("branch"), ensure_ascii=False) for e in emps)
    cc = Counter(json.dumps(e.get("company"), ensure_ascii=False) for e in emps)
    print("  branch:", dict(cb))
    print("  company:", dict(cc))
    print()
    rows, cont = [], Counter()
    for e in emps:
        nome = (e.get("full_name") or e.get("name") or "").strip()
        val, onde = unidade_de(e)
        rows.append((nome, val, onde))
        cont[val or "(vazio)"] += 1
    print("== Colaborador -> Unidade ==")
    for nome, val, onde in sorted(rows):
        print(f"  {nome:<42} {val or '—':<28} {('['+onde+']') if onde else ''}")
    print("\n== Resumo por unidade ==")
    for val, n in cont.most_common():
        print(f"  {val}: {n}")


if __name__ == "__main__":
    main()

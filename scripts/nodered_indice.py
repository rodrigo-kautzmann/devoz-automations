#!/usr/bin/env python3
"""Gera docs/nodered/README.md: o que cada aba do Node-RED expõe e chama.

Lê os exports SANITIZADOS em docs/nodered/*_flows.json e lista, por aba:
endpoints expostos (nós "http in"), hosts externos chamados (nós "http request"
e URLs dentro de functions) e quantos nós tem.

Uso:  python3 scripts/nodered_indice.py
"""
import collections, glob, json, os, re

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "nodered")
URL = re.compile(r"https?://([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
IGNORA = {"www.w3.org", "schemas.xmlsoap.org", "example.com"}


def hosts(texto):
    return {h.lower() for h in URL.findall(texto or "") if h.lower() not in IGNORA}


def main():
    out = ["# Node-RED — mapa dos flows",
           "",
           "Gerado por `scripts/nodered_indice.py` a partir dos exports sanitizados desta pasta",
           "(`scripts/nodered_sanitiza.py` remove credenciais e dados de teste; ids e ligações",
           "ficam intactos). Para atualizar: exporte os flows do Node-RED, rode o sanitiza em",
           "cada um, confira, e rode este script.",
           ""]
    for f in sorted(glob.glob(os.path.join(DIR, "*_flows.json"))):
        nos = json.load(open(f, encoding="utf-8"))
        abas = {n["id"]: n.get("label") or n["id"] for n in nos if n.get("type") == "tab"}
        subflows = {n["id"]: n.get("name") or n["id"] for n in nos if n.get("type") == "subflow"}
        por = collections.defaultdict(lambda: {"n": 0, "in": set(), "out": set(), "sub": collections.Counter()})
        for n in nos:
            z = n.get("z")
            if z not in abas:
                continue
            a = por[z]; a["n"] += 1
            t = n.get("type", "")
            if t == "http in":
                a["in"].add(f"{(n.get('method') or '').upper()} {n.get('url')}")
            if t == "http request":
                a["out"] |= hosts(n.get("url")) or ({"(url dinâmica, via msg.url)"} if not n.get("url") else set())
            if t == "function":
                a["out"] |= hosts(n.get("func"))
            if t.startswith("subflow:"):
                a["sub"][subflows.get(t.split(":", 1)[1], t)] += 1
        nome = os.path.basename(f).replace("_flows.json", "")
        out += [f"## {nome}", ""]
        for z, label in abas.items():
            a = por[z]
            out.append(f"### {label}  ({a['n']} nós)")
            if a["in"]:
                out.append("- **Expõe:** " + ", ".join(f"`{x}`" for x in sorted(a["in"])))
            if a["out"]:
                out.append("- **Chama:** " + ", ".join(sorted(a["out"])))
            if a["sub"]:
                out.append("- **Subflows:** " + ", ".join(f"{k} ×{v}" for k, v in a["sub"].most_common()))
            out.append("")
    open(os.path.join(DIR, "README.md"), "w", encoding="utf-8").write("\n".join(out))
    print("ok:", os.path.join(DIR, "README.md"))


if __name__ == "__main__":
    main()

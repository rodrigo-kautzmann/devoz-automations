#!/usr/bin/env python3
"""Gera cópia de um export do Node-RED SEM credenciais nem dados de teste, p/ versionar.

Mascara: valores de chaves sensíveis (token/senha/secret/key...), headers Bearer/Basic,
user:pass em URL, parâmetros sensíveis de query, JWT, tokens Zoho (1000.*), variáveis
JS com nome de segredo, comparações com segredo, env de subflow e change nodes com
nome sensível, qualquer string longa e aleatória (exceto id de planilha Google) e
payloads de inject > 500 chars (dumps de teste com dado de cliente) e CPF/CNPJ formatados. Não altera ids,
tipos nem ligações (wires) — o mapa do fluxo fica intacto.

Uso:  python3 scripts/nodered_sanitiza.py <export.json> <saida.json>
Depois confira com a varredura descrita em docs/nodered/README.md.
"""
import json, re, sys
SENS = r'(?:password|passwd|pass|pwd|token|access_token|refresh_token|api[_-]?key|apikey|app[_-]?token|secret|client_secret|client_?id|authorization|auth|x-api-key|private_key|senha|key|chave|signature|session_?id)'
PATS = [
  # "chave": "valor"  /  chave: 'valor'  /  chave = "valor"
  (re.compile(r'''(["']?\w*''' + SENS + r'''\w*["']?\s*[:=]\s*)(["'`])([^"'`\n]{6,})\2''', re.I), lambda m: m.group(1)+m.group(2)+"<REDACTED>"+m.group(2)),
  (re.compile(r'\b(Bearer|Basic|Zoho-oauthtoken|Token)\s+[A-Za-z0-9._~+/=-]{12,}', re.I), lambda m: m.group(1)+" <REDACTED>"),
  (re.compile(r'(https?://)[^/\s:@"\']+:[^/\s@"\']+@'), lambda m: m.group(1)+"<REDACTED>@"),
  (re.compile(r'([?&"\'](?:\w*' + SENS + r'\w*|access_key|hapikey)=)[^&\s"\'`]{6,}', re.I), lambda m: m.group(1)+"<REDACTED>"),
  (re.compile(r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}'), lambda m: "<REDACTED_JWT>"),
  (re.compile(r'\b1000\.[a-f0-9]{20,}\.[a-f0-9]{20,}\b'), lambda m: "<REDACTED_ZOHO>"),
  # variável JS cujo NOME sugere segredo:  const meuTokenBase64 = '...'
  (re.compile(r"""(\b\w*(?:token|key|secret|senha|password|chave|signature|session)\w*\s*[:=]\s*)(["'`])([^"'`\n]{8,})\2""", re.I), lambda m: m.group(1)+m.group(2)+"<REDACTED>"+m.group(2)),
  # fallback de env:  env.get('key') || '...'
  (re.compile(r"""(env\.get\([^)]*\)\s*\|\|\s*)(["'`])([^"'`\n]{8,})\2"""), lambda m: m.group(1)+m.group(2)+"<REDACTED>"+m.group(2)),
  # header como par de strings:  "webhook-signature", "valor"
  (re.compile(r"""(["'](?:webhook-signature|x-api-key|authorization|apikey|api-key|x-auth-token)["']\s*,\s*)(["'])([^"'\n]{6,})\2""", re.I), lambda m: m.group(1)+m.group(2)+"<REDACTED>"+m.group(2)),
  # comentário "chave -> valor"
  (re.compile(r"((?:chave|key|token)\s*-?>\s*)\S{12,}", re.I), lambda m: m.group(1)+"<REDACTED>"),
  (re.compile(r"""(\w*""" + SENS + r"""\w*\s*[!=]==?\s*)(["'`])([^"'`\n]{6,})\2""", re.I), lambda m: m.group(1)+m.group(2)+"<REDACTED>"+m.group(2)),
  (re.compile(r'\b1000\.[A-Za-z0-9._-]{20,}'), lambda m: "<REDACTED_ZOHO>"),
  (re.compile(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b'), lambda m: "<CPF>"),
  (re.compile(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b'), lambda m: "<CNPJ>"),
]
GENERICO = re.compile(r'[A-Za-z0-9_\-+/=%.]{32,}')
SHEET_CTX = re.compile(r'sheet(?:Id)?\W{0,8}$', re.I)
import math, collections
def _ent(x):
    c = collections.Counter(x); n = len(x); return -sum(v/n*math.log2(v/n) for v in c.values())
def generico(s):
    def sub(m):
        v = m.group(0)
        if v.startswith(("http", "www.")) or v.count("/") > 2: return v
        if not (re.search(r'[a-z]', v) and re.search(r'[A-Z]', v) and re.search(r'\d', v)): return v
        if _ent(v) < 4.0: return v
        if SHEET_CTX.search(s[max(0, m.start()-20):m.start()]): return v
        cont["n"] += 1; return "<REDACTED_GENERIC>"
    return GENERICO.sub(sub, s)

SENS_KEY = re.compile(r'^\w*' + SENS + r'\w*$', re.I)
cont = {"n": 0}
def red(s):
    for p, f in PATS:
        s, k = p.subn(f, s); cont["n"] += k
    return generico(s)
def walk(o, key=None):
    if isinstance(o, dict):
        o = dict(o)
        if o.get("type") == "inject" and isinstance(o.get("payload"), str) and len(o["payload"]) > 500:
            o["payload"] = f"<DADOS DE TESTE REMOVIDOS ({len(o['payload'])} chars)>"; cont["n"] += 1
        for nk, vk in (("name", "value"), ("p", "to")):
            if isinstance(o.get(nk), str) and SENS_KEY.match(o[nk].split(".")[-1]) and isinstance(o.get(vk), str) and len(o[vk]) >= 6:
                o[vk] = "<REDACTED>"; cont["n"] += 1
        return {k: walk(v, k) for k, v in o.items()}
    if isinstance(o, list): return [walk(v, key) for v in o]
    if isinstance(o, str):
        if key and SENS_KEY.match(key) and len(o) >= 6:
            cont["n"] += 1; return "<REDACTED>"
        return red(o)
    return o
src, dst = sys.argv[1], sys.argv[2]
d = walk(json.load(open(src, encoding="utf-8")))
json.dump(d, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{src}: {cont['n']} substituições")

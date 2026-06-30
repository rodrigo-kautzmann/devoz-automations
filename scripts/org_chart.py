#!/usr/bin/env python3
"""Gera o Organograma da DevOZ (PNG radial) a partir do Feedz e publica no Confluence.

- Lê colaboradores na API do Feedz (somente leitura; IGNORA remuneração).
- Monta a hierarquia pelo gestor direto.
- Aplica overrides (org_overrides.json): agrupamentos (ex.: Revenue + líder) e
  direção de cada pilar no layout (L/R/T/B).
- Cor por STATUS (diretor / gestor / pessoa), não por nível.
- Desenha PNG (Pillow), sobe como anexo na página Organograma e injeta selo de proveniência.

Env: FEEDZ_API_TOKEN, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN, DRY_RUN
Config (não-secreto): config.json, org_style.json, org_overrides.json
"""
import os, sys, json, re, datetime
from collections import Counter
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
FEEDZ_EMPLOYEES = "https://app.feedz.com.br/v2/integracao/employees"
DIRECTOR = re.compile(r"\b(CEO|CTO|CFO|CIO|COO|CRO|CMO)\b|Chief|Diretor", re.I)


def _load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


_PILAR = {}
def load_taxonomy():
    tx = _load("taxonomy.json")
    for e in tx["areas"]:
        _PILAR[e["area"]] = e["pilar"]
        if e.get("grupo"): _PILAR.setdefault(e["grupo"], e["pilar"])
        _PILAR.setdefault(e["pilar"], e["pilar"])
    return tx


def pilar(a):
    return _PILAR.get((a or "").strip(), "Sem área")


def fetch_feedz():
    tok = os.environ["FEEDZ_API_TOKEN"]
    r = requests.get(FEEDZ_EMPLOYEES,
                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                     timeout=60)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else d.get("data", [])


def norm(e):
    def dig(d, *ks):
        for k in ks:
            d = d.get(k) if isinstance(d, dict) else None
            if d is None: return None
        return d
    dept = dig(e, "department_data", "name") or (e.get("department") if isinstance(e.get("department"), str) else dig(e, "department", "name")) or ""
    cargo = dig(e, "job_description", "title") or ""
    mgr_email = (dig(e, "direct_manager", "email") or "").lower()
    mgr_name = dig(e, "direct_manager", "name") or (e.get("manager") if isinstance(e.get("manager"), str) else "") or ""
    return {"name": (e.get("full_name") or e.get("name") or "").strip(),
            "email": (e.get("email") or "").lower(),
            "cargo": (cargo or "").strip() or "—",
            "area": (dept or "").strip() or "—",
            "mgr": mgr_email, "mgr_name": mgr_name,
            "status": e.get("status", "Ativo")}


def build(people, ov):
    people = [p for p in people if str(p["status"]).lower().startswith("ativ") or p["status"] in (0, "0")]
    byid = {p["email"]: p for p in people if p["email"]}
    # root = CEO (ou quem não tem gestor)
    roots = [p for p in people if not p["mgr"] or p["mgr"] not in byid]
    ceo = next((p for p in people if DIRECTOR.search(p["cargo"]) and "CEO" in p["cargo"].upper()), None) or (roots[0] if roots else None)
    for r in roots:
        if ceo and r["email"] != ceo["email"]:
            r["mgr"] = ceo["email"]
    # kids
    def rebuild_kids():
        k = {}
        for p in people:
            if p["mgr"] and p["mgr"] in byid and p["mgr"] != p["email"]:
                k.setdefault(p["mgr"], []).append(p)
        return k
    kids = rebuild_kids()

    def unit_of(p):
        reps = kids.get(p["email"], [])
        if not reps: return None
        if p.get("display_unit"): return p["display_unit"]
        if (p["area"] or "").startswith("Diretoria"):
            return Counter(pilar(r["area"]) for r in reps).most_common(1)[0][0]
        return p["area"]

    # ---- overrides: grupos (ex.: Revenue) ----
    for g in ov.get("grupos", []):
        pilset = set(g.get("pilares", []))
        syn_email = "__grp_" + g["nome"].lower().replace(" ", "_") + "__"
        syn = {"name": g["nome"], "email": syn_email, "cargo": "CEO" if g.get("lider_nome") else "",
               "area": g["nome"], "mgr": ceo["email"] if ceo else "", "mgr_name": "",
               "status": "Ativo", "display_unit": g["nome"],
               "display_name": g.get("lider_nome", ""), "force_director": True}
        moved = False
        for c in list(kids.get(ceo["email"], []) if ceo else []):
            if (unit_of(c) in pilset) or (pilar(c["area"]) in pilset):
                c["mgr"] = syn_email
                moved = True
        if moved:
            people.append(syn); byid[syn_email] = syn
            kids = rebuild_kids()
    return people, byid, kids, ceo, unit_of


def is_director(p):
    return bool(p.get("force_director")) or bool(DIRECTOR.search(p.get("cargo", "") or ""))


def render(people, kids, ceo, unit_of, st, ov):
    from PIL import Image, ImageDraw, ImageFont
    SC = st["scale"]; COLW, RH, ROWV, COLV = st["COLW"], st["RH"], st["ROWV"], st["COLV"]
    MGRW, ICW, MGRH, ICH, ROOTW, ROOTH = st["mgr_w"], st["ic_w"], st["mgr_h"], st["ic_h"], st["root_w"], st["root_h"]
    c = st["colors"]
    def rgb(h): return tuple(int(h[i:i+2], 16) for i in (1, 3, 5))
    isleaf = lambda p: not kids.get(p["email"])
    boxw = lambda p: ICW if isleaf(p) else MGRW
    boxh = lambda p: ICH if isleaf(p) else MGRH

    CNT = {"L": [0], "R": [0], "T": [0], "B": [0]}
    alln = []
    def assign(p, prim, region):
        p["prim"] = prim; p["region"] = region; alln.append(p)
        ch = kids.get(p["email"], [])
        if not ch:
            cc = CNT[region]; p["cross"] = cc[0]; cc[0] += 1
        else:
            for x in ch: assign(x, prim + 1, region)
            p["cross"] = (ch[0]["cross"] + ch[-1]["cross"]) / 2
    rch = kids.get(ceo["email"], [])
    rch.sort(key=lambda x: x["name"])
    branch = {}
    for b in rch:
        d = ov["direcao"].get(unit_of(b) or "", ov.get("direcao_default", "R"))
        branch.setdefault(d, []).append(b)
    for reg in ["L", "R", "T", "B"]:
        for b in branch.get(reg, []): assign(b, 0, reg)
    mc = {k: (max([n["cross"] for n in alln if n["region"] == k], default=0)) for k in CNT}
    BAND = max(mc["L"], mc["R"]) * RH / 2 + 12
    GAPX = ROOTW / 2 + 34; GAPY = ROOTH / 2 + 34
    pos = {}
    for n in alln:
        r = n["region"]; w = boxw(n); h = boxh(n)
        if r == "R": pos[n["email"]] = (GAPX + n["prim"] * COLW + w / 2, (n["cross"] - mc["R"] / 2) * RH)
        elif r == "L": pos[n["email"]] = (-(GAPX + n["prim"] * COLW + w / 2), (n["cross"] - mc["L"] / 2) * RH)
        elif r == "B": pos[n["email"]] = ((n["cross"] - mc["B"] / 2) * COLV, BAND + GAPY + n["prim"] * ROWV + h / 2)
        else: pos[n["email"]] = ((n["cross"] - mc["T"] / 2) * COLV, -(BAND + GAPY + n["prim"] * ROWV + h / 2))
    pos[ceo["email"]] = (0, 0)
    allp = alln + [ceo]
    def bb(n):
        cx, cy = pos[n["email"]]; w = ROOTW if n is ceo else boxw(n); h = ROOTH if n is ceo else boxh(n)
        return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    PAD = 26
    sx = PAD - min(bb(n)[0] for n in allp); sy = PAD - min(bb(n)[1] for n in allp)
    W = int(max(bb(n)[2] for n in allp) + sx + PAD); H = int(max(bb(n)[3] for n in allp) + sy + PAD)
    img = Image.new("RGB", (W * SC, H * SC), "#FFFFFF"); dr = ImageDraw.Draw(img)
    def F(sz, bold=False):
        try: return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else ""), int(sz * SC))
        except Exception: return ImageFont.load_default()
    def S(v): return int(v * SC)
    def C(n): cx, cy = pos[n["email"]]; return cx + sx, cy + sy
    def rr(x, y, w, h, rad, fill, outline=None, width=1):
        dr.rounded_rectangle([S(x), S(y), S(x + w), S(y + h)], radius=S(rad),
                             fill=rgb(fill) if fill else None, outline=rgb(outline) if outline else None, width=max(1, int(width * SC)))
    def tx(x, y, s, sz, fill, bold=False): dr.text((S(x), S(y)), s, font=F(sz, bold), fill=rgb(fill))
    def ln(a, b): dr.line([(S(a[0]), S(a[1])), (S(b[0]), S(b[1]))], fill=rgb(c["line"]), width=max(1, int(1.5 * SC)))
    def tc(s, n): return s if len(s) <= n else s[:n - 1] + "…"
    for p in allp:
        for ch in kids.get(p["email"], []):
            pcx, pcy = C(p); ccx, ccy = C(ch); reg = ch["region"]
            pw = ROOTW if p is ceo else boxw(p); ph = ROOTH if p is ceo else boxh(p)
            cw = boxw(ch); chh = boxh(ch)
            if reg in ("R", "L"):
                x1 = pcx + (pw / 2 if reg == "R" else -pw / 2); x2 = ccx + (-cw / 2 if reg == "R" else cw / 2); mx = (x1 + x2) / 2
                ln((x1, pcy), (mx, pcy)); ln((mx, pcy), (mx, ccy)); ln((mx, ccy), (x2, ccy))
            else:
                y1 = pcy + (ph / 2 if reg == "B" else -ph / 2); y2 = ccy + (-chh / 2 if reg == "B" else chh / 2)
                my = ((BAND + sy + GAPY * 0.5) if reg == "B" else (sy - BAND - GAPY * 0.5)) if p is ceo else (y1 + y2) / 2
                ln((pcx, y1), (pcx, my)); ln((pcx, my), (ccx, my)); ln((ccx, my), (ccx, y2))
    for p in allp:
        cx, cy = C(p); u = unit_of(p); nm = p.get("display_name") or p["name"]
        if p is ceo:
            w, h = ROOTW, ROOTH; x, y = cx - w / 2, cy - h / 2
            rr(x, y, w, h, 8, c["root"]); tx(x + 12, y + 6, "DevOZ", 12, "#FFFFFF", bold=True); tx(x + 12, y + 21, tc(p["name"], 26), 9.5, c["root_sub"])
        elif is_director(p):
            w, h = MGRW, MGRH; x, y = cx - w / 2, cy - h / 2
            rr(x, y, w, h, 8, c["director"]); tx(x + 10, y + 4, tc(u or p["area"], 24), 10, c["ink"], bold=True); tx(x + 10, y + 18, tc(nm, 28), 9, c["ink"])
        elif not isleaf(p):
            w, h = MGRW, MGRH; x, y = cx - w / 2, cy - h / 2
            rr(x, y, w, h, 8, c["manager"], c["border"], 1); tx(x + 10, y + 4, tc(u or p["area"], 24), 10, c["ink"], bold=True); tx(x + 10, y + 18, tc(nm, 28), 9, c["mgr_sub"])
        else:
            w, h = ICW, ICH; x, y = cx - w / 2, cy - h / 2
            rr(x, y, w, h, 6, c["ic"], c["ic_border"], 1); tx(x + 8, y + 5, tc(nm, 27), 10, c["ink"])
    import io
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue(), len([n for n in allp])


def confluence_attach(base, auth, pid, fname, data):
    base = base.rstrip("/"); h = {"X-Atlassian-Token": "nocheck"}
    g = requests.get(f"{base}/rest/api/content/{pid}/child/attachment", params={"filename": fname}, auth=auth, timeout=30); g.raise_for_status()
    res = g.json().get("results", [])
    url = (f"{base}/rest/api/content/{pid}/child/attachment/{res[0]['id']}/data" if res
           else f"{base}/rest/api/content/{pid}/child/attachment")
    requests.post(url, headers=h, files={"file": (fname, data, "image/png")}, data={"minorEdit": "true"}, auth=auth, timeout=60).raise_for_status()


def confluence_embed(base, auth, pid, fname, catalogo, n):
    base = base.rstrip("/"); today = datetime.date.today().strftime("%d/%m/%Y")
    body = (f'<ac:structured-macro ac:name="info"><ac:rich-text-body><p>'
            f'<strong>Organograma gerado automaticamente em {today}</strong> ({n} nós) por '
            f'<code>org-chart</code> (repo devoz-automations), a partir do Feedz. View gerada — não edite à mão. '
            f'<a href="{catalogo}">Ver catálogo de automações</a>.</p></ac:rich-text-body></ac:structured-macro>'
            f'<p><ac:image><ri:attachment ri:filename="{fname}" /></ac:image></p>')
    g = requests.get(f"{base}/rest/api/content/{pid}", params={"expand": "version"}, auth=auth, timeout=30); g.raise_for_status()
    cur = g.json()
    payload = {"id": pid, "type": "page", "title": cur["title"],
               "version": {"number": cur["version"]["number"] + 1, "message": "Organograma (Feedz) atualizado"},
               "body": {"storage": {"value": body, "representation": "storage"}}}
    r = requests.put(f"{base}/rest/api/content/{pid}", json=payload, auth=auth, timeout=30); r.raise_for_status()
    return r.json()["version"]["number"]


def main():
    conf, st, ov = _load("config.json"), _load("org_style.json"), _load("org_overrides.json")
    people = [norm(e) for e in fetch_feedz()]
    # valida áreas do Feedz contra a taxonomia canônica (taxonomy.json)
    tax = load_taxonomy(); valid_pilares = {e["pilar"] for e in tax["areas"]}
    seen = sorted({p["area"] for p in people if p["area"] and p["area"] != "—"})
    off = [a for a in seen if pilar(a) not in valid_pilares]
    if off:
        print("AVISO: áreas do Feedz fora da taxonomia canônica (sem pilar):", off)
    print("Áreas do Feedz -> pilar:", {a: pilar(a) for a in seen})
    people, byid, kids, ceo, unit_of = build(people, ov)
    if not ceo:
        print("ERRO: não encontrei o CEO/raiz."); return 1
    png, n = render(people, kids, ceo, unit_of, st, ov)
    with open("organograma.png", "wb") as f: f.write(png)
    print(f"Organograma gerado: {n} nós, organograma.png ({len(png)} bytes).")
    if os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"):
        print("DRY_RUN: não publiquei. Baixe o artifact organograma.png.")
        return 0
    auth = (os.environ["CONFLUENCE_EMAIL"], os.environ["CONFLUENCE_API_TOKEN"])
    base = conf["confluence_base_url"]; fname = "organograma.png"
    confluence_attach(base, auth, conf["org_page_id"], fname, png)
    ver = confluence_embed(base, auth, conf["org_page_id"], fname, conf.get("catalogo_url", ""), n)
    print(f"Publicado no Confluence (versão {ver}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

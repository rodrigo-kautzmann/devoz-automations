#!/usr/bin/env python3
"""Gera o Organograma ESTRUTURAL da DevOZ (PNG radial) e publica no Confluence.

Modelo (decidido 2026-07-01): DevOZ → Área → Time → Grupo → pessoas.
- Só unidades com pessoas/responsável viram caixa. Funções/lentes (Recruiting,
  Innovation interna/externa, Sales Brazil/LATAM/ROW) NÃO entram (ver páginas de área).
- Áreas (ordem/lado do layout), Times e Grupos vêm do taxonomy.json (esqueleto
  completo; vazios aparecem em cinza). taxonomy.json é a ÚNICA fonte da estrutura.
- Líder de Área = Diretor; de Time = Gestor; de Grupo = Líder (destacado, sem estrela).
  Prioriza quem tem subordinados diretos no Feedz; se ninguém tiver mas existir
  exatamente 1 pessoa nesse nível, ela é a líder mesmo assim (protege área/time/
  grupo com um único responsável que zerou o time — ex.: área-folha) — o script
  AVISA quando usa esse fallback.
- REDE DE SEGURANÇA: quem tiver Time/Grupo inválido é colocado no nível válido acima
  e o script AVISA (nunca some ninguém do organograma).
- Layout congelado: Revenue à esquerda; Product & Develop à direita;
  People, Business Support e Innovation embaixo (Innovation mais à direita).

Fontes de dados (env ORG_SOURCE):
- "feedz" (padrão): API do Feedz. **department = Time** (ou a Área, p/ diretor/área-folha;
  ou "Executive" p/ o CEO). **Grupo vem dos GRUPOS** do colaborador (match case-insensitive
  contra a taxonomy). **Área é sempre derivada** do Time — nunca lida do Feedz. Papel = Líder
  se tem subordinados diretos, senão Liderado. IGNORA remuneração.
- "csv": arquivo pipe "nome|area|time|grupo|papel" em ORG_CSV (uso interino).

Env: FEEDZ_API_TOKEN, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN, DRY_RUN, ORG_SOURCE, ORG_CSV
Config (não-secreto): config.json, taxonomy.json
"""
import os, sys, json, datetime, io
from collections import defaultdict
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
FEEDZ_EMPLOYEES = "https://app.feedz.com.br/v2/integracao/employees"

# ---- layout: ordem e lado das áreas vêm do taxonomy.json (preenchidos em load_taxonomy) ----
DIRORDER = []
DIR = {}
# cores
ROOT_BG = "#111111"; PILAR = "#00D256"; MGRC = "#D6F8E4"; GRP = "#EAFBF2"; ICBG = "#FFFFFF"
BORDER = "#00B84C"; GLEAD = "#00902E"; ICB = "#E2E6E2"; LINE = "#BFC9C0"; INK = "#16231A"
MUTEBG = "#F1F3F1"; MUTEBD = "#C9D0C9"; MUTETX = "#9AA69C"
COLW = 214; RH = 34; ROWV = 72; COLV = 204; ROOTW, ROOTH = 182, 36; SC = 2


def _load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def load_taxonomy():
    tx = _load("taxonomy.json")
    global DIRORDER, DIR
    DIRORDER = [a["area"] for a in tx["areas"]]
    DIR = {a["area"]: a["lado"] for a in tx["areas"]}
    area_times = defaultdict(list); time_grupos = {}; time_area = {}
    for t in tx["times"]:
        if t["area"] == "Executive":
            continue
        area_times[t["area"]].append(t["time"])
        time_grupos[t["time"]] = t.get("grupos", [])
        time_area[t["time"]] = t["area"]
    return area_times, time_grupos, time_area


# ---------- fontes de dados -> linhas {name, area, time, grupo, papel} ----------
def rows_from_feedz(area_times, time_grupos, time_area):
    tok = os.environ["FEEDZ_API_TOKEN"]
    r = requests.get(FEEDZ_EMPLOYEES,
                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}, timeout=60)
    r.raise_for_status()
    d = r.json(); emps = d if isinstance(d, list) else d.get("data", [])

    def dig(o, *ks):
        for k in ks:
            o = o.get(k) if isinstance(o, dict) else None
            if o is None: return None
        return o

    def is_active(e):
        s = e.get("status", "Ativo")
        return str(s).lower().startswith("ativ") or s in (0, "0", 1, "1", True)

    emps = [e for e in emps if is_active(e)]
    # subordinados diretos (para inferir Papel)
    reports = defaultdict(int)
    for e in emps:
        m = (dig(e, "direct_manager", "email") or "").lower()
        if m: reports[m] += 1

    valid_grupos = set(g for gs in time_grupos.values() for g in gs)
    TIMES = {t.lower(): t for t in time_area}
    AREASL = {a.lower(): a for a in DIRORDER}
    GRUPOS = {g.lower(): (t, g) for t, gs in time_grupos.items() for g in gs}
    rows = []
    for e in emps:
        name = (e.get("full_name") or e.get("name") or "").strip()
        email = (e.get("email") or "").lower()
        dept = (dig(e, "department_data", "name") or (e.get("department") if isinstance(e.get("department"), str) else "") or "").strip()
        groups = e.get("groups") or []
        gnames = [(g.get("name") if isinstance(g, dict) else str(g)).strip() for g in groups] if isinstance(groups, list) else []
        # Modelo Feedz: department = Time (ou Área p/ diretor/área-folha, ou Executive); grupos = Grupo.
        dl = dept.lower()
        if dl in ("executive", "diretoria"):          # raiz (CEO); "Diretoria" = alias legado
            area = "Executive"; time = ""
        elif dl in TIMES:                             # department é um Time -> Área derivada
            time = TIMES[dl]; area = time_area[time]
        elif dl in AREASL:                            # department é uma Área (diretor ou área-folha)
            area = AREASL[dl]; time = ""
        else:                                         # desconhecido: rede de segurança
            area = dept or "—"; time = dept
        grupo = ""
        for g in gnames:                              # Grupo canônico válido para o Time
            gl = g.strip().lower()
            if time and gl in GRUPOS and GRUPOS[gl][0] == time:
                grupo = GRUPOS[gl][1]; break
        # Papel: tem subordinados => Líder do seu nível; senão Liderado
        papel = "Líder" if reports.get(email, 0) > 0 else "Liderado"
        if area == "Executive":                        # CEO
            papel = "Líder"
        rows.append({"name": name, "area": area, "time": time, "grupo": grupo, "papel": papel})
    return rows


def rows_from_csv(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"): continue
            a = (ln.split("|") + [""] * 5)[:5]
            rows.append({"name": a[0].strip(), "area": a[1].strip(), "time": a[2].strip(),
                         "grupo": a[3].strip(), "papel": a[4].strip()})
    return rows


# ---------- montagem estrutural + rede de segurança ----------
def build_nodes(rows, area_times, time_grupos):
    nodes = {}; kids = defaultdict(list)
    warn = []

    def mk(nid, typ, area, label, leader="", papel_leaf=""):
        nodes[nid] = {"name": nid, "type": typ, "area": area, "label": label,
                      "leader": leader, "papel_leaf": papel_leaf}
        return nid

    def pick_leader(candidates, nivel):
        """Escolhe o líder do nível (Área/Time/Grupo): prioriza quem tem
        subordinados diretos no Feedz (papel Líder). Se ninguém tiver
        subordinados mas existir exatamente 1 pessoa nesse nível, ela é a
        líder mesmo assim — protege área/time/grupo que zerou o time (ex.:
        área-folha com um único responsável, sem ninguém reportando pra ele
        no momento). Com 2+ candidatos e nenhum "Líder" no Feedz, não dá pra
        adivinhar -> nível fica sem líder destacado (comportamento anterior)."""
        lider = next((p for p in candidates if p["papel"] == "Líder"), None)
        if lider:
            return lider
        if len(candidates) == 1:
            warn.append("%s: assumido(a) como líder de %s sem subordinados diretos no Feedz"
                         % (candidates[0]["name"], nivel))
            return candidates[0]
        return None

    ceo = next((p["name"] for p in rows if p["area"] == "Executive"), "DevOZ")
    mk(ceo, "root", "Executive", "DevOZ", ceo)

    def person_node(p, parent, suffix):
        pid = mk(p["name"] + "##" + suffix, "person", p["area"], p["name"], papel_leaf=p["papel"])
        kids[parent].append(pid)

    anode = {}; tnode = {}; gnode = {}; leaders = {ceo}
    for area in DIRORDER:
        az = [p for p in rows if p["area"] == area]
        diretor = pick_leader([p for p in az if not p["time"]], "Área %s" % area)
        dname = diretor["name"] if diretor else ("Rodrigo Kautzmann" if area == "Revenue" else "")
        if diretor: leaders.add(diretor["name"])
        anid = mk("A::" + area, "area", area, area, dname); kids[ceo].append(anid); anode[area] = anid
        for time in area_times.get(area, []):
            tz = [p for p in az if p["time"] == time]
            gestor = pick_leader([p for p in tz if not p["grupo"]], "Time %s/%s" % (area, time))
            if gestor: leaders.add(gestor["name"])
            tnid = mk("T::%s::%s" % (area, time), "time", area, time, gestor["name"] if gestor else "")
            kids[anid].append(tnid); tnode[(area, time)] = tnid
            for grupo in time_grupos.get(time, []):
                gz = [p for p in tz if p["grupo"] == grupo]
                glider = pick_leader(gz, "Grupo %s/%s/%s" % (area, time, grupo))
                if glider: leaders.add(glider["name"])
                gnid = mk("G::%s::%s::%s" % (area, time, grupo), "grupo", area, grupo, glider["name"] if glider else "")
                kids[tnid].append(gnid); gnode[(area, time, grupo)] = gnid

    placed = set(leaders)
    for p in rows:
        if p["name"] in leaders or p["area"] == "Executive":
            continue
        area, time, grupo = p["area"], p["time"], p["grupo"]
        if area not in anode:
            warn.append("%s: área inválida '%s' -> ligado ao DevOZ" % (p["name"], area)); person_node(p, ceo, "root")
        elif not time:
            if area in area_times:
                warn.append("%s: sem Time reconhecido em %s (grupo fora do padrão?) -> nível da área" % (p["name"], area))
            person_node(p, anode[area], area)
        elif (area, time) not in tnode:
            warn.append("%s: time inválido '%s' em %s -> nível da área" % (p["name"], time, area)); person_node(p, anode[area], area)
        elif not grupo:
            person_node(p, tnode[(area, time)], time)
        elif (area, time, grupo) in gnode:
            person_node(p, gnode[(area, time, grupo)], grupo)
        else:
            warn.append("%s: grupo inválido '%s' em %s -> nível do time" % (p["name"], grupo, time)); person_node(p, tnode[(area, time)], time)
        placed.add(p["name"])

    # marca unidades vazias (sem pessoas nem líder)
    def haspeople(nid):
        n = nodes[nid]
        if n["type"] == "person" or n["leader"]: return True
        return any(haspeople(c) for c in kids.get(nid, []))
    for nid in list(nodes):
        nodes[nid]["empty"] = nodes[nid]["type"] in ("time", "grupo") and not haspeople(nid)

    total = len({p["name"] for p in rows}); missing = [p["name"] for p in rows if p["name"] not in placed]
    return nodes, kids, ceo, warn, len(placed), total, missing


# ---------- render ----------
def render(nodes, kids, ceo):
    from PIL import Image, ImageDraw, ImageFont

    def rgb(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    def bw(n): return 164 if n["type"] == "person" else 182
    def bh(n): return 20 if n["type"] == "person" else 32

    alln = []; CNT = {"L": [0], "R": [0], "T": [0], "B": [0]}

    def assign(nid, prim, reg):
        n = nodes[nid]; n["prim"] = prim; n["reg"] = reg; alln.append(nid)
        ch = kids.get(nid, [])
        if not ch:
            c = CNT[reg]; n["cross"] = c[0]; c[0] += 1
        else:
            for x in ch: assign(x, prim + 1, reg)
            n["cross"] = (nodes[ch[0]]["cross"] + nodes[ch[-1]]["cross"]) / 2

    branch = {}
    for anid in kids[ceo]:
        branch.setdefault(DIR.get(nodes[anid]["area"], "R"), []).append(anid)
    for reg in ["L", "R", "T", "B"]:
        for anid in branch.get(reg, []): assign(anid, 0, reg)

    mc = {k: max([nodes[i]["cross"] for i in alln if nodes[i]["reg"] == k], default=0) for k in CNT}
    BAND = max(mc["L"], mc["R"]) * RH / 2 + 12; GAPX = ROOTW / 2 + 34; GAPY = ROOTH / 2 + 34
    pos = {}
    for i in alln:
        n = nodes[i]; r = n["reg"]; w = bw(n); h = bh(n)
        if r == "R": pos[i] = (GAPX + n["prim"] * COLW + w / 2, (n["cross"] - mc["R"] / 2) * RH)
        elif r == "L": pos[i] = (-(GAPX + n["prim"] * COLW + w / 2), (n["cross"] - mc["L"] / 2) * RH)
        elif r == "B": pos[i] = ((n["cross"] - mc["B"] / 2) * COLV, BAND + GAPY + n["prim"] * ROWV + h / 2)
        else: pos[i] = ((n["cross"] - mc["T"] / 2) * COLV, -(BAND + GAPY + n["prim"] * ROWV + h / 2))
    pos[ceo] = (0, 0); allids = alln + [ceo]

    def bb(i):
        n = nodes[i]; cx, cy = pos[i]; w = ROOTW if i == ceo else bw(n); h = ROOTH if i == ceo else bh(n)
        return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    PAD = 26
    sx = PAD - min(bb(i)[0] for i in allids); sy = PAD - min(bb(i)[1] for i in allids)
    W = int(max(bb(i)[2] for i in allids) + sx + PAD); H = int(max(bb(i)[3] for i in allids) + sy + PAD)
    img = Image.new("RGB", (W * SC, H * SC), "#FFFFFF"); dr = ImageDraw.Draw(img)

    _FONTS = {
        False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"],
        True: ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"],
    }
    def F(s, b=False):
        for p in _FONTS[b]:
            try: return ImageFont.truetype(p, int(s * SC))
            except Exception: continue
        return ImageFont.load_default()
    def SS(v): return int(v * SC)
    def C(i): cx, cy = pos[i]; return cx + sx, cy + sy
    def rr(x, y, w, h, rad, fill, ol=None, wd=1):
        dr.rounded_rectangle([SS(x), SS(y), SS(x + w), SS(y + h)], radius=SS(rad),
                             fill=rgb(fill) if fill else None, outline=rgb(ol) if ol else None, width=max(1, int(wd * SC)))
    def tx(x, y, s, sz, fill, b=False): dr.text((SS(x), SS(y)), s, font=F(sz, b), fill=rgb(fill))
    def tr(s, n): return s if len(s) <= n else s[:n - 1] + "…"
    def ln(a, b): dr.line([(SS(a[0]), SS(a[1])), (SS(b[0]), SS(b[1]))], fill=rgb(LINE), width=max(1, int(1.4 * SC)))

    for i in allids:
        for c in kids.get(i, []):
            pcx, pcy = C(i); ccx, ccy = C(c); reg = nodes[c]["reg"]
            pw = ROOTW if i == ceo else bw(nodes[i]); ph = ROOTH if i == ceo else bh(nodes[i])
            cw = bw(nodes[c]); chh = bh(nodes[c])
            if reg in ("R", "L"):
                x1 = pcx + (pw / 2 if reg == "R" else -pw / 2); x2 = ccx + (-cw / 2 if reg == "R" else cw / 2); mx = (x1 + x2) / 2
                ln((x1, pcy), (mx, pcy)); ln((mx, pcy), (mx, ccy)); ln((mx, ccy), (x2, ccy))
            else:
                y1 = pcy + (ph / 2 if reg == "B" else -ph / 2); y2 = ccy + (-chh / 2 if reg == "B" else chh / 2)
                my = ((BAND + sy + GAPY * 0.5) if reg == "B" else (sy - BAND - GAPY * 0.5)) if i == ceo else (y1 + y2) / 2
                ln((pcx, y1), (pcx, my)); ln((pcx, my), (ccx, my)); ln((ccx, my), (ccx, y2))

    for i in allids:
        n = nodes[i]; cx, cy = C(i); t = n["type"]; em = n.get("empty")
        if t == "root":
            w, h = ROOTW, ROOTH; x, y = cx - w / 2, cy - h / 2
            rr(x, y, w, h, 8, ROOT_BG); tx(x + 12, y + 6, "DevOZ", 12, "#FFFFFF", True); tx(x + 12, y + 21, tr(n["leader"], 26), 9, "#BFE9CF")
        elif t == "area":
            w, h = 182, 32; x, y = cx - w / 2, cy - h / 2
            rr(x, y, w, h, 8, PILAR); tx(x + 10, y + 4, tr(n["label"], 24), 10, INK, True); tx(x + 10, y + 18, tr(n["leader"] or "—", 28), 9, INK)
        elif t == "time":
            w, h = 182, 32; x, y = cx - w / 2, cy - h / 2
            if em: rr(x, y, w, h, 8, MUTEBG, MUTEBD, 1); tx(x + 10, y + 9, tr(n["label"], 24), 9.5, MUTETX, True)
            elif n["leader"]: rr(x, y, w, h, 8, MGRC, BORDER, 1); tx(x + 10, y + 4, tr(n["label"], 24), 10, INK, True); tx(x + 10, y + 18, tr(n["leader"], 28), 9, "#3C5A48")
            else: rr(x, y, w, h, 8, MGRC, BORDER, 1); tx(x + 10, y + 9, tr(n["label"], 24), 10, INK, True)
        elif t == "grupo":
            w, h = 182, 30; x, y = cx - w / 2, cy - h / 2
            if em: rr(x, y, w, h, 7, MUTEBG, MUTEBD, 1); tx(x + 10, y + 8, tr(n["label"], 24), 9, MUTETX, True)
            elif n["leader"]: rr(x, y, w, h, 7, GRP, BORDER, 2); tx(x + 10, y + 3, tr(n["label"], 24), 9.5, INK, True); tx(x + 10, y + 16, tr(n["leader"], 26), 9, GLEAD, True)
            else: rr(x, y, w, h, 7, GRP, BORDER, 1); tx(x + 10, y + 8, tr(n["label"], 24), 9.5, INK, True)
        else:
            w, h = 164, 20; x, y = cx - w / 2, cy - h / 2; lead = n.get("papel_leaf") == "Líder"
            rr(x, y, w, h, 6, ICBG, BORDER if lead else ICB, 2 if lead else 1); tx(x + 7, y + 4, tr(n["label"], 26), 9.5, INK, lead)

    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue(), len(allids)


# ---------- Confluence ----------
def confluence_attach(base, auth, pid, fname, data):
    base = base.rstrip("/"); h = {"X-Atlassian-Token": "nocheck"}
    g = requests.get(f"{base}/rest/api/content/{pid}/child/attachment", params={"filename": fname}, auth=auth, timeout=30); g.raise_for_status()
    res = g.json().get("results", [])
    url = (f"{base}/rest/api/content/{pid}/child/attachment/{res[0]['id']}/data" if res
           else f"{base}/rest/api/content/{pid}/child/attachment")
    requests.post(url, headers=h, files={"file": (fname, data, "image/png")}, data={"minorEdit": "true"}, auth=auth, timeout=60).raise_for_status()


def confluence_embed(base, auth, pid, fname, conf, n):
    base = base.rstrip("/"); today = datetime.date.today().strftime("%d/%m/%Y")
    intro = conf.get("org_page_intro_storage", ""); footer = conf.get("org_page_footer_storage", "")
    # Padrão DevOZ (intranet): selo VISÍVEL de geração + data da última atualização;
    # detalhes de COMO é gerado ficam num expand COLAPSADO e autossuficiente (sem página externa).
    badge = ('<blockquote><p>🤖 <strong>Gerado automaticamente</strong> · '
             f'Última atualização: {today}</p></blockquote>')
    detalhes = ('<ac:structured-macro ac:name="expand">'
                '<ac:parameter ac:name="title">Como este organograma é gerado</ac:parameter>'
                '<ac:rich-text-body>'
                '<p><strong>Fonte:</strong> <code>taxonomy.json</code> (estrutura) + Feedz (pessoas e líderes).</p>'
                '<p><strong>Quando roda:</strong> automaticamente todo dia às 05:30 (BRT), '
                'via GitHub Actions no <code>devoz-automations</code> · '
                '<strong>Automação:</strong> <code>scripts/org_chart.py</code> '
                '(workflow <code>org-chart.yml</code>).</p>'
                '<p><strong>Para alterar:</strong> estrutura via PR no <code>taxonomy.json</code>; '
                'pessoas e líderes no Feedz. <strong>Não edite à mão</strong> — a automação sobrescreve.</p>'
                '</ac:rich-text-body></ac:structured-macro>')
    image = f'<p><ac:image><ri:attachment ri:filename="{fname}" /></ac:image></p>'
    body = intro + image + badge + detalhes + footer
    g = requests.get(f"{base}/rest/api/content/{pid}", params={"expand": "version"}, auth=auth, timeout=30); g.raise_for_status()
    cur = g.json()
    payload = {"id": pid, "type": "page", "title": cur["title"],
               "version": {"number": cur["version"]["number"] + 1, "message": "Organograma atualizado"},
               "body": {"storage": {"value": body, "representation": "storage"}}}
    r = requests.put(f"{base}/rest/api/content/{pid}", json=payload, auth=auth, timeout=30); r.raise_for_status()
    return r.json()["version"]["number"]


def main():
    conf = _load("config.json")
    area_times, time_grupos, time_area = load_taxonomy()
    source = os.environ.get("ORG_SOURCE", "feedz").lower()
    if source == "csv":
        rows = rows_from_csv(os.environ["ORG_CSV"])
    else:
        rows = rows_from_feedz(area_times, time_grupos, time_area)

    nodes, kids, ceo, warn, placed, total, missing = build_nodes(rows, area_times, time_grupos)
    png, n = render(nodes, kids, ceo)
    with open("organograma.png", "wb") as f:
        f.write(png)
    print(f"Fonte: {source}. Pessoas: {placed}/{total}. Nós: {n}. organograma.png ({len(png)} bytes).")
    if warn:
        print("AVISOS:")
        for w in warn:
            print("  -", w)
    if missing:
        print("!!! FORA DO ORGANOGRAMA:", missing)
    else:
        print("OK: todas as pessoas entraram no organograma.")

    if os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"):
        print("DRY_RUN: não publiquei. Baixe o artifact organograma.png.")
        return 0
    auth = (os.environ["CONFLUENCE_EMAIL"], os.environ["CONFLUENCE_API_TOKEN"])
    base = conf["confluence_base_url"]; fname = "organograma.png"
    confluence_attach(base, auth, conf["org_page_id"], fname, png)
    ver = confluence_embed(base, auth, conf["org_page_id"], fname, conf, n)
    print(f"Publicado no Confluence (versão {ver}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

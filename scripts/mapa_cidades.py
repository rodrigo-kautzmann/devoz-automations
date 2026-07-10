#!/usr/bin/env python3
"""Gera o mapa "Onde estamos" (cidade onde cada pessoa mora) e publica no Confluence.

Fonte (100% automática, decidida 2026-07-08): o export web pré-definido
"Colaboradores" do Feedz (feedz_export.py), que traz "Residência - Município/UF".
A API de integração v2 NÃO expõe endereço — por isso o export web.
People mantém o endereço no Feedz como já faz; nada de planilha paralela.

Regras:
- Ativo = sem "Desligamento - Tipo" e sem "Último dia trabalhado".
- Privacidade: o xlsx (CPF, banco etc.) fica SÓ em memória; usamos apenas
  nome, e-mail, cidade e UF. No Confluence vai somente cidade — nunca endereço.
- Fora do Brasil (IFD-33): Município/UF do Feedz são só BR; People preenche o
  campo "Endereço" terminando com "..., Cidade, País" — daqui a gente extrai as
  DUAS ÚLTIMAS partes (cidade, país) e descarta o resto do endereço na hora.
- Ativo sem cidade vira "Cidade pendente no Feedz" (nunca some em silêncio).
- Exceções/ajustes finos em map_overrides.json: {"email": {"cidade","uf"?,"pais"?,"lat"?,"lon"?}}.
- Coordenadas: data/cidades_br.csv (IBGE) + data/cidades_extra.csv (fora do BR,
  editável — cidade sem coordenada entra na tabela e vira aviso, não some).

Desenho robusto (sem sobreposição): as bolhas passam por resolução de colisão
(dodge); quando uma bolha é deslocada da posição real, um ponto + linha-guia
marcam a cidade. Países vizinhos aparecem no fundo e a moldura se expande
sozinha quando há gente fora do Brasil.

Env: FEEDZ_LOGIN_EMAIL, FEEDZ_LOGIN_PASSWORD, DRY_RUN,
     MAP_XLSX (opcional: caminho de um export baixado à mão — teste sem login)
Config (não-secreto): config.json (map_page_id, catalogo_url)
"""
import os, sys, csv, json, math, datetime, io, unicodedata
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
FNAME = "mapa_onde_estamos.png"

COL_NOME = "Nome completo"; COL_NOME2 = "Nome"; COL_EMAIL = "Email"
COL_CID = "Residência - Município"; COL_UF = "Residência - UF"
COL_END = "Residência - Endereço"
COL_DESLIG = "Desligamento - Tipo"; COL_ULTDIA = "Último dia trabalhado"
ALIAS_CIDADE = {("distrito federal", "DF"): ("Brasília", "DF")}
PAISES_BR = ("brasil", "brazil", "br")

GREEN = "#00D256"; GREEN_D = "#00B84C"; INK = "#16231A"; MUTED = "#3C5A48"
LAND = "#EEF4EF"; LAND_EXT = "#F7FAF8"; LINE = "#BFC9C0"

# extensão base (Brasil); expande sozinha se houver pontos fora
BR_BOX = (-75.0, -33.0, -35.0, 6.0)  # lon0, lon1, lat0, lat1


def _load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def load_coords_br():
    out = {}
    with open(os.path.join(HERE, "data", "cidades_br.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[(norm(r["nome"]), r["uf"].upper())] = (float(r["lat"]), float(r["lon"]))
    return out


def load_coords_extra():
    out = {}
    path = os.path.join(HERE, "data", "cidades_extra.csv")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[(norm(r["nome"]), norm(r["pais"]))] = (float(r["lat"]), float(r["lon"]))
    return out


def pessoas_from_xlsx(data):
    """bytes do export -> [{nome, email, cidade, uf, endereco}] só dos ATIVOS."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    h = [str(x) if x is not None else "" for x in next(rows)]

    def col(name):
        if name not in h:
            raise RuntimeError(f"Coluna '{name}' não está no export do Feedz — layout mudou? Colunas: {h[:20]}...")
        return h.index(name)

    inome, inome2, iem = col(COL_NOME), col(COL_NOME2), col(COL_EMAIL)
    icid, iuf, iend = col(COL_CID), col(COL_UF), col(COL_END)
    ides, iult = col(COL_DESLIG), col(COL_ULTDIA)
    out = []
    for r in rows:
        if (r[ides] and str(r[ides]).strip()) or (r[iult] and str(r[iult]).strip()):
            continue  # desligado
        nome = str(r[inome] or r[inome2] or "").strip()
        email = str(r[iem] or "").strip().lower()
        if not (nome or email):
            continue
        out.append({"nome": nome or email,
                    "email": email,
                    "cidade": str(r[icid] or "").strip(),
                    "uf": str(r[iuf] or "").strip().upper(),
                    "endereco": str(r[iend] or "").strip()})
    return out


def cidade_pais_do_endereco(endereco):
    """'..., Cidade, País' -> (cidade, pais) ou None. Só as 2 últimas partes; o
    resto do endereço é descartado aqui mesmo (privacidade)."""
    parts = [p.strip() for p in endereco.split(",") if p.strip()]
    if len(parts) >= 2 and not any(ch.isdigit() for ch in parts[-1]):
        return parts[-2], parts[-1]
    return None


def build(pessoas):
    """-> (cidades{label:{lat,lon,pessoas}}, sem_coord{label:[nomes]}, pendentes[], avisos[])"""
    coords_br = load_coords_br()
    coords_extra = load_coords_extra()
    try:
        overrides = _load("map_overrides.json")
    except FileNotFoundError:
        overrides = {}
    grouped, sem_coord, pend, warn = {}, {}, [], []
    for p in pessoas:
        ov = overrides.get(p["email"], {})
        cid = (ov.get("cidade") or p["cidade"]).strip()
        uf = (ov.get("uf") or p["uf"]).strip().upper()
        pais = (ov.get("pais") or "").strip()
        if not cid and p["endereco"]:                 # fora do BR (convenção IFD-33)
            cp = cidade_pais_do_endereco(p["endereco"])
            if cp:
                cid, pais = cp
                uf = ""
        if not cid:
            pend.append(p["nome"])
            continue
        if not pais or norm(pais) in PAISES_BR:
            if (norm(cid), uf) in ALIAS_CIDADE:
                cid, uf = ALIAS_CIDADE[(norm(cid), uf)]
            label = f"{cid}/{uf}" if uf else cid
            lat, lon = coords_br.get((norm(cid), uf), (None, None))
            if lat is None:
                warn.append(f"cidade não encontrada na base IBGE: {cid}/{uf} ({p['email']})")
        else:
            label = f"{cid}/{pais}"
            lat, lon = coords_extra.get((norm(cid), norm(pais)), (None, None))
            if lat is None:
                warn.append(f"cidade fora do BR sem coordenada (adicione em data/cidades_extra.csv "
                            f"ou map_overrides.json): {cid}/{pais} ({p['email']})")
        if "lat" in ov and "lon" in ov:
            lat, lon = float(ov["lat"]), float(ov["lon"])
        if lat is None:
            sem_coord.setdefault(label, []).append(p["nome"])
        else:
            g = grouped.setdefault(label, {"lat": lat, "lon": lon, "pessoas": []})
            g["pessoas"].append(p["nome"])
    for g in grouped.values():
        g["pessoas"].sort()
    for ns in sem_coord.values():
        ns.sort()
    return grouped, sem_coord, sorted(pend), warn


# ---------- desenho ----------
def _dodge(nodes, min_gap=0.10, iters=400, pull=0.015):
    """Resolução de colisão: bolhas se afastam até não sobrepor; âncora puxa de volta.
    A bolha menor cede mais. Posições em coordenadas de dado (graus)."""
    for _ in range(iters):
        for n in nodes:
            n["x"] += (n["ax"] - n["x"]) * pull
            n["y"] += (n["ay"] - n["y"]) * pull
        moved = False
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                dx = b["x"] - a["x"]; dy = b["y"] - a["y"]
                d = math.hypot(dx, dy) or 1e-6
                need = a["r"] + b["r"] + min_gap
                if d < need:
                    moved = True
                    push = (need - d)
                    wa = b["r"] / (a["r"] + b["r"]); wb = 1 - wa
                    ux, uy = dx / d, dy / d
                    a["x"] -= ux * push * wa; a["y"] -= uy * push * wa
                    b["x"] += ux * push * wb; b["y"] += uy * push * wb
        if not moved:
            break
    return nodes


def render(grouped, sem_coord, pend, total):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPoly, Circle
    from matplotlib.collections import PatchCollection

    # extensão: Brasil, expandida se houver pontos fora
    lon0, lon1, lat0, lat1 = BR_BOX
    for g in grouped.values():
        lon0 = min(lon0, g["lon"] - 4); lon1 = max(lon1, g["lon"] + 4)
        lat0 = min(lat0, g["lat"] - 3); lat1 = max(lat1, g["lat"] + 3)

    fig = plt.figure(figsize=(16.5, 10.5), dpi=150)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.02, 0.02, 0.60, 0.88]); ax.set_aspect(1.10); ax.axis("off")

    # países vizinhos (fundo) + estados do Brasil
    try:
        paises = _load(os.path.join("data", "paises.geojson"))
        pp = [MplPoly(poly[0], closed=True) for f in paises["features"]
              for poly in f["geometry"]["coordinates"]]
        ax.add_collection(PatchCollection(pp, facecolor=LAND_EXT, edgecolor="#E3EAE4", linewidth=0.6, zorder=0))
    except FileNotFoundError:
        pass
    gj = _load(os.path.join("data", "br_states.geojson"))
    patches = [MplPoly(poly[0], closed=True) for f in gj["features"]
               for poly in f["geometry"]["coordinates"]]
    ax.add_collection(PatchCollection(patches, facecolor=LAND, edgecolor="white", linewidth=0.7, zorder=1))
    ax.set_xlim(lon0, lon1); ax.set_ylim(lat0, lat1)

    # bolhas com dodge; escala do raio acompanha o tamanho da moldura
    span = (lon1 - lon0) / (BR_BOX[1] - BR_BOX[0])
    nodes = []
    for nome, g in grouped.items():
        n = len(g["pessoas"])
        r = (0.26 + 0.40 * math.sqrt(n)) * span
        nodes.append({"nome": nome, "n": n, "r": r, "ax": g["lon"], "ay": g["lat"],
                      "x": g["lon"], "y": g["lat"]})
    _dodge(nodes, min_gap=0.08 * span)

    import matplotlib.patheffects as pe
    halo = [pe.withStroke(linewidth=2.6, foreground="white")]
    texts, circles = [], []
    for nd in nodes:
        desloc = math.hypot(nd["x"] - nd["ax"], nd["y"] - nd["ay"])
        if desloc > nd["r"] * 0.35:  # linha-guia + ponto na posição real
            ax.plot([nd["ax"], nd["x"]], [nd["ay"], nd["y"]], color=LINE, lw=1.0, zorder=2)
            ax.add_patch(Circle((nd["ax"], nd["ay"]), 0.09 * span, facecolor=GREEN_D,
                                edgecolor="white", lw=0.5, zorder=3))
        c = Circle((nd["x"], nd["y"]), nd["r"], facecolor=GREEN, edgecolor=GREEN_D,
                   lw=1.2, alpha=.95, zorder=4)
        ax.add_patch(c); circles.append(c)
        ax.text(nd["x"], nd["y"], str(nd["n"]), ha="center", va="center",
                fontsize=8 + min(nd["n"], 10) * 0.3, color="white", fontweight="bold", zorder=5)
        texts.append(ax.text(nd["x"], nd["y"] + nd["r"] + 0.15 * span, nd["nome"].split("/")[0],
                             fontsize=8.3, color=INK, ha="center", va="bottom", zorder=6,
                             path_effects=halo))

    # rótulos: colisão resolvida automaticamente (adjustText); seta liga ao ponto
    try:
        from adjustText import adjust_text
        adjust_text(texts,
                    x=[nd["x"] for nd in nodes], y=[nd["y"] for nd in nodes],
                    objects=circles, ax=ax, expand=(1.25, 1.45),
                    force_text=(0.3, 0.5), force_static=(0.25, 0.45),
                    arrowprops=dict(arrowstyle="-", color=LINE, lw=0.7, shrinkA=2, shrinkB=8),
                    zorder=6)
    except ImportError:
        print("AVISO: adjustText não instalado — rótulos sem ajuste de colisão.")

    today = datetime.date.today().strftime("%d/%m/%Y")
    fig.text(0.035, 0.955, "Onde estamos", fontsize=24, fontweight="bold", color=INK)
    fig.text(0.035, 0.925, f"Distribuição do time por cidade — fonte: Feedz · {today}",
             fontsize=11, color=MUTED)

    px, y = 0.645, 0.875
    fig.text(px, 0.905, "Quem mora onde", fontsize=14, fontweight="bold", color=INK)
    for nome, g in sorted(grouped.items(), key=lambda kv: -len(kv[1]["pessoas"])):
        fig.text(px, y, f"{nome}  ·  {len(g['pessoas'])}", fontsize=10.5, fontweight="bold", color=GREEN_D)
        y -= 0.020
        line = ""
        ps = g["pessoas"]
        for i, p in enumerate(ps):
            line += p + ("  ·  " if i < len(ps) - 1 else "")
            if len(line) > 72 or i == len(ps) - 1:
                fig.text(px + 0.008, y, line, fontsize=8.6, color=INK); y -= 0.0165; line = ""
        y -= 0.008
    if sem_coord:
        fig.text(px, y, "Sem coordenada (fora do desenho)", fontsize=10.5, fontweight="bold", color=GREEN_D)
        y -= 0.020
        for nome, ps in sorted(sem_coord.items()):
            fig.text(px + 0.008, y, f"{nome}: " + ", ".join(ps), fontsize=8.6, color=INK); y -= 0.0165
        y -= 0.008
    if pend:
        fig.text(px, y, f"Cidade pendente no Feedz ({len(pend)})", fontsize=10.5, fontweight="bold", color=MUTED)
        y -= 0.020
        line = ""
        for i, p in enumerate(pend):
            line += p + ("  ·  " if i < len(pend) - 1 else "")
            if len(line) > 72 or i == len(pend) - 1:
                fig.text(px + 0.008, y, line, fontsize=8.6, color=MUTED); y -= 0.0165; line = ""

    ncid = len(grouped) + len(sem_coord)
    fig.text(0.035, 0.045, f"{total} pessoas · {ncid} cidades · gerado automaticamente do Feedz "
             "(somente cidade — nunca endereço)", fontsize=9, color=MUTED)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    return buf.getvalue()


# ---------- Confluence ----------
def confluence_attach(base, auth, pid, fname, data):
    base = base.rstrip("/"); h = {"X-Atlassian-Token": "nocheck"}
    g = requests.get(f"{base}/rest/api/content/{pid}/child/attachment",
                     params={"filename": fname}, auth=auth, timeout=30); g.raise_for_status()
    res = g.json().get("results", [])
    url = (f"{base}/rest/api/content/{pid}/child/attachment/{res[0]['id']}/data" if res
           else f"{base}/rest/api/content/{pid}/child/attachment")
    requests.post(url, headers=h, files={"file": (fname, data, "image/png")},
                  data={"minorEdit": "true"}, auth=auth, timeout=60).raise_for_status()


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def confluence_embed(base, auth, pid, conf, grouped, sem_coord, pend, total):
    base = base.rstrip("/"); today = datetime.date.today().strftime("%d/%m/%Y")
    catalogo = conf.get("catalogo_url", "")
    selo = (f'<blockquote><p>🤖 <strong>Gerado automaticamente</strong> a partir do Feedz em {today}. '
            f'Não edite à mão — cidade errada/faltando se corrige no <strong>perfil do Feedz</strong> '
            f'(Endereço › Município; fora do Brasil, campo Endereço terminando com "..., Cidade, País"). '
            f'<a href="{catalogo}">Ver catálogo de automações</a>.</p></blockquote>')
    intro = ('<p>Cidade onde cada pessoa do time mora — só a cidade, nunca o endereço. '
             'Útil pra encontros regionais, envio de brindes e conhecer a distribuição do time.</p>')
    image = f'<p><ac:image><ri:attachment ri:filename="{FNAME}" /></ac:image></p>'
    rows = ""
    allrows = list(grouped.items()) + [(k, {"pessoas": v}) for k, v in sem_coord.items()]
    for nome, g in sorted(allrows, key=lambda kv: -len(kv[1]["pessoas"])):
        rows += (f"<tr><td><p>{esc(nome)}</p></td><td><p>{len(g['pessoas'])}</p></td>"
                 f"<td><p>{esc(', '.join(g['pessoas']))}</p></td></tr>")
    table = ('<table><tbody><tr><th><p>Cidade</p></th><th><p>Pessoas</p></th><th><p>Quem</p></th></tr>'
             + rows + "</tbody></table>")
    pendhtml = ""
    if pend:
        pendhtml = (f"<h3>Cidade pendente no Feedz ({len(pend)})</h3>"
                    f"<p>Sem município no perfil do Feedz: {esc(', '.join(pend))}.</p>")
    body = selo + intro + image + table + pendhtml
    g = requests.get(f"{base}/rest/api/content/{pid}", params={"expand": "version"}, auth=auth, timeout=30)
    g.raise_for_status(); cur = g.json()
    payload = {"id": pid, "type": "page", "title": cur["title"],
               "version": {"number": cur["version"]["number"] + 1, "message": "Mapa de cidades atualizado"},
               "body": {"storage": {"value": body, "representation": "storage"}}}
    r = requests.put(f"{base}/rest/api/content/{pid}", json=payload, auth=auth, timeout=30)
    r.raise_for_status()
    return r.json()["version"]["number"]


def main():
    conf = _load("config.json")
    xlsx_path = os.environ.get("MAP_XLSX")
    if xlsx_path:
        with open(xlsx_path, "rb") as f:
            data = f.read()
        print(f"Fonte: arquivo local {xlsx_path} (teste).")
    else:
        from feedz_export import fetch_colaboradores_xlsx
        data = fetch_colaboradores_xlsx()
        print("Fonte: export web do Feedz (em memória).")

    pessoas = pessoas_from_xlsx(data)
    grouped, sem_coord, pend, warn = build(pessoas)
    total = len(pessoas)
    png = render(grouped, sem_coord, pend, total)
    with open(FNAME, "wb") as f:
        f.write(png)
    print(f"Pessoas ativas: {total} ({len(pend)} sem cidade). Cidades: {len(grouped) + len(sem_coord)}. "
          f"{FNAME} ({len(png)} bytes).")
    for w in warn:
        print("AVISO:", w)

    if os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"):
        print("DRY_RUN: não publiquei. Baixe o artifact mapa-onde-estamos.")
        return 0
    pid = conf.get("map_page_id")
    if not pid:
        print("ERRO: map_page_id vazio no config.json — crie a página no Confluence e preencha.")
        return 1
    auth = (os.environ["CONFLUENCE_EMAIL"], os.environ["CONFLUENCE_API_TOKEN"])
    base = conf["confluence_base_url"]
    confluence_attach(base, auth, pid, FNAME, png)
    ver = confluence_embed(base, auth, pid, conf, grouped, sem_coord, pend, total)
    print(f"Publicado no Confluence (versão {ver}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

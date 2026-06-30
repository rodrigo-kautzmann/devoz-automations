#!/usr/bin/env python3
"""Gerador de organograma da DevOZ a partir do Feedz.

Lê os colaboradores na API do Feedz, monta a hierarquia pelo gestor direto,
desenha um PNG (caixas + linhas) e o publica como anexo na página Organograma
do Confluence, com um selo de proveniência apontando o catálogo de automações.

NÃO usa nem registra remuneração (campo sensível ignorado de propósito).

Env vars:
  FEEDZ_API_TOKEN       token Bearer (Configurações → Integrações → Chave de Integração API v2)
  CONFLUENCE_EMAIL      e-mail Atlassian
  CONFLUENCE_API_TOKEN  token Confluence
  DRY_RUN               se "1": salva organograma.png local + 1 colaborador de amostra (redigido), NÃO toca no Confluence

Config (não-secreto): config.json (base_url, org_page_id, catalogo_url) e org_style.json (visual).
"""
import os, sys, json, io, datetime
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
FEEDZ_EMPLOYEES = "https://app.feedz.com.br/v2/integracao/employees"


def cfg():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def style():
    with open(os.path.join(HERE, "org_style.json"), encoding="utf-8") as f:
        return json.load(f)


def fetch_feedz():
    token = os.environ["FEEDZ_API_TOKEN"]
    r = requests.get(FEEDZ_EMPLOYEES,
                     headers={"Authorization": f"Bearer {token}",
                              "Content-Type": "application/json"},
                     timeout=60)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("data", [])


def norm(emp):
    def dig(d, *path):
        for k in path:
            d = d.get(k) if isinstance(d, dict) else None
            if d is None:
                return None
        return d
    dept = dig(emp, "department_data", "name") or (emp.get("department") if isinstance(emp.get("department"), str) else dig(emp, "department", "name")) or ""
    cargo = dig(emp, "job_description", "title") or ""
    mgr_email = (dig(emp, "direct_manager", "email") or "").lower()
    mgr_name = dig(emp, "direct_manager", "name") or (emp.get("manager") if isinstance(emp.get("manager"), str) else "") or ""
    return {
        "name": (emp.get("full_name") or emp.get("name") or "").strip(),
        "email": (emp.get("email") or "").lower(),
        "cargo": cargo.strip() or "—",
        "area": dept.strip() or "—",
        "mgr_email": mgr_email,
        "mgr_name": mgr_name,
        "status": emp.get("status", "Ativo"),
    }


def build_rows(people):
    active = [p for p in people if str(p["status"]).lower().startswith("ativ") or p["status"] in (0, "0")]
    by = {p["email"]: p for p in active if p["email"]}
    kids, roots = {}, []
    for p in active:
        m = p["mgr_email"]
        if m and m in by and m != p["email"]:
            kids.setdefault(m, []).append(p)
        else:
            roots.append(p)
    for v in kids.values():
        v.sort(key=lambda x: x["name"])
    roots.sort(key=lambda x: (x["cargo"] != "CEO", x["name"]))
    rows = []
    def walk(p, d):
        rows.append((p, d))
        for c in kids.get(p["email"], []):
            walk(c, d + 1)
    for r in roots:
        walk(r, 0)
    return rows, kids


def render_png(rows, kids, st):
    from PIL import Image, ImageDraw, ImageFont
    c = st["colors"]
    BW, BH, IND, ROW, PAD, SC = st["box_w"], st["box_h"], st["indent"], st["row"], st["pad"], st["scale"]
    maxd = max((d for _, d in rows), default=0)
    W = PAD + maxd * IND + BW + PAD
    H = PAD + len(rows) * ROW + PAD
    img = Image.new("RGB", (W * SC, H * SC), c["bg"])
    dr = ImageDraw.Draw(img)
    try:
        fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13 * SC)
        fr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11 * SC)
    except Exception:
        fb = fr = ImageFont.load_default()
    idx = {p["email"]: i for i, (p, _) in enumerate(rows)}

    def S(v):
        return v * SC

    # conectores
    for i, (p, d) in enumerate(rows):
        if d > 0 and p["mgr_email"] in idx:
            pi = idx[p["mgr_email"]]
            gx = PAD + (d - 1) * IND + 12
            py = PAD + pi * ROW + BH
            cy = PAD + i * ROW + BH // 2
            cx = PAD + d * IND
            dr.line([(S(gx), S(py)), (S(gx), S(cy))], fill=c["line"], width=max(1, SC))
            dr.line([(S(gx), S(cy)), (S(cx), S(cy))], fill=c["line"], width=max(1, SC))
    # caixas
    for i, (p, d) in enumerate(rows):
        x = PAD + d * IND
        y = PAD + i * ROW
        lead = len(kids.get(p["email"], [])) > 0
        dire = st.get("destacar_diretoria") and p["area"].lower().startswith("diretoria")
        fill = c["diretoria_box"] if dire else c["box"]
        outline = c["leader_stroke"] if (lead or dire) else c["stroke"]
        dr.rounded_rectangle([S(x), S(y), S(x + BW), S(y + BH)], radius=S(6),
                             fill=fill, outline=outline, width=max(1, SC))
        dr.text((S(x + 10), S(y + 5)), p["name"][:36], font=fb, fill=c["text"])
        sub = p["cargo"]
        if st.get("show_area"):
            sub += "  ·  " + p["area"]
        dr.text((S(x + 10), S(y + 22)), sub[:44], font=fr, fill=c["subtext"])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def confluence_attach(base, auth, page_id, filename, data):
    base = base.rstrip("/")
    h = {"X-Atlassian-Token": "nocheck"}
    g = requests.get(f"{base}/rest/api/content/{page_id}/child/attachment",
                     params={"filename": filename}, auth=auth, timeout=30)
    g.raise_for_status()
    results = g.json().get("results", [])
    files = {"file": (filename, data, "image/png")}
    if results:
        att_id = results[0]["id"]
        url = f"{base}/rest/api/content/{page_id}/child/attachment/{att_id}/data"
    else:
        url = f"{base}/rest/api/content/{page_id}/child/attachment"
    r = requests.post(url, headers=h, files=files,
                      data={"minorEdit": "true"}, auth=auth, timeout=60)
    r.raise_for_status()


def confluence_embed(base, auth, page_id, filename, catalogo_url, n):
    base = base.rstrip("/")
    today = datetime.date.today().strftime("%d/%m/%Y")
    selo = (f'<ac:structured-macro ac:name="info"><ac:rich-text-body>'
            f'<p><strong>Organograma gerado automaticamente em {today}</strong> '
            f'({n} pessoas) por <code>org-chart</code> (repo devoz-automations), a partir do Feedz. '
            f'View gerada — não edite à mão. '
            f'<a href="{catalogo_url}">Ver catálogo de automações</a>.</p>'
            f'</ac:rich-text-body></ac:structured-macro>')
    img = f'<p><ac:image><ri:attachment ri:filename="{filename}" /></ac:image></p>'
    body = selo + img
    g = requests.get(f"{base}/rest/api/content/{page_id}", params={"expand": "version"}, auth=auth, timeout=30)
    g.raise_for_status()
    cur = g.json()
    payload = {"id": page_id, "type": "page", "title": cur["title"],
               "version": {"number": cur["version"]["number"] + 1, "message": "Organograma (Feedz) atualizado"},
               "body": {"storage": {"value": body, "representation": "storage"}}}
    p = requests.put(f"{base}/rest/api/content/{page_id}", json=payload, auth=auth, timeout=30)
    p.raise_for_status()
    return p.json()["version"]["number"]


def main():
    conf, st = cfg(), style()
    people = [norm(e) for e in fetch_feedz()]
    rows, kids = build_rows(people)
    print(f"{len(rows)} pessoas no organograma (Feedz).")
    png = render_png(rows, kids, st)
    with open("organograma.png", "wb") as f:
        f.write(png)
    print(f"PNG gerado: organograma.png ({len(png)} bytes).")
    dry = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    if dry:
        sample = dict(rows[0][0]) if rows else {}
        print("DRY_RUN: amostra (sem dados sensíveis):", {k: sample.get(k) for k in ("name", "cargo", "area", "mgr_name")})
        print("DRY_RUN: não publiquei no Confluence. Baixe o artifact organograma.png pra avaliar.")
        return
    auth = (os.environ["CONFLUENCE_EMAIL"], os.environ["CONFLUENCE_API_TOKEN"])
    base = conf["confluence_base_url"]
    fname = "organograma.png"
    confluence_attach(base, auth, conf["org_page_id"], fname, png)
    ver = confluence_embed(base, auth, conf["org_page_id"], fname,
                           conf.get("catalogo_url", ""), len(rows))
    print(f"Organograma publicado no Confluence (versão {ver}).")


if __name__ == "__main__":
    sys.exit(main())

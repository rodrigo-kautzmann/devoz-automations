#!/usr/bin/env python3
"""Sincroniza o Diretório (Quem é Quem) da intranet a partir do Google Workspace Admin Directory.

Lê os usuários (Admin SDK), normaliza Department->área (area_map.json), resolve manager
(e-mail->nome) e reescreve a tabela de identidade da página Confluence.

NÃO toca em "dono de quê / backup" — isso vive nos perfis individuais, não nesta tabela.

Env vars necessárias:
  GOOGLE_SA_JSON        conteúdo JSON da service account (com domain-wide delegation)
  GOOGLE_ADMIN_EMAIL    e-mail de admin a personificar (subject)
  CONFLUENCE_BASE_URL   ex.: https://ozmap.atlassian.net/wiki
  CONFLUENCE_EMAIL      e-mail da conta Atlassian
  CONFLUENCE_API_TOKEN  token da API do Confluence
  CONFLUENCE_PAGE_ID    id da página Diretório (ex.: 2246836238)
  WORKSPACE_DOMAIN      opcional, default ozmap.com
  DRY_RUN               se "1/true", apenas imprime o que mudaria (não grava)
"""
import os, sys, json, html, datetime
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/admin.directory.user.readonly"]
HERE = os.path.dirname(os.path.abspath(__file__))


def load_area_map():
    with open(os.path.join(HERE, "area_map.json"), encoding="utf-8") as f:
        d = json.load(f)
    return d["map"], d["pilar_order"]


def get_users():
    info = json.loads(os.environ["GOOGLE_SA_JSON"])
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=SCOPES, subject=os.environ["GOOGLE_ADMIN_EMAIL"])
    svc = build("admin", "directory_v1", credentials=creds, cache_discovery=False)
    users, token = [], None
    while True:
        resp = svc.users().list(customer="my_customer", maxResults=500,
                                orderBy="email", projection="full",
                                pageToken=token).execute()
        users += resp.get("users", [])
        token = resp.get("nextPageToken")
        if not token:
            break
    return users


def extract(u):
    orgs = u.get("organizations") or []
    title = (orgs[0].get("title") if orgs else "") or ""
    dept = (orgs[0].get("department") if orgs else "") or ""
    mgr = ""
    for r in (u.get("relations") or []):
        if r.get("type") == "manager":
            mgr = (r.get("value") or "").lower()
            break
    return {
        "name": (u.get("name", {}) or {}).get("fullName") or "",
        "email": (u.get("primaryEmail") or "").lower(),
        "suspended": bool(u.get("suspended", False)),
        "title": title.strip(),
        "dept": dept.strip(),
        "mgr": mgr,
    }


def build_rows(users, area_map, pilar_order):
    people = [extract(u) for u in users]
    name_by_email = {p["email"]: p["name"] for p in people}
    rows = []
    for p in people:
        if p["suspended"]:
            continue
        if not p["title"] and not p["dept"]:
            continue  # conta de serviço/genérica
        pilar, area = area_map.get(p["dept"], ["(a definir)", p["dept"] or "—"])
        mgr = name_by_email.get(p["mgr"], p["mgr"].split("@")[0] if p["mgr"] else "—")
        rows.append((pilar, area, p["name"], p["title"] or "—", mgr))
    order = {k: i for i, k in enumerate(pilar_order)}
    rows.sort(key=lambda r: (order.get(r[0], 99), r[1], r[2]))
    return rows


def render_body(rows):
    e = html.escape
    today = datetime.date.today().strftime("%d/%m/%Y")
    def panel(kind, inner):
        return (f'<ac:structured-macro ac:name="{kind}"><ac:rich-text-body>'
                f'{inner}</ac:rich-text-body></ac:structured-macro>')
    parts = []
    parts.append(panel("info", '<p>Quem é cada pessoa na DevOZ: cargo, área e do que é dono. '
                                'Complementa o pilar <strong>People</strong> — aqui é o cadastro de todos.</p>'))
    parts.append(panel("warning", f'<p><strong>Atualizado automaticamente em {today}</strong> '
                                   f'({len(rows)} pessoas ativas) a partir do Google Workspace. '
                                   'Esta tabela é uma <strong>view gerada</strong> — não edite à mão. '
                                   '"Dono de quê" e "Backup" vivem nos perfis individuais, não aqui.</p>'))
    parts.append(f"<h2>Diretório — {len(rows)} pessoas</h2>")
    parts.append('<table><tbody><tr>'
                 '<th><p>Pessoa</p></th><th><p>Cargo</p></th><th><p>Pilar</p></th>'
                 '<th><p>Área / subárea</p></th><th><p>Reporta a</p></th></tr>')
    for pilar, area, name, title, mgr in rows:
        parts.append("<tr>" + "".join(f"<td><p>{e(c)}</p></td>" for c in (name, title, pilar, area, mgr)) + "</tr>")
    parts.append("</tbody></table>")
    parts.append(panel("note", '<p>Fonte: Admin Directory (Google Workspace), domínio @ozmap.com. '
                                'Atualização diária via GitHub Actions (skill workspace-directory-sync).</p>'))
    return "".join(parts)


def confluence_update(body):
    base = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
    pid = os.environ["CONFLUENCE_PAGE_ID"]
    auth = (os.environ["CONFLUENCE_EMAIL"], os.environ["CONFLUENCE_API_TOKEN"])
    g = requests.get(f"{base}/rest/api/content/{pid}?expand=version", auth=auth, timeout=30)
    g.raise_for_status()
    cur = g.json()
    payload = {
        "id": pid, "type": "page", "title": cur["title"],
        "version": {"number": cur["version"]["number"] + 1,
                    "message": "Sync automático do Diretório (Google Workspace)"},
        "body": {"storage": {"value": body, "representation": "storage"}},
    }
    p = requests.put(f"{base}/rest/api/content/{pid}", json=payload, auth=auth, timeout=30)
    p.raise_for_status()
    return p.json()["version"]["number"]


def main():
    area_map, pilar_order = load_area_map()
    rows = build_rows(get_users(), area_map, pilar_order)
    body = render_body(rows)
    dry = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    print(f"{len(rows)} pessoas montadas.")
    unmapped = sorted({r[3] for r in rows if r[0] == "(a definir)"})
    if unmapped:
        print("AVISO: departments sem mapeamento em area_map.json:", unmapped)
    if dry:
        print("DRY_RUN: não vou gravar. Primeiras linhas:")
        for r in rows[:10]:
            print("  ", r)
        return
    ver = confluence_update(body)
    print(f"Página atualizada para a versão {ver}.")


if __name__ == "__main__":
    sys.exit(main())

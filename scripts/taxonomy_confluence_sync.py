#!/usr/bin/env python3
"""Sincroniza scripts/taxonomy.json com a página "lista oficial" no Confluence.

Gera uma versão legível da taxonomia (Área › Time › Grupo) e sobrescreve a
página no Confluence via REST API v2. A página deixa claro que é gerada
automaticamente e que alterações devem ser feitas no repositório.

Uso:
    python scripts/taxonomy_confluence_sync.py            # atualiza a página
    python scripts/taxonomy_confluence_sync.py --dry-run  # só imprime o HTML

Env vars (obrigatórias para atualizar):
    ATLASSIAN_EMAIL      e-mail da conta Atlassian
    ATLASSIAN_API_TOKEN  API token (https://id.atlassian.com/manage-profile/security/api-tokens)
Opcionais:
    CONFLUENCE_BASE_URL  default: https://ozmap.atlassian.net/wiki
    CONFLUENCE_PAGE_ID   default: 2286845956
"""

import base64
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path

BASE_URL = os.environ.get("CONFLUENCE_BASE_URL", "https://ozmap.atlassian.net/wiki").rstrip("/")
PAGE_ID = os.environ.get("CONFLUENCE_PAGE_ID", "2286845956")
PAGE_TITLE = "Áreas, Times e Grupos — lista oficial"
TAXONOMY_PATH = Path(__file__).parent / "taxonomy.json"
TAXONOMY_URL = "https://github.com/rodrigo-kautzmann/devoz-automations/blob/main/scripts/taxonomy.json"


def render_html(tax: dict) -> str:
    """Gera o corpo da página em Confluence storage format."""
    areas = [a["area"] for a in tax["areas"]]
    times_by_area: dict[str, list[dict]] = {a: [] for a in areas}
    outros = []  # times cuja área não está na lista de áreas (ex.: Executive)
    for t in tax["times"]:
        (times_by_area.get(t["area"], outros)).append(t)

    rows = []
    for area in areas:
        times = times_by_area[area]
        if not times:
            rows.append((area, "<em>— (área-folha)</em>", "—"))
        for t in times:
            grupos = " · ".join(escape(g) for g in t.get("grupos", [])) or "—"
            rows.append((area, escape(t["time"]), grupos))

    rows_html = "".join(
        f"<tr><td><p><strong>{escape(area)}</strong></p></td>"
        f"<td><p>{time}</p></td><td><p>{grupos}</p></td></tr>"
        for area, time, grupos in rows
    )

    agora = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    outros_txt = ", ".join(f"<em>{escape(t['time'])}</em>" for t in outros)

    # Padrão DevOZ (intranet): selo VISÍVEL de geração + data; detalhes de COMO é gerada
    # ficam num expand COLAPSADO e autossuficiente (sem página externa).
    return (
        "<blockquote><p>🤖 <strong>Gerado automaticamente</strong> · "
        f"Última atualização: {agora}</p></blockquote>"
        '<ac:structured-macro ac:name="expand">'
        '<ac:parameter ac:name="title">Como esta lista é gerada</ac:parameter>'
        "<ac:rich-text-body>"
        f'<p><strong>Fonte:</strong> <a href="{TAXONOMY_URL}">taxonomy.json</a> no '
        "<code>devoz-automations</code>.</p>"
        "<p><strong>Quando roda:</strong> a cada mudança no <code>main</code> "
        "(workflow <code>taxonomy-confluence.yml</code>) · <strong>Automação:</strong> "
        "<code>scripts/taxonomy_confluence_sync.py</code>.</p>"
        "<p><strong>Para alterar:</strong> PR no <code>taxonomy.json</code>. "
        "<strong>Não edite à mão</strong> — a automação sobrescreve.</p>"
        "</ac:rich-text-body></ac:structured-macro>"
        "<p>Nomes de Áreas, Times e Grupos são <strong>sempre em inglês</strong>, conforme o "
        "organograma oficial. A pessoa pertence a um <strong>Time</strong>; o "
        "<strong>Grupo</strong> é o nível fino (opcional); a <strong>Área</strong> é derivada "
        "do Time.</p>"
        "<h2>Lista oficial</h2>"
        "<table><tbody><tr><th><p>Área</p></th><th><p>Time</p></th><th><p>Grupos</p></th></tr>"
        f"{rows_html}</tbody></table>"
        "<h2>Observações</h2><ul>"
        f"<li><p><strong>Executive</strong> é a raiz do organograma (CEO), não uma Área"
        f"{' — times ligados direto a ela: ' + outros_txt if outros_txt else ''}.</p></li>"
        "<li><p><strong>Áreas-folha</strong> (sem Times): as pessoas ficam ligadas direto à "
        "Área.</p></li></ul>"
    )


def api(method: str, path: str, payload: dict | None = None) -> dict:
    email = os.environ["ATLASSIAN_EMAIL"]
    token = os.environ["ATLASSIAN_API_TOKEN"]
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/v2{path}",
        method=method,
        data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main() -> None:
    tax = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    body = render_html(tax)

    if "--dry-run" in sys.argv:
        print(body)
        return

    page = api("GET", f"/pages/{PAGE_ID}")
    new_version = page["version"]["number"] + 1
    api(
        "PUT",
        f"/pages/{PAGE_ID}",
        {
            "id": PAGE_ID,
            "status": "current",
            "title": PAGE_TITLE,
            "body": {"representation": "storage", "value": body},
            "version": {
                "number": new_version,
                "message": f"sync automático de taxonomy.json ({os.environ.get('GITHUB_SHA', 'manual')[:7]})",
            },
        },
    )
    print(f"OK: página {PAGE_ID} atualizada para a versão {new_version}.")


if __name__ == "__main__":
    main()

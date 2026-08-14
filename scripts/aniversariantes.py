#!/usr/bin/env python3
"""Aniversariantes do mês (Feedz -> Confluence).

Busca as pessoas no Feedz, descobre quem faz aniversário no mês e publica uma
página na intranet (espaço Intranet1) no padrão DevOZ (selo de geração + expand
colapsado "como é gerado" + marca verde). IGNORA o ano de nascimento (só dia/mês)
e IGNORA remuneração.

Uso:
    python3 scripts/aniversariantes.py                 # mês atual, publica
    python3 scripts/aniversariantes.py --dry-run       # só imprime o HTML
    python3 scripts/aniversariantes.py --month 12      # dezembro (1-12)
    python3 scripts/aniversariantes.py --keys          # lista os campos do 1º
                                                       # colaborador (achar o
                                                       # campo de nascimento)
    MOCK=arquivo.json python3 scripts/aniversariantes.py --dry-run
                                                       # testa sem token do Feedz

Env (mesma convenção dos outros scripts do repo):
    FEEDZ_API_TOKEN      token do Feedz (Bearer)
    CONFLUENCE_EMAIL     e-mail Atlassian
    CONFLUENCE_API_TOKEN API token Atlassian
Config (não-secreto): scripts/config.json  -> confluence_base_url, aniversariantes_page_id
"""
import os
import re
import sys
import json
import datetime
import urllib.request
import urllib.error
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
BASE = os.environ.get("FEEDZ_BASE", "https://app.feedz.com.br").rstrip("/")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

# Chaves candidatas para a data de nascimento (o campo do Feedz não é documentado
# na API de integração; auto-detectamos por nome + formato de data).
BIRTH_HINTS = ("birth", "nasc", "aniversar", "dob", "dt_nasc", "data_nasc")
# Chaves que parecem data mas NÃO são nascimento (evita falso positivo).
BIRTH_ANTI = ("admiss", "demiss", "deslig", "hire", "termin", "created",
              "updated", "start", "end", "contrat", "last")


# ---------- util ----------
def dig(d, *ks):
    for k in ks:
        d = d.get(k) if isinstance(d, dict) else None
        if d is None:
            return None
    return d


def load_config():
    with open(HERE / "config.json", encoding="utf-8") as f:
        return json.load(f)


def time_area_map():
    try:
        with open(HERE / "taxonomy.json", encoding="utf-8") as f:
            tx = json.load(f)
        return {t["time"]: t["area"] for t in tx["times"]}, {a["area"] for a in tx.get("areas", [])}
    except Exception:
        return {}, set()


def parse_month_day(value):
    """Extrai (mês, dia) de uma string de data. Ignora o ano. None se não casar."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)          # YYYY-MM-DD (ISO)
    if m:
        return int(m.group(2)), int(m.group(3))
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", s)          # DD/MM/YYYY (BR)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.match(r"^(\d{2})-(\d{2})-(\d{4})", s)          # DD-MM-YYYY
    if m:
        return int(m.group(2)), int(m.group(1))
    return None


def find_birthday(emp):
    """Procura a data de nascimento no dict do colaborador. Retorna (mês, dia) ou None."""
    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = str(k).lower()
                if isinstance(v, str) and any(h in kl for h in BIRTH_HINTS) \
                        and not any(a in kl for a in BIRTH_ANTI):
                    md = parse_month_day(v)
                    if md:
                        return md
            for v in obj.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(obj, list):
            for v in obj:
                r = walk(v)
                if r:
                    return r
        return None
    return walk(emp)


def is_active(emp):
    """Ativo = sem data de desligamento/último dia trabalhado."""
    for key in ("dismissal_at", "dismissed_at", "termination_at", "last_working_day",
                "desligamento_at", "resignation_at"):
        if emp.get(key):
            return False
    status = str(emp.get("status", "")).strip().lower()
    if status in ("inactive", "inativo", "desligado", "terminated", "0", "false"):
        return False
    return True


# ---------- Feedz ----------
def fetch_feedz():
    mock = os.environ.get("MOCK")
    if mock:
        with open(mock, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else d.get("data", [])
    token = os.environ.get("FEEDZ_API_TOKEN")
    if not token:
        sys.exit('Defina o token:  export FEEDZ_API_TOKEN="..."  (ou use MOCK=arquivo.json)')
    req = urllib.request.Request(
        f"{BASE}/v2/integracao/employees",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            d = json.load(resp)
    except urllib.error.HTTPError as ex:
        sys.exit(f"Erro HTTP {ex.code}: {ex.read().decode('utf-8', 'ignore')[:300]}")
    return d if isinstance(d, list) else d.get("data", [])


def collect(emps, month):
    """Lista [(dia, nome, cargo, time_ou_area)] dos aniversariantes do mês + estatísticas."""
    t2a, _ = time_area_map()
    people, sem_data = [], []
    for e in emps:
        if not is_active(e):
            continue
        nome = (e.get("full_name") or e.get("name") or "").strip()
        md = find_birthday(e)
        if not md:
            sem_data.append(nome)
            continue
        mes, dia = md
        if mes != month:
            continue
        dept = (dig(e, "department_data", "name")
                or (e.get("department") if isinstance(e.get("department"), str) else "") or "").strip()
        area = t2a.get(dept, dept)
        people.append((dia, nome, area))
    people.sort(key=lambda x: (x[0], x[1].lower()))
    return people, sem_data


# ---------- render (Confluence storage format) ----------
def render_html(people, month, sem_data_count):
    hoje = datetime.date.today().strftime("%d/%m/%Y")
    mes_nome = MESES[month]

    badge = ('<blockquote><p>🤖 <strong>Gerado automaticamente</strong> · '
             f'Última atualização: {hoje}</p></blockquote>')

    if people:
        linhas = "".join(
            f"<tr><td><p><strong>{dia:02d}/{month:02d}</strong></p></td>"
            f"<td><p>🎉 {escape(nome)}</p></td>"
            f"<td><p>{escape(area) or '—'}</p></td></tr>"
            for dia, nome, area in people)
        tabela = (
            '<table data-layout="default"><tbody>'
            '<tr>'
            '<th><p>Dia</p></th><th><p>Quem</p></th>'
            '<th><p>Time / Área</p></th>'
            '</tr>'
            f'{linhas}</tbody></table>')
        resumo = (f'<p><strong>{len(people)}</strong> '
                  f'{"pessoa faz" if len(people) == 1 else "pessoas fazem"} '
                  f'aniversário em <strong>{mes_nome}</strong>. 🎂</p>')
    else:
        tabela = ''
        resumo = (f'<ac:structured-macro ac:name="info"><ac:rich-text-body>'
                  f'<p>Ninguém faz aniversário em <strong>{mes_nome}</strong>.</p>'
                  f'</ac:rich-text-body></ac:structured-macro>')

    aviso_sem_data = ''
    if sem_data_count:
        aviso_sem_data = (
            '<ac:structured-macro ac:name="info"><ac:rich-text-body>'
            f'<p>{sem_data_count} '
            f'{"pessoa está" if sem_data_count == 1 else "pessoas estão"} sem data de '
            'nascimento cadastrada no Feedz e não '
            f'{"aparece" if sem_data_count == 1 else "aparecem"} aqui. '
            'People pode completar o cadastro no Feedz.</p>'
            '</ac:rich-text-body></ac:structured-macro>')

    detalhes = (
        '<ac:structured-macro ac:name="expand">'
        '<ac:parameter ac:name="title">Como esta lista é gerada</ac:parameter>'
        '<ac:rich-text-body>'
        '<p><strong>Fonte:</strong> Feedz (data de nascimento dos colaboradores ativos). '
        'Usamos só <strong>dia e mês</strong> — o ano é ignorado.</p>'
        '<p><strong>Quando roda:</strong> automaticamente todo dia às 05:30 BRT '
        '(a lista vira sozinha na virada do mês), '
        'via GitHub Actions no <code>devoz-automations</code> · '
        '<strong>Automação:</strong> <code>scripts/aniversariantes.py</code> '
        '(workflow <code>aniversariantes.yml</code>).</p>'
        '<p><strong>Para alterar:</strong> a data de nascimento é cadastrada no Feedz. '
        '<strong>Não edite à mão</strong> — a automação sobrescreve.</p>'
        '</ac:rich-text-body></ac:structured-macro>')

    return f'<h2>🎂 Aniversariantes de {mes_nome}</h2>{resumo}{tabela}{badge}{aviso_sem_data}{detalhes}'


# ---------- Confluence ----------
def publish(base, auth, pid, body):
    base = base.rstrip("/")
    g = urllib_get(f"{base}/rest/api/content/{pid}?expand=version", auth)
    cur = g
    ver = cur["version"]["number"] + 1
    payload = {
        "id": str(pid), "type": "page", "title": cur["title"],
        "version": {"number": ver, "message": "Aniversariantes atualizado"},
        "body": {"storage": {"value": body, "representation": "storage"}},
    }
    urllib_put(f"{base}/rest/api/content/{pid}", auth, payload)
    return ver


def _auth_header(auth):
    import base64
    return "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()


def urllib_get(url, auth):
    req = urllib.request.Request(url, headers={"Authorization": _auth_header(auth),
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def urllib_put(url, auth, payload):
    req = urllib.request.Request(
        url, method="PUT", data=json.dumps(payload).encode(),
        headers={"Authorization": _auth_header(auth), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# ---------- main ----------
def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args

    emps = fetch_feedz()

    if "--keys" in args:
        if not emps:
            sys.exit("Nenhum colaborador retornado.")
        print("Campos do 1º colaborador (procure o de nascimento):")
        print(json.dumps(emps[0], indent=2, ensure_ascii=False)[:4000])
        return 0

    month = datetime.date.today().month
    if "--month" in args:
        month = int(args[args.index("--month") + 1])

    people, sem_data = collect(emps, month)
    print(f"{MESES[month]}: {len(people)} aniversariante(s); "
          f"{len(sem_data)} sem data de nascimento no Feedz.")
    for dia, nome, area in people:
        print(f"  {dia:02d}/{month:02d}  {nome}  —  {area or '?'}")
    if sem_data:
        print("Sem data de nascimento:", ", ".join(sorted(sem_data)) or "—")

    body = render_html(people, month, len(sem_data))

    if dry:
        print("\n----- HTML (storage) -----\n")
        print(body)
        return 0

    conf = load_config()
    pid = conf.get("aniversariantes_page_id")
    if not pid:
        sys.exit("Falta 'aniversariantes_page_id' no config.json.")
    auth = (os.environ["CONFLUENCE_EMAIL"], os.environ["CONFLUENCE_API_TOKEN"])
    ver = publish(conf["confluence_base_url"], auth, pid, body)
    print(f"Publicado no Confluence (página {pid}, versão {ver}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

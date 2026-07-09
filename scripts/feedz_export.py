#!/usr/bin/env python3
"""Baixa o export pré-definido "Colaboradores" do Feedz (xlsx) reusando sessão salva.

Por quê assim: o login do Feedz tem reCAPTCHA (login headless é detectado e falha)
e autenticação unificada TOTVS + 2FA. Automatizar o LOGIN foi abandonado.
Em vez disso: você loga UMA vez num navegador de verdade (resolve captcha/2FA),
o script salva o estado da sessão (cookies) num arquivo local, e os downloads
seguintes rodam headless reusando esse estado — sem tocar no login.

A cada download bem-sucedido o estado é re-salvo (cookies rotacionados), então
rodando com regularidade a sessão tende a se manter viva. Quando expirar, o
script avisa e você roda `login` de novo.

Uso:
    python3 feedz_export.py login                # 1x: abre navegador, você loga, salva sessão
    python3 feedz_export.py download -o colaboradores.xlsx
    python3 feedz_export.py download             # sem -o: só valida (mantém em memória)

Estado da sessão: ~/.config/devoz/feedz_state.json (chmod 600; fora de repo).
Override via env FEEDZ_STATE. Sem segredos no ambiente — a sessão É a credencial.
Requer: playwright (pip install playwright && python -m playwright install chromium).
O modo `download` não abre navegador (usa o cliente HTTP do Playwright).
"""
import argparse
import os
import stat
import sys

BASE = "https://app.feedz.com.br"
EXPORT_URL = f"{BASE}/empresa/colaboradores/exportar"
CHECK_URL = f"{BASE}/empresa/relatorios"
STATE_PATH = os.environ.get(
    "FEEDZ_STATE", os.path.expanduser("~/.config/devoz/feedz_state.json"))
LOGIN_WAIT_S = 300  # tempo máximo p/ você completar o login manual
XLSX_MAGIC = b"PK\x03\x04"  # xlsx é um zip


def _save_state(ctx):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    ctx.storage_state(path=STATE_PATH)
    os.chmod(STATE_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 600 — é credencial


def _logged_in(request_ctx):
    """True se a sessão atual acessa uma página autenticada (sem cair no login)."""
    try:
        resp = request_ctx.get(CHECK_URL, max_redirects=5)
        return resp.ok and "relatorios" in resp.url
    except Exception:
        return False


def do_login():
    """Abre um Chromium COM interface; você loga (captcha/2FA e tudo); salva a sessão."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(BASE, wait_until="domcontentloaded")
        print("[login] Faça o login normalmente na janela que abriu "
              "(captcha/2FA inclusos). Eu detecto sozinho quando entrar.")
        for waited in range(0, LOGIN_WAIT_S, 3):
            page.wait_for_timeout(3000)
            if _logged_in(ctx.request):
                _save_state(ctx)
                print(f"[login] OK — sessão salva em {STATE_PATH}")
                browser.close()
                return
        browser.close()
        raise SystemExit(f"[login] Não detectei login em {LOGIN_WAIT_S}s. Tente de novo.")


def fetch_colaboradores_xlsx():
    """Baixa o export usando a sessão salva. Retorna bytes. Levanta erro se expirou."""
    if not os.path.exists(STATE_PATH):
        raise SystemExit(
            f"Sessão não encontrada ({STATE_PATH}). Rode antes:\n"
            f"    python3 {os.path.basename(__file__)} login")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.request.new_context(
            storage_state=STATE_PATH,
            extra_http_headers={"User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")})
        try:
            resp = ctx.get(EXPORT_URL, max_redirects=5, timeout=120000)
            data = resp.body()
            if not resp.ok or not data.startswith(XLSX_MAGIC):
                # Diagnóstico: distingue sessão expirada (redirect p/ login) de
                # bloqueio por IP/WAF (403/challenge). Não vaza dado pessoal —
                # só roda quando NÃO veio xlsx.
                print(f"[debug] status={resp.status} url_final={resp.url} "
                      f"bytes={len(data)} inicio={data[:200]!r}", file=sys.stderr)
                raise SystemExit(
                    "Sessão do Feedz expirou OU o acesso foi bloqueado (veja [debug] acima). "
                    f"Se expirou, rode:\n    python3 {os.path.basename(__file__)} login")
            _save_state(ctx)  # persiste cookies rotacionados → estende a vida da sessão
            return data
        finally:
            ctx.dispose()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="login manual 1x; salva a sessão")
    d = sub.add_parser("download", help="baixa o export reusando a sessão")
    d.add_argument("-o", "--output", help="onde gravar o xlsx (contém CPF/banco — "
                   "cuidado; *.xlsx já está no .gitignore). Sem -o, só valida.")
    args = ap.parse_args()

    if args.cmd == "login":
        do_login()
        return

    data = fetch_colaboradores_xlsx()
    if args.output:
        with open(args.output, "wb") as f:
            f.write(data)
        os.chmod(args.output, stat.S_IRUSR | stat.S_IWUSR)
        print(f"OK: {len(data)} bytes -> {args.output}")
    else:
        print(f"OK: export válido, {len(data)} bytes (em memória; use -o p/ gravar).")


if __name__ == "__main__":
    main()

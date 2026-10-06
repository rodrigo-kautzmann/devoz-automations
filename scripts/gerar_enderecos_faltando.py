#!/usr/bin/env python3
"""Gera a planilha "Endereços faltando no Feedz" (para o People preencher).

Lê o export "Colaboradores" do Feedz e lista as pessoas ATIVAS que não têm cidade
utilizável para o mapa "Onde estamos" (Município vazio e Endereço que não termina em
"..., Cidade, País"). Separa Exterior (DevOZ LLC) de Brasil (DevOZ LTDA) e traz a
instrução certa por linha. Contas sem Unidade (testes) são descartadas.

Uso:
    # 1) baixe dados de agora do Feedz (usa a sessão salva na sua máquina):
    python3 scripts/feedz_export.py download -o scripts/colaboradores.xlsx
    # 2) gere a planilha:
    python3 scripts/gerar_enderecos_faltando.py
    #    (opcional) apontar entrada/saída:
    python3 scripts/gerar_enderecos_faltando.py <colaboradores.xlsx> -o <saida.xlsx>

Sem argumentos: lê scripts/colaboradores.xlsx e grava Enderecos_faltando_Feedz.xlsx
na raiz do projeto. Depende de openpyxl.
"""
import argparse
import datetime
import os
import sys

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))  # raiz do projeto

# marca OZmap
GREEN = "00D256"; DARK = "00A344"; LIGHT = "E8FBF0"; BLACK = "000000"
WHITE = "FFFFFF"; GRAY = "4A4A4A"; FILLIN = "FFF7CC"; EXTRA = "D6F5E3"


def font(sz=10, b=False, color=BLACK):
    return Font(name="Poppins", size=sz, bold=b, color=color)


def local(unidade):
    return "Exterior" if "LLC" in (unidade or "") else "Brasil"


def instr(unidade):
    if local(unidade) == "Exterior":
        return ("Preencher “Residência - Endereço” terminando em "
                "“..., Cidade, País”. Deixar Município/UF vazios.")
    return "Preencher “Residência - Município” + “Residência - UF” (padrão Brasil)."


def parse_ok(end):
    parts = [p.strip() for p in (end or "").split(",") if p.strip()]
    return len(parts) >= 2 and not any(ch.isdigit() for ch in parts[-1])


def ler_pendentes(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    h = [str(x) if x is not None else "" for x in next(rows)]
    need = ["Nome completo", "Email", "Cargo", "Unidade", "Departamento",
            "Residência - Endereço", "Residência - Município", "Residência - UF",
            "Desligamento - Tipo", "Último dia trabalhado"]
    for n in need:
        if n not in h:
            raise SystemExit(f"Coluna '{n}' não está no export — layout do Feedz mudou? Colunas: {h[:15]}...")
    I = {c: h.index(c) for c in need}
    pend = []
    for r in rows:
        if (r[I["Desligamento - Tipo"]] and str(r[I["Desligamento - Tipo"]]).strip()) or \
           (r[I["Último dia trabalhado"]] and str(r[I["Último dia trabalhado"]]).strip()):
            continue
        rec = {c: (str(r[I[c]]).strip() if r[I[c]] is not None else "") for c in need}
        if not (rec["Nome completo"] or rec["Email"]):
            continue
        if rec["Residência - Município"] or parse_ok(rec["Residência - Endereço"]):
            continue
        if not rec["Unidade"].strip():
            continue  # conta de teste sem unidade
        pend.append(rec)
    pend.sort(key=lambda a: (0 if local(a["Unidade"]) == "Exterior" else 1, a["Nome completo"].lower()))
    return pend


def gerar(pend, out):
    fill_h = PatternFill("solid", fgColor=GREEN)
    fill_fillin = PatternFill("solid", fgColor=FILLIN)
    fill_alt = PatternFill("solid", fgColor=LIGHT)
    fill_ex = PatternFill("solid", fgColor=EXTRA)
    fill_white = PatternFill("solid", fgColor=WHITE)
    thin = Side(style="thin", color="BFE9CE")
    bord = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Endereços a preencher"

    ws.merge_cells("A1:K1")
    ws["A1"] = "OZmap · Endereços faltando no Feedz — mapa “Onde estamos”"
    ws["A1"].font = font(15, True, WHITE); ws["A1"].fill = fill_h
    ws["A1"].alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:K2")
    ws["A2"] = ("Estas pessoas ativas estão sem cidade no Feedz, por isso não aparecem no mapa. "
                "Preencha as colunas amarelas e ajuste direto no Feedz. Colunas cinza = como está hoje (só leitura).")
    ws["A2"].font = font(9, False, GRAY); ws["A2"].alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[2].height = 30

    ws.merge_cells("A3:K3")
    ws["A3"] = ("Regra: EXTERIOR (DevOZ LLC) → preencher só “Residência - Endereço” terminando em "
                "“..., Cidade, País” e deixar Município/UF vazios.  BRASIL (DevOZ LTDA) → preencher "
                "“Residência - Município” + “Residência - UF”.")
    ws["A3"].font = font(9, True, DARK); ws["A3"].fill = fill_ex
    ws["A3"].alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[3].height = 32

    headers = ["Nome completo", "E-mail", "Unidade", "Contratação", "Município atual (Feedz)",
               "UF atual", "Endereço atual (Feedz)", "O que preencher no Feedz",
               "Cidade  ✍", "País (se exterior) / UF (se BR)  ✍",
               "Endereço p/ campo “Residência - Endereço” (só exterior)  ✍"]
    hrow = 5
    for j, t in enumerate(headers, 1):
        c = ws.cell(hrow, j, t); c.font = font(9, True, WHITE); c.fill = fill_h
        c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True); c.border = bord
    ws.row_dimensions[hrow].height = 42

    ex = ["(EXEMPLO) Maria Perez", "maria.perez@ozmap.com", "DevOZ LLC", "Exterior", "", "", "",
          instr("DevOZ LLC"), "Lima", "Peru", "Av. Arequipa 1234, Lima, Peru"]
    r = hrow + 1
    for j, v in enumerate(ex, 1):
        c = ws.cell(r, j, v); c.font = font(9, True, GRAY) if j <= 8 else font(9, True, DARK)
        c.fill = fill_ex; c.alignment = Alignment(vertical="center", wrap_text=True); c.border = bord
    ws.row_dimensions[r].height = 28

    r = hrow + 2
    for a in pend:
        row = [a["Nome completo"], a["Email"], a["Unidade"], local(a["Unidade"]),
               a["Residência - Município"], a["Residência - UF"], a["Residência - Endereço"],
               instr(a["Unidade"]), "", "", ""]
        alt = fill_alt if ((r - hrow) % 2 == 0) else fill_white
        for j, v in enumerate(row, 1):
            c = ws.cell(r, j, v); c.border = bord
            c.alignment = Alignment(vertical="center", wrap_text=True)
            if j in (9, 10, 11):
                c.fill = fill_fillin; c.font = font(9, False, BLACK)
            elif j == 4:
                c.fill = alt; c.font = font(9, True, DARK if v == "Exterior" else GRAY)
            else:
                c.fill = alt; c.font = font(9, False, BLACK if j <= 4 else GRAY)
        ws.row_dimensions[r].height = 26
        r += 1

    for j, w in enumerate([30, 26, 13, 12, 17, 7, 26, 34, 16, 20, 34], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A6"
    ws.sheet_view.showGridLines = False

    ws2 = wb.create_sheet("Contexto")
    n_ext = sum(1 for a in pend if local(a["Unidade"]) == "Exterior")
    info = [("Gerado em", datetime.datetime.now().strftime("%d/%m/%Y %H:%M")),
            ("Fonte", "Export “Colaboradores” do Feedz"),
            ("Pessoas listadas", len(pend)),
            ("Exterior (DevOZ LLC)", n_ext),
            ("Brasil (DevOZ LTDA)", len(pend) - n_ext),
            ("Contas de teste", "excluídas (sem Unidade)"),
            ("Runbook", "Cadastrar pessoas no Feedz → seção “Pessoas fora do Brasil”")]
    ws2["A1"] = "Contexto"; ws2["A1"].font = font(13, True, WHITE); ws2["A1"].fill = fill_h
    ws2.merge_cells("A1:B1"); ws2.row_dimensions[1].height = 26
    for i, (k, v) in enumerate(info, 3):
        ws2.cell(i, 1, k).font = font(9, True, BLACK); ws2.cell(i, 2, str(v)).font = font(9, False, GRAY)
    ws2.column_dimensions["A"].width = 24; ws2.column_dimensions["B"].width = 55
    ws2.sheet_view.showGridLines = False

    wb.save(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", nargs="?", default=os.path.join(HERE, "colaboradores.xlsx"),
                    help="export xlsx do Feedz (default: scripts/colaboradores.xlsx)")
    ap.add_argument("-o", "--output", default=os.path.join(PROJ, "Enderecos_faltando_Feedz.xlsx"),
                    help="planilha de saída (default: Enderecos_faltando_Feedz.xlsx na raiz do projeto)")
    args = ap.parse_args()
    if not os.path.exists(args.input):
        raise SystemExit(f"Não achei o export: {args.input}\n"
                         f"Baixe antes: python3 scripts/feedz_export.py download -o scripts/colaboradores.xlsx")
    pend = ler_pendentes(args.input)
    gerar(pend, args.output)
    n_ext = sum(1 for a in pend if local(a["Unidade"]) == "Exterior")
    print(f"OK: {args.output}")
    print(f"  {len(pend)} pessoas ({n_ext} Exterior/LLC, {len(pend) - n_ext} Brasil/LTDA)")


if __name__ == "__main__":
    main()

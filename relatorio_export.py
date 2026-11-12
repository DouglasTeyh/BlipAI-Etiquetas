"""Geracao de relatorios em CSV, XLSX e PDF a partir de uma consulta ja
resolvida pelo financeiro_db.

Formato de entrada (o mesmo que o montador monta):
  {"titulo": str, "colunas": [str], "linhas": [[...]], "subtitulo": str,
   "totais": {coluna: valor}, "rodape": str}

Por que sem pandas: pandas e pesado e nao esta no build do PyInstaller.
openpyxl e reportlab sao Python puro e ja funcionam localmente.
"""

import csv
import io
import os
from datetime import datetime

BRANCO = "#ffffff"
VERDE = "#0f9d63"
VERDE_ESCURO = "#07764a"
CINZA = "#6b7a76"
CINZA_CLARO = "#e3eae7"
TINTA = "#12312a"


def _argb(cor):
    """openpyxl exige ARGB de 8 digitos; as cores do tema sao RRGGBB."""
    cor = (cor or "").lstrip("#")
    if len(cor) == 6:
        return "FF" + cor.upper()
    if len(cor) == 8:
        return cor.upper()
    return "FF000000"


def _formatar(valor, colunas, indice):
    nome = (colunas[indice] if indice < len(colunas) else "").lower()
    eh_numero = any(m in nome for m in ("valor", "saldo", "total", "quantidade", "preco", "preço"))
    if valor is None:
        return ""
    if eh_numero and isinstance(valor, (int, float)):
        return f"{valor:,.2f}"
    if isinstance(valor, float):
        return f"{valor:,.2f}"
    return str(valor)


def _numero(valor):
    if isinstance(valor, (int, float)):
        return valor
    if valor in (None, ""):
        return None
    texto = str(valor).replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def gerar_csv(caminho, dados):
    colunas = dados["colunas"]
    with open(caminho, "w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        if dados.get("titulo"):
            escritor.writerow([dados["titulo"]])
        if dados.get("subtitulo"):
            escritor.writerow([dados["subtitulo"]])
        if dados.get("titulo") or dados.get("subtitulo"):
            escritor.writerow([])
        escritor.writerow(colunas)
        for linha in dados["linhas"]:
            escritor.writerow([_formatar(v, colunas, i) for i, v in enumerate(linha)])
        for coluna, valor in (dados.get("totais") or {}).items():
            escritor.writerow([f"TOTAL {coluna}", valor])
    return caminho


def gerar_xlsx(caminho, dados):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    livro = Workbook()
    folha = livro.active
    folha.title = "Relatorio"[:31]
    colunas = dados["colunas"]
    linha_atual = 1

    if dados.get("titulo"):
        celula = folha.cell(row=linha_atual, column=1, value=dados["titulo"])
        celula.font = Font(size=15, bold=True, color=_argb(VERDE_ESCURO))
        linha_atual += 1
    if dados.get("subtitulo"):
        celula = folha.cell(row=linha_atual, column=1, value=dados["subtitulo"])
        celula.font = Font(size=10, color=_argb(CINZA))
        linha_atual += 1
    if dados.get("titulo") or dados.get("subtitulo"):
        linha_atual += 1

    cabecalho = linha_atual
    for indice, coluna in enumerate(colunas, start=1):
        celula = folha.cell(row=cabecalho, column=indice, value=coluna)
        celula.font = Font(bold=True, color=_argb(BRANCO))
        celula.fill = PatternFill("solid", fgColor=_argb(VERDE))
        celula.alignment = Alignment(horizontal="center", vertical="center")
    linha_atual += 1

    borda_fina = Side(style="thin", color=_argb(CINZA_CLARO))
    for indice_linha, linha in enumerate(dados["linhas"]):
        for indice, valor in enumerate(linha, start=1):
            nome = (colunas[indice - 1] if indice - 1 < len(colunas) else "").lower()
            if any(m in nome for m in ("valor", "saldo", "total", "quantidade", "preco", "preço")):
                numero = _numero(valor)
                celula = folha.cell(row=linha_atual, column=indice,
                                    value=numero if numero is not None else valor)
                celula.number_format = '#,##0.00'
            else:
                celula = folha.cell(row=linha_atual, column=indice, value=valor)
            celula.border = Border(bottom=borda_fina)
            if indice_linha % 2:
                celula.fill = PatternFill("solid", fgColor=_argb("#f7faf9"))
        linha_atual += 1

    if dados.get("totais"):
        linha_totais = linha_atual
        rotulo = folha.cell(row=linha_totais, column=1, value="TOTAL")
        rotulo.font = Font(bold=True)
        rotulo.border = Border(top=Side(style="medium", color=_argb(VERDE)))
        for coluna, valor in dados["totais"].items():
            if coluna in colunas:
                indice = colunas.index(coluna) + 1
                celula = folha.cell(row=linha_totais, column=indice, value=_numero(valor))
                celula.font = Font(bold=True)
                celula.number_format = '#,##0.00'
                celula.border = Border(top=Side(style="medium", color=_argb(VERDE)))
        linha_atual += 1

    for indice, coluna in enumerate(colunas, start=1):
        maior = len(str(coluna))
        for linha in dados["linhas"][:400]:
            if indice - 1 < len(linha):
                maior = max(maior, len(_formatar(linha[indice - 1], colunas, indice - 1)))
        folha.column_dimensions[get_column_letter(indice)].width = min(max(maior + 3, 10), 40)

    folha.freeze_panes = folha.cell(row=cabecalho + 1, column=1)
    if dados.get("rodape"):
        linha_atual += 1
        folha.cell(row=linha_atual, column=1, value=dados["rodape"]).font = Font(size=8, color=_argb(CINZA))
    livro.save(caminho)
    return caminho


def _pdf_bytes(dados):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    colunas = dados["colunas"]
    paginas = landscape(A4) if len(colunas) > 6 else A4
    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=paginas,
        leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
        title=dados.get("titulo") or "Relatorio")
    largura_util = paginas[0] - documento.leftMargin - documento.rightMargin

    estilo_titulo = ParagraphStyle("tit", fontName="Helvetica-Bold", fontSize=15,
                                   textColor=colors.HexColor(VERDE_ESCURO), spaceAfter=2)
    estilo_sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=9,
                                textColor=colors.HexColor(CINZA), spaceAfter=8)
    estilo_rodape = ParagraphStyle("rod", fontName="Helvetica", fontSize=7,
                                   textColor=colors.HexColor(CINZA))
    estilo_cabecalho = ParagraphStyle("cab", fontName="Helvetica-Bold", fontSize=8,
                                      textColor=colors.white)

    elementos = []
    if dados.get("titulo"):
        elementos.append(Paragraph(dados["titulo"], estilo_titulo))
    if dados.get("subtitulo"):
        elementos.append(Paragraph(dados["subtitulo"], estilo_sub))
    if not elementos:
        elementos.append(Spacer(1, 4))

    total_colunas = max(len(colunas), 1)
    largura_coluna = largura_util / total_colunas
    cabecalho = [Paragraph(str(c), estilo_cabecalho) for c in colunas]
    corpo = [cabecalho]
    for linha in dados["linhas"]:
        corpo.append([Paragraph(str(_formatar(v, colunas, i)), estilo_rodape)
                      for i, v in enumerate(linha)])

    # O Table do reportlab 5 copia a lista no __init__, entao a linha de
    # totais precisa entrar ANTES de a Tabela ser criada.
    estilo_tabela = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(VERDE)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 1), 7.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor(CINZA_CLARO)),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7faf9")]),
    ]
    if dados.get("totais"):
        celulas = [""] * total_colunas
        celulas[0] = "TOTAL"
        for coluna, valor in dados["totais"].items():
            if coluna in colunas:
                celulas[colunas.index(coluna)] = f"{_numero(valor) or 0:,.2f}"
        corpo.append([Paragraph(c, estilo_rodape) for c in celulas])
        ultima = len(corpo) - 1
        estilo_tabela += [
            ("FONTNAME", (0, ultima), (-1, ultima), "Helvetica-Bold"),
            ("BACKGROUND", (0, ultima), (-1, ultima), colors.HexColor("#eef5f2")),
            ("LINEABOVE", (0, ultima), (-1, ultima), 0.8, colors.HexColor(VERDE)),
        ]

    tabela = Table(corpo, colWidths=[largura_coluna] * total_colunas, repeatRows=1)
    tabela.setStyle(TableStyle(estilo_tabela))
    elementos.append(tabela)
    if dados.get("rodape"):
        elementos.append(Spacer(1, 6))
        elementos.append(Paragraph(dados["rodape"], estilo_rodape))

    documento.build(elementos)
    return buffer.getvalue()


def gerar_pdf(caminho, dados):
    conteudo = _pdf_bytes(dados)
    with open(caminho, "wb") as arquivo:
        arquivo.write(conteudo)
    return caminho


GERADORES = {"csv": gerar_csv, "xlsx": gerar_xlsx, "pdf": gerar_pdf}


def gerar(caminho, dados, formato):
    formato = (formato or "csv").lower().strip()
    gerador = GERADORES.get(formato)
    if not gerador:
        raise ValueError(f"formato nao suportado: {formato}")
    os.makedirs(os.path.dirname(os.path.abspath(caminho)) or ".", exist_ok=True)
    return gerador(caminho, dados)

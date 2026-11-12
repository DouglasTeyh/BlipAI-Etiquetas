"""Painel AUTOMATA - aplicativo de impressao de etiquetas (5 abas).

Abas:
  - Etiquetas  : fila de impressao com busca, ordenacao, edicao de copias,
                 detalhe do item, pre-visualizacao da etiqueta e totais.
  - Imagens    : busca de produtos, foto do item da fila e visualizador de
                 foto com zoom/pan, navegacao e salvamento.
  - Produtos   : catalogo Bling com busca, paginacao, ordenacao, copiar
                 dados e exportacao CSV (destaque para itens sem SKU).
  - Dashboard  : painel geral com cartoes, graficos de barras (ultimos
                 7 dias e por hora) e ranking de produtos impressos.
  - Configuracoes: conexao com a API, ajuste de offsets, preferencias de
                 impressao/monitoramento e diagnostico.

A impressao em BPLB/RAW usa a mesma logica comprovada no PC da loja.
"""

import csv
import io
import json
import math
import os
import queue
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None
    filedialog = messagebox = ttk = None

# painel_ui e obrigatorio: e dele que vem toda a aparencia do app. Sem ele a
# janela nem chega a abrir, entao e melhor falhar aqui do que estourar um
# AttributeError no meio da montagem.
import imagens_api
import painel_ui as ui
import relatorios
import relatorio_export
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None


def _config_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(_config_dir(), "painel_automata_config.json")
LOG_FILE = os.path.join(_config_dir(), "painel_automata_erros.log")
API_URL_PADRAO = "https://webhook.casadobebeoficial.com.br"
API_TOKEN_PADRAO = "BVv7d1vTLLpHWd5MpiuknLsBW-b5AQFgreoX3Y4SKvc"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
STORES = 1
# Aparece na statusbar. Sobe quando a entrega muda de forma visivel, nao a
# cada ajuste interno.
VERSAO = "2.0"

# ------------------------------------------------------- escopo do app
# O executavel .py faz SO' Etiquetas. O resto (Imagens, Produtos, Dashboard,
# Relatorios, Configuracoes) virou site em webhook.casadobebeoficial.com.br.
# Um unico lugar decide o que e' montado: navbar, paginas e criadores lei
# todos desta tupla, entao reativar uma tela e' adicionar a chave aqui.
PAGINAS_ATIVAS = ("etiquetas",)

# ---------------------------------------------------------------- tema
# Os nomes antigos continuam valendo: as abas ja os usavam. Os valores vem do
# design system (painel_ui), para a paleta ter um unico lugar de verdade.
BG = ui.FUNDO
CARD = ui.BRANCO
SURFACE = ui.TINTA
BORDER = ui.BORDA
BORDER_SOFT = ui.TINTA_BORDA
INK = ui.TINTA_TEXTO
MUTED = ui.TEXTO
FAINT = ui.TEXTO_FRACO
ACCENT = ui.MARCA
ACCENT_DARK = ui.MARCA_ESCURA
ACCENT_SOFT = ui.MARCA_CLARA
ACCENT_TINT = ui.MARCA_TINTA
DANGER = ui.PERIGO
DANGER_SOFT = ui.PERIGO_CLARO
WARN = ui.AVISO
WARN_SOFT = ui.AVISO_CLARO
ROW_EVEN = ui.TINTA
HOVER = "#f1f5f9"
SHADOW = "#e4e9ef"
INFO = ui.INFO
INFO_SOFT = ui.INFO_CLARO
FONTE = "Segoe UI"
FONTE_MONO = "Consolas"


def _font(tamanho=10, peso="normal"):
    """As abas ainda pedem o tamanho em pontos. Mapeia para a escala do
    design system, que e maior e mais legivel que a antiga."""
    return ui.font(_escala_fonte(tamanho), peso)


# a escala antiga usava 8..15; a nova usa 11..26
_ESCALA_FONTE = {8: ui.TEXTO_MENOR - 1, 9: ui.TEXTO_MENOR, 10: ui.TEXTO_BASE,
                 11: ui.TEXTO_BASE, 12: ui.TEXTO_MEDIO, 13: ui.TEXTO_MEDIO,
                 14: ui.TEXTO_MEDIO, 15: ui.TEXTO_GRANDE}


def _escala_fonte(tamanho):
    """Interpola entre os pontos da escala, arredondando para o mais proximo."""
    try:
        tamanho = float(tamanho)
    except (TypeError, ValueError):
        return ui.TEXTO_BASE
    if tamanho in _ESCALA_FONTE:
        return _ESCALA_FONTE[tamanho]
    return max(ui.TEXTO_MENOR - 1,
               min(ui.TEXTO_TITULO, int(round(tamanho + 3))))


def _round_points(x0, y0, x1, y1, r):
    """Pontos de um retangulo com cantos arredondados (poligono suave)."""
    r = max(1, min(r, int((x1 - x0) / 2), int((y1 - y0) / 2)))
    return [
        x0 + r, y0, x1 - r, y0,
        x1, y0, x1, y0 + r,
        x1, y1 - r, x1, y1,
        x1 - r, y1, x0 + r, y1,
        x0, y1, x0, y1 - r,
        x0, y0 + r, x0, y0,
    ]


def desenhar_canto_arredondado(canvas, x0, y0, x1, y1, raio=12, fill=CARD,
                              outline=BORDER, largura=1):
    """Desenha um retangulo de cantos arredondados no canvas."""
    tag = canvas.find_withtag("fundo")
    if tag:
        canvas.delete("fundo")
    pontos = _round_points(x0, y0, x1, y1, raio)
    canvas.create_polygon(pontos, fill=fill, outline=outline, width=largura,
                          smooth=True, splinesteps=24, tags="fundo")


# todos os Cards criados, para sincronizar tamanho em um unico timer
_CARDS = []


class SearchField(tk.Frame):
    """Campo de busca com fundo arredondado, lupa e texto placeholder."""

    def __init__(self, master, texto="Buscar...", comando=None, parent_bg=None,
                 largura=30, variavel=None, **kwargs):
        fundo = parent_bg or (master.cget("bg") or BG)
        super().__init__(master, bg=fundo, highlightthickness=0, bd=0, **kwargs)
        self._raio = 11
        self._fundo = CARD
        self._borda = BORDER
        self.texto = texto
        self.var = variavel if variavel is not None else tk.StringVar(master=self)
        self.var.trace_add("write", lambda *a: self._atualizar_placeholder())

        # Largura explicita e encolhivel. Sem ela o Canvas pede os 378px de
        # default do Tk e virava o item mais largo da linha de filtros: a
        # pagina de relatorios media 1890px vazia e a barra horizontal
        # aparecia sem conteudo que justificasse. O campo cresce de
        # verdade pelo `expand=True` do pack e pelo `sticky="ew"` do grid,
        # entao este valor e' so o piso.
        self._largura_piso = min(largura, 200)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=fundo,
                                height=ui.ALTURA_CONTROLE,
                                width=self._largura_piso)
        self.canvas.pack(fill="both", expand=True)
        self.entry = tk.Entry(self.canvas, textvariable=self.var, bd=0,
                              relief="flat", bg=CARD, fg=INK, insertbackground=ACCENT,
                              font=_font(10), highlightthickness=0)
        self._janela = self.canvas.create_window((34, 2), window=self.entry,
                                                 anchor="nw",
                                                 height=ui.ALTURA_CONTROLE - 6)

        self._on_command = comando
        self._focado = False

        self.canvas.bind("<Configure>", self._redesenhar)
        self.entry.bind("<FocusIn>", self._focar)
        self.entry.bind("<FocusOut>", self._desfocar)
        self.entry.bind("<Return>", self._enter)
        self.canvas.bind("<Button-1>", lambda e: self.entry.focus_set())
        self._atualizar_placeholder()

    def _redesenhar(self, _event=None):
        largura = self.canvas.winfo_width()
        altura = self.canvas.winfo_height()
        if largura < 8 or altura < 8:
            return
        self.canvas.delete("tudo")
        desenhar_canto_arredondado(self.canvas, 1, 1, largura - 1, altura - 1,
                                   self._raio, self._fundo, self._borda, 1)
        # lupa desenhada (circulo + cabo) em vez do glifo "⌕": caractere de
        # fonte some em parte das maquinas e desalinha na vertical
        cor_lupa = ACCENT if self._focado else FAINT
        meio = altura / 2
        self.canvas.create_oval(10, meio - 6, 20, meio + 4, outline=cor_lupa,
                                width=2, tags="icones")
        self.canvas.create_line(19, meio + 3, 24, meio + 8, fill=cor_lupa,
                                width=2, tags="icones")
        self.canvas.create_text(largura - 14, altura / 2,
                                text="x" if self.var.get() else "", fill=FAINT,
                                font=_font(11, "bold"), tags="icones")
        self.canvas.tag_raise("icones")
        self.canvas.itemconfigure(self._janela, width=largura - 66)
        if not self.var.get():
            self.canvas.create_text(34, altura / 2, text=self.texto, fill=FAINT,
                                    font=_font(10), anchor="w", tags="ph")
            self.canvas.tag_lower("ph")

    def _atualizar_placeholder(self):
        self.after_idle(self._redesenhar)

    def _focar(self, _event=None):
        self._focado = True
        self._redesenhar()

    def _desfocar(self, _event=None):
        self._focado = False
        self._redesenhar()

    def _enter(self, _event=None):
        if self._on_command:
            self._on_command()

    def limpar(self):
        self.var.set("")

    def get(self):
        return self.var.get()

    def delete(self, inicio, fim=None):
        valor = self.var.get()
        if inicio == 0 and fim == "end":
            self.var.set("")
            return
        pos = len(valor) if fim in (None, "end") else int(fim)
        self.var.set(valor[:inicio] + valor[pos:])

    def insert(self, indice, texto):
        valor = self.var.get()
        self.var.set(valor[:indice] + str(texto) + valor[indice:])



def escrever_erro(texto):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as log_file:
            log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {texto}\n")
    except OSError:
        pass


def strip_accents(value):
    return "".join(
        char for char in unicodedata.normalize("NFD", str(value or ""))
        if unicodedata.category(char) != "Mn"
    )


def ean13_checksum(code_12):
    total = sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(code_12))
    return str((10 - total % 10) % 10)


def generate_internal_ean13(used_codes):
    import random
    while True:
        code_12 = f"20{random.randint(0, 9999999999):010d}"
        code = code_12 + ean13_checksum(code_12)
        if code not in used_codes:
            used_codes.add(code)
            return code


def _moeda(valor):
    try:
        return f"R$ {float(valor):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return f"R$ {valor}" if str(valor).strip() else "--"


def build_row_data_pplb(labels_in_row, offset_x_mm=0.0, offset_y_mm=0.0, used_codes=None):
    """Gera uma fileira de ate tres etiquetas no layout original 33 x 17 mm."""
    used_codes = used_codes if used_codes is not None else set()

    def format_product_lines(name, limit=20):
        base = re.sub(r'["\r\n]', "", strip_accents(name)).upper().strip()
        words = [word[:limit] for word in base.split()]
        line_one, line_two = "", ""
        for word in words:
            if not line_one:
                line_one = word
            elif len(line_one) + 1 + len(word) <= limit and not line_two:
                line_one += " " + word
            elif not line_two:
                line_two = word
            elif len(line_two) + 1 + len(word) <= limit:
                line_two += " " + word
            else:
                line_two = line_two[:limit - 2].rstrip() + ".."
                break
        return line_one, line_two

    column_definitions = [(12, 37, 37), (288, 37, 37), (564, 37, 37)]
    offset_x = int(float(offset_x_mm) * 8.0)
    offset_y = int(float(offset_y_mm) * 8.0)
    commands = ["n", "N", "q832", "Q136,24", "S2", "D14"]

    for column_index, product in enumerate(labels_in_row[:3]):
        column_x, text_offset, barcode_offset = column_definitions[column_index]
        name = product.get("name", "")
        color = product.get("color", "")
        size = product.get("size", "")
        price = str(product.get("price", "")).strip()
        sku = str(product.get("sku", "")).strip()
        line_one, line_two = format_product_lines(name)

        attr_parts = [
            strip_accents(value).upper().strip()
            for value in (color, size)
            if str(value).strip() and str(value).upper().strip() not in ("UNICO", "DIVERSOS", "SEM MODELO")
        ]
        attributes = " ".join(attr_parts)
        attributes = attributes if len(attributes) <= 18 else attributes[:16].rstrip() + ".."

        price_number = price.replace("R$", "").replace(",", ".").strip()
        try:
            price_text = f"R$ {float(price_number):.2f}".replace(".", ",")
        except ValueError:
            price_text = f"R$ {price}"

        text_x = column_x + text_offset + offset_x
        barcode_x = column_x + barcode_offset + offset_x
        y_line_one = 20 + offset_y
        y_line_two = 36 + offset_y
        y_attributes = 52 + offset_y
        y_price = 68 + offset_y
        y_barcode = 94 + offset_y

        commands.append(f'A{text_x},{y_line_one},0,1,1,1,N,"{line_one.replace(chr(34), "")}"')
        if line_two:
            commands.append(f'A{text_x},{y_line_two},0,1,1,1,N,"{line_two.replace(chr(34), "")}"')
        if attributes:
            commands.append(f'A{text_x},{y_attributes},0,1,1,1,N,"{attributes.replace(chr(34), "")}"')
        commands.append(f'A{text_x},{y_price},0,3,1,1,N,"{price_text.replace(chr(34), "")}"')
        sku_text = (strip_accents(sku).upper()).replace(chr(34), "") or "SEM SKU"
        # Ajuste de truncagem segura para etiqueta térmica 33 x 17 mm:
        # Code128 em barra fina (p5=1) suporta com segurança até 18 caracteres sem estourar as margens.
        sku_text = sku_text[:18].rstrip()

        # SKU como codigo de barras CODE 128 (BPLB).
        # p5=1: barra fina; p6=2: barra grossa; p7=28: altura.
        # p8=B: imprime a leitura humana do SKU abaixo do codigo.
        commands.append(
            f'B{barcode_x},{y_barcode},0,1,1,2,28,B,"{sku_text}"'
        )

    commands.append("P1")
    return ("\r\n".join(commands) + "\r\n").encode("ascii", errors="replace")


def get_windows_printers():
    printers = []
    try:
        import win32print
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        for printer in win32print.EnumPrinters(flags):
            printers.append(printer[2])
    except Exception as error:
        print("Erro ao listar impressoras:", error)
    if not printers:
        try:
            default_printer = win32print.GetDefaultPrinter()
            if default_printer:
                printers.append(default_printer)
        except Exception:
            pass
    if not printers:
        return ["Nenhuma Impressora Encontrada"]

    def _printer_priority(name):
        upper = name.upper().strip()
        if upper == "ELGIN":
            return (0, upper)
        if "ELGIN" in upper:
            return (1, upper)
        if "BTP" in upper and "L42" in upper:
            return (2, upper)
        if "BTP" in upper or "L42" in upper:
            return (3, upper)
        if "ARGOX" in upper or "ZEBRA" in upper:
            return (4, upper)
        return (5, upper)

    printers.sort(key=_printer_priority)
    return printers


# A raiz e um CTk quando o customtkinter esta instalado, para ganhar modo
# escuro e scaling de HighDPI. Sem o pacote cai para tk.Tk e o app abre do
# mesmo jeito: e por isso que a escolha mora no painel_ui e nao aqui.
TkBase = ui.raiz_ctk() if tk is not None else object


class GraficoBarras(tk.Canvas):
    """Canvas que desenha um grafico de barras simples (labels x valores)."""

    def __init__(self, master, altura=170, **kwargs):
        kwargs.setdefault("height", altura)
        # um tk.Canvas pede 378px de largura por padrao e nunca encolhe, o
        # que estourava a coluna do dashboard. Largura 1 deixa o grid
        # encolher o grafico; o fill="both" do pack estica para o espaco real.
        kwargs.setdefault("width", 1)
        kwargs.setdefault("bg", CARD)
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(master, **kwargs)

    def desenhar(self, rotulos, valores, cor=ACCENT, titulo=""):
        self.delete("all")
        if titulo:
            self.create_text(10, 8, anchor="nw", text=titulo, fill=MUTED,
                             font=_font(9, "bold"))
        largura = self.winfo_width()
        base = self.winfo_height() - 26
        if largura < 30:
            self.after(60, lambda: self.desenhar(rotulos, valores, cor, titulo))
            return
        numericos = [int(v or 0) for v in valores]
        if titulo:
            self.create_line(12, base + 14, largura - 12, base + 14, fill=BORDER)
        if not numericos or sum(numericos) <= 0:
            self.create_text(largura // 2, base - 40, text="Sem dados ainda",
                             fill=FAINT, font=_font(11))
            return
        margem = 30
        topo = 24
        vmax = max(numericos)
        n = len(numericos)
        passo = (largura - 2 * margem) / n
        larg_barra = max(6, passo - 10)
        for i, (rotulo, valor) in enumerate(zip(rotulos, numericos)):
            centro = margem + i * passo + passo / 2
            x0 = centro - larg_barra / 2
            alto = (valor / vmax) * (base - topo - 8)
            self.create_rectangle(x0, base - alto, x0 + larg_barra, base,
                                  fill=cor, outline="")
            if valor:
                self.create_text(centro, base - alto - 5, text=str(valor),
                                 fill=INK, font=_font(8, "bold"))
            if rotulo:
                self.create_text(centro, base + 4, text=str(rotulo),
                                 fill=MUTED, font=_font(8))


class _ValorKpi:
    """Adaptador que faz a FaixaKpi falar a lingua antiga do dashboard.

    `_atualizar_dashboard` faz `self.dash_cartoes[chave].set(valor)`, com
    StringVar. Em vez de reescrever toda a logica de atualizacao do
    dashboard, cada KPI da faixa ganha este embrulho com o mesmo `.set`.
    """

    def __init__(self, faixa, indice):
        self._faixa = faixa
        self._indice = indice

    def set(self, valor):
        self._faixa.definir(self._indice, valor)

    def get(self):
        kpi = self._faixa._kpis.get(self._indice)
        return kpi._valor_widget.cget("text") if kpi else ""


class LabelPrinterApp(TkBase):
    def __init__(self):
        if tk is None:
            raise RuntimeError("Este Python nao possui Tkinter. Instale Python 3.8 para Windows com Tk.")
        super().__init__()
        self.title("Painel AUTOMATA")
        self.geometry("1360x860")
        self.minsize(1040, 700)

        self.queue = []
        self.used_codes = set()
        self.offset_x_mm = 0.0
        self.offset_y_mm = 0.0
        self.api_url = ""
        self.api_token = ""
        self.api_seen = set()
        self.batch_size = 15
        self.batch_pause = 3
        self.dash_auto = True
        self.dash_seg = 60
        self.auto_imprimir = False
        self.confirmar_csv = False

        self.fila_termo = ""
        self.fila_ordenar_col = None
        self.fila_ordenar_rev = False
        self.dash_cartoes = {}
        self.dash_timer = None
        self.ultimo_stats = {}
        self._foto_refs = []
        # fila para as threads entregarem callbacks na main thread com seguranca
        self._fila_ui = queue.Queue()
        self.after(80, self._pump_ui)
        self.after(200, self._sync_cards)

        self.imagens_resultados = []
        self.imagens_indice = 0
        # curadoria de imagens (servidor de imagens em imagens_api)
        self.curadoria_url = ""
        self.curadoria_itens = []
        self.curadoria_codigo = ""
        self.curadoria_detalhe = None
        self.curadoria_views = {}
        self._foto_pil = None
        self._foto_bytes = None
        self._foto_url = ""
        self._foto_zoom = 1.0
        self._foto_dx = 0.0
        self._foto_dy = 0.0
        self._foto_drag = None

        self.catalogo_pagina = 1
        self.catalogo_limite = 100
        self.catalogo_resultados = []
        self.catalogo_termo = ""

        self.catalogo_ordenar_col = None
        self.catalogo_ordenar_rev = False

        self.load_config()
        self.create_widgets()
        self.refresh_printers()
        self.start_api_watcher()
        self.carregar_fila_inicial()
        if "dashboard" in PAGINAS_ATIVAS:
            self.atualizar_dashboard()
        self._tick_relogio()
        escrever_erro(f"App iniciado | impressora: {self.printer.get()} | fila: {len(self.queue)}")

    # ==================================================================
    # CONFIGURACAO
    # ==================================================================
    def load_config(self):
        self.offset_x_mm = 0.0
        self.offset_y_mm = 0.0
        self.api_url = API_URL_PADRAO
        self.api_token = API_TOKEN_PADRAO
        self.batch_size = 15
        self.batch_pause = 3
        self.dash_auto = True
        self.dash_seg = 60
        self.auto_imprimir = False
        self.confirmar_csv = False
        self.curadoria_url = imagens_api.URL_PADRAO
        try:
            with open(CONFIG_FILE, encoding="utf-8") as config_file:
                config = json.load(config_file)
            self.offset_x_mm = float(config.get("offset_x_mm", 0.0))
            self.offset_y_mm = float(config.get("offset_y_mm", 0.0))
            self.api_url = str(config.get("api_url", "") or API_URL_PADRAO).strip() or API_URL_PADRAO
            self.api_token = str(config.get("api_token", "") or API_TOKEN_PADRAO).strip() or API_TOKEN_PADRAO
            self.batch_size = max(1, int(config.get("batch_size", 15)))
            self.batch_pause = max(0, float(config.get("batch_pause", 3)))
            self.dash_auto = bool(config.get("dashboard_auto", True))
            self.dash_seg = max(10, int(config.get("dashboard_seg", 60)))
            self.auto_imprimir = bool(config.get("auto_imprimir", False))
            self.confirmar_csv = bool(config.get("confirmar_csv", False))
            self.curadoria_url = (str(config.get("curadoria_url", "") or "")
                                  or imagens_api.URL_PADRAO).rstrip("/")
        except (OSError, ValueError, TypeError):
            pass

        # cache seguro para as threads (Tk nao pode ser usado fora da main thread)
        self._api_url_cache = (self.api_url or API_URL_PADRAO).rstrip("/")
        self._api_token_cache = self.api_token or API_TOKEN_PADRAO
        self._curadoria_url_cache = imagens_api.normalizar_url(self.curadoria_url)

    def save_config(self):
        try:
            self.offset_x_mm = self._ler_offset(self.offset_x_entry)
            self.offset_y_mm = self._ler_offset(self.offset_y_entry)
        except AttributeError:
            pass
        try:
            self.api_url = self.api_url_entry.get().strip()
            self.api_token = self.api_token_entry.get().strip()
        except (AttributeError, tk.TclError):
            pass
        self._api_url_cache = self.api_url.rstrip("/") or API_URL_PADRAO
        self._api_token_cache = self.api_token or API_TOKEN_PADRAO
        preferences = self._ler_preferencias()
        config = {
            "offset_x_mm": float(self.offset_x_mm),
            "offset_y_mm": float(self.offset_y_mm),
            "api_url": self.api_url,
            "api_token": self.api_token,
            "batch_size": int(preferences[0]),
            "batch_pause": float(preferences[1]),
            "dashboard_auto": bool(preferences[2]),
            "dashboard_seg": int(preferences[3]),
            "auto_imprimir": bool(preferences[4]),
            "confirmar_csv": bool(preferences[5]),
            "curadoria_url": imagens_api.normalizar_url(self.curadoria_url),
        }
        self.batch_size = int(preferences[0])
        self.batch_pause = float(preferences[1])
        self.dash_auto = bool(preferences[2])
        self.dash_seg = int(preferences[3])
        self.auto_imprimir = bool(preferences[4])
        self.confirmar_csv = bool(preferences[5])
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as config_file:
                json.dump(config, config_file, indent=2, ensure_ascii=False)
        except OSError:
            pass
        return config

    def _ler_preferencias(self):
        """Preferencias de impressao e de atualizacao.

        Cada valor vem de um campo da aba de Configuracoes quando ele
        existe. Sem essa aba (o .py faz so' Etiquetas), a leitura cai no
        valor ja' carregado do arquivo -- e nao num padrao fixo -- para um
        save disparado por outra tela nao resetar a configuracao."""
        batch = self._ler_int("batch_entry", self.batch_size, 1)
        pause = self._ler_float("pause_entry", self.batch_pause, 0.0)
        seg = self._ler_int("dash_seg_entry", self.dash_seg, 10)
        dash_auto = self._ler_bool("dash_auto_var", self.dash_auto)
        auto_imprimir = self._ler_bool("auto_imprimir_var", self.auto_imprimir)
        csv = self._ler_bool("csv_var", self.confirmar_csv)
        return (batch, pause, dash_auto, seg, auto_imprimir, csv)

    def _ler_int(self, nome, padrao, minimo):
        campo = getattr(self, nome, None)
        if campo is None:
            return int(padrao)
        try:
            return max(minimo, int(float(campo.get().strip() or padrao)))
        except (AttributeError, ValueError, tk.TclError):
            return int(padrao)

    def _ler_float(self, nome, padrao, minimo):
        campo = getattr(self, nome, None)
        if campo is None:
            return float(padrao)
        try:
            texto = campo.get().replace(",", ".").strip()
            return max(minimo, float(texto or padrao))
        except (AttributeError, ValueError, tk.TclError):
            return float(padrao)

    def _ler_bool(self, nome, padrao):
        variavel = getattr(self, nome, None)
        if variavel is None:
            return bool(padrao)
        try:
            return bool(variavel.get())
        except (AttributeError, tk.TclError):
            return bool(padrao)

    @staticmethod
    def _ler_offset(entry):
        try:
            return float(entry.get().replace(",", ".").strip())
        except (AttributeError, ValueError):
            return 0.0

    # ==================================================================
    # WIDGETS / TEMA
    # ==================================================================
    def create_widgets(self):
        self.configure(bg=BG)
        # CTk primeiro: ele precisa saber o modo de aparencia antes de
        # qualquer widget ser criado, senao os temas internos nascem no azul
        # padrao e so mudam no proximo rebuild.
        ui.aplicar_tema_ctk("Light")
        estilo = ui.aplicar_estilos(self, fundo=ui.FUNDO)
        ui.estilo_tabela(estilo)
        # A statusbar entra antes do shell: `conteudo` usa expand=True e
        # consome a altura toda. Empacotada depois, ela fica com 0px.
        self._create_statusbar()
        self._create_shell()
        self._montar_abas()

        # So' monta o que PAGINAS_ATIVAS permite. O executavel .py e' a
        # ferramenta de etiquetas; o restante do painel e' o site.
        if "etiquetas" in PAGINAS_ATIVAS:
            self._create_etiquetas_tab()
        if "imagens" in PAGINAS_ATIVAS:
            self._create_imagens_tab()
        if "produtos" in PAGINAS_ATIVAS:
            self._create_produtos_tab()
        if "dashboard" in PAGINAS_ATIVAS:
            self._create_dashboard_tab()
        if "relatorios" in PAGINAS_ATIVAS and relatorios is not None:
            self._create_relatorios_tab()
        if "config" in PAGINAS_ATIVAS:
            self._create_config_tab()

    # ==================================================================
    # SHELL: navbar no topo + area de paginas embaixo
    # ==================================================================
    def _create_shell(self):
        """Monta o esqueleto do app. A navegacao fica numa barra no topo e
        cada aba ganha titulo e subtitulo proprios, que e o que diferencia
        um SaaS de um app de desktop com abas no topo.

        A barra de paginas (`ui.Abas`) nao desenha tira de abas: quem
        navega e' a navbar. Uma pasta com abas superiores ao lado de uma
        navegacao lateral era duasways de escolher a mesma tela.
        """
        fundo = ui.FUNDO

        self.navbar = ui.Navbar(self, self._grupos_navegacao(),
                                direita=self._acoes_navbar)
        self.navbar.pack(fill="x", side="top")

        conteudo = tk.Frame(self, bg=fundo)
        conteudo.pack(fill="both", expand=True)
        self._conteudo = conteudo

        # barra superior: contexto da pagina + estado global
        barra = tk.Frame(conteudo, bg=ui.BRANCO, width=ui.LARGURA_MINIMA,
                      height=ui.ALTURA_BARRA)
        barra.pack(fill="x")
        barra.pack_propagate(False)
        tk.Frame(barra, bg=ui.BORDA, width=ui.LARGURA_MINIMA,
                 height=1).pack(fill="x", side="bottom")

        esquerda = tk.Frame(barra, bg=ui.BRANCO)
        esquerda.pack(side="left", padx=(ui.ESPACO_6, ui.ESPACO_4))

        # Leitura de duas linhas: contexto pequeno em cima, titulo grande
        # embaixo. O titulo em 16 semibold e o que diz em que pagina voce esta;
        # antes ele era 13 bold e competia de igual para igual com o conteudo.
        self.migalha = tk.Label(esquerda, text="Painel AUTOMATA", bg=ui.BRANCO,
                                fg=ui.TEXTO_FRACO,
                                font=ui.font(ui.TEXTO_MENOR), anchor="w")
        self.migalha.pack(anchor="w")
        self.migalha_titulo = tk.Label(esquerda, text="", bg=ui.BRANCO,
                                       fg=ui.TINTA_TEXTO,
                                       font=ui.font(ui.TEXTO_GRANDE, "bold"),
                                       anchor="w")
        self.migalha_titulo.pack(anchor="w")

        direita = tk.Frame(barra, bg=ui.BRANCO)
        direita.pack(side="right", padx=ui.ESPACO_6)

        # O selo antigo tinha largura FIXA de 190px e um texto de 12 letras:
        # 150px de bloco vazio. O indicador desenha o ponto e encolhe ate o
        # texto, com o detalhe completo em tooltip.
        self.api_status = ui.IndicadorStatus(
            direita, "Conectando", ui.AVISO,
            command=self._reconectar_api, tooltip="Conectando a API...")
        self.api_status.pack(side="left", pady=(ui.ESPACO_3, ui.ESPACO_3))
        self._api_texto = "Conectando"
        self._api_cor = ui.AVISO
        self.after(60, self._desenhar_api_status)

        # O relogio NAO e criado aqui. Ele e metrica, nao contexto: nasce em
        # _create_statusbar. Antes ele vivia neste cabecalho e ocupava 204px
        # brigando com o titulo da pagina.

        # area de paginas: um container por aba, com cabecalho proprio
        paginas = tk.Frame(conteudo, bg=fundo)
        paginas.pack(fill="both", expand=True)
        self._paginas = paginas

        # nao e' ttk.Notebook: a tira de abas do ttk virava uma pasta com
        # abas superiores duplicando a navegacao da navbar
        self.notebook = ui.Abas(paginas, fundo=fundo)
        self.notebook.pack(fill="both", expand=True)

        self._scroll_abas = {}
        self._paginas_por_chave = {}
        for chave in self._ordem_paginas():
            # sem `pack` de proposito: quem posiciona a pagina e' a
            # `ui.Abas`, com `place`. Um widget com pack E place fica
            # registrado nos dois gerenciadores, e as pagunas antigas
            # voltavam a aparecer por cima da atual -- quatro telas
            # empilhadas no mesmo lugar.
            rolagem = ui.AreaRolavel(self.notebook, fundo=fundo)
            pagina = tk.Frame(rolagem.body, bg=fundo)
            pagina.pack(fill="both", expand=True)

            cabecalho = ui.CabecalhoPagina(pagina)
            # 16px em vez de 32: o proprio padding estourava a janela nas
            # paginas mais largas (dashboard)
            cabecalho.pack(fill="x", padx=ui.ESPACO_4,
                           pady=(ui.ESPACO_5, ui.ESPACO_4))
            conteudo_pagina = tk.Frame(pagina, bg=fundo)
            conteudo_pagina.pack(fill="both", expand=True,
                                 padx=ui.ESPACO_4, pady=(0, ui.ESPACO_5))

            setattr(self, f"tab_{chave}", conteudo_pagina)
            setattr(self, f"pagina_{chave}", pagina)
            setattr(self, f"cabecalho_{chave}", cabecalho)
            # a navegacao e pela navbar: as abas ficam sem rotulo para nao
            # sobrar faixa nenhuma no topo. No Windows o showtabs=False do
            # estilo ja remove a faixa inteira; o texto vazio cobre o resto.
            self.notebook.add(rolagem, text="")
            # o corpo rolavel guarda o mapa de abas antigo, que outros codigos
            # ainda consultam (ex.: _selecionar_aba)
            self._scroll_abas[conteudo_pagina] = rolagem
            self._paginas_por_chave[chave] = (pagina, conteudo_pagina, cabecalho)

    def _area_da_pagina(self, chave):
        """A AreaRolavel que envolve a pagina. Serve para as tabelas reagirem
        a mudanca de largura da janela."""
        conteudo = getattr(self, f"tab_{chave}", None)
        area = self._scroll_abas.get(conteudo) if conteudo is not None else None
        return area or self._conteudo

    def _ordem_paginas(self):
        return list(PAGINAS_ATIVAS)

    def _grupos_navegacao(self):
        """Monta os grupos da navbar, ja ligando cada item a sua pagina.
        So' entra o que esta' em PAGINAS_ATIVAS; grupo que fica vazio some
        por inteiro para nao sobrar titulo nem separador solto."""
        grupos = []
        for titulo, itens in ui.GRUPOS:
            montados = []
            for nome, glifo, chave, descricao in itens:
                if chave not in PAGINAS_ATIVAS:
                    continue
                if chave == "relatorios" and relatorios is None:
                    continue
                montados.append((nome, glifo, chave, descricao,
                                 lambda c=chave: self._ir_para(c)))
            if montados:
                grupos.append((titulo, montados))
        return grupos

    def _acoes_navbar(self, navbar):
        """Lado direito da navbar: estado da API e um atalho para reconectar.

        Na barra lateral isso era um bloco de 86px empilhado embaixo dos
        itens. Na navbar vira um par horizontal: o indicador (que encolhe
        ate o texto) e o botao.
        """
        caixa = tk.Frame(navbar, bg=ui.NAV_FUNDO)
        self.navbar_api_texto = tk.Label(caixa, text="verificando...",
                                          bg=ui.NAV_FUNDO, fg=ui.TEXTO,
                                          font=ui.font(ui.TEXTO_MENOR),
                                          anchor="e")
        self.navbar_api_texto.pack(side="left", padx=(0, ui.ESPACO_3))

        botao = ui.Botao(caixa, "Reconectar", self._reconectar_api,
                         variante="secundario", tamanho=ui.TEXTO_MENOR,
                         parent_bg=ui.NAV_FUNDO)
        botao.pack(side="left")
        self.navbar_botao_api = botao
        return caixa

    def _montar_abas(self):
        """Deixa cada pagina com titulo e subtitulo e abre a primeira."""
        for titulo, itens in ui.GRUPOS:
            for nome, _glifo, chave, descricao in itens:
                if chave not in self._paginas_por_chave:
                    continue
                _pagina, _conteudo, cabecalho = self._paginas_por_chave[chave]
                cabecalho.definir(nome, descricao)
        self._ir_para("etiquetas")

    def _ir_para(self, chave):
        """Navegacao pela navbar. Aplica a selecao das abas e atualiza
        o breadcrumb da barra superior."""
        if chave not in self._paginas_por_chave:
            return
        _pagina, conteudo, cabecalho = self._paginas_por_chave[chave]
        rolagem = self._scroll_abas.get(conteudo)
        try:
            self.notebook.select(rolagem if rolagem is not None else conteudo)
        except tk.TclError:
            pass
        self.navbar.marcar_ativo(chave)
        self._pagina_ativa = chave
        self.migalha.configure(text="Painel AUTOMATA")
        self.migalha_titulo.configure(text=cabecalho.titulo_var.get())
        if rolagem is not None:
            # a aba pode ter ficado escondida enquanto a janela mudava de
            # tamanho: so agora que ela aparece da para medir as colunas
            # e decidir se precisa de barra. Sem o reexibir, a pagina voltava
            # sem barra e o conteudo mais alto ficava inalcancavel.
            rolagem.reexibir()

    def _selecionar_aba(self, aba):
        """Mantido por compatibilidade: o codigo antigo (e os testes) chamam
        pelo widget da aba. Descobre a chave e delega para _ir_para."""
        for chave, (_pagina, conteudo, _cabecalho) in self._paginas_por_chave.items():
            if conteudo is aba:
                self._ir_para(chave)
                return
        # tambem aceita o wrapper de rolagem da area rolavel
        for chave, (_pagina, conteudo, _cabecalho) in self._paginas_por_chave.items():
            if self._scroll_abas.get(conteudo) is aba:
                self._ir_para(chave)
                return

    def _desenhar_api_status(self):
        """O desenho do indicador e do proprio widget. Este metodo so
        empurra o texto e a cor que a camada de rede mudou."""
        indicador = getattr(self, "api_status", None)
        if indicador is None:
            return
        try:
            indicador.atualizar(texto=self._api_texto, cor=self._api_cor)
        except tk.TclError:
            pass

    def _tick_relogio(self):
        try:
            self.relogio.configure(
                text=time.strftime("%A, %d/%m/%Y  %H:%M:%S").capitalize())
        except tk.TclError:
            return
        except AttributeError:
            return
        self.after(1000, self._tick_relogio)

    # --------- ponte segura entre threads e a main thread do Tk ---------
    def _na_ui(self, funcao, *args, **kwargs):
        """Agenda um callback para a main thread. Seguro chamar de qualquer
        thread: nao usa Tk.after direto (que exige o loop principal ativo)."""
        self._fila_ui.put((funcao, args, kwargs))

    def _pump_ui(self):
        try:
            while True:
                funcao, args, kwargs = self._fila_ui.get_nowait()
                try:
                    funcao(*args, **kwargs)
                except tk.TclError:
                    pass
        except queue.Empty:
            pass
        try:
            self.after(80, self._pump_ui)
        except tk.TclError:
            pass

    def _sync_cards(self):
        """Um unico timer mantem todos os Cards com o tamanho do conteudo.
        Isso resolve o caso em que o conteudo de um card aninhado cresce
        sem gerar evento de <Configure> nos cards pais."""
        vivos = []
        for card in _CARDS:
            try:
                if not card.winfo_exists():
                    continue
                card._propagar()
                vivos.append(card)
            except tk.TclError:
                continue
        _CARDS[:] = vivos
        try:
            self.after(200, self._sync_cards)
        except tk.TclError:
            pass

    def _create_statusbar(self):
        """Barra de contexto do rodape. Fica do lado de fora da navbar para
        nao competir com a hierarquia da pagina."""
        barra = tk.Frame(self, bg=ui.FUNDO_ABAIXO,
                         width=ui.LARGURA_MINIMA, height=30)
        # `side="bottom"` e obrigatorio: `conteudo` usa expand=True e enche
        # toda a altura restante. Se a statusbar fosse empacotada depois, o
        # package ja teria dado 0px de altura para ela. Por isso
        # create_widgets chama _create_statusbar ANTES de _create_shell.
        barra.pack(side="bottom", fill="x")
        barra.pack_propagate(False)
        # O divisor vai DEPOIS, para o `side="bottom"` do proximo reserve a
        # faixa logo ACIMA da statusbar. Empacotado antes, ele desceria para
        # baixo dela.
        tk.Frame(self, bg=ui.BORDA, width=ui.LARGURA_MINIMA,
                 height=1).pack(side="bottom", fill="x")

        # O ponto era o glifo U+25CF num Label. Em Segoe UI esse caractere nao
        # existe e o Windows caia em fonte de reserva, entao a "luzinha de
        # status" virava caixa vazia. Agora e um circulo desenhado.
        self.status_dot = ui.PontoStatus(barra, ui.MARCA)
        self.status_dot.pack(side="left", padx=(ui.ESPACO_4, ui.ESPACO_2))

        self.status = tk.StringVar(value="Pronto")
        self.status_label = tk.Label(barra, textvariable=self.status,
                                     bg=ui.FUNDO_ABAIXO, fg=ui.TEXTO,
                                     font=ui.font(ui.TEXTO_MENOR))
        self.status_label.pack(side="left")

        # Esquerda da direita: fila. E a metrica que a pessoa mais consulta do
        # app inteiro e nao tinha lugar nenhum na tela.
        self.status_fila = tk.Label(barra, text="", bg=ui.FUNDO_ABAIXO,
                                    fg=ui.TEXTO_FRACO,
                                    font=ui.font(ui.TEXTO_MENOR))
        self.status_fila.pack(side="left", padx=(ui.ESPACO_5, 0))

        # Direita: versao, relogio e as contagens de sempre.
        self.status_versao = tk.Label(barra, text=f"v{VERSAO}",
                                      bg=ui.FUNDO_ABAIXO, fg=ui.TEXTO_FRACO,
                                      font=ui.font(ui.TEXTO_MENOR))
        self.status_versao.pack(side="right", padx=(0, ui.ESPACO_4))
        self.status_direita = tk.Label(barra, text="", bg=ui.FUNDO_ABAIXO,
                                       fg=ui.TEXTO, font=ui.font(ui.TEXTO_MENOR))
        self.status_direita.pack(side="right", padx=ui.ESPACO_4)
        self.status_fps = tk.Label(barra, text="", bg=ui.FUNDO_ABAIXO,
                                   fg=ui.TEXTO_FRACO, font=ui.font(ui.TEXTO_MENOR))
        self.status_fps.pack(side="right", padx=ui.ESPACO_3)
        self.status_apoio = tk.Label(barra, text="", bg=ui.FUNDO_ABAIXO,
                                     fg=ui.TEXTO_FRACO,
                                     font=ui.font(ui.TEXTO_MENOR))
        self.status_apoio.pack(side="right", padx=ui.ESPACO_3)

        # O relogio e criado AQUI, com a statusbar como master. Quando ele
        # vivia no cabecalho, um `pack` novo nao o trazia para ca: no Tk o
        # container e o master do widget, nao o metodo que chama o pack.
        self.relogio = tk.Label(barra, text="", bg=ui.FUNDO_ABAIXO,
                                fg=ui.TEXTO_FRACO,
                                font=ui.font(ui.TEXTO_MENOR))
        self.relogio.pack(side="right", padx=(ui.ESPACO_2, ui.ESPACO_4))

    def _atualizar_status_fila(self):
        """Contagem da fila na statusbar. Fica em metodo proprio porque e
        chamado de dois lugares: ao carregar a fila e depois de cada
        remocao/limpeza."""
        try:
            if not self.queue:
                self.status_fila.configure(text="fila vazia")
                return
            etiquetas = 0
            for produto in self.queue:
                try:
                    etiquetas += max(1, int(float(produto.get("copies") or 1)))
                except (TypeError, ValueError):
                    etiquetas += 1
            itens = len(self.queue)
            self.status_fila.configure(
                text=f"{itens} {'item' if itens == 1 else 'itens'} na fila"
                     f" · {etiquetas} "
                     f"{'etiqueta' if etiquetas == 1 else 'etiquetas'}")
        except (tk.TclError, AttributeError):
            pass

    def _atualizar_status_direita(self):
        pendentes = self.ultimo_stats.get("pendentes", "--")
        hoje = self.ultimo_stats.get("impressos_periodo", "--")
        self.status_direita.configure(
            text=f"Fila: {len(self.queue)}  |  Pendentes API: {pendentes}  |  Impressos hoje: {hoje}")
        try:
            self.status_apoio.configure(text=time.strftime("atualizado %H:%M:%S"))
        except tk.TclError:
            pass

    # ==================================================================
    # ABA ETIQUETAS
    # ==================================================================
    def _create_etiquetas_tab(self):
        """Fila de impressao, montada em tres faixas: filtros, trabalho e
        acao.

        Antes a tela tinha barra de busca + quatro botoes soltos na mesma
        linha, cartao da tabela, cartao do detalhe e cartao do rodape: quatro
        molduras para uma acao. Agora a acao principal esta na propria
        faixa de filtros, a tabela e o detalhe dividem o espaco com pesos
        declarados, e o rodape e uma linha so de impressora + total.
        """
        tela = ui.Tela(self.tab_etiquetas, linhas=3)
        # a Tela e' o unico filho gerenciado da pagina, entao `pack` aqui
        # nao briga com o `grid` dela. Sem este fill/expand a tela inteira
        # fica com 1px e todo filho reporta largura 1.
        tela.pack(fill="both", expand=True)
        tela.linha(1, peso=1)

        acoes = self.cabecalho_etiquetas.acoes
        self.fila_contagem = tk.StringVar(value="0 itens")
        tk.Label(acoes, textvariable=self.fila_contagem, bg=ui.FUNDO,
                 fg=ui.TEXTO_FRACO,
                 font=ui.font(ui.TEXTO_MENOR)).pack(side="left")

        # --- faixa 1: busca e acoes, tudo na base para a barra alinhar
        filtros = ui.BarraFiltros(tela, colunas=2)
        tela.celula(filtros, 0, 0)
        self.fila_busca_var = tk.StringVar()
        self.fila_busca_var.trace_add("write", lambda *a: self._render_fila())
        self.fila_busca = SearchField(
            filtros, texto="sku, nome, cor...",
            parent_bg=ui.FUNDO, largura=240,
            variavel=self.fila_busca_var)
        filtros.campo("Buscar na fila", self.fila_busca)

        acoes_dir = tk.Frame(filtros, bg=ui.FUNDO)
        # `acoes` ja posiciona na linha dos campos; so o sticky muda
        filtros.acoes(coluna=1).grid(sticky="sew")
        barra = ui.BarraBotoes(acoes_dir, fundo=ui.FUNDO, espaco=ui.ESPACO_2)
        barra.pack(side="left", anchor="s")
        for texto, comando in (("Selecionar tudo", self.selecionar_todos_fila),
                               ("Editar copias", self.editar_copias_selecionadas),
                               ("Duplicar", self.duplicar_selecionado),
                               ("Exportar CSV", self.exportar_fila_csv)):
            barra.criar(texto, comando, variante="secundario",
                        tamanho=ui.TEXTO_BASE, parent_bg=ui.FUNDO)
        self.botao_imprimir_selecionadas = ui.Botao(
            acoes_dir, "Imprimir selecionadas",
            lambda: self.print_queue(somente_selecionadas=True),
            variante="primario", parent_bg=ui.FUNDO)
        self.botao_imprimir_selecionadas.pack(side="left", padx=(ui.ESPACO_3, 0))

        # --- faixa 2: tabela (3) ao lado do detalhe (1)
        trabalho = tela.secao(1, 0, peso_linha=1)
        trabalho.coluna(0, peso=3, minima=420)
        trabalho.coluna(1, peso=1, minima=260)
        trabalho.linha(0, peso=1)
        self._criar_tabela_fila(trabalho)
        self._criar_detalhe_fila(trabalho)

        # --- faixa 3: impressora e total, uma linha
        self._criar_rodape_fila(tela)

    def _criar_tabela_fila(self, parent):
        colunas = ("sku", "barcode", "name", "brand", "model", "color", "size",
                   "price", "copies")
        painel = ui.Painel(parent, colunas, titulo="Fila de impressao",
                           fundo=ui.FUNDO)
        parent.celula(painel, 0, 0)
        self.painel_fila = painel
        self.table = painel.montar_tabela(
            altura=10, area=self._area_da_pagina("etiquetas"))
        rotulos = {"sku": "SKU", "barcode": "Codigo de barras", "name": "Nome",
                   "brand": "Marca", "model": "Modelo", "color": "Cor",
                   "size": "Tam", "price": "Preco", "copies": "Copias"}
        larguras = {"sku": 150, "barcode": 130, "name": 240, "brand": 110,
                    "model": 100, "color": 90, "size": 70, "price": 90,
                    "copies": 70}
        for coluna in colunas:
            self.table.heading(coluna, text=rotulos[coluna],
                               command=lambda c=coluna: self._ordenar_fila(c))
            # minwidth baixo + stretch: a tabela encolhe em vez de estourar
            self.table.column(coluna, width=larguras[coluna], minwidth=46,
                              anchor="w", stretch=True)
        self.table.column("price", anchor="e")
        self.table.column("copies", anchor="center")
        self.table.tag_configure("odd", background=ui.BRANCO)
        self.table.tag_configure("even", background=ui.TINTA)
        self.table.tag_configure("sem_sku", background=ui.AVISO_CLARO,
                                 foreground="#92600f")
        self.table.bind("<<TreeviewSelect>>", lambda e: self._atualizar_detalhe())
        self.table.bind("<Double-1>", lambda e: self.editar_copias_selecionadas())
        self.table.bind("<Delete>", lambda e: self.remove_selected())

    def _criar_detalhe_fila(self, parent):
        bloco = ui.Bloco(parent, titulo="Detalhe", fundo=ui.FUNDO)
        parent.celula(bloco, 0, 1)
        corpo = bloco.corpo
        corpo.rowconfigure(1, weight=1)

        self.detalhe_texto = tk.Label(corpo, text="Selecione um item na fila.",
                                      bg=ui.FUNDO, fg=ui.TEXTO,
                                      font=ui.font(ui.TEXTO_MENOR),
                                      justify="left", wraplength=230, anchor="w")
        self.detalhe_texto.grid(row=0, column=0, sticky="ew")

        self.previa_caixa = tk.Frame(corpo, bg=ui.TINTA)
        self.previa_caixa.grid(row=1, column=0, sticky="nsew",
                               pady=(ui.ESPACO_3, 0))
        self.canvas_previa = tk.Canvas(self.previa_caixa, width=240, height=126,
                                       bg=ui.TINTA, highlightthickness=0, bd=0)
        self.canvas_previa.pack(fill="both", expand=True,
                                padx=ui.ESPACO_2, pady=ui.ESPACO_2)

    def _criar_rodape_fila(self, tela):
        rodape = ui.BarraFiltros(tela, colunas=3, fundo=ui.BRANCO)
        tela.celula(rodape, 2, 0)
        rodape._espaco = ui.ESPACO_2

        impressora = tk.Frame(rodape, bg=ui.BRANCO)
        rodape.campo("Impressora", impressora, coluna=0, hint="usada ao imprimir")
        impressora.columnconfigure(0, weight=1)
        self.printer = tk.StringVar()
        self.printer_box = ttk.Combobox(impressora, textvariable=self.printer,
                                        state="readonly", width=20)
        self.printer_box.grid(row=0, column=0, sticky="ew")
        ui.Botao(impressora, "Atualizar", self.refresh_printers,
                 variante="fantasma", tamanho=ui.TEXTO_MENOR,
                 parent_bg=ui.BRANCO).grid(row=0, column=1, padx=(ui.ESPACO_2, 0))

        self.fila_total_label = tk.Label(rodape, text="", bg=ui.BRANCO,
                                         fg=ui.TEXTO, anchor="e",
                                         font=ui.font(ui.TEXTO_BASE))
        rodape.campo("Total", self.fila_total_label, coluna=1)

        acao = rodape.acoes(coluna=2)
        self.botao_imprimir = ui.Botao(acao, "IMPRIMIR FILA",
                                       self.print_queue, variante="primario",
                                       tamanho=ui.TEXTO_BASE, peso="bold",
                                       altura=42, parent_bg=ui.BRANCO)
        self.botao_imprimir.pack(side="right")

        # acoes destrutivas ficam na propria faixa, sem cartao em volta
        destrutivas = tk.Frame(rodape, bg=ui.BRANCO)
        destrutivas.grid(row=1, column=0, columnspan=3, sticky="ew")
        barra = ui.BarraBotoes(destrutivas, fundo=ui.BRANCO, espaco=ui.ESPACO_2)
        barra.pack(side="left")
        for texto, comando, variante in (
                ("Remover selecionadas", self.limpar_nova_fila_selecionadas,
                 "secundario"),
                ("Duplicar item", self.duplicar_selecionado, "secundario"),
                ("Limpar fila", self.clear_queue, "perigo")):
            barra.criar(texto, comando, variante=variante,
                        tamanho=ui.TEXTO_MENOR, parent_bg=ui.BRANCO)

    def _render_fila(self):
        if not hasattr(self, "table"):
            return
        self.table.delete(*self.table.get_children())
        termo = strip_accents(self.fila_busca_var.get().lower().strip())
        itens_reais = 0
        total_etiquetas = 0
        total_preco = 0.0
        for posicao, produto in enumerate(self.queue):
            texto = strip_accents(" ".join(str(produto.get(campo, "")) for campo in
                                           ("sku", "name", "brand", "model", "color", "size", "barcode"))).lower()
            if termo and termo not in texto:
                continue
            try:
                copias = max(1, int(float(produto.get("copies") or 1)))
            except (TypeError, ValueError):
                copias = 1
            total_etiquetas += copias
            try:
                total_preco += float(produto.get("price") or 0) * copias
            except (TypeError, ValueError):
                pass
            tag = "even" if (posicao % 2 == 0) else "odd"
            if not str(produto.get("sku") or "").strip():
                tag = "sem_sku"
            self.table.insert("", "end", iid=f"r{posicao}", tags=(tag,), values=(
                produto.get("sku", ""), produto.get("barcode", ""), produto.get("name", ""),
                produto.get("brand", ""), produto.get("model", ""), produto.get("color", ""),
                produto.get("size", ""), _moeda(produto.get("price")),
                str(copias),
            ))
            itens_reais += 1
        self.fila_contagem.set(f"{itens_reais} itens | {total_etiquetas} etiquetas")
        try:
            self.fila_total_label.configure(text=f"Total: {_moeda(total_preco)}")
        except AttributeError:
            pass

    def _ordenar_fila(self, column):
        if self.fila_ordenar_col == column:
            self.fila_ordenar_rev = not self.fila_ordenar_rev
        else:
            self.fila_ordenar_col = column
            self.fila_ordenar_rev = False

        def chave(produto):
            valor = str(produto.get(column, "") or "")
            if column == "price" or column == "copies":
                try:
                    return float(str(produto.get(column, "")).replace(",", "."))
                except ValueError:
                    return 0.0
            return strip_accents(valor).lower()

        self.queue.sort(key=chave, reverse=self.fila_ordenar_rev)
        self._render_fila()

    def _atualizar_detalhe(self):
        selected = self.table.selection()
        if not selected:
            self.detalhe_texto.configure(text="Selecione um item na fila.")
            self._limpar_previa()
            return
        posicao = int(selected[0][1:])
        if posicao >= len(self.queue):
            return
        produto = self.queue[posicao]
        linhas = [
            f"SKU          : {produto.get('sku', '')}",
            f"EAN/Barcode  : {produto.get('barcode', '') or 'sem codigo'}",
            f"Nome         : {produto.get('name', '')}",
            f"Marca        : {produto.get('brand', '') or '-'}",
            f"Modelo       : {produto.get('model', '') or '-'}",
            f"Cor          : {produto.get('color', '') or '-'}",
            f"Tamanho      : {produto.get('size', '') or '-'}",
            f"Preco        : {_moeda(produto.get('price'))}",
            f"Copias       : {produto.get('copies', 1)}",
            f"Estoque      : {produto.get('quantity', '-')}",
            f"ID Bling     : {produto.get('id', '') or '-'}",
        ]
        self.detalhe_texto.configure(text="\n".join(linhas))
        self._desenhar_previa(produto)

    def _desenhar_previa(self, produto):
        canvas = self.canvas_previa
        canvas.delete("all")
        largura = canvas.winfo_width() or 300
        altura = canvas.winfo_height() or 160

        escala = min(largura / 264.0, altura / 136.0) * 0.92
        ox = (largura - 264 * escala) / 2
        oy = (altura - 136 * escala) / 2
        canvas.create_rectangle(ox, oy, ox + 264 * escala, oy + 136 * escala,
                                fill="#ffffff", outline=ACCENT, width=2)

        def ymm(valor):
            return oy + valor * escala

        def xmm(valor):
            return ox + valor * escala

        nome = str(produto.get("name", "") or "").upper()
        canvas.create_text(xmm(37), ymm(20), anchor="nw", text=strip_accents(nome)[:20],
                           font=_font(9, "bold"), fill=INK)
        canvas.create_text(xmm(37), ymm(36), anchor="nw",
                           text=strip_accents(nome)[20:40], font=_font(8), fill=INK)
        attr = " ".join(str(produto.get(c) or "") for c in ("color", "size")
                        if str(produto.get(c) or "").strip())
        canvas.create_text(xmm(37), ymm(52), anchor="nw", text=strip_accents(attr)[:18],
                           font=_font(8), fill=INK)
        canvas.create_text(xmm(37), ymm(68), anchor="nw", text=_moeda(produto.get("price")),
                           font=_font(9, "bold"), fill=INK)
        sku = str(produto.get("sku", "") or "SEM SKU").upper()[:15]
        yb = ymm(94)
        x = xmm(37)
        canais = [3, 6, 3, 9, 6, 3, 9, 6, 3, 6, 9, 3, 6, 3]  # pseudo-barcode
        aleatorio = 0
        for char in sku:
            aleatorio += ord(char)
        passo = 0
        for i in range(14):
            larg = canais[i % len(canais)] * escala
            if (aleatorio + i) % 3 != 0:
                canvas.create_rectangle(x + passo, yb, x + passo + larg, yb + 26 * escala,
                                        fill="#0f172a", outline="")
            passo += larg + 2 * escala
        canvas.create_text(xmm(37), yb + 30 * escala, anchor="nw", text=sku,
                           font=(FONTE_MONO, 10, "bold"), fill=INK)

    def _limpar_previa(self):
        try:
            self.canvas_previa.delete("all")
        except tk.TclError:
            pass

    def _produtos_selecionados(self):
        produtos = []
        for iid in self.table.selection():
            try:
                posicao = int(iid[1:])
            except (TypeError, ValueError):
                continue
            if 0 <= posicao < len(self.queue):
                produtos.append(self.queue[posicao])
        return produtos

    def selecionar_todos_fila(self):
        self.table.selection_set(self.table.get_children())

    def remove_selected(self):
        produtos = self._produtos_selecionados()
        if not produtos:
            messagebox.showinfo("Fila", "Selecione um ou mais itens na fila.")
            return
        self.queue = [p for p in self.queue if p not in produtos]
        self._render_fila()
        self.status.set(f"Fila: {len(self.queue)} itens")

    def limpar_nova_fila_selecionadas(self):
        self.clear_queue()

    def clear_queue(self):
        self.queue.clear()
        self._render_fila()
        self.status.set("Fila vazia")

    def editar_copias_selecionadas(self):
        produtos = self._produtos_selecionados()
        if not produtos:
            messagebox.showinfo("Fila", "Selecione um item na fila para editar as copias.")
            return
        dialogo = tk.Toplevel(self)
        dialogo.title("Editar copias")
        dialogo.geometry("340x220")
        dialogo.configure(bg=BG)
        dialogo.transient(self)
        dialogo.grab_set()
        wrapper = tk.Frame(dialogo, bg=ui.FUNDO)
        wrapper.pack(fill="both", expand=True, padx=ui.ESPACO_4, pady=ui.ESPACO_4)
        cartao = ui.Cartao(wrapper, titulo="Quantidade de copias",
                           padding=ui.ESPACO_5)
        cartao.pack(fill="both", expand=True)
        box = cartao.interior
        entrada = ttk.Entry(box, width=10)
        entrada.pack(anchor="w", fill="x", pady=(ui.ESPACO_2, ui.ESPACO_4))
        entrada.insert(0, str(produtos[0].get("copies") or 1))
        entrada.focus_set()

        def aplicar():
            try:
                valor = max(1, int(entrada.get().strip()))
            except ValueError:
                return
            for produto in produtos:
                produto["copies"] = str(valor)
            self._render_fila()
            dialogo.destroy()

        def Enter(event):
            aplicar()
            return "break"

        entrada.bind("<Return>", Enter)
        ui.Botao(box, "Aplicar", aplicar, variante="primario",
                parent_bg=ui.BRANCO).pack(anchor="e")

    def duplicar_selecionado(self):
        produtos = self._produtos_selecionados()
        if not produtos:
            messagebox.showinfo("Fila", "Selecione um item na fila para duplicar.")
            return
        adicionados = []
        for produto in produtos:
            novo = dict(produto)
            novo["copies"] = "1"
            self.queue.append(novo)
            adicionados.append(novo)
        self._render_fila()
        self.status.set(f"{len(adicionados)} item(ns) duplicado(s)")

    def exportar_fila_csv(self):
        if not self.queue:
            messagebox.showinfo("Fila", "A fila esta vazia.")
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"fila_etiquetas_{time.strftime('%Y%m%d_%H%M%S')}.csv")
        if not caminho:
            return
        colunas = ("sku", "barcode", "name", "brand", "model", "color", "size", "price", "copies", "id", "fila_id")
        try:
            with open(caminho, "w", encoding="utf-8-sig", newline="") as arquivo:
                escritor = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";")
                escritor.writeheader()
                for produto in self.queue:
                    escritor.writerow({campo: produto.get(campo, "") for campo in colunas})
            self.status.set(f"Fila exportada: {caminho}")
        except OSError as error:
            messagebox.showerror("Fila", f"Falha ao exportar:\n{error}")

    # ==================================================================
    # ABA IMAGENS
    # ==================================================================
    def _create_imagens_tab(self):
        """Fotos do catalogo: lista a esquerda, visor a direita, e duas
        visoes que ocupam o mesmo espaco.

        Mudanca de forma: a lista era um `Cartao` solto e o visor outro, com
        `pack` dentro dos dois, enquanto o frame do meio usava `grid`. Os
        botoes de navegacao usavam os glifos U+25C0/U+25B6/U+2212/U+FF0B,
        que em Segoe UI viram caixa vazia no Windows. Agora tudo passa pelo
        `Painel`/`Bloco`, e a navegacao usa texto.
        """
        tela = ui.Tela(self.tab_imagens, linhas=2)
        tela.pack(fill="both", expand=True)
        tela.linha(1, peso=1)

        self._criar_comutador_imagens(tela)

        # As duas visoes ficam empilhadas na mesma celula: so uma aparece por
        # vez. `place` e' o gerenciador certo aqui (e' troca de visao, nao
        # empilhamento), mas o frame que as contem e' um so, para as duas
        # medirem a mesma area.
        pilha = tk.Frame(tela, bg=ui.FUNDO)
        tela.celula(pilha, 1, 0)
        visualizador = ui.Coluna(pilha, fundo=ui.FUNDO)
        curadoria = ui.Coluna(pilha, fundo=ui.FUNDO)
        # `place` nao empilha: colocar as duas deixaria as duas visoes no
        # mesmo lugar, uma sobre a outra. A curadoria so entra no lugar
        # quando `_trocar_vista_imagens` chama.
        visualizador.place(relx=0, rely=0, relwidth=1, relheight=1)
        curadoria.place(relx=0, rely=0, relwidth=1, relheight=1)
        curadoria.place_forget()
        # `place` da o tamanho, mas quem distribui o espaco dentro de cada
        # visao e' o grid delas: sem peso na coluna 0, o grid fica com a
        # largura do maior filho e o resto da area sobrava vazia a direita.
        visualizador.coluna(0, peso=1)
        curadoria.coluna(0, peso=1)
        self.curadoria_views = {"visualizador": visualizador, "curadoria": curadoria}
        self.vista_imagens = "visualizador"

        visualizador.linha(1, peso=1)
        self._create_barra_imagens(visualizador)

        meio = visualizador.secao(1, 0, peso_linha=1)
        meio.coluna(0, peso=3, minima=380)
        meio.coluna(1, peso=2, minima=320)
        meio.linha(0, peso=1)

        colunas = ("sku", "name", "color", "size", "price", "foto")
        lista = ui.Painel(meio, colunas, titulo="Produtos", fundo=ui.FUNDO)
        meio.celula(lista, 0, 0)
        self.imagens_tree = lista.montar_tabela(
            altura=10, selectmode="browse",
            area=self._area_da_pagina("imagens"))
        rotulos = {"sku": "SKU", "name": "Nome", "color": "Cor", "size": "Tam",
                   "price": "Preco", "foto": "Foto"}
        for coluna, largura in (("sku", 130), ("name", 230), ("color", 90),
                                ("size", 70), ("price", 88), ("foto", 70)):
            self.imagens_tree.heading(coluna, text=rotulos[coluna])
            self.imagens_tree.column(coluna, width=largura, minwidth=46,
                                     anchor="w", stretch=True)
        self.imagens_tree.column("price", anchor="e")
        self.imagens_tree.column("foto", anchor="center")
        self.imagens_tree.tag_configure("odd", background=ui.BRANCO)
        self.imagens_tree.tag_configure("even", background=ui.TINTA)
        self.imagens_tree.tag_configure("sem_foto", background=ui.AVISO_CLARO)
        self.imagens_tree.bind("<<TreeviewSelect>>", self._imagem_selecionada)

        visor = ui.Bloco(meio, titulo="Visualizacao", fundo=ui.FUNDO)
        meio.celula(visor, 0, 1)
        corpo = visor.corpo
        corpo.rowconfigure(1, weight=1)

        # navegacao em texto: glifo de seta e' o que some no Windows
        self.foto_nav = tk.Frame(corpo, bg=ui.FUNDO)
        self.foto_nav.grid(row=0, column=0, sticky="ew", pady=(0, ui.ESPACO_2))
        for texto, comando, largura in (("Anterior", lambda: self._navegar_foto(-1), 74),
                                        ("Proxima", lambda: self._navegar_foto(1), 66),
                                        ("-", lambda: self._ajustar_zoom(-1), 32),
                                        ("1:1", self._zoom_reset, 40),
                                        ("+", lambda: self._ajustar_zoom(1), 32)):
            ui.Botao(self.foto_nav, texto, comando, variante="secundario",
                     tamanho=ui.TEXTO_MENOR, altura=28, largura=largura,
                     parent_bg=ui.FUNDO).pack(side="left", padx=(0, ui.ESPACO_1))
        self.foto_indice_label = tk.Label(self.foto_nav, text="", bg=ui.FUNDO,
                                          fg=ui.TEXTO_FRACO,
                                          font=ui.font(ui.TEXTO_MENOR))
        self.foto_indice_label.pack(side="left", padx=ui.ESPACO_2)

        quadro = tk.Frame(corpo, bg=ui.TINTA)
        quadro.grid(row=1, column=0, sticky="nsew")
        self.canvas_foto = tk.Canvas(quadro, width=320, height=320,
                                     bg=ui.TINTA, highlightthickness=0, bd=0,
                                     cursor="crosshair")
        self.canvas_foto.pack(fill="both", expand=True,
                              padx=ui.ESPACO_2, pady=ui.ESPACO_2)
        self.canvas_foto.create_text(160, 160, text="Sem foto selecionada",
                                     fill=ui.TEXTO_FRACO,
                                     font=ui.font(ui.TEXTO_MEDIO),
                                     tags="placeholder")
        self.canvas_foto.bind("<ButtonPress-1>", self._foto_press)
        self.canvas_foto.bind("<B1-Motion>", self._foto_drag_motion)
        self.canvas_foto.bind("<ButtonRelease-1>", lambda e: self._foto_release())
        self.canvas_foto.bind("<MouseWheel>", self._foto_wheel)
        self.canvas_foto.bind("<Button-4>", lambda e: self._ajustar_zoom(1))
        self.canvas_foto.bind("<Button-5>", lambda e: self._ajustar_zoom(-1))

        self.foto_info = tk.Label(corpo, text="", bg=ui.FUNDO, fg=ui.TEXTO,
                                  font=ui.font(ui.TEXTO_MENOR),
                                  justify="left", wraplength=300, anchor="w")
        self.foto_info.grid(row=2, column=0, sticky="ew", pady=(ui.ESPACO_2, 0))

        acoes = tk.Frame(corpo, bg=ui.FUNDO)
        acoes.grid(row=3, column=0, sticky="ew", pady=(ui.ESPACO_2, 0))
        ui.Botao(acoes, "Abrir original", self.abrir_foto_original,
                 variante="secundario", tamanho=ui.TEXTO_MENOR,
                 parent_bg=ui.FUNDO).pack(side="left", padx=(0, ui.ESPACO_2))
        ui.Botao(acoes, "Salvar foto", self.salvar_foto, variante="secundario",
                 tamanho=ui.TEXTO_MENOR, parent_bg=ui.FUNDO).pack(side="left")
        self.zoom_label = tk.Label(acoes, text="", bg=ui.FUNDO, fg=ui.TEXTO,
                                   font=ui.font(ui.TEXTO_MENOR))
        self.zoom_label.pack(side="right")

        self._create_pagina_curadoria(curadoria)

    def _criar_comutador_imagens(self, parent):
        """Alterna entre o visualizador (a foto que o Bling ja tem) e a
        curadoria (as candidatas que o servidor de imagens baixou)."""
        linha = tk.Frame(parent, bg=ui.FUNDO)
        linha.grid(row=0, column=0, sticky="ew", pady=(0, ui.ESPACO_3))
        self._imagens_vista_botoes = {}
        for chave, texto in (("visualizador", "Visualizador"),
                             ("curadoria", "Curadoria")):
            botao = ui.Botao(linha, texto, lambda c=chave: self._trocar_vista_imagens(c),
                             variante="secundario", altura=32,
                             parent_bg=ui.FUNDO)
            botao.pack(side="left", padx=(0, ui.ESPACO_2))
            self._imagens_vista_botoes[chave] = botao
        self._curadoria_selo = ui.Selo(linha, texto="Servidor: nao testado",
                                       cor=ui.TEXTO, fundo=ui.TINTA,
                                       largura=210)
        self._curadoria_selo.pack(side="right")

    def _trocar_vista_imagens(self, chave):
        if chave not in self.curadoria_views:
            return
        self.vista_imagens = chave
        for nome, pagina in self.curadoria_views.items():
            pagina.place_forget()
        self.curadoria_views[chave].place(relx=0, rely=0, relwidth=1, relheight=1)
        for nome, botao in self._imagens_vista_botoes.items():
            botao.definir_variante("primario" if nome == chave else "secundario")
        if chave == "curadoria" and not self.curadoria_itens:
            self.curadoria_recarregar()
        elif chave == "visualizador":
            # o canvas do visualizador foi redimensionado enquanto escondido
            self.after(60, self._renderizar_foto)

    def _create_pagina_curadoria(self, parent):
        """Curadoria: colecao a esquerda, candidatas do produto a direita.

        A triagem (confirmar/rejeitar) e a acao principal, entao as candidatas
        ocupam a maior parte e a colecao fica como lista de contexto.
        """
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        barra = tk.Frame(parent, bg=ui.FUNDO)
        barra.grid(row=0, column=0, sticky="ew", pady=(0, ui.ESPACO_2))
        self.curadoria_servidor_entry = ttk.Entry(barra, width=30)
        self.curadoria_servidor_entry.insert(0, self.curadoria_url)
        self.curadoria_servidor_entry.pack(side="left", padx=(0, ui.ESPACO_2))
        ui.Botao(barra, "Conectar", self.curadoria_conectar,
                 variante="secundario", parent_bg=ui.FUNDO).pack(side="left")
        ui.Botao(barra, "Recarregar", self.curadoria_recarregar,
                 variante="secundario", parent_bg=ui.FUNDO).pack(
                     side="left", padx=(0, ui.ESPACO_2))
        ui.Botao(barra, "Buscar de novo", self.curadoria_buscar_novamente,
                 variante="secundario", parent_bg=ui.FUNDO).pack(side="left")
        ui.Botao(barra, "Coletar do catalogo", self.curadoria_coletar_selecionado,
                 variante="primario", parent_bg=ui.FUNDO).pack(side="left")
        self.curadoria_resumo = tk.Label(barra, text="", bg=ui.FUNDO, fg=ui.TEXTO,
                                         font=ui.font(ui.TEXTO_BASE))
        self.curadoria_resumo.pack(side="right")

        meio = tk.Frame(parent, bg=ui.FUNDO)
        meio.grid(row=1, column=0, sticky="nsew")
        meio.columnconfigure(0, weight=2, minsize=340)
        meio.columnconfigure(1, weight=3)
        meio.rowconfigure(0, weight=1)

        colecao = ui.Cartao(meio, titulo="Colecao", padding=ui.ESPACO_2)
        colecao.grid(row=0, column=0, sticky="nsew", padx=(0, ui.ESPACO_2))
        self.curadoria_tree = ttk.Treeview(colecao.interior, columns=("nome", "conf", "pend"),
                                           show="headings", selectmode="browse",
                                           style="Tabela.Treeview", height=8)
        self.curadoria_tree.heading("nome", text="Produto")
        self.curadoria_tree.heading("conf", text="Aprovadas")
        self.curadoria_tree.heading("pend", text="Aguardando")
        self.curadoria_tree.column("nome", width=220, minwidth=120, stretch=True, anchor="w")
        self.curadoria_tree.column("conf", width=92, minwidth=70, stretch=False, anchor="e")
        self.curadoria_tree.column("pend", width=96, minwidth=78, stretch=False, anchor="e")
        self.curadoria_tree.tag_configure("odd", background=ui.BRANCO)
        self.curadoria_tree.tag_configure("even", background=ui.TINTA)
        self.curadoria_tree.tag_configure("sem_confirmada", background=ui.AVISO_CLARO)
        self.curadoria_tree.bind("<<TreeviewSelect>>", self._curadoria_produto_sel)
        self.curadoria_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(colecao.interior, orient="vertical",
                               command=self.curadoria_tree.yview)
        self.curadoria_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")

        painel = ui.Cartao(meio, titulo="Candidatas", padding=ui.ESPACO_4)
        painel.grid(row=0, column=1, sticky="nsew")
        self.curadoria_info = tk.Label(painel.interior, text="", bg=ui.BRANCO,
                                       fg=ui.TEXTO, font=ui.font(ui.TEXTO_BASE),
                                       anchor="w")
        self.curadoria_info.pack(fill="x", anchor="w", pady=(0, ui.ESPACO_2))
        # as candidatas sao poucas (6 por produto), entao uma grade com scroll
        self.curadoria_grade = ui.AreaRolavel(painel.interior, fundo=ui.BRANCO)
        self.curadoria_grade.pack(fill="both", expand=True)
        self.curadoria_grade.body.columnconfigure(0, weight=1)
        self._curadoria_cartoes = []
        self.curadoria_barra = tk.Frame(painel.interior, bg=ui.BRANCO)
        self.curadoria_barra.pack(fill="x", pady=(ui.ESPACO_2, 0))

    # ------------------------------------------------------- aba: curadoria
    def _curadoria_url_atual(self):
        """URL do servidor de imagens. Como as demais URLs, e lida na main
        thread e cacheada, porque as chamadas rodam em thread."""
        if threading.current_thread() is threading.main_thread():
            try:
                self.curadoria_url = self.curadoria_servidor_entry.get().strip()
            except (AttributeError, tk.TclError):
                pass
            self._curadoria_url_cache = imagens_api.normalizar_url(self.curadoria_url)
        return self._curadoria_url_cache or imagens_api.URL_PADRAO

    def curadoria_conectar(self):
        """So testa a conexao e devolve o selo. Nao muda nada no servidor."""
        url = self._curadoria_url_atual()

        def trabalho():
            try:
                itens = imagens_api.listar_colecao(url)
            except imagens_api.ErroCuradoria as erro:
                self._na_ui(lambda: self._curadoria_selo_falhou(str(erro)))
                return
            except Exception as erro:  # noqa: BLE001 - rede pode falhar de varios jeitos
                self._na_ui(lambda: self._curadoria_selo_falhou(str(erro)))
                return
            self._na_ui(self._curadoria_aplicar_colecao, itens)

        self.status.set("Testando o servidor de imagens...")
        threading.Thread(target=trabalho, daemon=True).start()

    def _curadoria_selo_falhou(self, texto):
        self._curadoria_selo.atualizar(texto="Servidor fora do ar",
                                       cor=ui.PERIGO, fundo=ui.PERIGO_CLARO)
        self.curadoria_resumo.configure(text=texto[:70])
        self.status.set(f"Servidor de imagens: {texto[:120]}")

    def curadoria_recarregar(self):
        url = self._curadoria_url_atual()

        def trabalho():
            try:
                itens = imagens_api.listar_colecao(url)
            except Exception as erro:  # noqa: BLE001
                self._na_ui(lambda: self._curadoria_selo_falhou(str(erro)))
                return
            self._na_ui(self._curadoria_aplicar_colecao, itens)

        self.status.set("Carregando a colecao de imagens...")
        threading.Thread(target=trabalho, daemon=True).start()

    def _curadoria_aplicar_colecao(self, itens, detalhe=None, codigo=None):
        """Atualiza a lista da colecao. detalhe/codigo sao opcionais: quando
        vem junto, e o retorno de uma triagem, e o painel ja sabe o estado
        novo sem precisar refazer o GET do produto."""
        self.curadoria_itens = itens or []
        resumo = imagens_api.resumir_colecao(self.curadoria_itens)
        selecionado = self.curadoria_tree.selection()
        for item in self.curadoria_tree.get_children():
            self.curadoria_tree.delete(item)
        for indice, item in enumerate(self.curadoria_itens):
            codigo = str(item.get("codigo") or "")
            tag = "odd" if indice % 2 else "even"
            if item.get("sem_confirmada"):
                tag = "sem_confirmada"
            self.curadoria_tree.insert("", "end", iid=indice, tags=(tag,),
                                       values=(item.get("nome") or codigo,
                                               int(item.get("confirmadas") or 0),
                                               int(item.get("pendentes") or 0)))
        self.curadoria_resumo.configure(
            text=f"{resumo['produtos']} produtos  |  {resumo['confirmadas']} aprovadas"
                 f"  |  {resumo['pendentes']} aguardando"
                 f"  |  {resumo['sem_confirmada']} sem nenhuma aprovada")
        sem_erro = any(int(i.get("confirmadas") or 0) for i in self.curadoria_itens)
        self._curadoria_selo.atualizar(
            texto="Servidor conectado", cor=ui.MARCA_ESCURA, fundo=ui.MARCA_CLARA)
        if not sem_erro and self.curadoria_itens:
            self._curadoria_selo.atualizar(
                texto="Sem imagem aprovada", cor=ui.AVISO, fundo=ui.AVISO_CLARO)
        self.status.set(f"Colecao: {resumo['produtos']} produto(s), "
                        f"{resumo['pendentes']} candidata(s) aguardando triagem")

        alvo = None
        if codigo:
            for indice, item in enumerate(self.curadoria_itens):
                if str(item.get("codigo") or "") == codigo:
                    alvo = str(indice)
                    break
        if alvo is None:
            alvo = selecionado[0] if selecionado else (
                self.curadoria_tree.get_children() or [None])[0]
        if alvo is not None:
            self.curadoria_tree.selection_set(alvo)
            self.curadoria_tree.see(alvo)
            if detalhe is not None and codigo:
                self.curadoria_codigo = codigo
                self.curadoria_detalhe = detalhe
                self._curadoria_pintar()
            else:
                self._curadoria_produto_sel()

    def _curadoria_produto_sel(self, event=None):
        selecao = self.curadoria_tree.selection()
        if not selecao:
            return
        indice = int(selecao[0])
        if indice >= len(self.curadoria_itens):
            return
        codigo = str(self.curadoria_itens[indice].get("codigo") or "")
        if not codigo or codigo == self.curadoria_codigo:
            if codigo:
                self._curadoria_pintar()
            return
        self.curadoria_codigo = codigo
        self.curadoria_detalhe = None
        self.curadoria_info.configure(text="Carregando candidatas...")
        url = self._curadoria_url_atual()

        def trabalho():
            try:
                detalhe = imagens_api.detalhe(url, codigo)
            except Exception as erro:  # noqa: BLE001
                self._na_ui(lambda codigo=codigo, erro=erro:
                            self._curadoria_erro(codigo, erro))
                return
            self._na_ui(self._curadoria_aplicar_detalhe, codigo, detalhe)

        threading.Thread(target=trabalho, daemon=True).start()

    def _curadoria_erro(self, codigo, erro):
        if codigo != self.curadoria_codigo:
            return
        self.curadoria_info.configure(text=f"Falha ao carregar: {erro}")
        self.status.set(f"Curadoria: {erro}")

    def _curadoria_aplicar_detalhe(self, codigo, detalhe):
        if codigo != self.curadoria_codigo:
            return
        self.curadoria_detalhe = detalhe
        self._curadoria_pintar()

    def _curadoria_pintar(self):
        """Desenha as candidatas do produto atual. Cada uma e um cartao com a
        miniatura, a origem e os botois de triagem; as confirmadas primeiro,
        porque sao as que valem para o Bling."""
        detalhe = self.curadoria_detalhe or {}
        imagens = detalhe.get("imagens") or []
        info = detalhe.get("info") or {}
        grupos = imagens_api.agrupar_por_estado(imagens)
        origem = str(info.get("nome") or detalhe.get("codigo") or "")

        self.curadoria_info.configure(
            text=f"{origem}  ({detalhe.get('codigo') or ''})")
        for widget in self._curadoria_cartoes:
            widget.destroy()
        self._curadoria_cartoes = []
        for cartao in self.curadoria_barra.winfo_children():
            cartao.destroy()

        if not imagens:
            vazio = tk.Label(self.curadoria_grade.body,
                             text="Nenhuma candidata para este produto.\n"
                                  "Use 'Buscar de novo' ou 'Coletar do catalogo'.",
                             bg=ui.BRANCO, fg=ui.TEXTO_FRACO,
                             font=ui.font(ui.TEXTO_BASE), justify="left")
            vazio.pack(anchor="w", pady=ui.ESPACO_4)
            self._curadoria_cartoes.append(vazio)
            return

        linha = tk.Frame(self.curadoria_grade.body, bg=ui.BRANCO)
        linha.pack(fill="both", expand=True)
        for indice, (estado, lista) in enumerate(
                ((imagens_api.CONFIRMADA, grupos[imagens_api.CONFIRMADA]),
                 (imagens_api.PENDENTE, grupos[imagens_api.PENDENTE]),
                 (imagens_api.REJEITADA, grupos[imagens_api.REJEITADA]))):
            if not lista:
                continue
            for coluna in range(3):
                linha.columnconfigure(coluna, weight=1, uniform="cand")
            for posicao, imagem in enumerate(lista):
                self._curadoria_cartao(linha, posicao, imagem, estado)

        ui.Botao(self.curadoria_barra, "Buscar de novo",
                 self.curadoria_buscar_novamente, variante="secundario",
                 parent_bg=ui.BRANCO).pack(side="left")
        origem_gerada = sum(1 for i in imagens if i.get("origem") == "gerada")
        if origem_gerada:
            tk.Label(self.curadoria_barra,
                     text=f"{origem_gerada} gerada(s) por falta de resultado na busca",
                     bg=ui.BRANCO, fg=ui.AVISO,
                     font=ui.font(ui.TEXTO_MENOR)).pack(side="left",
                                                         padx=ui.ESPACO_3)

    def _curadoria_cartao(self, parent, posicao, imagem, estado):
        cor = {imagens_api.CONFIRMADA: ui.MARCA_ESCURA,
               imagens_api.PENDENTE: ui.AVISO,
               imagens_api.REJEITADA: ui.TEXTO_FRACO}.get(estado, ui.TEXTO)
        cartao = tk.Frame(parent, bg=ui.BRANCO, highlightthickness=1,
                          highlightbackground=ui.BORDA)
        cartao.grid(row=posicao // 3, column=posicao % 3, sticky="nsew",
                    padx=(0 if posicao % 3 == 0 else ui.ESPACO_1, ui.ESPACO_1),
                    pady=(0, ui.ESPACO_2))
        self._curadoria_cartoes.append(cartao)

        moldura = tk.Frame(cartao, bg=ui.TINTA, height=150,
                           highlightthickness=0)
        moldura.pack(fill="both", expand=True, padx=ui.ESPACO_2,
                     pady=(ui.ESPACO_2, 0))
        rotulo = tk.Label(moldura, text="carregando...", bg=ui.TINTA,
                          fg=ui.TEXTO_FRACO, font=ui.font(ui.TEXTO_MENOR))
        rotulo.pack(expand=True)

        rodape = tk.Frame(cartao, bg=ui.BRANCO)
        rodape.pack(fill="x", padx=ui.ESPACO_2, pady=ui.ESPACO_1)
        tk.Label(rodape, text=estado.capitalize(), bg=ui.BRANCO, fg=cor,
                 font=ui.font(ui.TEXTO_MENOR, "bold")).pack(side="left")
        gerada = imagem.get("origem") == "gerada"
        if gerada:
            tk.Label(rodape, text="gerada", bg=ui.BRANCO, fg=ui.TEXTO_FRACO,
                     font=ui.font(ui.TEXTO_MENOR)).pack(side="left",
                                                         padx=ui.ESPACO_1)

        acoes = tk.Frame(cartao, bg=ui.BRANCO)
        acoes.pack(fill="x", padx=ui.ESPACO_2, pady=(0, ui.ESPACO_2))
        id_imagem = imagem.get("id")
        pendente = estado == imagens_api.PENDENTE
        if pendente:
            ui.Botao(acoes, "Aprovar",
                     lambda i=id_imagem: self.curadoria_confirmar(i),
                     variante="primario", altura=28,
                     parent_bg=ui.BRANCO).pack(side="left", padx=(0, ui.ESPACO_1))
            ui.Botao(acoes, "Descartar",
                     lambda i=id_imagem: self.curadoria_rejeitar(i),
                     variante="perigo", altura=28,
                     parent_bg=ui.BRANCO).pack(side="left")
        elif estado == imagens_api.CONFIRMADA:
            ui.Botao(acoes, "Descartar",
                     lambda i=id_imagem: self.curadoria_rejeitar(i),
                     variante="perigo", altura=28,
                     parent_bg=ui.BRANCO).pack(side="left")
        fonte = str(imagem.get("url_fonte") or "")
        if fonte:
            ui.Botao(acoes, "Abrir original",
                     lambda u=fonte: self._abrir_url(u), variante="fantasma",
                     altura=28, parent_bg=ui.BRANCO).pack(side="right")

        codigo = self.curadoria_codigo
        arquivo = str(imagem.get("arquivo") or "")
        url = self._curadoria_url_atual()
        threading.Thread(
            target=self._curadoria_thumb_thread,
            args=(imagens_api.link_arquivo(url, codigo, arquivo), rotulo),
            daemon=True).start()

    def _curadoria_thumb_thread(self, url, rotulo):
        """Baixa e reduz a miniatura fora da main thread. Em caso de falha
        mostra 'indisponivel' em vez de esconder a candidata, porque uma
        imagem quebrada ainda precisa ser triada."""
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=20) as resposta:
                dados = resposta.read()
            if Image is None:
                self._na_ui(rotulo.configure, text="sem Pillow")
                return
            imagem = Image.open(io.BytesIO(dados)).convert("RGB")
            imagem.thumbnail((200, 150))
        except Exception:  # noqa: BLE001 - arquivo pode sumir no servidor
            self._na_ui(self._curadoria_thumb_falhou, rotulo)
            return
        self._na_ui(self._curadoria_thumb_ok, rotulo, imagem)

    def _curadoria_thumb_ok(self, rotulo, imagem):
        if not rotulo.winfo_exists():
            return
        try:
            foto = ImageTk.PhotoImage(imagem)
        except Exception:  # noqa: BLE001
            rotulo.configure(text="indisponivel")
            return
        # a referencia fica presa ao rotulo: sem isso o PhotoImage e coletado
        # pelo garbage collector e a miniatura some depois de alguns segundos
        rotulo.foto = foto
        rotulo.configure(image=foto, text="")

    def _curadoria_thumb_falhou(self, rotulo):
        if not rotulo.winfo_exists():
            return
        rotulo.configure(text="indisponivel")

    def curadoria_confirmar(self, id_imagem):
        codigo = self.curadoria_codigo
        if not codigo:
            return
        url = self._curadoria_url_atual()

        def trabalho():
            try:
                detalhe = imagens_api.confirmar(url, id_imagem, codigo)
                itens = imagens_api.listar_colecao(url)
            except Exception as erro:  # noqa: BLE001
                self._na_ui(lambda erro=erro: self.status.set(f"Curadoria: {erro}"))
                return
            self._na_ui(self._curadoria_aplicar_colecao, itens, detalhe, codigo)

        self.status.set("Aprovando candidata...")
        threading.Thread(target=trabalho, daemon=True).start()

    def curadoria_rejeitar(self, id_imagem):
        codigo = self.curadoria_codigo
        if not codigo:
            return
        url = self._curadoria_url_atual()

        def trabalho():
            try:
                detalhe = imagens_api.rejeitar(url, id_imagem, codigo)
                itens = imagens_api.listar_colecao(url)
            except Exception as erro:  # noqa: BLE001
                self._na_ui(lambda erro=erro: self.status.set(f"Curadoria: {erro}"))
                return
            self._na_ui(self._curadoria_aplicar_colecao, itens, detalhe, codigo)

        self.status.set("Descartando candidata...")
        threading.Thread(target=trabalho, daemon=True).start()

    def curadoria_buscar_novamente(self):
        codigo = self.curadoria_codigo
        if not codigo:
            messagebox.showinfo("Curadoria", "Escolha um produto na colecao primeiro.")
            return
        # O servidor preserva o que ja foi aprovado e joga fora as
        # candidatas que ainda nao foram triadas. Como essa triagem em curso
        # nao se repete, o painel pede confirmacao.
        pendentes = len(imagens_api.agrupar_por_estado(
            (self.curadoria_detalhe or {}).get("imagens") or []
        )[imagens_api.PENDENTE])
        aviso = (f"Refazer a busca de {codigo} descarta {pendentes} candidata(s) "
                 "que ainda nao foram aprovadas e busca substitutas.\n\n"
                 "O que ja foi aprovado e preservado. Refazer mesmo assim?")
        if not messagebox.askyesno("Refazer a busca", aviso, parent=self):
            return
        url = self._curadoria_url_atual()

        def trabalho():
            try:
                detalhe = imagens_api.buscar_novamente(url, codigo)
                itens = imagens_api.listar_colecao(url)
            except Exception as erro:  # noqa: BLE001
                self._na_ui(lambda erro=erro:
                            self.status.set(f"Curadoria: {erro}"))
                return
            self._na_ui(self._curadoria_aplicar_colecao, itens, detalhe, codigo)

        self.status.set(f"Buscando candidatas novas para {codigo}...")
        threading.Thread(target=trabalho, daemon=True).start()

    def curadoria_coletar_selecionado(self):
        """Pega o produto que esta selecionado na aba visualizador e manda o
        servidor buscar candidatas para ele. E atalho para quem ve o produto
        na busca e ja sabe que esta sem foto boa."""
        produto = self._produto_da_busca_atual()
        if produto is None:
            messagebox.showinfo(
                "Curadoria",
                "Selecione um produto na aba Visualizador antes de coletar.")
            return
        payload = imagens_api.produto_para_coleta(produto)
        if not payload.get("codigo"):
            messagebox.showinfo("Curadoria", "Esse produto nao tem SKU para usar como codigo.")
            return
        url = self._curadoria_url_atual()

        def trabalho():
            try:
                resultado = imagens_api.coletar(url, [payload])
                itens = imagens_api.listar_colecao(url)
            except Exception as erro:  # noqa: BLE001
                self._na_ui(lambda erro=erro:
                            self.status.set(f"Curadoria: {erro}"))
                return
            self._na_ui(self._curadoria_coletar_ok, itens, payload, resultado)

        self.status.set(f"Coletando candidatas para {payload['codigo']}...")
        threading.Thread(target=trabalho, daemon=True).start()

    def _produto_da_busca_atual(self):
        if getattr(self, "vista_imagens", "visualizador") != "visualizador":
            return None
        selecao = self.imagens_tree.selection()
        if selecao:
            posicao = int(selecao[0])
            if 0 <= posicao < len(self.imagens_resultados):
                return self.imagens_resultados[posicao]
        return None

    def _curadoria_coletar_ok(self, itens, payload, resultado):
        self._curadoria_aplicar_colecao(itens)
        # a arvore foi repovoada; seleciona o produto recem-coletado para que
        # o detalhe e as candidatas aparecam sem novo clique do usuario
        for indice, item in enumerate(self.curadoria_itens):
            if str(item.get("codigo") or "") == payload["codigo"]:
                self.curadoria_tree.selection_set(str(indice))
                self.curadoria_tree.see(str(indice))
                self._curadoria_produto_sel()
                break
        primeiro = (resultado or [{}])[0]
        self.status.set(f"{primeiro.get('codigo') or payload['codigo']}: "
                        f"{primeiro.get('status') or 'sem retorno'} "
                        f"({primeiro.get('qtd') or 0} candidata(s))")

    def _abrir_url(self, url):
        if not url:
            return
        try:
            webbrowser.open(url)
        except Exception as erro:  # noqa: BLE001
            self.status.set(f"Nao consegui abrir o navegador: {erro}")

    def _create_barra_imagens(self, parent):
        acoes = self.cabecalho_imagens.acoes
        ui.Botao(acoes, "Buscar", self.buscar_imagem, variante="primario",
                 parent_bg=ui.FUNDO).pack(side="left", padx=(0, ui.ESPACO_2))
        self.imagens_modo_label = tk.Label(acoes, text="", bg=ui.FUNDO,
                                           fg=ui.TEXTO,
                                           font=ui.font(ui.TEXTO_BASE))
        self.imagens_modo_label.pack(side="right")

        barra = tk.Frame(parent, bg=ui.FUNDO)
        barra.grid(row=0, column=0, sticky="ew", pady=(0, ui.ESPACO_2))
        self.imagens_termo = SearchField(barra, texto="nome, SKU, GTIN ou id do produto...",
                                         parent_bg=ui.FUNDO,
                                         comando=self.buscar_imagem)
        self.imagens_termo.pack(side="left", fill="x", expand=True,
                                padx=(0, ui.ESPACO_2))
        ui.Botao(barra, "Foto do item na fila", self.mostrar_foto_da_fila,
                 variante="secundario", parent_bg=ui.FUNDO).pack(side="left")

    def buscar_imagem(self):
        termo = self.imagens_termo.get().strip()
        if not termo:
            messagebox.showwarning("Imagens", "Digite um SKU/codigo/EAN para buscar.")
            return
        self.status.set(f"Buscando imagem por '{termo}'...")
        threading.Thread(target=self._buscar_imagem_thread, args=(termo,), daemon=True).start()

    def _buscar_imagem_thread(self, termo):
        try:
            api_url = self._api_url_atual()
            api_token = self._api_token_atual()
            request = urllib.request.Request(
                f"{api_url}/api/etiquetas/produtos/busca?termo={urllib.parse.quote(termo)}&limite=50",
                headers={"Authorization": f"Bearer {api_token}", "Accept": "application/json", "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            self._na_ui(self._mostrar_busca, body.get("data", []), termo)
        except Exception as error:
            self._na_ui(lambda error=error: messagebox.showerror("Imagens", str(error)))

    def _mostrar_busca(self, produtos, termo):
        for item in self.imagens_tree.get_children():
            self.imagens_tree.delete(item)
        self.imagens_resultados = produtos
        for posicao, produto in enumerate(produtos):
            tag = "even" if (posicao % 2 == 0) else "odd"
            if not str(produto.get("imagem_url") or "").strip():
                tag = "sem_foto"
            self.imagens_tree.insert("", "end", iid=str(posicao), tags=(tag,), values=(
                produto.get("sku", ""), produto.get("name", ""), produto.get("color", ""),
                produto.get("size", ""), _moeda(produto.get("price")),
                "tem" if str(produto.get("imagem_url") or "").strip() else "sem",
            ))
        self.imagens_modo_label.configure(text=f"{len(produtos)} resultado(s)")
        if produtos:
            self.imagens_tree.selection_set("0")
            self.imagens_indice = 0
            self._imagem_selecionada()
        else:
            self._limpar_foto()
        self.status.set(f"Busca '{termo}': {len(produtos)} produto(s)")

    def _imagem_selecionada(self, event=None):
        selection = self.imagens_tree.selection()
        if not selection:
            return
        posicao = int(selection[0])
        if posicao >= len(self.imagens_resultados):
            return
        self.imagens_indice = posicao
        self._exibir_foto(self.imagens_resultados[posicao])

    def _navegar_foto(self, delta):
        if not self.imagens_resultados:
            return
        self.imagens_indice = (self.imagens_indice + delta) % len(self.imagens_resultados)
        self.imagens_tree.selection_set(str(self.imagens_indice))
        self.imagens_tree.see(str(self.imagens_indice))
        self._exibir_foto(self.imagens_resultados[self.imagens_indice])

    def _exibir_foto(self, produto):
        self._foto_url = str(produto.get("imagem_url") or "").strip()
        self.foto_info.configure(
            text=f"{produto.get('sku', '')} - {produto.get('name', '')}\n"
                 f"{' | '.join(str(v) for v in (produto.get('color'), produto.get('size')) if v)}"
                 f"  |  {_moeda(produto.get('price'))}")
        self.foto_indice_label.configure(text=f"{self.imagens_indice + 1}/{max(1, len(self.imagens_resultados))}" if self.imagens_resultados else "")
        if not self._foto_url:
            self._limpar_foto()
            self.canvas_foto.create_text(180, 180, text="Sem imagem cadastrada",
                                         fill=FAINT, font=_font(12), tags="placeholder")
            return
        self.foto_ref_atual = produto
        self.canvas_foto.delete("placeholder")
        self.canvas_foto.create_text(180, 180, text="Carregando foto...", fill=FAINT,
                                     font=_font(12), tags="placeholder")
        threading.Thread(target=self._carregar_foto_thread, args=(self._foto_url,), daemon=True).start()

    def _carregar_foto_thread(self, imagem_url):
        try:
            request = urllib.request.Request(imagem_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=25) as response:
                dados = response.read()
            if Image is None or ImageTk is None:
                self._na_ui(lambda: self.canvas_foto.itemconfigure(
                    "placeholder", text="Pillow nao instalado"))
                return
            imagem = Image.open(io.BytesIO(dados))
            imagem = imagem.convert("RGB")
            self._foto_bytes = dados
            self._na_ui(self._aplicar_foto, imagem)
        except Exception as error:
            self._na_ui(lambda error=error: self.canvas_foto.itemconfigure(
                "placeholder", text=f"Falha ao carregar foto\n{error}"))

    def _aplicar_foto(self, imagem):
        self._foto_pil = imagem
        self._foto_zoom = 1.0
        self._foto_dx = 0.0
        self._foto_dy = 0.0
        self.canvas_foto.delete("placeholder")
        self._renderizar_foto()

    def _tamanho_box_foto(self):
        try:
            return max(60, self.canvas_foto.winfo_width()), max(60, self.canvas_foto.winfo_height())
        except tk.TclError:
            return 360, 360

    def _renderizar_foto(self):
        if self._foto_pil is None:
            return
        canvas = self.canvas_foto
        canvas.delete("foto")
        base_w, base_h = self._tamanho_box_foto()
        imagem_base = self._foto_pil.copy()
        imagem_base.thumbnail((base_w, base_h))
        fator = max(0.1, self._foto_zoom)
        nova_w = max(1, int(imagem_base.width * fator))
        nova_h = max(1, int(imagem_base.height * fator))
        if fator != 1.0:
            imagem_base = imagem_base.resize((nova_w, nova_h), Image.LANCZOS)
        foto = ImageTk.PhotoImage(imagem_base)
        self._foto_refs.append(foto)
        if len(self._foto_refs) > 20:
            self._foto_refs = self._foto_refs[-20:]
        centro_x = base_w / 2 + self._foto_dx
        centro_y = base_h / 2 + self._foto_dy
        canvas.create_image(centro_x, centro_y, image=foto, anchor="center", tags="foto")
        self.zoom_label.configure(text=f"{int(fator * 100)}%")

    def _ajustar_zoom(self, direcao):
        if self._foto_pil is None:
            return
        self._foto_zoom = min(12.0, max(0.1, self._foto_zoom * (1.4 if direcao > 0 else 0.72)))
        self._renderizar_foto()

    def _zoom_reset(self):
        self._foto_zoom = 1.0
        self._foto_dx = self._foto_dy = 0.0
        self._renderizar_foto()

    def _foto_wheel(self, event):
        self._ajustar_zoom(1 if event.delta > 0 else -1)

    def _foto_press(self, event):
        self._foto_drag = (event.x, event.y)

    def _foto_drag_motion(self, event):
        if self._foto_drag is None:
            return
        x0, y0 = self._foto_drag
        self._foto_dx += event.x - x0
        self._foto_dy += event.y - y0
        self._foto_drag = (event.x, event.y)
        self._renderizar_foto()

    def _foto_release(self):
        self._foto_drag = None

    def _limpar_foto(self):
        self._foto_pil = None
        self._foto_bytes = None
        self._foto_url = ""
        try:
            self.canvas_foto.delete("all")
        except tk.TclError:
            pass

    def abrir_foto_original(self):
        if self._foto_url:
            webbrowser.open(self._foto_url)

    def salvar_foto(self):
        if not self._foto_bytes:
            messagebox.showinfo("Imagens", "Nenhuma foto carregada.")
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".jpg", filetypes=[("Imagem", "*.jpg *.png *.jpeg")],
            initialfile=f"foto_{time.strftime('%Y%m%d_%H%M%S')}.jpg")
        if not caminho:
            return
        try:
            with open(caminho, "wb") as arquivo:
                arquivo.write(self._foto_bytes)
            self.status.set(f"Foto salva: {caminho}")
        except OSError as error:
            messagebox.showerror("Imagens", f"Falha ao salvar:\n{error}")

    def mostrar_foto_da_fila(self):
        selection = self.table.selection()
        if not selection:
            messagebox.showinfo("Imagens", "Selecione um item na aba Etiquetas primeiro.")
            return
        posicao = int(selection[0][1:])
        if posicao >= len(self.queue):
            return
        produto = self.queue[posicao]
        imagem_url = str(produto.get("imagem_url") or "").strip()
        if not imagem_url:
            self.notebook.select(self._scroll_abas[self.tab_imagens])
            self.imagens_modo_label.configure(text="sem imagem na fila; buscando por SKU")
            termo = str(produto.get("sku") or "").strip()
            if not termo:
                messagebox.showinfo("Imagens", "Este item nao possui imagem cadastrada.")
                return
            self.imagens_termo.delete(0, "end")
            self.imagens_termo.insert(0, termo)
            self.buscar_imagem()
            return
        self.notebook.select(self._scroll_abas[self.tab_imagens])
        self.imagens_resultados = [produto]
        self.imagens_indice = 0
        self.imagens_tree.delete(*self.imagens_tree.get_children())
        self.imagens_tree.insert("", "end", iid="0", values=(
            produto.get("sku", ""), produto.get("name", ""), produto.get("color", ""),
            produto.get("size", ""), _moeda(produto.get("price")), "tem"))
        self.imagens_tree.selection_set("0")
        self._exibir_foto(produto)

    # ==================================================================
    # ABA PRODUTOS (CATALOGO BLING)
    # ==================================================================
    def _create_produtos_tab(self):
        """Catalogo da Bling em modo leitura.

        Mudanca de forma: a busca e os tres botoes de acao estavam na mesma
        linha, com a busca em `expand=True` e os botoes Dimensionados pelo
        texto. Em 1040px o "Exportar CSV" encostava na borda. Agora a busca
        e' um campo com rotulo em cima, e as acoes ficam alinhadas na base
        dela; a tabela ocupa a faixa inteira e a paginacao desceu para o
        rodape do painel.
        """
        tela = ui.Tela(self.tab_produtos, linhas=2)
        tela.pack(fill="both", expand=True)
        tela.linha(1, peso=1)

        filtros = ui.BarraFiltros(tela, colunas=2)
        tela.celula(filtros, 0, 0)
        self.produtos_termo = SearchField(
            filtros, texto="nome, SKU ou id  |  vazio lista o catalogo",
            parent_bg=ui.FUNDO, comando=lambda: self.buscar_produtos(1))
        filtros.campo("Buscar no catalogo", self.produtos_termo)
        filtros.botao("Buscar / Listar", lambda: self.buscar_produtos(1),
                      variante="primario", coluna=1)

        colunas = ("sku", "name", "brand", "model", "color", "size", "price",
                   "quantity", "barcode", "foto")
        painel = ui.Painel(tela, colunas, titulo="Catalogo", fundo=ui.FUNDO)
        tela.celula(painel, 1, 0)
        # o cabecalho do painel tem duas linhas: titulo+acoes em cima,
        # contagem de resultados embaixo, alinhada a esquerda
        textos = tk.Frame(painel.cabecalho, bg=ui.FUNDO)
        textos.grid(row=1, column=0, columnspan=2, sticky="w")
        self.catalogo_info = tk.Label(textos, text="", bg=ui.FUNDO,
                                      fg=ui.TEXTO_FRACO, anchor="w",
                                      font=ui.font(ui.TEXTO_MENOR))
        self.catalogo_info.pack(side="left")

        for texto, comando in (("Copiar SKU", lambda: self.copiar_catalogo("sku")),
                               ("Copiar nome", lambda: self.copiar_catalogo("name")),
                               ("Exportar CSV", self.exportar_catalogo_csv)):
            ui.Botao(painel.acoes, texto, comando, variante="secundario",
                     parent_bg=ui.FUNDO).pack(side="left", padx=(0, ui.ESPACO_1))

        rodape = painel.rodape()
        self.btn_pag_ant = ui.Botao(rodape, "Anterior",
                                    lambda: self.buscar_produtos(self.catalogo_pagina - 1),
                                    variante="secundario", altura=30,
                                    parent_bg=ui.FUNDO)
        self.btn_pag_ant.pack(side="left")
        self.catalogo_pagina_label = tk.Label(rodape, text="pagina 1", bg=ui.FUNDO,
                                              fg=ui.TEXTO, anchor="center",
                                              font=ui.font(ui.TEXTO_BASE))
        self.catalogo_pagina_label.pack(side="left", fill="x", expand=True)
        self.btn_pag_prox = ui.Botao(rodape, "Proxima",
                                     lambda: self.buscar_produtos(self.catalogo_pagina + 1),
                                     variante="secundario", altura=30,
                                     parent_bg=ui.FUNDO)
        self.btn_pag_prox.pack(side="right")

        self.produtos_tree = painel.montar_tabela(
            altura=10, area=self._area_da_pagina("produtos"))
        rotulos = {"sku": "SKU", "name": "Nome", "brand": "Marca", "model": "Modelo",
                   "color": "Cor", "size": "Tam", "price": "Preco",
                   "quantity": "Estoque", "barcode": "Codigo de barras",
                   "foto": "Foto"}
        larguras = {"sku": 135, "name": 260, "brand": 110, "model": 100,
                    "color": 90, "size": 66, "price": 88, "quantity": 76,
                    "barcode": 120, "foto": 70}
        for coluna in colunas:
            self.produtos_tree.heading(coluna, text=rotulos[coluna],
                                       command=lambda c=coluna: self._ordenar_catalogo(c))
            self.produtos_tree.column(coluna, width=larguras[coluna], minwidth=46,
                                      anchor="w", stretch=True)
        for coluna in ("price", "quantity"):
            self.produtos_tree.column(coluna, anchor="e")
        self.produtos_tree.column("foto", anchor="center")
        self.produtos_tree.tag_configure("odd", background=ui.BRANCO)
        self.produtos_tree.tag_configure("even", background=ui.TINTA)
        self.produtos_tree.tag_configure("sem_sku", background=ui.AVISO_CLARO,
                                         foreground="#92600f")
        self.produtos_tree.tag_configure("sem_foto", background=ui.MARCA_TINTA)
        self.produtos_tree.bind("<<TreeviewSelect>>", self._catalogo_selecionado)

    def buscar_produtos(self, pagina):
        if pagina < 1:
            return
        termo = self.produtos_termo.get().strip()
        self.catalogo_termo = termo
        self.catalogo_pagina = pagina
        self.status.set(f"Consultando catalogo (pagina {pagina})...")
        threading.Thread(target=self._buscar_catalogo_thread, args=(termo, pagina), daemon=True).start()

    def _buscar_catalogo_thread(self, termo, pagina):
        try:
            api_url = self._api_url_atual()
            api_token = self._api_token_atual()
            query = f"pagina={pagina}&limite={self.catalogo_limite}"
            if termo:
                query = f"termo={urllib.parse.quote(termo)}&limite={self.catalogo_limite}"
            request = urllib.request.Request(
                f"{api_url}/api/etiquetas/produtos/busca?{query}",
                headers={"Authorization": f"Bearer {api_token}", "Accept": "application/json", "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=40) as response:
                body = json.loads(response.read().decode("utf-8"))
            self._na_ui(self._mostrar_catalogo, body, termo, pagina)
        except Exception as error:
            self._na_ui(lambda error=error: messagebox.showerror("Catalogo", str(error)))

    def _mostrar_catalogo(self, body, termo, pagina):
        produtos = body.get("data", [])
        self.catalogo_resultados = produtos
        if termo:
            self.catalogo_resultados_pagina = 1
            self.catalogo_total = len(produtos)
        else:
            self.catalogo_pagina = pagina
            self.catalogo_total = body.get("total", len(produtos))
        for item in self.produtos_tree.get_children():
            self.produtos_tree.delete(item)
        for posicao, produto in enumerate(produtos):
            tag = "even" if (posicao % 2 == 0) else "odd"
            if not str(produto.get("sku") or "").strip():
                tag = "sem_sku"
            elif not str(produto.get("imagem_url") or "").strip():
                tag = "sem_foto"
            self.produtos_tree.insert("", "end", iid=f"c{posicao}", tags=(tag,), values=(
                produto.get("sku", ""), produto.get("name", ""), produto.get("brand", ""),
                produto.get("model", ""), produto.get("color", ""), produto.get("size", ""),
                _moeda(produto.get("price")), produto.get("quantity", ""),
                produto.get("barcode", ""),
                "tem" if str(produto.get("imagem_url") or "").strip() else "sem",
            ))
        sem_sku = sum(1 for p in produtos if not str(p.get("sku") or "").strip())
        info = f"pagina {self.catalogo_pagina}"
        if self.catalogo_total:
            info += f" de ~{math.ceil(self.catalogo_total / self.catalogo_limite)}"
        info += f" | {len(produtos)} exibidos"
        if termo:
            info = f"busca '{termo}' | {len(produtos)} resultado(s)"
        if sem_sku:
            info += f" | {sem_sku} sem SKU"
        self.catalogo_info.configure(text=info)
        self.catalogo_pagina_label.configure(text=f"pagina {self.catalogo_pagina}")
        self.status.set(info)

    def _catalogo_selecionado(self, event=None):
        selection = self.produtos_tree.selection()
        if not selection:
            return
        primeira = selection[0]
        if self.catalogo_resultados:
            posicao = int(primeira[1:])
            if 0 <= posicao < len(self.catalogo_resultados):
                produto = self.catalogo_resultados[posicao]
                self.status.set(f"Selecionado: {produto.get('sku', 'sem SKU')} - {produto.get('name', '')} [{len(selection)}]")

    def _ordenar_catalogo(self, column):
        if self.catalogo_ordenar_col == column:
            self.catalogo_ordenar_rev = not self.catalogo_ordenar_rev
        else:
            self.catalogo_ordenar_col = column
            self.catalogo_ordenar_rev = False

        def chave(produto):
            valor = str(produto.get(column, "") or "")
            if column in ("price", "quantity"):
                try:
                    return float(valor.replace(",", "."))
                except ValueError:
                    return 0.0
            return strip_accents(valor).lower()

        ordenados = sorted(self.catalogo_resultados, key=chave, reverse=self.catalogo_ordenar_rev)
        self.catalogo_resultados = ordenados
        for item in self.produtos_tree.get_children():
            self.produtos_tree.delete(item)
        for posicao, produto in enumerate(ordenados):
            tag = "even" if (posicao % 2 == 0) else "odd"
            if not str(produto.get("sku") or "").strip():
                tag = "sem_sku"
            elif not str(produto.get("imagem_url") or "").strip():
                tag = "sem_foto"
            self.produtos_tree.insert("", "end", iid=f"c{posicao}", tags=(tag,), values=(
                produto.get("sku", ""), produto.get("name", ""), produto.get("brand", ""),
                produto.get("model", ""), produto.get("color", ""), produto.get("size", ""),
                _moeda(produto.get("price")), produto.get("quantity", ""),
                produto.get("barcode", ""),
                "tem" if str(produto.get("imagem_url") or "").strip() else "sem",
            ))

    def copiar_catalogo(self, campo):
        selecionados = self.produtos_tree.selection()
        if not selecionados:
            messagebox.showinfo("Catalogo", "Selecione uma ou mais linhas.")
            return
        termos = []
        for iid in selecionados:
            posicao = int(iid[1:])
            if 0 <= posicao < len(self.catalogo_resultados):
                termos.append(str(self.catalogo_resultados[posicao].get(campo, "") or ""))
        if termos:
            texto = "\n".join(termos)
            self.clipboard_clear()
            self.clipboard_append(texto)
            self.status.set(f"{len(termos)} SKU(s) copiado(s)" if campo == "sku" else
                            f"{len(termos)} nome(s) copiado(s)")

    def exportar_catalogo_csv(self):
        if not self.catalogo_resultados:
            messagebox.showinfo("Catalogo", "Consulte o catalogo primeiro.")
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"catalogo_{time.strftime('%Y%m%d_%H%M%S')}.csv")
        if not caminho:
            return
        colunas = ("sku", "name", "brand", "model", "color", "size", "price", "quantity", "barcode")
        try:
            with open(caminho, "w", encoding="utf-8-sig", newline="") as arquivo:
                escritor = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";")
                escritor.writeheader()
                for produto in self.catalogo_resultados:
                    escritor.writerow({campo: produto.get(campo, "") for campo in colunas})
            self.status.set(f"Catalogo exportado: {caminho}")
        except OSError as error:
            messagebox.showerror("Catalogo", f"Falha ao exportar:\n{error}")

    # ==================================================================
    # ABA DASHBOARD
    # ==================================================================
    def _create_dashboard_tab(self):
        """Visao geral da operacao: faixa de numeros, dois graficos e duas
        listas.

        Mudanca de forma: os seis numeros deixaram de ser seis cartoes
        empilhados em grade 3x2 e viraram uma faixa unica de KPIs separada
        por filetes. Card em cada numero produzia xadrez, e o grid 3x2
        truncava a taxa de impressao ("12." em vez de "12.4%") em 1040px.

        A grade de baixo e' 2x2 de blocos com peso declarado: graficos
        (peso 3) em cima, listas (peso 2) embaixo.
        """
        tela = ui.Tela(self.tab_dashboard, linhas=3)
        tela.pack(fill="both", expand=True)
        tela.linha(2, peso=1)

        # --- acoes no cabecalho da pagina
        cabecalho = self.cabecalho_dashboard.acoes
        self.dash_auto_var = tk.BooleanVar(value=self.dash_auto)
        self._alternar_auto = ui.Comutador(
            cabecalho, "Atualizar sozinho", self.dash_auto_var,
            self._alternar_dash_auto, parent_bg=ui.FUNDO)
        self._alternar_auto.pack(side="left", padx=(0, ui.ESPACO_3))
        self.dash_ultimo_label = tk.Label(cabecalho, text="", bg=ui.FUNDO,
                                          fg=ui.TEXTO_FRACO,
                                          font=ui.font(ui.TEXTO_MENOR))
        self.dash_ultimo_label.pack(side="left", padx=(0, ui.ESPACO_3))
        ui.Botao(cabecalho, "Atualizar agora", self.atualizar_dashboard,
                 variante="secundario", parent_bg=ui.FUNDO).pack(side="left")

        # --- faixa 1: KPIs, sem card em volta. Um bloco branco so, e os
        # numeros separados por filete: cartao em cada numero vira xadrez.
        faixa = tk.Frame(tela, bg=ui.BRANCO)
        tela.celula(faixa, 0, 0)
        indicadores = ui.FaixaKpi(faixa, 6, fundo=ui.BRANCO)
        indicadores.pack(fill="x")

        rotulos = (("Pendentes na fila", "pendentes"),
                   ("Impressos hoje", "impressos_hoje"),
                   ("Total confirmados", "total_confirmados"),
                   ("Media por dia", "media_dia"),
                   ("Ultima varredura", "ultima_varredura"),
                   ("Impressao hoje", "taxa"))
        self.dash_cartoes = {}
        for indice, (rotulo, chave) in enumerate(rotulos):
            indicadores.montar(rotulo, "--", indice)
            self.dash_cartoes[chave] = _ValorKpi(indicadores, indice)

        # --- faixa 2: graficos
        graficos = tela.secao(1, 0, peso_linha=3, minima_linha=150)
        graficos.coluna(0, peso=1, minima=320)
        graficos.coluna(1, peso=1, minima=320)
        graficos.linha(0, peso=1)

        bloco_7 = ui.Bloco(graficos, titulo="Impressos nos ultimos 7 dias",
                           fundo=ui.FUNDO)
        graficos.celula(bloco_7, 0, 0)
        self.dash_grafico_7 = GraficoBarras(bloco_7.corpo, altura=132)
        self.dash_grafico_7.pack(fill="both", expand=True)

        bloco_hora = ui.Bloco(graficos, titulo="Impressos por hora (hoje)",
                              fundo=ui.FUNDO)
        graficos.celula(bloco_hora, 0, 1)
        self.dash_grafico_hora = GraficoBarras(bloco_hora.corpo, altura=132)
        self.dash_grafico_hora.pack(fill="both", expand=True)

        # --- faixa 3: listas
        listas = tela.secao(2, 0, peso_linha=2, minima_linha=130)
        listas.coluna(0, peso=1, minima=320)
        listas.coluna(1, peso=1, minima=320)
        listas.linha(0, peso=1)

        mais = ui.Painel(listas, ("nome", "qtd"), titulo="Mais impressos",
                         fundo=ui.FUNDO)
        listas.celula(mais, 0, 0)
        self.dash_top = mais.montar_tabela(
            altura=4, selectmode="none",
            area=self._area_da_pagina("dashboard"))
        self.dash_top.heading("nome", text="Produto")
        self.dash_top.heading("qtd", text="Vezes")
        self.dash_top.column("nome", width=220, minwidth=80, stretch=True,
                             anchor="w")
        self.dash_top.column("qtd", width=60, minwidth=48, stretch=False,
                             anchor="e")

        ultimos = ui.Painel(listas, ("quando", "nome"),
                             titulo="Ultimas impressoes", fundo=ui.FUNDO)
        listas.celula(ultimos, 0, 1)
        self.dash_tree = ultimos.montar_tabela(
            altura=4, selectmode="none",
            area=self._area_da_pagina("dashboard"))
        self.dash_tree.heading("quando", text="Quando")
        self.dash_tree.heading("nome", text="Produto")
        self.dash_tree.column("quando", width=120, minwidth=80, stretch=False,
                              anchor="w")
        self.dash_tree.column("nome", width=260, minwidth=80, stretch=True,
                              anchor="w")

        for tabela in (self.dash_top, self.dash_tree):
            tabela.tag_configure("odd", background=ui.BRANCO)
            tabela.tag_configure("even", background=ui.TINTA)

    def _alternar_dash_auto(self):
        self.dash_auto = bool(self.dash_auto_var.get())
        if self.dash_auto:
            self.atualizar_dashboard()
            self.status.set("Dashboard com atualizacao automatica ON")
        else:
            self.status.set("Dashboard com atualizacao automatica OFF")
        if self.dash_timer:
            self.after_cancel(self.dash_timer)
            self.dash_timer = None

    def atualizar_dashboard(self):
        # Sem a tela de Dashboard (PAGINAS_ATIVAS), nao ha widgets para
        # atualizar: sair cedo evita thread e AttributeError no callback.
        if not hasattr(self, "dash_grafico_7"):
            return
        threading.Thread(target=self._dashboard_thread, daemon=True).start()

    def _dashboard_thread(self):
        try:
            api_url = self._api_url_atual()
            api_token = self._api_token_atual()
            request = urllib.request.Request(
                f"{api_url}/api/etiquetas/stats",
                headers={"Authorization": f"Bearer {api_token}", "Accept": "application/json", "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=40) as response:
                stats = json.loads(response.read().decode("utf-8"))
            self._na_ui(self._mostrar_dashboard, stats)
        except Exception as error:
            self._na_ui(lambda error=error: self.status.set(f"Dashboard indisponivel: {error}"))

    def _mostrar_dashboard(self, stats):
        self.ultimo_stats = stats
        pendentes = int(stats.get("pendentes") or 0)
        impressos = int(stats.get("impressos_periodo") or 0)
        confirmados = int(stats.get("total_confirmados") or 0)
        # data compacta (dd/mm hh:mm) para o card nao ficar largo demais
        crua = str(stats.get("ultima_varredura") or "")
        if crua and crua != "--":
            try:
                varredura = crua.replace("T", " ")
                varredura = f"{varredura[8:10]}/{varredura[5:7]} {varredura[11:16]}"
            except IndexError:
                varredura = crua[:16]
        else:
            varredura = "--"
        media = stats.get("media_dia")
        if media is not None:
            try:
                media = f"{float(media):.1f}"
            except (TypeError, ValueError):
                media = "--"
        else:
            media = "--"
        taxa = stats.get("taxa_hoje")
        if taxa is not None:
            try:
                taxa = f"{float(taxa):.1f}%"
            except (TypeError, ValueError):
                taxa = "--"
        else:
            taxa = "--"

        def set_val(chave, valor):
            if chave in self.dash_cartoes:
                self.dash_cartoes[chave].set(str(valor))

        set_val("pendentes", pendentes)
        set_val("impressos_hoje", impressos)
        set_val("total_confirmados", confirmados)
        set_val("media_dia", media)
        set_val("ultima_varredura", varredura)
        set_val("taxa", taxa)

        por_dia = stats.get("impressos_por_dia") or {}
        dias = sorted(por_dia.keys())[-7:]
        self.dash_grafico_7.desenhar(
            [d[5:] for d in dias], [por_dia[d] for d in dias],
            cor=ACCENT, titulo="Impressos - ultimos 7 dias")
        por_hora = stats.get("impressos_por_hora") or {}
        horas = [str(h).zfill(2) for h in range(0, 24, 3)]
        self.dash_grafico_hora.desenhar(
            horas, [por_hora.get(h, 0) for h in horas],
            cor="#0ea5e9", titulo="Impressos por hora (hoje)")

        for tabela in (self.dash_top, self.dash_tree):
            for item in tabela.get_children():
                tabela.delete(item)

        for indice, rank in enumerate(stats.get("top_produtos", [])):
            self.dash_top.insert("", "end", values=(
                rank.get("nome") or rank.get("fila_id", ""),
                rank.get("qtd", 0)), tags=("odd" if indice % 2 else "even",))

        for indice, ultimo in enumerate(stats.get("ultimos_impressos", [])):
            quando = str(ultimo.get("quando") or "").replace("T", " ")[:16]
            nome = ultimo.get("nome") or ultimo.get("fila_id", "")
            self.dash_tree.insert("", "end", values=(quando, nome),
                                  tags=("odd" if indice % 2 else "even",))

        self.dash_ultimo_label.configure(text=time.strftime("ultima atualizacao %H:%M:%S"))
        self._atualizar_status_direita()
        if self.dash_auto:
            self.dash_timer = self.after(self.dash_seg * 1000, self.atualizar_dashboard)

    # ==================================================================
    # ABA RELATORIOS
    # ==================================================================
    def _create_relatorios_tab(self):
        """Montador livre: fonte, colunas, agrupamento, modelos e previa.

        Mudanca de forma: a tela tinha tres faixas horizontais e SEIS
        cartoes (filtros, colunas, agrupamento, modelos, previa, exportar).
        Seis molduras para uma tarefa. Agora sao tres faixas:

          linha 0  filtros (fonte / de / ate / busca) + Consultar
          linha 1  previa, que e' o trabalho de verdade, com peso 1
          linha 2  configuracao (colunas, agrupamento, modelos, exportar)

        A configuracao foi para BAIXO da previa porque ela e' acessoria e a
        previa e' o resultado. Antes as duas disputavam a mesma linha e a
        previa ficava com metade da altura.
        """
        tela = ui.Tela(self.tab_relatorios, linhas=3)
        tela.pack(fill="both", expand=True)
        tela.linha(1, peso=1)

        acoes = self.cabecalho_relatorios.acoes
        ui.Botao(acoes, "Limpar", self.rel_limpar, variante="secundario",
                 parent_bg=ui.FUNDO).pack(side="left")
        ui.Botao(acoes, "Consultar", self.rel_consultar, variante="primario",
                 parent_bg=ui.FUNDO).pack(side="left", padx=(0, ui.ESPACO_2))

        # --- linha 0: filtros
        filtros = ui.BarraFiltros(tela, colunas=5)
        tela.celula(filtros, 0, 0)

        self.rel_entidade = ttk.Combobox(
            filtros, state="readonly",
            values=list(relatorios.ENTIDADES.values()))
        filtros.campo("Fonte", self.rel_entidade)
        self.rel_entidade.bind("<<ComboboxSelected>>",
                               lambda e: self._rel_atualizar_colunas())
        # ja nasce com a primeira fonte marcada, entao a aba abre consistente
        self.rel_entidade_codigo = list(relatorios.ENTIDADES)[0]
        self.rel_entidade.set(relatorios.ENTIDADES[self.rel_entidade_codigo])

        self.rel_de = ttk.Entry(filtros)
        filtros.campo("De", self.rel_de, hint="aaaa-mm-dd")
        self.rel_ate = ttk.Entry(filtros)
        filtros.campo("Ate", self.rel_ate, hint="aaaa-mm-dd")

        self.rel_busca = SearchField(filtros,
                                     texto="descricao, numero ou cliente...",
                                     parent_bg=ui.FUNDO,
                                     comando=self.rel_consultar)
        # o campo de busca e' o mais largo da linha (o placeholder e' longo),
        # entao ele ocupa as duas ultimas colunas em vez de uma
        filtros.campo("Buscar", self.rel_busca, coluna=3, span=2)

        # --- linha 1: previa (o resultado)
        # as colunas da previa sao dinamicas (ate 14), mas o ids precisam
        # existir na construcao do Treeview
        colunas_prev = tuple(f"c{i}" for i in range(14))
        previa = ui.Painel(tela, colunas_prev, titulo="Previa do relatorio",
                           fundo=ui.FUNDO)
        tela.celula(previa, 1, 0)
        barra = previa.rodape()
        self.rel_status = tk.Label(barra, text="Escolha a fonte e clique em Consultar.",
                                   bg=ui.FUNDO, fg=ui.TEXTO,
                                   font=ui.font(ui.TEXTO_BASE), anchor="w")
        self.rel_status.pack(side="left")
        self.rel_total_label = tk.Label(barra, text="", bg=ui.FUNDO, fg=ui.TEXTO,
                                        font=ui.font(ui.TEXTO_BASE), anchor="e")
        self.rel_total_label.pack(side="right")

        self.rel_max_colunas = 14
        self.rel_tabela = previa.montar_tabela(
            altura=12, selectmode="extended",
            area=self._area_da_pagina("relatorios"))
        # nasce com as 14 colunas colapsadas em largura 0. Sem isto a previa
        # vazia somava 14x200 = 2800px de conteudo e a barra horizontal
        # aparecia assim que a aba abria, antes de existir relatorio algum.
        # `_rel_mostrar` e' quem abre as colunas que o relatorio usa.
        for indice in range(self.rel_max_colunas):
            self.rel_tabela.column(f"c{indice}", width=0, minwidth=0,
                                   stretch=False)
        self.rel_tabela.tag_configure("odd", background=ui.BRANCO)
        self.rel_tabela.tag_configure("even", background=ui.TINTA)
        self.rel_tabela.tag_configure("total", background=ui.MARCA_CLARA,
                                      foreground=ui.MARCA_ESCURA)

        exportar = tk.Frame(barra, bg=ui.FUNDO)
        exportar.pack(side="right", padx=ui.ESPACO_3)
        for texto, formato in (("CSV", "csv"), ("Excel", "xlsx"), ("PDF", "pdf")):
            ui.Botao(exportar, texto, lambda f=formato: self.rel_exportar(f),
                     variante="primario" if formato == "xlsx" else "secundario",
                     tamanho=ui.TEXTO_MENOR, parent_bg=ui.FUNDO).pack(
                         side="left", padx=(0, ui.ESPACO_1))

        # --- linha 2: configuracao em quatro colunas
        config = tela.secao(2, 0)
        config.coluna(0, peso=3, minima=260)
        config.coluna(1, peso=2, minima=200)
        config.coluna(2, peso=2, minima=200)
        config.coluna(3, peso=2, minima=200)
        config.linha(0, peso=1)

        colunas_bloco = ui.Bloco(config, titulo="Colunas do relatorio",
                                  fundo=ui.FUNDO)
        config.celula(colunas_bloco, 0, 0)
        self.rel_colunas = self._rel_lista(colunas_bloco.corpo, height=5)
        self.rel_colunas.pack(fill="both", expand=True)

        opcoes = ui.Bloco(config, titulo="Agrupamento", fundo=ui.FUNDO)
        config.celula(opcoes, 0, 1)
        corpo = opcoes.corpo
        corpo.columnconfigure(0, weight=1)
        self.rel_agrupar = ttk.Combobox(corpo, state="readonly",
                                        values=["(sem agrupamento)"])
        self.rel_agrupar.grid(row=0, column=0, sticky="ew",
                              pady=(0, ui.ESPACO_2))
        self.rel_agrupar.bind("<<ComboboxSelected>>",
                              lambda e: self._rel_sincronizar_agregado())
        self.rel_agregar_col = ttk.Combobox(corpo, state="readonly",
                                            values=["(nenhum)"])
        self.rel_agregar_col.grid(row=1, column=0, sticky="ew",
                                  pady=(0, ui.ESPACO_2))
        self.rel_agregar_col.bind("<<ComboboxSelected>>",
                                  lambda e: self._rel_sincronizar_agregado())
        self.rel_agregar_op = ttk.Combobox(
            corpo, state="readonly",
            values=list(relatorios.AGREGACOES.values()))
        self.rel_agregar_op.grid(row=2, column=0, sticky="ew")

        modelos = ui.Bloco(config, titulo="Modelos salvos", fundo=ui.FUNDO)
        config.celula(modelos, 0, 2)
        corpo = modelos.corpo
        corpo.columnconfigure(0, weight=1)
        self.rel_modelos = self._rel_lista(corpo, height=4)
        self.rel_modelos.grid(row=0, column=0, sticky="nsew")
        self.rel_nome_var = tk.StringVar(value="")
        ttk.Entry(corpo, textvariable=self.rel_nome_var).grid(
            row=1, column=0, sticky="ew", pady=(ui.ESPACO_2, ui.ESPACO_2))
        acoes_modelo = tk.Frame(corpo, bg=ui.FUNDO)
        acoes_modelo.grid(row=2, column=0, sticky="ew")
        for texto, cmd, variante in (("Salvar", self.rel_salvar_modelo, "secundario"),
                                     ("Usar", self.rel_usar_modelo, "secundario"),
                                     ("Excluir", self.rel_apagar_modelo, "perigo")):
            ui.Botao(acoes_modelo, texto, cmd, variante=variante, altura=30,
                     parent_bg=ui.FUNDO).pack(side="left", padx=(0, ui.ESPACO_1))

        self.rel_dados = None
        self.rel_chaves = []
        self.rel_agregado_pendente = False
        self.rel_catalogo = {}
        self._rel_recarregar_modelos()
        self.after(120, self._rel_carregar_catalogo)

    @staticmethod
    def _rel_campo(master, texto):
        """Rotulo de campo do filtro. Fica maiusculo e esverdeado igual o resto
        das legendas, para nao competir com o valor do campo ao lado."""
        tk.Label(master, text=texto.upper(), bg=ui.BRANCO, fg=ui.TEXTO_FRACO,
                 font=ui.font(ui.TEXTO_MENOR, "bold")).pack(side="left")

    @staticmethod
    def _rel_lista(master, height, largura=None):
        """Listbox com a mesma moldura das tabelas, para as tres listas da
        aba de Relatorios nao destoarem do resto do painel."""
        lista = tk.Listbox(master, selectmode="multiple", height=height,
                           width=largura, bg=ui.BRANCO, fg=ui.TINTA_TEXTO,
                           bd=0, highlightthickness=1, highlightbackground=ui.BORDA,
                           highlightcolor=ui.MARCA, font=ui.font(ui.TEXTO_MENOR),
                           activestyle="none", selectbackground=ui.MARCA_CLARA,
                           selectforeground=ui.MARCA_ESCURA, exportselection=False)
        lista.configure(highlightbackground=ui.BORDA)
        return lista

    def _rel_carregar_catalogo(self):
        """Busca as colunas reais no servidor. Sem servidor, segue com as fixas."""
        self._rel_atualizar_colunas()
        url = self._api_url_atual()
        token = self._api_token_atual()

        def trabalho():
            try:
                dados = relatorios.catalogo(url, token)
                entidades = dados.get("entidades") or {}
                if isinstance(entidades, dict):
                    self._na_ui(self._rel_aplicar_catalogo, entidades)
            except Exception as erro:
                escrever_erro(f"Relatorios catalogo: {erro}")

        threading.Thread(target=trabalho, daemon=True).start()

    def _rel_aplicar_catalogo(self, entidades):
        self.rel_catalogo = {k: v for k, v in entidades.items()
                             if k in relatorios.ENTIDADES and isinstance(v, list) and v}
        if self.rel_catalogo:
            self._rel_atualizar_colunas()

    def _rel_entidade_codigo_atual(self):
        rotulo = self.rel_entidade.get()
        for codigo, nome in relatorios.ENTIDADES.items():
            if nome == rotulo:
                return codigo
        return list(relatorios.ENTIDADES)[0]

    def _rel_atualizar_colunas(self):
        """Repoe as colunas disponiveis conforme a fonte escolhida."""
        self.rel_entidade_codigo = self._rel_entidade_codigo_atual()
        disponiveis = list(relatorios.COLUNAS_FIXAS)
        if self.rel_catalogo and self.rel_entidade_codigo in self.rel_catalogo:
            disponiveis = self.rel_catalogo[self.rel_entidade_codigo]
        anteriores = set(self.rel_colunas.curselection())
        self.rel_colunas.delete(0, "end")
        for chave in disponiveis:
            self.rel_colunas.insert("end", relatorios.rotulo_coluna(chave))
        picked = 0
        for indice, chave in enumerate(disponiveis):
            if chave in anteriores or picked == 0:
                self.rel_colunas.selection_set(indice)
                picked += 1
        # ao menos a primeira coluna fica marcada
        if not self.rel_colunas.curselection():
            self.rel_colunas.selection_set(0)
        self._rel_sincronizar_agregado()

    def _rel_colunas_selecionadas(self):
        """Devolve as chaves (nao os rotulos) das colunas marcadas."""
        disponiveis = list(relatorios.COLUNAS_FIXAS)
        if self.rel_catalogo and self.rel_entidade_codigo in self.rel_catalogo:
            disponiveis = self.rel_catalogo[self.rel_entidade_codigo]
        escolhidas = []
        for indice in self.rel_colunas.curselection():
            if indice < len(disponiveis):
                escolhidas.append(disponiveis[indice])
        return escolhidas or disponiveis[:1]

    def _rel_sincronizar_agregado(self, agrupar=None):
        """A agregacao so faz sentido agrupando; sem grupo, desliga os dois campos
        e repopula as listas com as colunas da fonte atual."""
        disponiveis = self._rel_chaves_disponiveis()
        if agrupar is not None:
            self.rel_agrupar.set(agrupar)
        agrupando = self.rel_agrupar.get() != "(sem agrupamento)"
        self.rel_agregar_col.config(state="readonly" if agrupando else "disabled")
        self.rel_agregar_op.config(state="readonly" if agrupando else "disabled")
        self.rel_agregado_pendente = agrupando
        rotulos = [relatorios.rotulo_coluna(c) for c in disponiveis]
        anteriores_agrupar = self.rel_agrupar.get()
        anteriores_col = self.rel_agregar_col.get()
        self.rel_agrupar["values"] = ["(sem agrupamento)"] + rotulos
        self.rel_agregar_col["values"] = ["(nenhum)"] + rotulos
        if agrupar is None:
            if anteriores_agrupar in rotulos:
                self.rel_agrupar.set(anteriores_agrupar)
            else:
                self.rel_agrupar.set("(sem agrupamento)")
            if anteriores_col in rotulos:
                self.rel_agregar_col.set(anteriores_col)
            else:
                self.rel_agregar_col.set("valor" if "valor" in disponiveis else "(nenhum)")

    def _rel_chaves_disponiveis(self):
        disponiveis = list(relatorios.COLUNAS_FIXAS)
        if self.rel_catalogo and self.rel_entidade_codigo in self.rel_catalogo:
            disponiveis = self.rel_catalogo[self.rel_entidade_codigo]
        return disponiveis

    def _rel_chave_por_rotulo(self, rotulo):
        for chave in self._rel_chaves_disponiveis():
            if relatorios.rotulo_coluna(chave) == rotulo:
                return chave
        return None

    def _rel_filtros(self):
        filtros = {}
        if self.rel_de.get().strip():
            filtros["de"] = self.rel_de.get().strip()
        if self.rel_ate.get().strip():
            filtros["ate"] = self.rel_ate.get().strip()
        if self.rel_busca.get().strip():
            filtros["termo"] = self.rel_busca.get().strip()
        return filtros

    def rel_consultar(self):
        colunas = self._rel_colunas_selecionadas()
        # Le direto dos widgets, em vez de depender de rel_agregado_pendente:
        # aplicar modelo ou trocar a fonte mexe nos campos sem passar pelo
        # evento da combobox, e a agregacao sumia sem aviso.
        agrupar = None
        agregar = []
        operacao = "soma"
        rotulo_grupo = self.rel_agrupar.get()
        if rotulo_grupo and rotulo_grupo != "(sem agrupamento)":
            chave_grupo = self._rel_chave_por_rotulo(rotulo_grupo)
            rotulo_agregado = self.rel_agregar_col.get()
            chave_agregada = self._rel_chave_por_rotulo(rotulo_agregado)
            if chave_grupo and chave_agregada:
                agrupar = chave_grupo
                agregar = [chave_agregada]
                operacao = relatorios.chave_agregacao(
                    self.rel_agregar_op.get()) or "soma"
        self.rel_agregado_pendente = False
        query = relatorios.montar_query(
            self.rel_entidade_codigo, colunas, filtros=self._rel_filtros(),
            agrupar=agrupar, agregar=agregar or None, limite=5000,
            operacao=operacao)
        # URL e token sao lidos AQUI, na main thread: a thread nao pode tocar em
        # widget, e o cache so se atualiza quando a leitura acontece na main.
        url = self._api_url_atual()
        token = self._api_token_atual()
        self.rel_status.configure(text="Consultando...")
        self.rel_tabela.delete(*self.rel_tabela.get_children())
        threading.Thread(target=self._rel_consultar_thread,
                         args=(query, operacao, url, token), daemon=True).start()

    def _rel_consultar_thread(self, query, operacao="soma", url=None, token=None):
        try:
            if url is None or token is None:
                url, token = self._api_url_atual(), self._api_token_atual()
            corpo = relatorios.consultar(url, token, query)
        except urllib.error.HTTPError as erro:
            # _na_ui so aceita positional: os kwargs de configure iriam para
            # _na_ui e nao para o metodo
            codigo = erro.code
            if codigo == 401:
                texto = "Sessao expirada: atualize o token em Configuracoes."
            elif codigo == 403:
                texto = "Sem permissao para ler dados financeiros."
            else:
                texto = f"Falha na consulta ({codigo})."
            self._na_ui(self.rel_status.configure, text=texto)
            return
        except (urllib.error.URLError, OSError, ValueError) as erro:
            escrever_erro(f"Relatorios: {erro}")
            self._na_ui(self.rel_status.configure, text="Servidor nao respondeu.")
            return
        self._na_ui(self._rel_mostrar, corpo, operacao)

    def _rel_mostrar(self, corpo, operacao="soma"):
        """Pinta a previa e guarda os dados ja no formato de exportacao."""
        linhas = corpo.get("linhas") or []
        colunas = corpo.get("colunas") or self._rel_colunas_selecionadas()
        totais = corpo.get("totais") or {}
        dados = relatorios.preparar_linhas(colunas, linhas, totais)

        self.rel_tabela.delete(*self.rel_tabela.get_children())
        # o ttk nao tem "esconder coluna": colapsa as excedentes em largura 0
        for indice in range(self.rel_max_colunas):
            cid = f"c{indice}"
            if indice < len(dados["colunas"]):
                rotulo = dados["colunas"][indice]
                eh_numero = any(k in rotulo.lower() for k in
                                ("valor", "saldo", "total", "quantidade"))
                self.rel_tabela.heading(cid, text=rotulo,
                                        command=lambda i=indice: self._rel_ordenar(i))
                self.rel_tabela.column(cid, width=150 if eh_numero else 220,
                                       minwidth=60, stretch=True,
                                       anchor="e" if eh_numero else "w")
            else:
                self.rel_tabela.heading(cid, text="")
                self.rel_tabela.column(cid, width=0, minwidth=0, stretch=False)
        for n, linha in enumerate(dados["linhas"]):
            self.rel_tabela.insert("", "end", values=["" if v is None else v for v in linha],
                                   tags=("odd" if n % 2 else "even",))

        # guarda as chaves cruas: a tela mostra rotulos, a exportacao tambem,
        # mas o merge dos totais precisa casar com a coluna pelo rotulo
        self.rel_chaves = list(colunas)
        self.rel_dados = dados
        self.rel_dados.update({
            "titulo": relatorios.ENTIDADES.get(self.rel_entidade_codigo, "Relatorio"),
            "subtitulo": relatorios.subtitulo_padrao(self._rel_filtros(), len(linhas)),
            "rodape": f"Painel AUTOMATA - gerado em {time.strftime('%d/%m/%Y %H:%M')}",
        })
        resumo = []
        for rotulo, valor in dados["totais"].items():
            if isinstance(valor, (int, float)):
                resumo.append(f"{rotulo}: {valor:,.2f}")
        self.rel_total_label.configure(text="  |  ".join(resumo) or f"{len(linhas)} linha(s)")
        self.rel_status.configure(text="Pronto.")

    def _rel_ordenar(self, indice):
        """Ordena a previa e a exportacao pela coluna. Alterna crescente/decrescente."""
        if not self.rel_dados or not self.rel_dados.get("linhas"):
            return
        self.rel_ordem = getattr(self, "rel_ordem", {})
        chave = (indice, not self.rel_ordem.get(indice, False))
        self.rel_ordem[indice] = chave[1]
        crescente = chave[1]

        def valor_de(linha):
            bruto = linha[indice] if indice < len(linha) else None
            if isinstance(bruto, (int, float)) and not isinstance(bruto, bool):
                return (0, float(bruto))
            return (1, str(bruto or "").lower())

        self.rel_dados["linhas"].sort(key=valor_de, reverse=not crescente)
        self._rel_repintar_previa()

    def _rel_repintar_previa(self):
        """Redesenha a previa a partir de self.rel_dados, sem refazer a consulta."""
        self.rel_tabela.delete(*self.rel_tabela.get_children())
        for n, linha in enumerate(self.rel_dados["linhas"]):
            self.rel_tabela.insert("", "end",
                                   values=["" if v is None else v for v in linha],
                                   tags=("odd" if n % 2 else "even",))
        self.rel_status.configure(text="Ordenado localmente.")

    def rel_limpar(self):
        self.rel_tabela.delete(*self.rel_tabela.get_children())
        self.rel_dados = None
        self.rel_de.delete(0, "end")
        self.rel_ate.delete(0, "end")
        self.rel_busca.limpar()
        self.rel_total_label.configure(text="")
        self.rel_status.configure(text="Escolha a fonte e clique em Consultar.")

    def rel_salvar_modelo(self):
        nome = self.rel_nome_var.get().strip()
        if not nome:
            messagebox.showinfo("Relatorios", "Informe um nome para o modelo.")
            return
        relatorios.salvar_modelo(nome, self._rel_definicao())
        self._rel_recarregar_modelos()
        self.rel_status.configure(text=f"Modelo '{nome}' salvo.")

    def rel_usar_modelo(self):
        selecao = self.rel_modelos.curselection()
        if not selecao:
            return
        nome = self.rel_modelos.get(selecao[0])
        for modelo in relatorios.carregar_modelos():
            if modelo.get("nome") == nome:
                self._rel_aplicar(modelo)
                return

    def rel_apagar_modelo(self):
        selecao = self.rel_modelos.curselection()
        if not selecao:
            return
        nome = self.rel_modelos.get(selecao[0])
        if not messagebox.askyesno("Relatorios", f"Excluir o modelo '{nome}'?"):
            return
        relatorios.apagar_modelo(nome)
        self._rel_recarregar_modelos()
        self.rel_status.configure(text=f"Modelo '{nome}' excluido.")

    def _rel_definicao(self):
        return {
            "entidade": self.rel_entidade_codigo,
            "colunas": self._rel_colunas_selecionadas(),
            "filtros": self._rel_filtros(),
            "agrupar": self.rel_agrupar.get(),
            "agregar": self.rel_agregar_col.get(),
            "operacao": self.rel_agregar_op.get(),
        }

    def _rel_aplicar(self, modelo):
        entidade = modelo.get("entidade")
        if entidade in relatorios.ENTIDADES:
            self.rel_entidade.set(relatorios.ENTIDADES[entidade])
            self.rel_entidade_codigo = entidade
            self._rel_atualizar_colunas()
            disponiveis = self._rel_chaves_disponiveis()
            marcadas = self.rel_colunas.curselection()
            self.rel_colunas.selection_clear(0, "end")
            for chave in modelo.get("colunas", []):
                if chave in disponiveis:
                    self.rel_colunas.selection_set(disponiveis.index(chave))
            if not self.rel_colunas.curselection():
                for indice in marcadas:
                    self.rel_colunas.selection_set(indice)
        filtros = modelo.get("filtros") or {}
        for campo, widget in (("de", self.rel_de), ("ate", self.rel_ate),
                              ("termo", self.rel_busca)):
            widget.delete(0, "end")
            if filtros.get(campo):
                widget.insert(0, filtros[campo])
        rotulo_agrupar = modelo.get("agrupar") or "(sem agrupamento)"
        if rotulo_agrupar not in self.rel_agrupar["values"]:
            rotulo_agrupar = "(sem agrupamento)"
        rotulo_agregar = modelo.get("agregar") or "(nenhum)"
        if rotulo_agregar not in self.rel_agregar_col["values"]:
            rotulo_agregar = "(nenhum)"
        operacao = modelo.get("operacao")
        if operacao not in self.rel_agregar_op["values"]:
            operacao = list(relatorios.AGREGACOES.values())[0]
        self.rel_agregar_op.set(operacao)
        self._rel_sincronizar_agregado(agrupar=rotulo_agrupar)
        self.rel_agregar_col.set(rotulo_agregar)
        self.rel_status.configure(text=f"Modelo '{modelo.get('nome')}' carregado. Click em Consultar.")

    def _rel_recarregar_modelos(self):
        self.rel_modelos.delete(0, "end")
        for modelo in relatorios.carregar_modelos():
            self.rel_modelos.insert("end", modelo.get("nome", "?"))

    def rel_exportar(self, formato):
        if not self.rel_dados or not self.rel_dados.get("linhas"):
            messagebox.showinfo("Relatorios", "Consulte um relatorio antes de exportar.")
            return
        aviso = relatorios.aviso_limite(formato, len(self.rel_dados["linhas"]))
        if aviso and not messagebox.askyesno("Relatorios", aviso + "\n\nExportar mesmo assim?"):
            return
        extensoes = {"csv": ".csv", "xlsx": ".xlsx", "pdf": ".pdf"}
        nomes = {"csv": "CSV", "xlsx": "Excel", "pdf": "PDF"}
        caminho = filedialog.asksaveasfilename(
            defaultextension=extensoes[formato],
            filetypes=[(nomes[formato], f"*{extensoes[formato]}")],
            initialfile=f"relatorio_{time.strftime('%Y%m%d_%H%M%S')}{extensoes[formato]}")
        if not caminho:
            return
        try:
            relatorio_export.gerar(caminho, self.rel_dados, formato)
        except Exception as erro:
            escrever_erro(f"Exportacao {formato}: {erro}")
            messagebox.showerror("Relatorios", f"Falha ao exportar:\n{erro}")
            return
        self.rel_status.configure(text=f"Exportado: {os.path.basename(caminho)}")

    # ==================================================================
    # ABA CONFIGURACOES
    # ==================================================================
    # grupos da aba de configuracao: o nome do metodo que monta cada um e a
    # ordem em que aparecem no segmentado
    GRUPOS_CONFIG = (("conexao", "Conexao"), ("impressao", "Impressao"),
                     ("preferencias", "Preferencias"),
                     ("diagnostico", "Diagnostico"))

    def _create_config_tab(self):
        """Configuracao em abas, uma por assunto.

        Mudanca de forma: eram quatro `Cartao` numa grade 2x2. Em 1040px
        cada card ficava com ~495px e os tres botoes de diagnostico (212px
        cada) nao cabiam, obrigando a `BarraBotoes` a quebrar linha e
        empurrando o rotulo de status para fora. Agora cada assunto tem a
        largura inteira da pagina e so um fica visivel por vez, entao nada
        precisa se comprimir para caber ao lado de outro assunto.
        """
        tela = ui.Tela(self.tab_config, linhas=2)
        tela.pack(fill="both", expand=True)
        tela.linha(1, peso=1)

        self.config_segmentado = ui.BotaoSegmentado(
            tela, [texto for _, texto in self.GRUPOS_CONFIG],
            comando=self._trocar_grupo_config, parent_bg=ui.FUNDO,
            valor=self.GRUPOS_CONFIG[0][1], altura=34)
        tela.celula(self.config_segmentado, 0, 0, sticky="ew")

        # `place` aqui e' troca de visao, nao empilhamento: as quatro paginas
        # ocupam a mesma celula e uma delas fica visivel. O frame que as
        # contem e' gridded por `tela`, e cada pagina e' grid por dentro.
        pilha = tk.Frame(tela, bg=ui.FUNDO)
        tela.celula(pilha, 1, 0)

        self.config_vistas = {}
        for chave, texto in self.GRUPOS_CONFIG:
            pagina = ui.Coluna(pilha, fundo=ui.FUNDO)
            pagina.coluna(0, peso=1)
            pagina.linha(0, peso=1)
            # placeadas uma a uma so para o conteudo ser medido; `place` nao
            # empilha, entao as quatro ficariam no mesmo lugar, uma por cima
            # da outra. Depois do laco so a ativa continua no lugar.
            pagina.place(relx=0, rely=0, relwidth=1, relheight=1)
            bloco = ui.Bloco(pagina, titulo=texto, fundo=ui.FUNDO,
                             padding=ui.ESPACO_5)
            pagina.celula(bloco, 0, 0)
            bloco.corpo.columnconfigure(0, weight=1)
            bloco.corpo.rowconfigure(0, weight=1)
            getattr(self, f"_criar_{chave}")(bloco.corpo)
            self.config_vistas[chave] = pagina

        self.vista_config = self.GRUPOS_CONFIG[0][0]
        for pagina in self.config_vistas.values():
            pagina.place_forget()
        self.config_vistas[self.vista_config].place(
            relx=0, rely=0, relwidth=1, relheight=1)

    def _trocar_grupo_config(self, rotulo):
        for chave, texto in self.GRUPOS_CONFIG:
            if texto != rotulo:
                continue
            self.vista_config = chave
            for nome, pagina in self.config_vistas.items():
                pagina.place_forget()
            self.config_vistas[chave].place(relx=0, rely=0, relwidth=1,
                                            relheight=1)
            # o conteudo de cada grupo foi montado escondido e alguns
            # widgets (canvas, barras) so calculam o tamanho ao aparecer
            self.update_idletasks()
            return

    def _criar_conexao(self, card):
        ttk.Label(card, text="CONEXAO COM A API", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(card, text="URL API ETIQUETAS", style="Field.TLabel").grid(row=1, column=0, sticky="sw")
        self.api_url_entry = ttk.Entry(card, width=18)
        self.api_url_entry.insert(0, self.api_url)
        self.api_url_entry.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 8), pady=(4, 8))
        ttk.Label(card, text="TOKEN API", style="Field.TLabel").grid(row=3, column=0, sticky="sw")
        self.api_token_entry = ttk.Entry(card, width=18, show="*")
        self.api_token_entry.insert(0, self.api_token)
        self.api_token_entry.grid(row=4, column=0, columnspan=2, sticky="ew", padx=(0, 8), pady=(4, 8))
        ui.Botao(card, "Testar conexao", self.testar_conexao, variante="primario",
                parent_bg=ui.BRANCO).grid(row=5, column=0, columnspan=2,
                                          sticky="ew", pady=(ui.ESPACO_2, 0))
        self.conexao_ok = ttk.Label(card, text="", style="Field.TLabel")
        self.conexao_ok.grid(row=6, column=0, columnspan=2, sticky="w",
                            pady=(ui.ESPACO_2, 0))

    def _criar_impressao(self, card):
        card.columnconfigure(0, weight=1, uniform="imp")
        card.columnconfigure(1, weight=1, uniform="imp")
        ttk.Label(card, text="AJUSTE DA ETIQUETA", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w",
            pady=(0, ui.ESPACO_2))
        # 2x2: os quatro campos cabem em qualquer largura
        campos = (
            ("Offset X (mm)", "offset_x_entry", f"{self.offset_x_mm:.1f}".replace(".", ","), 10),
            ("Offset Y (mm)", "offset_y_entry", f"{self.offset_y_mm:.1f}".replace(".", ","), 10),
            ("Lote (etiquetas)", "batch_entry", str(self.batch_size), 8),
            ("Pausa (s)", "pause_entry", f"{self.batch_pause:g}", 8),
        )
        for indice, (rotulo, atributo, valor, largura) in enumerate(campos):
            linha, coluna = divmod(indice, 2)
            ttk.Label(card, text=rotulo, style="Field.TLabel").grid(
                row=linha * 2, column=coluna, sticky="w",
                padx=(0 if coluna == 0 else ui.ESPACO_2, 0),
                pady=(0 if linha == 0 else ui.ESPACO_2, 0))
            entrada = ttk.Entry(card, width=largura)
            entrada.insert(0, valor)
            entrada.grid(row=linha * 2 + 1, column=coluna, sticky="w",
                         padx=(0 if coluna == 0 else ui.ESPACO_2, 0),
                         pady=(ui.ESPACO_1, 0))
            setattr(self, atributo, entrada)
        ttk.Label(card, text=("A impressao e BPLB/RAW direto na fila. Os offsets "
                              "deslocam o conteudo em milimetros; o lote divide o "
                              "envio em blocos com pausa entre eles."),
                  style="Field.TLabel", wraplength=260).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _criar_preferencias(self, card):
        ttk.Label(card, text="PREFERENCIAS", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 12))
        # reaproveita a mesma variavel usada no Dashboard (evita dessincronia)
        if not hasattr(self, "dash_auto_var"):
            self.dash_auto_var = tk.BooleanVar(value=self.dash_auto)
        ttk.Checkbutton(card, text="Atualizar Dashboard automaticamente",
                        variable=self.dash_auto_var,
                        command=self._alternar_dash_auto).pack(anchor="w")
        linha_seg = ttk.Frame(card, style="TFrame")
        linha_seg.pack(anchor="w", pady=(4, 0))
        ttk.Label(linha_seg, text="Intervalo (s):", style="Field.TLabel").pack(side="left")
        self.dash_seg_entry = ttk.Entry(linha_seg, width=6)
        self.dash_seg_entry.insert(0, str(self.dash_seg))
        self.dash_seg_entry.pack(side="left", padx=(ui.ESPACO_2, 0))
        self.auto_imprimir_var = tk.BooleanVar(value=self.auto_imprimir)
        ttk.Checkbutton(card, text="Imprimir automaticamente novos itens ao chegar",
                        variable=self.auto_imprimir_var).pack(anchor="w", pady=(8, 0))
        self.csv_var = tk.BooleanVar(value=self.confirmar_csv)
        ttk.Checkbutton(card, text="Salvar CSV das etiquetas impressas",
                        variable=self.csv_var).pack(anchor="w", pady=(4, 0))

    def _criar_diagnostico(self, card):
        ttk.Label(card, text="DIAGNOSTICO", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        endpoints = f"Produtos : {self._api_url_padrao_text()}/api/etiquetas/produtos\n" \
                    f"Busca    : .../produtos/busca?termo=\n" \
                    f"Confirmar: .../produtos/confirmar\n" \
                    f"Stats    : .../stats"
        ttk.Label(card, text=endpoints, style="Field.TLabel", justify="left",
                  wraplength=360).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 12))
        # quebra o caminho em varias linhas para nao estourar a largura do card
        ttk.Label(card, text=f"Config: {CONFIG_FILE}\nLog   : {LOG_FILE}",
                  style="Field.TLabel", justify="left", wraplength=360).grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(0, 12))
        # tres botoes de 212px side a side num card de 495px estouravam a
        # largura e o "Gerar etiqueta teste" saia pela borda. A barra reflow
        # decide quantos cabem em cada linha.
        diagnostico = ui.BarraBotoes(card, fundo=ui.BRANCO, espaco=ui.ESPACO_2)
        diagnostico.grid(row=3, column=0, columnspan=3, sticky="ew")
        for texto, comando in (("Abrir pasta", self.abrir_pasta),
                               ("Ver ultimos erros", self.ver_erros),
                               ("Gerar etiqueta teste", self.gerar_etiqueta_teste)):
            diagnostico.criar(texto, comando, variante="secundario", altura=32,
                              parent_bg=ui.BRANCO)

    def _api_url_padrao_text(self):
        return self._api_url_cache or API_URL_PADRAO

    def _api_url_atual(self):
        """URL da API. Threads leem o cache (Tk so pode ser usado na main thread)."""
        if threading.current_thread() is threading.main_thread():
            try:
                self._api_url_cache = self.api_url_entry.get().strip().rstrip("/")
            except (AttributeError, tk.TclError):
                pass
        return self._api_url_cache or API_URL_PADRAO

    def _api_token_atual(self):
        if threading.current_thread() is threading.main_thread():
            try:
                self._api_token_cache = self.api_token_entry.get().strip()
            except (AttributeError, tk.TclError):
                pass
        return self._api_token_cache or API_TOKEN_PADRAO

    def testar_conexao(self):
        api_url = self._api_url_atual()
        api_token = self._api_token_atual()
        if not api_url or not api_token:
            messagebox.showwarning("Conexao", "Informe a URL da API e o token.")
            return
        threading.Thread(target=self._testar_conexao_thread, args=(api_url, api_token), daemon=True).start()

    def _testar_conexao_thread(self, api_url, api_token):
        try:
            request = urllib.request.Request(
                f"{api_url}/api/etiquetas/stats",
                headers={"Authorization": f"Bearer {api_token}", "Accept": "application/json", "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            self._na_ui(lambda: (self.conexao_ok.configure(
                text=f"Conexao OK - {body.get('pendentes', 0)} pendentes, "
                     f"{body.get('total_confirmados', 0)} confirmados no total",
                foreground=ACCENT_DARK), self.status.set("Conexao com a API OK")))
        except Exception as error:
            self._na_ui(lambda error=error: (self.conexao_ok.configure(
                text=f"Falha: {error}", foreground=DANGER),
                self.status.set("Falha na conexao com a API")))

    def abrir_pasta(self):
        import subprocess
        try:
            if sys.platform.startswith("darwin"):
                subprocess.Popen(["open", _config_dir()])
            else:
                subprocess.Popen(["explorer", _config_dir()])
        except Exception as error:
            self.status.set(f"Nao foi possivel abrir a pasta: {error}")

    def ver_erros(self):
        try:
            with open(LOG_FILE, encoding="utf-8") as arquivo:
                linhas = arquivo.readlines()[-40:]
        except OSError:
            linhas = ["(sem log ainda)"]
        janela = tk.Toplevel(self)
        janela.title("Ultimos erros")
        janela.geometry("720x420")
        texto = tk.Text(janela, wrap="none", font=ui.fonte_mono(ui.TEXTO_BASE))
        texto.pack(fill="both", expand=True)
        texto.insert("1.0", "".join(linhas))
        texto.configure(state="disabled")

    def gerar_etiqueta_teste(self):
        produto = {"name": "ETIQUETA DE TESTE", "color": "BRANCO", "size": "P",
                   "price": 19.90, "sku": "TST-999-XYZ", "barcode": ""}
        stream = build_row_data_pplb([produto], self.offset_x_mm, self.offset_y_mm)
        caminho = os.path.join(_config_dir(), "etiqueta_teste.bin")
        try:
            with open(caminho, "wb") as arquivo:
                arquivo.write(stream)
            self.status.set(f"Etiqueta teste gerada em {caminho}")
            messagebox.showinfo("Teste", f"Etiqueta BPLB gerada em:\n{caminho}\n\n"
                                         f"Pode ser enviada para a impressora como RAW para calibrar offsets.")
        except OSError as error:
            messagebox.showerror("Teste", f"Falha ao gerar:\n{error}")

    def _salvar_config_aba(self):
        config = self.save_config()
        self._set_api_status(True)
        self.status.set("Configuracoes salvas")
        self._agendar_dash_depois_salvar()
        messagebox.showinfo("Configuracoes", "Configuracoes salvas com sucesso.")

    def _agendar_dash_depois_salvar(self):
        def _reagendar():
            if self.dash_timer:
                self.after_cancel(self.dash_timer)
                self.dash_timer = None
            self.dash_auto_var.set(self.dash_auto)
            if self.dash_auto:
                self.atualizar_dashboard()
        self.after(150, _reagendar)

    # ==================================================================
    # LOGICA DA FILA / API
    # ==================================================================
    def refresh_printers(self):
        names = get_windows_printers()
        self.printer_box["values"] = names
        current = self.printer.get()
        if not current or current not in names:
            self.printer.set(names[0] if names else "")
        if not current:
            escrever_erro(f"Impressora padrao selecionada: {self.printer.get()}")

    def add_product(self, product):
        try:
            copies = max(1, int(float(product.get("copies") or 1)))
        except (TypeError, ValueError):
            copies = 1
        product["copies"] = str(copies)
        self.queue.append(product)
        self._render_fila()
        self.status.set(f"Fila: {len(self.queue)} itens")

    def start_api_watcher(self):
        threading.Thread(target=self._api_watcher_loop, daemon=True).start()

    def carregar_fila_inicial(self):
        threading.Thread(target=self._carregar_fila_inicial_thread, daemon=True).start()

    def _carregar_fila_inicial_thread(self):
        try:
            api_url = self._api_url_atual()
            api_token = self._api_token_atual()
            novos = self._fetch_todas_paginas(api_url, api_token, esperar=False)
            if novos:
                self._na_ui(self._adicionar_da_api, novos)
        except Exception:
            pass

    def _api_watcher_loop(self):
        api_url = self._api_url_atual()
        api_token = self._api_token_atual()
        self._na_ui(lambda: self._set_api_status(True))
        while True:
            try:
                novos = self._fetch_todas_paginas(api_url, api_token, esperar=True)
                if novos:
                    self._na_ui(self._adicionar_da_api, novos)
            except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as error:
                escrever_erro(f"API watcher: {error}")
                self._na_ui(lambda: self._set_api_status(False))
                time.sleep(5)

    def _fetch_todas_paginas(self, api_url, api_token, esperar=False):
        novos = []
        page = 1
        while True:
            base = f"{api_url}/api/etiquetas/produtos?pagina={page}&limite=100"
            if esperar and page == 1:
                base += "&esperar=1"
            request = urllib.request.Request(
                base,
                headers={"Authorization": f"Bearer {api_token}", "Accept": "application/json", "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=70) as response:
                body = json.loads(response.read().decode("utf-8"))
            produtos = body.get("data", [])
            for product in produtos:
                fila_id = str(product.get("fila_id", "") or "").strip()
                if not fila_id or fila_id in self.api_seen:
                    continue
                self.api_seen.add(fila_id)
                product["copies"] = product.get("quantity") or 1
                novos.append(product)
            if not body.get("tem_mais") or not produtos:
                break
            page += 1
        return novos

    def _set_api_status(self, connected):
        try:
            if connected:
                self._api_texto = "API conectada"
                self._api_cor = ACCENT
                self.status_dot.configure(fg=ACCENT)
            else:
                self._api_texto = "API desconectada"
                self._api_cor = DANGER
                self.status_dot.configure(fg=DANGER)
            self._desenhar_api_status()
        except tk.TclError:
            pass

    def _reconectar_api(self):
        self.status.set("Reconectando na API...")
        self.after(10, self.fetch_api_products)

    def _adicionar_da_api(self, produtos):
        for product in produtos:
            self.queue.append(product)
        self._render_fila()
        self.status.set(f"API: {len(produtos)} produto(s) novo(s) | Fila: {len(self.queue)} itens")
        if self.auto_imprimir and produtos:
            self.after(300, self.print_queue)

    def fetch_api_products(self):
        api_url = self._api_url_atual()
        api_token = self._api_token_atual()
        if not api_url or not api_token:
            messagebox.showwarning("API", "Informe a URL da API e o token.")
            return
        self.api_url = api_url
        self.api_token = api_token
        try:
            novos = self._fetch_todas_paginas(api_url, api_token, esperar=False)
            if novos:
                self._adicionar_da_api(novos)
            self.save_config()
            self._set_api_status(True)
            self.status.set(f"API: {len(novos)} produto(s) recebido(s) | Fila: {len(self.queue)} itens")
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as error:
            messagebox.showerror("API", f"Nao foi possivel buscar produtos:\n{error}")

    # ==================================================================
    # IMPRESSAO
    # ==================================================================
    def make_stream(self, produtos=None):
        self.save_config()
        produtos = produtos if produtos is not None else self.queue
        jobs = []
        for product in produtos:
            try:
                copies = max(1, int(float(product.get("copies") or 1)))
            except (TypeError, ValueError):
                copies = 1
            jobs.extend([product] * copies)
        streams = []
        for start in range(0, len(jobs), self.batch_size):
            batch = jobs[start:start + self.batch_size]
            stream = bytearray()
            for row_start in range(0, len(batch), 3):
                stream.extend(build_row_data_pplb(batch[row_start:row_start + 3], self.offset_x_mm, self.offset_y_mm, self.used_codes))
            streams.append(bytes(stream))
        return streams, len(jobs)

    def print_queue(self, somente_selecionadas=False):
        escrever_erro("Botao IMPRIMIR FILA clicado")
        if not self.queue:
            escrever_erro("Fila vazia, abortando")
            messagebox.showwarning("Impressao", "A fila esta vazia")
            return
        produtos = self._produtos_selecionados() if somente_selecionadas else self.queue
        if not produtos:
            messagebox.showinfo("Impressao", "Nenhum item selecionado.")
            return
        printer_name = self.printer.get()
        escrever_erro(f"Fila: {len(produtos)} itens | impressora selecionada: {printer_name}")
        if not printer_name or printer_name == "Nenhuma Impressora Encontrada":
            escrever_erro("Nenhuma impressora ativa, abortando")
            messagebox.showerror("Impressao", "Nao foi configurada nenhuma impressora ativa no sistema.")
            return
        escrever_erro(f"Impressao iniciada: {len(produtos)} item(ns) na impressora {printer_name}")
        try:
            streams, count = self.make_stream(produtos)
        except Exception as error:
            escrever_erro(f"make_stream: {error}")
            messagebox.showerror("Configuracao", str(error))
            return
        escrever_erro(f"{count} etiqueta(s), {len(streams)} lote(s) preparado(s)")
        threading.Thread(target=self.send_batches, args=(streams, count, produtos), daemon=True).start()

    def _purge_stuck_jobs(self, printer_name):
        """
        Nao apaga jobs automaticamente.

        Apagar jobs exige permissao de gerenciamento da fila e nao e
        necessario para uma impressao RAW normal. A fila do Windows deve
        ser preservada para que o job enviado pelo aplicativo possa ser
        processado normalmente.
        """
        escrever_erro(f"Limpeza automatica de jobs ignorada para {printer_name}")

    def _set_custom_paper(self, printer_name):
        """
        Nao altera o DEVMODE do Windows.

        A BTP-L42 recebe a etiqueta diretamente como BPLB/RAW e o
        proprio stream ja contem as definicoes originais de largura e
        comprimento da etiqueta (q832 / Q136,24).

        Tentar SetPrinter() aqui exige permissao administrativa para
        alterar as propriedades da fila. Em computadores onde o usuario
        comum nao possui essa permissao, a impressao era interrompida
        antes mesmo de chegar ao WritePrinter.

        Por isso esta etapa fica somente como registro diagnostico.
        """
        escrever_erro(
            f"Configuracao do papel via DEVMODE ignorada para {printer_name}; "
            "impressao sera enviada diretamente em BPLB/RAW"
        )

    def _get_printer_status(self):
        try:
            import win32print
            handle = win32print.OpenPrinter(self.printer.get())
            try:
                info = win32print.GetPrinter(handle, 2)
                return int(info.get("Status", 0))
            finally:
                win32print.ClosePrinter(handle)
        except Exception as error:
            escrever_erro(f"Status da impressora: {error}")
            return -1

    def _get_printer_details(self, printer_name):
        """Le os dados da fila/driver sem alterar nenhuma configuracao."""
        try:
            import win32print
            handle = win32print.OpenPrinter(printer_name)
            try:
                info = win32print.GetPrinter(handle, 2)
                return {
                    "name": info.get("pPrinterName") or printer_name,
                    "driver": info.get("pDriverName") or "(nao informado)",
                    "port": info.get("pPortName") or "(nao informado)",
                    "datatype": info.get("pDatatype") or "(nao informado)",
                    "status": int(info.get("Status", 0)),
                    "attributes": int(info.get("Attributes", 0)),
                }
            finally:
                win32print.ClosePrinter(handle)
        except Exception as error:
            escrever_erro(f"Erro ao consultar dados da impressora: {error}")
            return {
                "name": printer_name,
                "driver": "(erro ao consultar)",
                "port": "(erro ao consultar)",
                "datatype": "(erro ao consultar)",
                "status": -1,
                "attributes": 0,
            }

    def send_batches(self, streams, count, produtos):
        """
        Envia os lotes diretamente para a BTP-L42 como BPLB/RAW.

        Nao altera o stream das etiquetas. O layout gerado por
        build_row_data_pplb() permanece exatamente o mesmo.

        Diferenca importante:
        - verifica se WritePrinter aceitou TODOS os bytes;
        - fecha corretamente pagina/documento mesmo em caso de erro;
        - nao considera sucesso apenas porque o Windows aceitou uma
          quantidade parcial de bytes;
        - registra o job criado no spooler para facilitar diagnostico;
        - somente confirma os produtos na API depois de todos os lotes
          serem enviados sem erro.
        """
        printer_name = self.printer.get()
        try:
            import win32print

            self._set_custom_paper(printer_name)
            printer_details = self._get_printer_details(printer_name)
            escrever_erro(f"Impressora: {printer_details['name']}")
            escrever_erro(f"Driver: {printer_details['driver']}")
            escrever_erro(f"Porta: {printer_details['port']}")
            escrever_erro(f"Datatype da fila: {printer_details['datatype']}")
            status = printer_details["status"]
            escrever_erro(f"Status da impressora antes de imprimir: {status} ({'OK' if status == 0 else 'NAO PRONTA'})")
            if status != 0:
                raise RuntimeError(
                    f"Impressora {printer_name} nao esta pronta "
                    f"(Status={status}). Verifique papel/fita e se esta online."
                )

            for index, stream in enumerate(streams, 1):
                if not stream:
                    raise RuntimeError(f"Lote {index} esta vazio. Nenhum dado foi enviado.")
                expected_bytes = len(stream)
                last_error = None
                for attempt in range(3):
                    printer_handle = None
                    doc_started = False
                    page_started = False
                    try:
                        escrever_erro(f"Iniciando lote {index}/{len(streams)} | {expected_bytes} bytes | tentativa {attempt + 1}/3")
                        printer_handle = win32print.OpenPrinter(printer_name)
                        job_info = f"Painel AUTOMATA {count} etiquetas - lote {index}/{len(streams)}"
                        job_id = win32print.StartDocPrinter(printer_handle, 1, (job_info, None, "RAW"))
                        doc_started = True
                        escrever_erro(f"Job criado no spooler: {job_id} | Datatype enviado: RAW")
                        win32print.StartPagePrinter(printer_handle)
                        page_started = True
                        written = win32print.WritePrinter(printer_handle, stream)
                        escrever_erro(f"Lote {index}/{len(streams)}: WritePrinter aceitou {written}/{expected_bytes} bytes")
                        if written != expected_bytes:
                            raise RuntimeError(
                                f"A impressora aceitou somente {written} de {expected_bytes} bytes do lote {index}."
                            )
                        win32print.EndPagePrinter(printer_handle)
                        page_started = False
                        win32print.EndDocPrinter(printer_handle)
                        doc_started = False
                        escrever_erro(f"Lote {index}/{len(streams)} finalizado no spooler. Job enviado: {job_id}")
                        last_error = None
                        break
                    except Exception as error:
                        last_error = error
                        escrever_erro(f"Lote {index}/{len(streams)} FALHOU (tentativa {attempt + 1}/3): {error}")
                        if printer_handle is not None:
                            if page_started:
                                try:
                                    win32print.EndPagePrinter(printer_handle)
                                except Exception:
                                    pass
                            if doc_started:
                                try:
                                    win32print.EndDocPrinter(printer_handle)
                                except Exception:
                                    pass
                        if attempt < 2:
                            time.sleep(3)
                    finally:
                        if printer_handle is not None:
                            try:
                                win32print.ClosePrinter(printer_handle)
                            except Exception:
                                pass
                if last_error is not None:
                    raise last_error
                self._na_ui(lambda i=index, total=len(streams): self.status.set(f"Lote {i}/{total} enviado ({count} etiquetas)"))
                if index < len(streams):
                    time.sleep(self.batch_pause)

            self.confirm_api_products(produtos)
            escrever_erro("Impressao concluida: todos os lotes foram enviados integralmente ao spooler RAW")
            self._na_ui(lambda: (self.status.set("Impressao concluida"),
                                   messagebox.showinfo("Impressao", "Etiquetas enviadas com sucesso")))
        except Exception as error:
            escrever_erro(f"Impressao: {error}")
            self._na_ui(lambda error=error: messagebox.showerror("Erro de impressao", str(error)))

    def confirm_api_products(self, produtos=None):
        produtos = produtos if produtos is not None else self.queue
        itens = [
            {"fila_id": str(product.get("fila_id", "") or "").strip(),
             "name": str(product.get("name", "") or "")[:80]}
            for product in produtos if product.get("fila_id")
        ]
        if not itens or not self.api_url or not self.api_token:
            return
        body = json.dumps({"itens": itens}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_url.rstrip('/')}/api/etiquetas/produtos/confirmar",
            data=body,
            headers={"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                pass
        except (urllib.error.URLError, urllib.error.HTTPError) as error:
            print(f"Erro ao confirmar produtos na API: {error}")
        if self.confirmar_csv:
            self._salvar_csv_impressos(itens)

    def _salvar_csv_impressos(self, itens):
        caminho = os.path.join(_config_dir(), f"impressos_{time.strftime('%Y%m%d')}.csv")
        novo = not os.path.exists(caminho)
        try:
            with open(caminho, "a", encoding="utf-8-sig", newline="") as arquivo:
                escritor = csv.writer(arquivo, delimiter=";")
                if novo:
                    escritor.writerow(["quando", "fila_id", "nome"])
                for item in itens:
                    escritor.writerow([time.strftime("%Y-%m-%d %H:%M:%S"),
                                       item["fila_id"], item["name"]])
            self.status.set(f"CSV de impressos salvo em {caminho}")
        except OSError:
            pass


if __name__ == "__main__":
    try:
        LabelPrinterApp().mainloop()
    except RuntimeError as error:
        print(f"Erro: {error}")
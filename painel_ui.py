"""Camada de design do Painel AUTOMATA.

Tokens e primitivas de UI (sidebar, cabecalho de pagina, cartao, botao,
tabela). Fica separado do `painel_automata.py` para que o app continue
legivel: aquele arquivo tem a logica de negocio, este tem a aparencia.

Convencoes:
  - espaco em multiplos de 4 (grade de 4px), nomeado por uso e nao por numero
  - canto arredondado cresce com o tamanho do elemento
  - borda e sombra sao sutis: a hierarquia vem do espaco, nao do peso

CustomTkinter entra como camada opcional, e so nos controles em que ele e
claramente melhor que o ttk: chave (CTkSwitch), menu de opcoes, botao
segmentado, barra de progresso e caixa de texto. A barra de rolagem, os
cartoes e os botoes continuam sendo os daqui, porque os do CTk nao tem
rolagem de dois eixos nem o controle de estado que o app precisa.

Regra da casa: o app NUNCA importa customtkinter direto. Passa pelos
adaptadores deste arquivo, que caem para o ttk quando o pacote nao esta
instalado. Sem isso o executavel do Windows quebra na maquina do cliente
quando o pip falhar.
"""

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

# CustomTkinter e opcional de proposito. Ver o docstring do modulo.
try:
    import customtkinter as ctk

    CTK_DISPONIVEL = True
except Exception:  # pragma: no cover - so acontece no Windows sem o pacote
    ctk = None
    CTK_DISPONIVEL = False

# ---------------------------------------------------------------- tokens
FONTE = "Segoe UI"
FONTE_MONO = "Consolas"

# neutros frios, levemente esverdeados para nao brigar com o verde de marca
BRANCO = "#ffffff"
TINTA = "#fbfcfd"          # fundo de tabela alternado
FUNDO = "#f5f7f9"          # fundo do app
FUNDO_ABAIXO = "#eef1f5"   # fundo de barra/statusbar

BORDA = "#e2e6ec"          # borda padrao
BORDA_FORTE = "#cfd6df"    # borda de foco/hover
TINTA_BORDA = "#f2f5f8"    # fundo de cabecalho de tabela

TINTA_TEXTO = "#0f172a"    # texto principal
TEXTO = "#475569"          # texto secundario
TEXTO_FRACO = "#8795a8"    # texto terciario, legendas
TEXTO_INVERTIDO = "#f8fafc"

# Navegacao: navbar no topo, branca, separada do conteudo por 1px.
NAV_FUNDO = BRANCO
NAV_HOVER = "#eef2f6"       # hover do item
NAV_ATIVO = "#e8eef5"       # pilula do item ativo (cinza suave)
NAV_BORDA = "#e6eaf0"       # contorno fino do item sem hover
NAV_TEXTO = TEXTO
NAV_TEXTO_ATIVO = TINTA_TEXTO
ALTURA_NAVBAR = 64

MARCA = "#0f9d63"          # verde de marca
MARCA_ESCURA = "#0a7a4c"
MARCA_CLARA = "#e7f6ef"
MARCA_TINTA = "#f2fbf7"

PERIGO = "#d92d20"
PERIGO_CLARO = "#fef3f2"
AVISO = "#b54708"
AVISO_CLARO = "#fffaeb"
INFO = "#175cd3"
INFO_CLARO = "#eff8ff"

# escala de espaco: nome pelo uso, nao pelo numero
ESPACO_1 = 4
ESPACO_2 = 8
ESPACO_3 = 12
ESPACO_4 = 16
ESPACO_5 = 20
ESPACO_6 = 24
ESPACO_8 = 32
ESPACO_10 = 40
ESPACO_12 = 48

# escala tipografica: nome pela funcao
# o texto estava grande demais para a densidade de informação das telas
TEXTO_MENOR = 10
TEXTO_BASE = 11
TEXTO_MEDIO = 13
TEXTO_GRANDE = 16
TEXTO_NUMERO = 24           # numeros grandes de KPI
TEXTO_TITULO = 21

RAIO_SMALL = 6
RAIO = 10
RAIO_GRANDE = 14
RAIO_PILL = 999

ALTURA_BARRA = 64
# Uma unica altura para TODO controle (botao, entrada, combo, busca).
# Antes cada chamadaedia a sua e o app endedo com botoes de 28/30/32/36/42
# e entradas de 21/28/36 lado a lado. Isso e' o que faz uma barra de
# acao parecer bagunca: nada encosta, nada alinha. O destaque de um
# botao vem da cor (preenchido vs contornado), nunca da altura.
ALTURA_CONTROLE = 38
# Padding vertical dos campos. 10 nao esta na escala de proposito: e' o
# valor que, com a fonte do campo, faz a caixa fechar em ALTURA_CONTROLE.
# Medindo: 8 -> 28px, 9 -> 38px, 10 -> 40px, 12 -> 44px.
# 38 e' o que o campo entrega, e' o que a escala permite, entao
# 38 e' a altura do controle: botao, entrada, combo e busca.
PADDING_CAMPO = 9
# Piso de largura das barras de largura cheia (cabecalho, statusbar).
# `pack_propagate(False)` desliga a propagacao de tamanho dos filhos, e com
# isso o frame passa a PEDIR 0px. O `fill="x"` nao salva: ele preenche o
# parcelo, e o parcelo ja veio com 0. Resultado: barra de 1px e filhos nunca
# mapeados. A correcao e dar uma largura minima explicita e deixar o fill
# esticar ate a janela.
LARGURA_MINIMA = 760

GRUPOS = [
    ("Operacao", [
        ("Etiquetas", "etiquetas", "etiquetas",
         "Fila de impressao, detalhe do item e pre-visualizacao"),
        ("Imagens", "imagens", "imagens",
         "Fotos de produto, zoom e salvamento"),
    ]),
    ("Dados", [
        ("Produtos", "produtos", "produtos",
         "Catalogo Bling com busca e exportacao"),
        ("Dashboard", "dashboard", "dashboard",
         "Numeros de impressao, graficos e ranking"),
        ("Relatorios", "relatorios", "relatorios",
         "Montador livre com agrupamento e exportacao"),
    ]),
    ("Sistema", [
        ("Configuracoes", "config", "config",
         "Conexao com a API, offsets e preferencias"),
    ]),
]


def font(tamanho=TEXTO_BASE, peso="normal"):
    return (FONTE, tamanho, peso)


def fonte_mono(tamanho=TEXTO_MENOR):
    return (FONTE_MONO, tamanho)


def ajustar_colunas(tree, disponivel, minimo=60):
    """Define o piso de largura das colunas de um Treeview e deixa o proprio
    widget esticar (stretch=True) ate ocupar o espaco disponivel.

    Por que so o piso: se a largura declarada de cada coluna fosse igual a
    largura disponivel, o card que contem a tabela passaria a pedir essa
    largura, o grid daria mais espaco, e a tabela pediria de novo. Um laco
    que so cresce. Reportando apenas o minimo, o card encolhe de verdade e o
    Treeview distribui o que sobra na hora de desenhar.

    Sem isso, N colunas de 200px estouravam qualquer janela de 1000px e o
    usuario ficava preso empurrando a barra horizontal.
    """
    try:
        disponivel = int(disponivel)
    except (TypeError, ValueError):
        return []
    colunas = list(tree.cget("columns") or ())
    visiveis = [c for c in colunas if tree.column(c, "width") > 0]
    if not visiveis or disponivel <= 0:
        return []
    # com muitas colunas o minimo de 60px ja estoura a janela: nesse caso
    # baixa o piso para caberem todas, senao o usuario so ve as primeiras
    piso = minimo
    if len(visiveis) * minimo > disponivel:
        piso = max(24, disponivel // len(visiveis))
    for coluna in visiveis:
        tree.column(coluna, width=piso, minwidth=piso, stretch=True)
    return [piso] * len(visiveis)


def prender_tabela(tree, area):
    """Faz as colunas de um Treeview ocuparem a largura disponivel e mantem isso
    mesmo quando o codigo da tela redefine as largunas/limites da pagina.

    Chame logo apos criar a tabela, antes de configurar as colunas.
    """
    estado = {"id": None, "tentativas": 0, "dentro": False}
    original_column = tree.column
    original_heading = tree.heading

    def _medir():
        estado["id"] = None
        if estado["dentro"]:
            return
        limite = area.canvas.winfo_width()
        alvo = tree.winfo_width()
        if alvo > limite > 1:
            alvo = limite
        if alvo <= 1:
            estado["tentativas"] += 1
            if estado["tentativas"] <= 60:
                estado["id"] = area.after_idle(_medir)
                return
            alvo = limite or 600
        estado["tentativas"] = 0
        estado["dentro"] = True
        try:
            ajustar_colunas(tree, alvo)
            # o Tk guarda em cache o tamanho pedido pelo Treeview: mexer so
            # nas colunas nao atualiza o reqwidth e o grid continuava
            # reservando a largura antiga, mantendo a barra horizontal.
            # Tocar no height obriga o recalculo.
            try:
                altura = int(tree.cget("height"))
            except (TypeError, ValueError):
                altura = 10
            tree.configure(height=altura)
        finally:
            estado["dentro"] = False

    def agendar(_ev=None):
        # dentro do ajuste as propias chamadas a column() passam por aqui:
        # sem esta guarda a area se reagenda sozinha para sempre
        if estado["dentro"] or estado["id"] is not None:
            return
        estado["tentativas"] = 0
        estado["id"] = area.after_idle(_medir)

    def column(*args, **kwargs):
        res = original_column(*args, **kwargs)
        agendar()
        return res

    def heading(*args, **kwargs):
        res = original_heading(*args, **kwargs)
        agendar()
        return res

    tree.column = column
    tree.heading = heading
    area.body.bind("<Configure>", agendar, add="+")
    tree.bind("<Configure>", agendar, add="+")
    tree.bind("<Map>", agendar, add="+")
    # a aba pode ficar escondida enquanto a janela ganha tamanho: ao virar a
    # aba de novo o ajuste e refeito, senao a tabela fica com a largura da
    # primeira medicao (feita antes de existir largura util)
    registro = getattr(area, "_ajustar_tabelas", None)
    if registro is None:
        registro = []
        area._ajustar_tabelas = registro
    if agendar not in registro:
        registro.append(agendar)
    agendar()
    return agendar


def tamanho_fonte(widget, padrao=TEXTO_BASE):
    """Em telas de alta DPI o Tk ainda entrega pontos, entao usamos o valor
    pedido. Mantido como funcao para o ponto unico de ajuste."""
    return padrao


# ---------------------------------------------------------------- helpers
def pontos_arredondados(x0, y0, x1, y1, raio):
    """Poligono suave de um retangulo de cantos arredondados."""
    raio = max(1, min(raio, int((x1 - x0) / 2), int((y1 - y0) / 2)))
    return [
        x0 + raio, y0, x1 - raio, y0,
        x1, y0, x1, y0 + raio,
        x1, y1 - raio, x1, y1,
        x1 - raio, y1, x0 + raio, y1,
        x0, y1, x0, y1 - raio,
        x0, y0 + raio, x0, y0,
    ]


def retangulo(canvas, x0, y0, x1, y1, raio=RAIO, fundo=BRANCO,
              borda=BORDA, largura=1, tag="fundo"):
    """Retangulo de cantos arredondados no canvas. `tag` permite redesenhar
    sem apagar o conteudo por cima."""
    if tag:
        if canvas.find_withtag(tag):
            canvas.delete(tag)
    canvas.create_polygon(
        pontos_arredondados(x0, y0, x1, y1, raio),
        fill=fundo, outline=borda, width=largura, smooth=True,
        splinesteps=24, tags=tag)
    if tag:
        canvas.tag_raise(tag)


def pilula(canvas, x0, y0, x1, y1, fundo, tag="fundo", contorno=None):
    """Capsula (raio total) usada em selos e botoes."""
    retangulo(canvas, x0, y0, x1, y1, (y1 - y0) // 2, fundo,
              contorno or fundo, 0, tag)


def limpar_mensagem(texto):
    """Tira acento e normaliza para comparar rotulo com chave."""
    import unicodedata
    decomposto = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower().strip()


# ---------------------------------------------------------------- estilos
def aplicar_estilos(root, fundo=FUNDO):
    """Registra os estilos ttk do design system. `clam` e obrigatorio: e o
    unico tema do Tk que deixa colorir borda e fundo de campo."""
    estilo = ttk.Style(root)
    try:
        estilo.theme_use("clam")
    except tk.TclError:
        pass

    estilo.configure("TFrame", background=fundo)
    estilo.configure("TLabel", background=fundo, foreground=TINTA_TEXTO,
                     font=font(TEXTO_BASE))
    estilo.configure("Pagina.TFrame", background=fundo)
    estilo.configure("Titulo.TLabel", background=fundo, foreground=TINTA_TEXTO,
                     font=font(TEXTO_GRANDE, "bold"))
    estilo.configure("Subtitulo.TLabel", background=fundo, foreground=TEXTO_FRACO,
                     font=font(TEXTO_BASE))
    estilo.configure("Cartao.TFrame", background=BRANCO, borderwidth=0)
    estilo.configure("CartaoTitulo.TLabel", background=BRANCO, foreground=TINTA_TEXTO,
                     font=font(TEXTO_MEDIO, "bold"))
    estilo.configure("Campo.TLabel", background=BRANCO, foreground=TEXTO,
                     font=font(TEXTO_BASE))
    estilo.configure("Rotulo.TLabel", background=BRANCO, foreground=TEXTO_FRACO,
                     font=font(TEXTO_MENOR, "bold"))
    estilo.configure("Legenda.TLabel", background=fundo, foreground=TEXTO_FRACO,
                     font=font(TEXTO_MENOR))

    estilo.configure("TNotebook", background=fundo, borderwidth=0,
                     tabmargins=(0, 0, 0, 0), showtabs=False)
    estilo.configure("TNotebook.Tab", background=fundo, foreground=TEXTO,
                     font=font(TEXTO_BASE), padding=(0, 0, 0, 0))
    estilo.map("TNotebook.Tab", background=[("selected", fundo)],
               foreground=[("selected", TINTA_TEXTO)],
               expand=[("selected", (0, 0, 0, 0))])

    estilo.configure("TEntry", fieldbackground=BRANCO, foreground=TINTA_TEXTO,
                     bordercolor=BORDA, lightcolor=BORDA, darkcolor=BORDA,
                     insertcolor=MARCA, padding=(ESPACO_3, PADDING_CAMPO),
                     font=font(TEXTO_BASE))
    estilo.map("TEntry", bordercolor=[("focus", MARCA)],
               lightcolor=[("focus", MARCA)], darkcolor=[("focus", MARCA)])

    estilo.configure("TCombobox", fieldbackground=BRANCO, background=BRANCO,
                     foreground=TINTA_TEXTO, arrowcolor=MARCA_ESCURA,
                     bordercolor=BORDA, lightcolor=BORDA, darkcolor=BORDA,
                     padding=(ESPACO_2, PADDING_CAMPO), font=font(TEXTO_BASE))
    estilo.map("TCombobox",
               selectbackground=[("readonly", BRANCO)],
               selectforeground=[("readonly", TINTA_TEXTO)],
               fieldbackground=[("readonly", BRANCO)],
               bordercolor=[("focus", MARCA)],
               arrowcolor=[("focus", MARCA_ESCURA)])

    estilo.configure("Checkbutton", background=BRANCO, foreground=TEXTO,
                     focuscolor=BRANCO, font=font(TEXTO_BASE),
                     indicatorcolor=BRANCO, indicatorbackground=BRANCO)
    estilo.map("Checkbutton", background=[("active", BRANCO)],
               foreground=[("active", TINTA_TEXTO)],
               indicatorbackground=[("selected", MARCA), ("active", BRANCO)],
               indicatorcolor=[("selected", MARCA), ("active", BRANCO)],
               bordercolor=[("focus", MARCA)])

    estilo.configure("TScrollbar", background=BORDA, troughcolor=fundo,
                     bordercolor=fundo, arrowcolor=TEXTO_FRACO,
                     darkcolor=BORDA, lightcolor=BORDA, width=11,
                     arrowsize=11)
    estilo.map("TScrollbar", background=[("active", BORDA_FORTE)])

    estilo.configure("TProgressbar", background=MARCA, troughcolor=BORDA,
                     borderwidth=0, thickness=ESPACO_1)
    return estilo


def estilo_tabela(estilo, altura_linha=38):
    """Estilo das tabelas: cabecalho discreto, linhas zebradas, sem grade
    pesada. Zebra e o unico jeito de acompanhar uma linha em tabela larga."""
    estilo.configure("Tabela.Treeview", background=BRANCO, fieldbackground=BRANCO,
                     foreground=TINTA_TEXTO, borderwidth=0, rowheight=altura_linha,
                     font=font(TEXTO_BASE))
    estilo.map("Tabela.Treeview",
               background=[("selected", MARCA_CLARA)],
               foreground=[("selected", MARCA_ESCURA)])
    estilo.configure("Tabela.Treeview.Heading", background=TINTA_BORDA,
                     foreground=TEXTO, font=font(TEXTO_MENOR, "bold"),
                     borderwidth=0, relief="flat",
                     padding=(ESPACO_3, ESPACO_3), anchor="w")
    estilo.map("Tabela.Treeview.Heading",
               background=[("active", MARCA_CLARA)],
               foreground=[("active", MARCA_ESCURA)])
    estilo.layout("Tabela.Treeview", estilo.layout("Treeview"))


# ---------------------------------------------------------------- primitivas
class Icone(tk.Canvas):
    """Icone de navegacao desenhado com primitivas, nao com glifo de fonte.

    Antes os itens usavam caracteres Unicode (◫ ◨ ◧ ◩ ▤ ⚙) com a fonte
    Segoe UI. Segoe UI nao tem esses caracteres: no Windows o Tk caia numa
    fonte de reserva e o resultado era caixa vazia, glifo de tamanho errado ou
    nada. Aqui o desenho e vetorial e sai igual em qualquer maquina, sem
    depender de fonte instalada.

    O grid interno e 16x16 e o desenho ocupa o Canvas inteiro: o passo de
    `_p` inclui o `escala`, senao o icone sai no cantinho de cima a esquerda
    de um canvas vazio.
    """

    def __init__(self, master, nome, tamanho=16, cor=TEXTO, fundo=FUNDO_ABAIXO,
                 escala=1):
        # `escala` nao e'supersampling: num tk.Canvas puro o Tk desenha em
        # 1x e o SO escala o resultado, entao dobrar o canvas dobra o icone
        # e nao deixa nada mais nitido. Quem faz HiDPI de verdade e' o
        # CustomTkinter. Aqui `escala` existe so para quem quiser um icone
        # maior, e o desenho ocupa a largura toda do canvas.
        lado = tamanho * escala
        super().__init__(master, width=lado, height=lado, bg=fundo,
                         highlightthickness=0, bd=0)
        self._nome = nome
        self._cor = cor
        self._fundo = fundo
        self._tamanho = tamanho
        self._escala = escala
        self.bind("<Configure>", lambda e: self.redesenhar())
        self.redesenhar()

    def atualizar_cor(self, cor):
        self._cor = cor
        self.configure(bg=self._fundo)
        self.redesenhar()

    def _p(self, x, y):
        """Grid 16x16 -> pixels do canvas.

        O passo e' `tamanho * escala / 16`, e nao `tamanho / 16`: o Canvas
        tem `tamanho * escala` de lado e o desenho precisa ocupar a largura
        toda. Sem o `escala` no passo, um icone de tamanho 16 num canvas de
        32 era desenhado no cantinho de cima a esquerda, com metade do canvas
        vazia — e o icone ficava aparente uns 8px a esquerda do centro,
        torto em relacao ao rotulo ao lado.
        """
        passo = self._tamanho * self._escala / 16.0
        return x * passo, y * passo

    def _linha(self, x1, y1, x2, y2, largura=None):
        a, b = self._p(x1, y1)
        c, d = self._p(x2, y2)
        self.create_line(a, b, c, d, fill=self._cor,
                         width=largura or max(1.0, 1.5 * self._escala / 2),
                         capstyle="round", joinstyle="round")

    def _caixa(self, x1, y1, x2, y2, preenchida=False):
        a, b = self._p(x1, y1)
        c, d = self._p(x2, y2)
        if preenchida:
            self.create_rectangle(a, b, c, d, fill=self._cor, outline="")
        else:
            self.create_rectangle(a, b, c, d, outline=self._cor,
                                  width=max(1.0, 1.5 * self._escala / 2))

    def _circulo(self, cx, cy, raio, preenchido=False):
        a, b = self._p(cx - raio, cy - raio)
        c, d = self._p(cx + raio, cy + raio)
        if preenchido:
            self.create_oval(a, b, c, d, fill=self._cor, outline="")
        else:
            self.create_oval(a, b, c, d, outline=self._cor,
                             width=max(1.0, 1.5 * self._escala / 2))

    def redesenhar(self):
        self.delete("tudo")
        desenhar = getattr(self, f"_desenhar_{self._nome}", None)
        if desenhar is None:
            self._caixa(2, 2, 14, 14)
            return
        desenhar()

    # --- os icones proprios ------------------------------------------
    def _desenhar_etiquetas(self):
        # impressora: papel entrando por cima e bandeja embaixo
        self._caixa(2, 6, 14, 13)
        self._caixa(4, 2, 12, 6)
        self._linha(4, 10, 12, 10)
        self._circulo(12, 8.5, 0.9, preenchido=True)

    def _desenhar_imagens(self):
        # foto: moldura, sol e montanha
        self._caixa(2, 3, 14, 13)
        self._circulo(5.5, 6, 1.2, preenchido=True)
        self._linha(2.5, 12, 6.5, 7.5)
        self._linha(6.5, 7.5, 9.5, 11)
        self._linha(9.5, 11, 13.5, 6.5)

    def _desenhar_produtos(self):
        # caixa de catalogo: grade de 2x2
        self._caixa(2.5, 2.5, 13.5, 13.5)
        self._linha(8, 2.5, 8, 13.5)
        self._linha(2.5, 8, 13.5, 8)

    def _desenhar_dashboard(self):
        # barras de grafico de alturas diferentes
        self._linha(2.5, 2.5, 2.5, 13.5)
        self._caixa(5, 8, 7.5, 13.5, preenchida=True)
        self._caixa(9, 4.5, 11.5, 13.5, preenchida=True)
        self._linha(13, 2.5, 13, 13.5)

    def _desenhar_relatorios(self):
        # documento com linhas e canto dobrado
        self._linha(3.5, 2.5, 10, 2.5)
        self._linha(10, 2.5, 10, 5.5)
        self._linha(10, 5.5, 12.5, 5.5)
        self._linha(12.5, 5.5, 12.5, 13.5)
        self._linha(12.5, 13.5, 3.5, 13.5)
        self._linha(3.5, 13.5, 3.5, 2.5)
        self._linha(5.5, 8, 10.5, 8)
        self._linha(5.5, 11, 9, 11)

    def _desenhar_config(self):
        # engrenagem: circulo central com dentes em volta
        import math
        self._circulo(8, 8, 3.1)
        for angulo in range(0, 360, 45):
            rad = math.radians(angulo)
            x1, y1 = 8 + 4.2 * math.cos(rad), 8 + 4.2 * math.sin(rad)
            x2, y2 = 8 + 6.2 * math.cos(rad), 8 + 6.2 * math.sin(rad)
            self._linha(x1, y1, x2, y2,
                        largura=max(1.0, 1.6 * self._escala / 2))


class ItemNav(tk.Frame):
    """Item da navbar: icone e rotulo lado a lado, com pílula no hover e
    no estado ativo.

    A pílula e' um Canvas e o conteudo e' um Frame na MESMA celula do grid,
    criados nesta ordem: quem entra depois fica por cima. Nao da para usar
    `place` dentro do Canvas aqui: o glifo ja e' um Canvas, e Canvas
    aninhado com `place` mais `pack` mistura gerenciadores e o item sai com
    1px.

    `mostrar_texto=False` esvazia o rotulo e deixa so o icone. A navbar usa
    isso quando a janela fica estreita: seis rotulos mais a marca e' o que
    estoura primeiro, e cortar o texto do item ativo quebra a orientacao
    ("qual pagina eu estou?") sem cortar o item.
    """

    def __init__(self, master, texto, icone, comando, ativo=False):
        super().__init__(master, bg=NAV_FUNDO, cursor="hand2", takefocus=1)
        self._texto = texto
        self._icone = icone
        self._comando = comando
        self._ativo = ativo
        self._hover = False
        self._fundo_atual = NAV_FUNDO
        self._mostrar_texto = True

        # width/height 1 de proposito: um Canvas sem medida explicita pede
        # 378x265 (o default do Tk) e o item inteiro passava a exigir 378px
        # dentro de um trilho de 84px. O grid estica o Canvas para a celula
        # de qualquer forma, entao 1x1 e' o piso correto.
        self._fundo_item = tk.Canvas(self, highlightthickness=0, bd=0,
                                     bg=NAV_FUNDO, width=1, height=1)
        self._fundo_item.grid(row=0, column=0, sticky="nsew")

        conteudo = tk.Frame(self, bg=NAV_FUNDO)
        conteudo.grid(row=0, column=0, sticky="nsew")
        # A altura do item e' a dos outros controles. Quem fixa e' o
        # `minsize` da linha: `pack_propagate` nao vale aqui (os filhos do
        # conteudo estao em grid) e `pack_propagate(False)` no proprio item
        # fixaria tambem a largura, que precisa acompanhar o texto, porque
        # o rotulo some quando a janela aperta.
        conteudo.rowconfigure(0, minsize=ALTURA_CONTROLE)
        self._conteudo = conteudo

        self._glifo = Icone(conteudo, icone, tamanho=16, cor=NAV_TEXTO,
                            fundo=NAV_FUNDO)
        self._glifo.grid(row=0, column=0)

        self._rotulo = tk.Label(conteudo, text=texto, bg=NAV_FUNDO,
                                foreground=NAV_TEXTO, anchor="w",
                                font=font(TEXTO_BASE))
        self._rotulo.grid(row=0, column=1, padx=(ESPACO_2, 0))

        self._fundo_item.bind("<Configure>", lambda e: self._pintar_fundo())
        self._ligar_eventos()
        self._aplicar_estado()

    def _ligar_eventos(self, widget=None):
        """Liga os eventos no item INTEIRO, e nao so na casca.

        A pilula de fundo e o `conteudo` sao filhos em `sticky="nsew"`,
        entao cobrem o item inteiro: o clique cai neles. O Tk nao repassa
        evento de filho para pai, e entao ligar so no `self` deixava os
        seis itens da navbar sem reacao nenhuma -- o hover tambem, porque
        `<Enter>`/`<Leave>` paravam no filho.
        """
        if widget is None:
            widget = self
        widget.bind("<Enter>", self._entrar)
        widget.bind("<Leave>", self._sair)
        widget.bind("<ButtonPress-1>", self._pressionar)
        widget.bind("<ButtonRelease-1>", self._soltar)
        widget.bind("<Return>", self._ativar)
        widget.bind("<KP_Enter>", self._ativar)
        widget.bind("<space>", self._ativar)
        for filho in widget.winfo_children():
            self._ligar_eventos(filho)

    def _dentro(self, event=None):
        """O ponteiro esta sobre o item? Medido na raiz porque o evento
        chega com x/y relativos ao filho que recebeu o clique."""
        ax, ay = self.winfo_rootx(), self.winfo_rooty()
        if event is not None and getattr(event, "x_root", None) is not None:
            x, y = event.x_root, event.y_root
        else:
            x, y = self.winfo_pointerxy()
        return (ax <= x < ax + self.winfo_width()
                and ay <= y < ay + self.winfo_height())

    def mostrar_texto(self, mostrar):
        """Liga/desliga o rotulo, para a navbar caber em janela estreita."""
        mostrar = bool(mostrar)
        if mostrar == self._mostrar_texto:
            return
        self._mostrar_texto = mostrar
        if mostrar:
            self._rotulo.grid(row=0, column=1, padx=(ESPACO_2, 0))
        else:
            self._rotulo.grid_remove()

    def _pintar_fundo(self):
        """Contorno de 1px sempre visivel, preenchido no hover e no ativo.

        Sem o contorno, os itens eram so texto solto na barra e o unico sinal
        de que eram clicaveis era o hover. A borda aparece sempre, discreta,
        e engrossa no hover.
        """
        self._fundo_item.delete("tudo")
        largura = self._fundo_item.winfo_width()
        altura = self._fundo_item.winfo_height()
        if largura < 8 or altura < 8:
            return
        if self._ativo:
            fundo, borda = NAV_ATIVO, BORDA_FORTE
        elif self._hover:
            fundo, borda = NAV_HOVER, BORDA_FORTE
        else:
            fundo, borda = NAV_FUNDO, NAV_BORDA
        retangulo(self._fundo_item, 0.5, 0.5, largura - 0.5, altura - 0.5,
                  RAIO_SMALL, fundo, borda=borda, largura=1, tag="fundo")

    def _aplicar_estado(self):
        # a pílula e' desenhada no Canvas, entao o frame e os filhos ficam
        # com o fundo da navbar: so o glifo e o rotulo mudam de cor
        if self._ativo:
            fundo, cor_rotulo, cor_glifo = (NAV_FUNDO, NAV_TEXTO_ATIVO, MARCA)
        elif self._hover:
            fundo, cor_rotulo, cor_glifo = (NAV_FUNDO, NAV_TEXTO_ATIVO, MARCA)
        else:
            fundo, cor_rotulo, cor_glifo = (NAV_FUNDO, NAV_TEXTO, NAV_TEXTO)
        self._fundo_atual = fundo
        self.configure(bg=fundo)
        self._fundo_item.configure(bg=fundo)
        self._conteudo.configure(bg=fundo)
        self._rotulo.configure(bg=fundo, fg=cor_rotulo)
        self._glifo.atualizar_cor(cor_glifo)
        self._glifo.configure(bg=fundo)
        self._pintar_fundo()

    def definir_ativo(self, ativo):
        self._ativo = bool(ativo)
        self._aplicar_estado()

    def _entrar(self, _event=None):
        if not self._hover:
            self._hover = True
            self._aplicar_estado()

    def _sair(self, event=None):
        # `<Leave>` tambem dispara quando o ponteiro sai de um filho para
        # outro (o glifo, o rotulo, o conteudo). So apaga o hover quando o
        # ponteiro saiu mesmo do item, senao a pilula pisca ao andar sobre
        # o item.
        if self._dentro(event):
            return
        self._hover = False
        self._aplicar_estado()

    def _pressionar(self, _event=None):
        self.focus_set()
        self.configure(cursor="hand2")

    def _soltar(self, event=None):
        if self._dentro(event) and self._comando:
            try:
                self._comando()
            except Exception as erro:  # noqa: BLE001 - erro de UI nao pode derrubar o app
                from painel_automata import escrever_erro
                escrever_erro(f"Acao do item de navegacao falhou: {erro}")

    def _ativar(self, _event=None):
        if self._comando:
            try:
                self._comando()
            except Exception as erro:  # noqa: BLE001
                from painel_automata import escrever_erro
                escrever_erro(f"Ativacao do item de navegacao falhou: {erro}")


class Navbar(tk.Frame):
    """Barra de navegacao no topo: marca a esquerda, itens no meio, acoes
    a direita, e uma linha de 1px separando do conteudo.

    A janela tem largura minima de 1040px. Com seis itens e a marca, o texto
    de todos cabe folgado; quando nao cabe, `mostrar_texto(False)` deixa so
    os icones em vez de deixar a barra estourar ou empilhar.
    """

    def __init__(self, master, grupos, direita=None):
        super().__init__(master, bg=NAV_FUNDO, height=ALTURA_NAVBAR)
        self.pack_propagate(False)
        self._itens = []
        # acesso publico: os testes clicam nos itens para garantir que a
        # navegacao funciona
        self.itens = self._itens
        self._texto_visivel = True
        # mesma folga usada no `pack` e na conta de espaco necessario
        self._folga_item = ESPACO_2

        tk.Frame(self, bg=BORDA, height=1).pack(fill="x", side="bottom")

        marca = tk.Frame(self, bg=NAV_FUNDO)
        marca.pack(side="left", padx=(ESPACO_4, ESPACO_5))

        glifo = tk.Canvas(marca, width=30, height=30, bg=NAV_FUNDO,
                          highlightthickness=0, bd=0)
        glifo.pack(side="left")
        pilula(glifo, 1, 1, 29, 29, MARCA)
        glifo.create_text(15, 16, text="A", fill=BRANCO, font=font(14, "bold"))

        tk.Label(marca, text="AUTOMATA", bg=NAV_FUNDO, fg=NAV_TEXTO_ATIVO,
                 font=font(TEXTO_BASE, "bold")).pack(side="left", padx=(ESPACO_2, 0))

        navegacao = tk.Frame(self, bg=NAV_FUNDO)
        navegacao.pack(side="left", fill="y")

        for titulo, itens in grupos:
            for texto, icone, chave, *resto in itens:
                # o 5o elemento da tupla e o callback (a acao do item). Sem
                # ele, o comando fica None e o clique nao faz nada.
                acao = resto[-1] if resto and callable(resto[-1]) else None
                item = ItemNav(navegacao, texto, icone, acao)
                # folga entre os itens: 4px colava os rotulos uns nos outros
                item.pack(side="left", padx=(0, self._folga_item),
                          pady=(ESPACO_3, ESPACO_3))
                item._chave = chave
                self._itens.append(item)

        if direita is not None:
            direita(self).pack(side="right", padx=(0, ESPACO_4))

        self.bind("<Configure>", lambda _e: self._ajustar_texto())

    def _ajustar_texto(self):
        """Esconde os rotulos quando os itens nao cabem lado a lado."""
        try:
            necessario = self._espaco_necessario()
            disponivel = self.winfo_width()
        except tk.TclError:
            return
        if disponivel <= 1:
            return
        mostrar = disponivel >= necessario
        if mostrar != self._texto_visivel:
            self._texto_visivel = mostrar
            for item in self._itens:
                item.mostrar_texto(mostrar)

    def _espaco_necessario(self):
        total = 0
        for item in self._itens:
            total += item._glifo.winfo_reqwidth() + item._rotulo.winfo_reqwidth()
            # ESPACO_2 entre glifo e rotulo, mais a folga entre os itens
            total += ESPACO_2 + self._folga_item
        return total

    def marcar_ativo(self, chave):
        for item in self._itens:
            item.definir_ativo(item._chave == chave)


class Selo(tk.Canvas):
    """Selo compacto de status, com ponto colorido e texto."""

    def __init__(self, master, texto, cor=MARCA, fundo=MARCA_CLARA,
                 largura=170, altura=30, command=None):
        super().__init__(master, width=largura, height=ALTURA_CONTROLE,
                         bg=master.cget("bg"), highlightthickness=0, bd=0,
                         cursor="hand2" if command else "")
        self._texto = texto
        self._cor = cor
        self._fundo = fundo
        self.bind("<Configure>", lambda e: self.redesenhar())
        if command:
            self.bind("<Button-1>", lambda e: command())

    def atualizar(self, texto=None, cor=None, fundo=None):
        if texto is not None:
            self._texto = texto
        if cor is not None:
            self._cor = cor
        if fundo is not None:
            self._fundo = fundo
        self.configure(bg=self.master.cget("bg"))
        self.redesenhar()

    def redesenhar(self):
        self.delete("tudo")
        largura = self.winfo_width()
        altura = self.winfo_height()
        if largura < 12 or altura < 12:
            return
        pilula(self, 1, 1, largura - 1, altura - 1, self._fundo)
        self.create_oval(ESPACO_2 + 2, altura / 2 - 3, ESPACO_2 + 8,
                         altura / 2 + 3, fill=self._cor, outline="")
        self.create_text(ESPACO_2 + ESPACO_3 + 3, altura / 2, text=self._texto,
                         anchor="w", fill=self._cor, font=font(TEXTO_MENOR, "bold"))


class PontoStatus(tk.Canvas):
    """Circulo de status, desenhado.

    Substitui um Label com o glifo U+25CF. O caractere nao existe em Segoe UI
    e no Windows virava caixa vazia. `configure(fg=...)` e aceito para o app
    poder trocar a cor sem conhecer o desenho.
    """

    def __init__(self, master, cor=MARCA, fundo=FUNDO_ABAIXO, escala=2):
        lado = 10 * escala
        super().__init__(master, width=lado, height=lado, bg=fundo,
                         highlightthickness=0, bd=0)
        self._cor = cor
        self._fundo = fundo
        self._escala = escala
        self._raio = 3.5 * escala
        self._centro = lado / 2.0
        self.redesenhar()

    def configurar_cor(self, cor):
        self._cor = cor
        self.redesenhar()

    def configure(self, **kwargs):
        # aceita fg= porque e o nome que o tk.Label usava
        if "fg" in kwargs:
            self._cor = kwargs.pop("fg")
        if "bg" in kwargs:
            self._fundo = kwargs.pop("bg")
        if kwargs:
            super().configure(**kwargs)
        self.redesenhar()

    config = configure

    def redesenhar(self):
        self.delete("tudo")
        self.create_oval(self._centro - self._raio, self._centro - self._raio,
                         self._centro + self._raio, self._centro + self._raio,
                         fill=self._cor, outline="")


class IndicadorStatus(tk.Canvas):
    """Ponto de status + texto curto, com a largura seguindo o texto.

    Substitui o selo de largura fixa de 190px: um bloco de 190px que quase
    sempre ficava com duas palavras dentro e o resto vazio. Aqui o desenho
    acompanha o texto, o ponto e desenhado (nao e glifo de fonte, que no
    Windows virava caixa) e o texto inteiro aparece em tooltip.
    """

    def __init__(self, master, texto="", cor=MARCA, command=None,
                 tooltip=None, escala=2):
        self._texto = texto
        self._cor = cor
        self._tooltip = tooltip or ""
        # `font()` deste arquivo devolve uma TUPLA para o parametro font dos
        # widgets, e tupla nao mede. Para medir o texto de verdade e preciso
        # um objeto tkfont.Font.
        self._medida = tkfont.Font(family=FONTE, size=TEXTO_BASE)
        self._fonte = (FONTE, TEXTO_BASE, "normal")
        self._escala = escala
        super().__init__(master, bg=master.cget("bg"), highlightthickness=0,
                         bd=0, height=22 * escala, cursor="hand2" if command else "")
        self.configure(width=self._largura_necessaria())
        self.bind("<Configure>", lambda e: self.redesenhar())
        if command:
            self.bind("<Button-1>", lambda e: command())
        self.bind("<Enter>", self._mostrar_tooltip)
        self.bind("<Leave>", self._esconder_tooltip)
        self._dica = None

    def _largura_necessaria(self):
        texto = self._texto or ""
        largura = self._medida.measure(texto)
        largura += ESPACO_2 * self._escala + 10 * self._escala
        return max(60, largura + 8)

    def atualizar(self, texto=None, cor=None):
        if texto is not None:
            self._texto = texto
        if cor is not None:
            self._cor = cor
        self.configure(width=self._largura_necessaria())
        self.redesenhar()

    def redesenhar(self):
        self.delete("tudo")
        altura = self.winfo_height()
        if altura < 8:
            return
        raio = 4 * self._escala
        centro = ESPACO_2 * self._escala
        self.create_oval(centro - raio, altura / 2 - raio,
                         centro + raio, altura / 2 + raio,
                         fill=self._cor, outline="")
        if self._texto:
            self.create_text(centro + raio + ESPACO_1 * self._escala,
                             altura / 2, text=self._texto, anchor="w",
                             fill=self._cor, font=self._fonte)

    def _mostrar_tooltip(self, _event=None):
        if not self._tooltip:
            return
        from tkinter import Toplevel
        if self._dica is not None:
            return
        dica = Toplevel(self)
        dica.wm_overrideredirect(True)
        dica.configure(bg=TINTA_TEXTO)
        tk.Label(dica, text=self._tooltip, bg=TINTA_TEXTO, fg=TEXTO_INVERTIDO,
                 font=font(TEXTO_MENOR), padx=8, pady=4).pack()
        x = self.winfo_rootx() + self.winfo_width() // 2
        y = self.winfo_rooty() + self.winfo_height() + 4
        dica.wm_geometry(f"+{x}+{y}")
        self._dica = dica

    def _esconder_tooltip(self, _event=None):
        if self._dica is not None:
            self._dica.destroy()
            self._dica = None


class CabecalhoPagina(tk.Frame):
    """Titulo, subtitulo e acoes no topo de cada pagina.

    Substitui o cabecalho fixo do app: cada aba passa a ter titulo proprio,
    que e como funciona em SaaS de verdade.
    """

    def __init__(self, master, titulo="", subtitulo="", fundo=FUNDO):
        super().__init__(master, bg=fundo)
        textos = tk.Frame(self, bg=fundo)
        textos.pack(side="left", fill="y")

        self.titulo_var = tk.StringVar(value=titulo)
        self.subtitulo_var = tk.StringVar(value=subtitulo)

        self._titulo = tk.Label(textos, textvariable=self.titulo_var, bg=fundo,
                                fg=TINTA_TEXTO, font=font(TEXTO_GRANDE, "bold"),
                                anchor="w")
        self._titulo.pack(anchor="w")
        self._subtitulo = tk.Label(textos, textvariable=self.subtitulo_var,
                                   bg=fundo, fg=TEXTO_FRACO,
                                   font=font(TEXTO_BASE), anchor="w")
        self._subtitulo.pack(anchor="w")

        self.acoes = tk.Frame(self, bg=fundo)
        self.acoes.pack(side="right", anchor="e")

        textos.pack(side="left", fill="both", expand=True)
        self.bind("<Configure>", self._limitar_textos, add="+")

    def _limitar_textos(self, _event=None):
        """Impede que titulo e subtitulo empurrem a largura da pagina. Sem o
        width explicito o rotulo pede o tamanho do texto e a coluna do grid
        cresce ate o ponto em que nenhuma barra horizontal resolve."""
        largura = self.winfo_width()
        if largura <= 1:
            return
        disponivel = largura - self.acoes.winfo_reqwidth() - ESPACO_4
        if disponivel < ESPACO_10:
            return
        for rotulo, var in ((self._titulo, self.titulo_var),
                            (self._subtitulo, self.subtitulo_var)):
            natural = len(var.get() or "")
            # ~9px por caractere no corpo do titulo. O teto pelo tamanho
            # natural evita o laco: sem ele o rotulo pede mais do que a
            # janela tem, a janela cresce e o rotulo pede mais ainda.
            cabem = max(4, disponivel // 9)
            rotulo.configure(width=max(4, min(natural + 1, cabem)))

    def definir(self, titulo=None, subtitulo=None):
        if titulo is not None:
            self.titulo_var.set(titulo)
        if subtitulo is not None:
            self.subtitulo_var.set(subtitulo)


class Cartao(tk.Frame):
    """Bloco branco com borda e cantode 10px, como os cards de SaaS."""

    def __init__(self, master, titulo=None, fundo=BRANCO, padding=ESPACO_5):
        super().__init__(master, bg=fundo)
        self._fundo = fundo
        self.interior = tk.Frame(self, bg=fundo)
        self._titulo_widget = None
        if titulo:
            cabecalho = tk.Frame(self, bg=fundo)
            cabecalho.pack(fill="x", padx=padding, pady=(padding, 0))
            self._titulo_widget = tk.Label(cabecalho, text=titulo, bg=fundo,
                                           fg=TINTA_TEXTO,
                                           font=font(TEXTO_MEDIO, "bold"),
                                           anchor="w")
            self._titulo_widget.pack(side="left")
            self.cabecalho_extra = tk.Frame(cabecalho, bg=fundo)
            self.cabecalho_extra.pack(side="right")
            self.interior.pack(fill="both", expand=True, padx=padding,
                               pady=(ESPACO_3, padding))
        else:
            self.interior.pack(fill="both", expand=True, padx=padding,
                               pady=padding)

    def definir_titulo(self, texto):
        if self._titulo_widget is not None:
            self._titulo_widget.configure(text=texto)


class BarraBotoes(tk.Frame):
    """Barra de acoes que quebra linha quando os botoes nao cabem.

    O Botao e um Canvas cuja largura vem do texto e nao encolhe. Amarrados
    numa linha so, tres botoes de 200px estouram um card de 500px e o
    ultimo some pela borda. Aqui o numero de botoes por linha e recalculado
    sempre que a barra muda de largura, entao nada nunca vaza do card.

    Use:
        barra = BarraBotoes(cartao, fundo=BRANCO)
        barra.adicionar(ui.Botao(barra, "Salvar", salvar))
        barra.adicionar(ui.Botao(barra, "Cancelar", cancelar))
        barra.pack(fill="x")
    """

    def __init__(self, master, fundo=None, espaco=ESPACO_2, altura_linha=36):
        super().__init__(master, bg=fundo if fundo is not None
                         else (master.cget("bg") or FUNDO))
        self._itens = []
        self._espaco = espaco
        self._altura_linha = altura_linha
        self._colunas = 0
        self.bind("<Configure>", lambda e: self._reorganizar())

    def adicionar(self, botao, esticar=False):
        """Inclui um botao ja criado. esticar=True faz o botao ocupar a linha
        inteira (botao de acao principal)."""
        self._itens.append((botao, esticar))
        self._reorganizar()
        return botao

    def criar(self, texto, comando=None, variante="secundario", esticar=False,
              **kwargs):
        """Atalho: cria o Botao e ja inclui na barra."""
        botao = Botao(self, texto, comando, variante=variante, **kwargs)
        return self.adicionar(botao, esticar=esticar)

    def limpar(self):
        for botao, _ in self._itens:
            botao.destroy()
        self._itens = []

    def _reorganizar(self):
        if not self._itens:
            return
        try:
            disponivel = self.winfo_width()
        except tk.TclError:
            return
        if disponivel <= 1:
            return
        larguras = []
        for botao, _ in self._itens:
            try:
                larguras.append(max(20, botao.winfo_reqwidth()))
            except tk.TclError:
                larguras.append(80)
        colunas = self._colunas_que_cabem(larguras, disponivel)
        if colunas == self._colunas:
            return
        self._colunas = colunas

        try:
            for indice, (botao, esticar) in enumerate(self._itens):
                linha, coluna = divmod(indice, colunas)
                # Botao que abre a ultima linha e ocupa a linha inteira via
                # columnspan. Esticar a largura dele direto nao serve: a coluna
                # ficaria larga e empurraria os botoes das linhas de cima para
                # fora da barra.
                abre_linha = (coluna == 0
                              and indice + colunas >= len(self._itens))
                if esticar and abre_linha:
                    botao.grid(row=linha, column=0, columnspan=colunas,
                               sticky="ew", pady=(0, self._espaco))
                    continue
                botao.devolver_largura()
                botao.grid(row=linha, column=coluna, sticky="w",
                           padx=((0, self._espaco) if coluna < colunas - 1
                                 else 0),
                           pady=((0, self._espaco) if linha == 0
                                 else self._espaco))
            for indice in range(colunas):
                self.grid_columnconfigure(indice, weight=0, minsize=0)
        except tk.TclError:
            # <Configure> ainda pode chegar depois do app fechar
            self._colunas = 0

    def _colunas_que_cabem(self, larguras, disponivel):
        """Maior numero de botoes por linha que NAO estoura a barra.

        Nao da para simplesmente somar as larguras da linha: o grid dimensura
        cada coluna pela largura do botao mais largo que cai nela, e nao pela
        soma dos botoes daquela linha. Com 4 botoes de larguras diferentes
        numa coluna de largura media, a conta pela soma erra e o ultimo
        botao vaza. Aqui o grid e simulado coluna a coluna.
        """
        total_itens = len(larguras)
        melhor = 1
        for candidatas in range(1, total_itens + 1):
            colunas = [0] * candidatas
            for indice, larg in enumerate(larguras):
                posicao = indice % candidatas
                if larg > colunas[posicao]:
                    colunas[posicao] = larg
            # a ultima coluna da linha nao leva espacaco depois dela
            total = sum(colunas) + self._espaco * (candidatas - 1)
            if total <= disponivel:
                melhor = candidatas
            elif candidatas > melhor:
                break
        return max(1, melhor)

    def _limpar_grid(self):
        for botao, _ in self._itens:
            botao.grid_forget()


class Botao(tk.Frame):
    """Botao do app. CTkButton quando o CTk esta instalado, Canvas nas
    demais maquinas.

    Antes era um `tk.Canvas` com o retangulo arredondado desenhado a mao e a
    largura calculada como `len(texto) * 9 + 32`. Esse `* 9 + 32` e' o que
    fazia a tela parecer amadora: cada botao saia com uma largura diferente,
    o texto era cortado ou sobrava espaco em branco conforme o tamanho da
    fonte, e o canto arredondado era um arco imperfeito. O CTkButton mede o
    texto de verdade, tem canto de verdade e estados de hover/press de
    verdade.

    A casca continua sendo um `tk.Frame` (e nao o botao do CTk direto)
    porque `BarraBotoes` mede `winfo_reqwidth()` dos itens para decidir a
    quebra de linha, e o `Segoe UI` do CTk mede diferente do Canvas.
    """

    VARIANTES = {
        "primario": (MARCA, BRANCO, MARCA_ESCURA, "#0b8f5b"),
        "secundario": (BRANCO, TINTA_TEXTO, "#f1f5f9", "#e8edf3"),
        "suave": (MARCA_CLARA, MARCA_ESCURA, "#d6efe3", "#cbe7d9"),
        "fantasma": (BRANCO, TEXTO, "#f1f5f9", "#e8edf3"),
        "perigo": (PERIGO_CLARO, "#b42318", "#fee4e2", "#fdd8d5"),
    }

    def __init__(self, master, texto, comando=None, variante="secundario",
                 tamanho=TEXTO_BASE, peso="normal", altura=None, largura=None,
                 raio=RAIO_SMALL, parent_bg=None):
        # `altura` continua no assinatura por compatibilidade, mas e' sempre
        # ALTURA_CONTROLE: nenhum botao do app pode escolher a propria altura.
        altura = ALTURA_CONTROLE
        fundo = parent_bg or master.cget("bg") or FUNDO
        super().__init__(master, bg=fundo)
        self._texto = texto
        self._comando = comando
        self._variante = variante
        self._altura_fixa = altura
        self._raio = raio
        self._largura_minima = largura

        if CTK_DISPONIVEL:
            normal, texto_cor, hover, _press = self.VARIANTES[variante]
            self._widget = ctk.CTkButton(
                self, text=texto, command=comando, height=altura,
                width=largura or 0, corner_radius=raio, bg_color=fundo,
                fg_color=normal, hover_color=hover,
                text_color=texto_cor,
                border_width=0 if variante in ("primario", "suave") else 1,
                border_color=BORDA,
                font=font(tamanho, peso))
            self._widget.pack(fill="both", expand=True)
        else:
            self._widget = _BotaoCanvas(
                self, texto, comando, variante=variante, tamanho=tamanho,
                peso=peso, altura=altura, largura=largura, raio=raio,
                parent_bg=fundo)
            self._widget.pack(fill="both", expand=True)

    def definir_variante(self, variante):
        """Troca o estilo em tempo de execucao. Usado pelo comutador de
        visao da aba de Imagens, que marca a aba ativa no botao."""
        if variante not in self.VARIANTES:
            return
        self._variante = variante
        if CTK_DISPONIVEL:
            normal, texto_cor, hover, _press = self.VARIANTES[variante]
            self._widget.configure(fg_color=normal, hover_color=hover,
                                   text_color=texto_cor,
                                   border_width=0 if variante in
                                   ("primario", "suave") else 1)
        else:
            self._widget.definir_variante(variante)

    def definir_texto(self, texto):
        self._texto = texto
        if CTK_DISPONIVEL:
            self._widget.configure(text=texto)
        else:
            self._widget.definir_texto(texto)

    def definir_comando(self, comando):
        self._comando = comando
        if CTK_DISPONIVEL:
            self._widget.configure(command=comando)
        else:
            self._widget.definir_comando(comando)

    def devolver_largura(self):
        """Volta a largura natural do texto.

        A `BarraBotoes` chama isto quando o botao deixa de ser o unico da
        linha. No Canvas antigo era preciso, porque a largura ficava
        gravada no widget depois de esticar. Com CTkButton a largura ja e'
        medida pelo texto: basta soltar a largura fixa, se houver.
        """
        if CTK_DISPONIVEL:
            self._widget.configure(width=self._largura_minima or 0)
        else:
            self._widget.devolver_largura()

    def _redesenhar(self):  # pragma: no cover - compatibilidade
        if not CTK_DISPONIVEL:
            self._widget._redesenhar()


class _BotaoCanvas(tk.Canvas):
    """Botao desenhado a mao, para as maquinas sem CustomTkinter.

    E' o mesmo desenho de antes: retangulo arredondado no
    Canvas com a largura estimada por `len(texto) * 9 + 32`. Nao e' o
    caminho preferencial — quando o CTk esta instalado, `Botao` nem chega
    aqui — mas precisa continuar funcionando na build do Windows sem o
    pacote opcional instalado.
    """

    VARIANTES = {
        "primario": (MARCA, BRANCO, MARCA_ESCURA, "#0b8f5b"),
        "secundario": (BRANCO, TINTA_TEXTO, "#f1f5f9", "#e8edf3"),
        "suave": (MARCA_CLARA, MARCA_ESCURA, "#d6efe3", "#cbe7d9"),
        "fantasma": (BRANCO, TEXTO, "#f1f5f9", "#e8edf3"),
        "perigo": (PERIGO_CLARO, "#b42318", "#fee4e2", "#fdd8d5"),
    }

    def __init__(self, master, texto, comando=None, variante="secundario",
                 tamanho=TEXTO_BASE, peso="normal", altura=36, largura=None,
                 raio=RAIO, parent_bg=None):
        super().__init__(master, width=largura or (len(texto) * 9 + 32),
                         height=altura,
                         bg=parent_bg or master.cget("bg") or FUNDO,
                         highlightthickness=0, bd=0, cursor="hand2", takefocus=1)
        self._texto = texto
        self._comando = comando
        self._variante = variante
        self._fonte = font(tamanho, peso)
        self._altura_fixa = altura
        self._raio = raio
        self._hover = False
        self._press = False
        self._estado = "normal"
        self._largura_minima = largura
        self._largura_natural = largura or (len(texto) * 9 + 32)

        self.bind("<Configure>", lambda e: self._redesenhar())
        self.bind("<Enter>", self._entrar)
        self.bind("<Leave>", self._sair)
        self.bind("<ButtonPress-1>", self._pressionar)
        self.bind("<ButtonRelease-1>", self._soltar)
        self.bind("<Return>", self._ativar)
        self.bind("<KP_Enter>", self._ativar)
        self.bind("<space>", self._ativar)
        self._redesenhar()

    def definir_variante(self, variante):
        """Troca o estilo em tempo de execucao. Usado pelo comutador de
        visao da aba de Imagens, que marca a aba ativa no botao."""
        if variante not in self.VARIANTES:
            return
        self._variante = variante
        self._redesenhar()

    def definir_texto(self, texto):
        self._texto = texto
        self._largura_natural = len(texto) * 9 + 32
        self.configure(width=self._largura_natural)
        self._redesenhar()

    def definir_estado(self, estado):
        self._estado = estado
        self.configure(cursor="arrow" if estado == "disabled" else "hand2")
        self._redesenhar()

    def definir_largura(self, largura):
        self.configure(width=largura)

    def devolver_largura(self):
        """Volta a largura natural do texto. A BarraBotoes usa quando o botao
        deixa de ser o unico da linha: sem isso ele carregaria para a linha
        seguinte a largura que ganhou antes e empurraria os vizinhos."""
        if self._largura_natural:
            self.configure(width=self._largura_natural)

    def _redesenhar(self):
        self.delete("tudo")
        largura = self.winfo_width()
        altura = self.winfo_height()
        if largura < 4:
            largura = self._largura_minima or self.winfo_reqwidth()
        if altura < 4:
            altura = self._altura_fixa

        fundo, texto, hover, press = self.VARIANTES.get(
            self._variante, self.VARIANTES["secundario"])
        if self._estado == "disabled":
            fundo, texto = "#eef2f6", "#a8b4c2"
            hover = press = fundo
        elif self._press:
            fundo = press
        elif self._hover:
            fundo = hover

        borda = BORDA if self._variante in ("secundario", "fantasma") else fundo
        retangulo(self, 1, 1, largura - 1, altura - 1, self._raio, fundo,
                  borda, 1 if borda != fundo else 0)
        self.create_text(largura / 2, altura / 2, text=self._texto, fill=texto,
                         font=self._fonte)

    def _entrar(self, _event=None):
        self._hover = True
        self.configure(cursor="hand2")
        self._redesenhar()

    def _sair(self, _event=None):
        self._hover = False
        self._press = False
        self.configure(cursor="arrow")
        self._redesenhar()

    def _pressionar(self, _event=None):
        if self._estado == "disabled":
            return
        self._press = True
        self.focus_set()
        self._redesenhar()

    def _soltar(self, event=None):
        if self._estado == "disabled":
            return
        self._press = False
        self._redesenhar()
        if event is None:
            return
        dentro = (0 <= event.x < self.winfo_width()
                  and 0 <= event.y < self.winfo_height())
        if dentro and self._hover and self._comando:
            try:
                self._comando()
            except Exception as erro:  # noqa: BLE001
                from painel_automata import escrever_erro
                escrever_erro(f"Acao do botao falhou: {erro}")

    def _ativar(self, _event=None):
        if self._estado == "disabled":
            return
        if self._comando:
            try:
                self._comando()
            except Exception as erro:  # noqa: BLE001
                from painel_automata import escrever_erro
                escrever_erro(f"Ativacao do botao falhou: {erro}")


class AreaRolavel(tk.Frame):
    """Container com rolagem nos dois eixos. O corpo cresce com o conteudo
    e a barra horizontal so aparece quando o conteudo e mais largo que a
    janela, o que mantem as tabelas largas acessiveis em tela pequena."""

    def __init__(self, master, fundo=FUNDO):
        super().__init__(master, bg=fundo, highlightthickness=0, bd=0)
        self._fundo = fundo
        self.canvas = tk.Canvas(self, bg=fundo, highlightthickness=0, bd=0,
                                takefocus=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical",
                                  command=self.canvas.yview,
                                  style="TScrollbar")
        self.hbar = ttk.Scrollbar(self, orient="horizontal",
                                  command=self.canvas.xview,
                                  style="TScrollbar")
        self.canvas.configure(yscrollcommand=self.vbar.set,
                              xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.body = tk.Frame(self.canvas, bg=fundo, highlightthickness=0, bd=0)
        self._janela = self.canvas.create_window((0, 0), window=self.body,
                                                 anchor="nw")
        self.body.bind("<Configure>", self._ao_redimensionar_corpo)
        self.canvas.bind("<Configure>", self._ao_redimensionar)
        self._ligar_roda()

    def _ao_redimencionar_corpo(self, _event=None):
        """O corpo acompanha a altura do conteudo (para a barra vertical
        existir de verdade) e recalcula o scrollregion."""
        self._atualizar_scrollregion()

    # nome publico, usado nos testes e por quem quiser forcar o recalculo
    _ao_redimensionar_corpo = _ao_redimencionar_corpo

    def _ao_redimensionar(self, _event=None):
        """O corpo acompanha a largura da janela, para o texto quebrar em vez
        de vazar. Sem isso o conteudo largo some na borda direita."""
        self._atualizar_scrollregion()

    def _atualizar_scrollregion(self, _event=None):
        """Recalcula a area rolavel. O canvas e fixo (do tamanho da janela) e o
        corpo cresce pelo conteudo: e a diferenca entre os dois que cria o
        scroll e decide se as barras aparecem."""
        largura = max(1, self.canvas.winfo_width())
        altura = max(1, self.canvas.winfo_height())
        # largura segue a janela para o texto quebrar; altura NAO e forcada,
        # senao o conteudo alto nunca gera barra vertical
        # a janela do canvas acompanha a largura e nunca fica menor que a tela.
        # A ALTURA precisa poder crescer com o conteudo: se for fixada no
        # tamanho da janela, o grid de dentro esmaga os cards (a tabela de
        # relatorios cai para 83px) e nao existe rolagem vertical nenhuma.
        # e essa diferenca entre a altura do conteudo e a da janela que cria a
        # barra vertical.
        self.canvas.itemconfigure(self._janela, width=largura,
                                  height=max(altura, self.body.winfo_reqheight()))
        # a regiao precisa alcancar o conteudo inteiro nos DOIS eixos. Com a
        # largura limitada ao canvas o xview ficava sem curso e a barra
        # horizontal aparecia mas nao movia nada.
        self.canvas.configure(scrollregion=(0, 0, max(largura, self._largura_excedente()),
                                            max(altura, self.body.winfo_reqheight())))
        self._ajustar_barras()

    def _ajustar_barras(self):
        self.vbar.grid_remove()
        self.hbar.grid_remove()
        self.canvas.configure(yscrollcommand=self.vbar.set,
                              xscrollcommand=self.hbar.set)
        # barra vertical so quando o conteudo e mais alto que a janela
        if self.body.winfo_reqheight() > self.canvas.winfo_height() + 2:
            self.vbar.grid()
        # barra horizontal so quando alguma coisa e mais larga que a janela
        if self._largura_excedente() > self.canvas.winfo_width() + 2:
            self.hbar.grid()

    def _largura_excedente(self):
        """Maior largura pedida por qualquer filho do corpo. winfo_reqwidth do
        body sozinho engana: um grid com colunas de peso distributes a largura
        e nunca pede mais que o canvas, escondendo tabelas largas."""
        maior = 0
        for widget in self.body.winfo_children():
            for item in (widget, *widget.winfo_children()):
                try:
                    maior = max(maior, item.winfo_reqwidth())
                except tk.TclError:
                    continue
        return maior

    def reajustar_tabelas(self):
        """Refaz o encaixe das colunas. Chamar ao exibir a pagina."""
        for ajustar in getattr(self, "_ajustar_tabelas", ()):
            ajustar()

    def reexibir(self):
        """Reexibe a pagina: refaz colunas, scrollregion e barras.

        Precisa ser chamado ao TROCAR de aba. While a aba esta escondida o
        <Configure> do canvas nao dispara, entao a decricao de "cabe ou nao
        cabe" fica presa no tamanho antigo e a pagina volta sem barra: o
        conteudo que passa da janela fica invisivel e nao ha como rolar ate
        ele, nem com a roda do mouse.
        """
        try:
            self.reajustar_tabelas()
            self.update_idletasks()
            self._atualizar_scrollregion()
        except tk.TclError:
            pass

    def _rolar(self, unidades, _event=None):
        self.canvas.yview_scroll(unidades, "units")

    def _ligar_roda(self):
        for widget in (self, self.canvas, self.body):
            widget.bind("<MouseWheel>", self._rolar, add="+")
            widget.bind("<Button-4>", lambda e: self._rolar(-3), add="+")
            widget.bind("<Button-5>", lambda e: self._rolar(3), add="+")

# ------------------------------------------------------- adaptadores CTk
# Espelho minimo da API do CTk, com a mesma assinatura em ambos os caminhos.
# Assim o `painel_automata.py` escreve uma vez e nao sabe qual esta rodando.
#
# O que NAO virou adaptador, de proposito:
#   - area rolavel: o CTkScrollableFrame e so um eixo e nao tem o
#     `_largura_excedente` que a tabela precisa. A AreaRolavel daqui faz
#     scroll nos dois eixos e ja tem teste.
#   - cartao e botao: os daqui ja desenham raio, borda e os 4 estados, e o
#     Botao e referenciado direto pelos testes.
#   - tabela: o CTk nao tem grid. As 7 Treeview continuam ttk, estilizadas.


class Comutador(tk.Frame):
    """Chave liga/desliga. CTkSwitch quando ha CTk, Checkbutton do ttk caso
    contrario. Mesma assinatura: var, comando, parent_bg."""

    def __init__(self, master, texto="", variavel=None, comando=None,
                 parent_bg=None, **kwargs):
        # o switch e' um controle como outro qualquer: sem esta caixa o
        # "Atualizar sozinho" fica com 24px ao lado de botoes de 38px e a
        # linha do cabecalho nao fecha
        super().__init__(master, bg=parent_bg or FUNDO,
                         height=ALTURA_CONTROLE)
        self.pack_propagate(False)
        self._variavel = variavel
        if CTK_DISPONIVEL:
            self._widget = ctk.CTkSwitch(
                self, text=texto, variable=variavel, command=comando,
                progress_color=MARCA, button_color=BRANCO,
                fg_color=BORDA_FORTE, text_color=TEXTO,
                font=font(TEXTO_BASE), switch_width=34, switch_height=18,
                **({} if not kwargs else kwargs))
        else:
            self._widget = ttk.Checkbutton(self, text=texto,
                                           variable=variavel, command=comando)
        self._widget.pack(side="left",
                             pady=((ALTURA_CONTROLE - 24) // 2, 0))

    def configure(self, **kwargs):
        self._widget.configure(**kwargs)

    config = configure

    def get(self):
        return self._variavel.get() if self._variavel is not None else False

    def set(self, valor):
        if self._variavel is not None:
            self._variavel.set(valor)


class MenuOpcoes(tk.Frame):
    """Combobox de escolha unica. CTkOptionMenu quando ha CTk."""

    def __init__(self, master, valores, variavel=None, comando=None,
                 parent_bg=None, largura=140, **kwargs):
        super().__init__(master, bg=parent_bg or FUNDO)
        lista = list(valores)
        inicial = lista[0] if lista else ""
        if CTK_DISPONIVEL:
            atual = inicial
            if variavel is not None:
                try:
                    atual = variavel.get() or inicial
                except tk.TclError:
                    atual = inicial
            self._widget = ctk.CTkOptionMenu(
                self, values=lista, command=comando,
                variable=variavel, width=largura, height=28,
                corner_radius=RAIO_SMALL, fg_color=BRANCO,
                button_color=TINTA_BORDA, button_hover_color=BORDA,
                text_color=TINTA_TEXTO, dropdown_fg_color=BRANCO,
                dropdown_text_color=TINTA_TEXTO,
                dropdown_hover_color=MARCA_CLARA,
                font=font(TEXTO_BASE), dropdown_font=font(TEXTO_BASE))
        else:
            estado = kwargs.pop("state", "readonly")
            self._widget = ttk.Combobox(self, values=lista,
                                       textvariable=variavel, width=18,
                                       state=estado)
            if comando is not None:
                self._widget.bind("<<ComboboxSelected>>",
                                  lambda e: comando(), add="+")
        self._widget.pack(fill="x")

    def configure(self, **kwargs):
        self._widget.configure(**kwargs)

    config = configure

    def get(self):
        if CTK_DISPONIVEL:
            return self._widget.get()
        return self._widget.get()

    def set(self, valor):
        self._widget.set(valor)


class BotaoSegmentado(tk.Frame):
    """Grupo de opcoes mutuamente exclusivas (periodo do dashboard, modo da
    pagina de imagens). CTkSegmentedButton quando ha CTk."""

    def __init__(self, master, opcoes, comando=None, parent_bg=None,
                 valor=None, altura=None):
        # mesma regra do Botao: altura unica, o destaque vem da cor
        altura = ALTURA_CONTROLE
        super().__init__(master, bg=parent_bg or FUNDO)
        self._opcoes = list(opcoes)
        self._comando = comando
        self._variavel = tk.StringVar(value=valor or (
            self._opcoes[0] if self._opcoes else ""))
        if CTK_DISPONIVEL:
            self._widget = ctk.CTkSegmentedButton(
                self, values=self._opcoes, variable=self._variavel,
                command=self._ao_mudar, height=altura,
                corner_radius=RAIO_SMALL, border_width=1,
                fg_color=BRANCO, selected_color=MARCA,
                selected_hover_color=MARCA_ESCURA,
                unselected_color=BRANCO, unselected_hover_color=TINTA_BORDA,
                text_color=TINTA_TEXTO, font=font(TEXTO_BASE))
        else:
            # ttk nao tem segmentado: vira um grupo de radiobuttons, que e a
            # mesma ideia com o desenho do toolkit.
            self._widget = ttk.Frame(self, style="TFrame")
            for opcao in self._opcoes:
                ttk.Radiobutton(self._widget, text=opcao,
                                value=opcao, variable=self._variavel,
                                command=self._ao_mudar).pack(side="left")
            self._widget.bind("<Configure>", lambda e: None)
        self._widget.pack(fill="x")

    def _ao_mudar(self, *_):
        if self._comando is not None:
            self._comando(self._variavel.get())

    def get(self):
        return self._variavel.get()

    def set(self, valor):
        self._variavel.set(valor)
        if CTK_DISPONIVEL:
            self._widget.set(valor)


class BarraProgresso(tk.Frame):
    """Progresso fino. CTkProgressBar quando ha CTk."""

    def __init__(self, master, parent_bg=None, altura=6, cor=MARCA):
        super().__init__(master, bg=parent_bg or FUNDO)
        if CTK_DISPONIVEL:
            self._widget = ctk.CTkProgressBar(
                self, height=altura, corner_radius=altura // 2,
                fg_color=BORDA, progress_color=cor)
        else:
            self._widget = ttk.Progressbar(
                self, mode="determinate", length=200,
                style="Horizontal.Horizontal.TProgressbar")
        self._widget.pack(fill="x")

    def set(self, fracao):
        fracao = max(0.0, min(1.0, float(fracao)))
        if CTK_DISPONIVEL:
            self._widget.set(fracao)
        else:
            self._widget["value"] = fracao * 100

    def parar(self):
        self.set(0.0)


class CaixaTexto(tk.Frame):
    """Caixa de texto multilinha. CTkTextbox quando ha CTk."""

    def __init__(self, master, parent_bg=None, altura=120, largura=200):
        super().__init__(master, bg=parent_bg or FUNDO)
        if CTK_DISPONIVEL:
            self._widget = ctk.CTkTextbox(
                self, width=largura, height=altura,
                corner_radius=RAIO_SMALL, border_width=1,
                fg_color=BRANCO, border_color=BORDA,
                text_color=TINTA_TEXTO, font=font(TEXTO_BASE),
                wrap="word")
        else:
            self._widget = tk.Text(self, width=largura, height=altura,
                                   bg=BRANCO, fg=TINTA_TEXTO,
                                   font=font(TEXTO_BASE), relief="solid",
                                   borderwidth=1, highlightthickness=0,
                                   wrap="word")
        self._widget.pack(fill="both", expand=True)

    def ver(self, texto=""):
        self._widget.delete("1.0", "end")
        self._widget.insert("1.0", texto)

    def escrever(self, texto):
        self._widget.insert("end", texto)

    def limpar(self):
        self._widget.delete("1.0", "end")

    def texto(self):
        return self._widget.get("1.0", "end")


def aplicar_tema_ctk(modo="Light"):
    """Aponta o CTk para a paleta do app. Sem customtkinter e no-op."""
    if not CTK_DISPONIVEL:
        return False
    ctk.set_appearance_mode(modo)
    ctk.set_default_color_theme("blue")
    return True


def raiz_ctk():
    """Classe da janela raiz: CTk quando disponivel, tk.Tk caso contrario.

    O app herda daqui. Com tk.Tk puro, os widgets do CTk funcionam como
    hijos normais, mas perde-se o modo escuro e o scaling automatico.
    """
    return ctk.CTk if CTK_DISPONIVEL else tk.Tk


# ==================================================================
# KIT DE LAYOUT
#
# Por que isto existe: cada tela antiga misturava `pack` e `grid` no mesmo
# frame e usava `padx`/`pady` como espacador. Isso produz tres doencas
# recorrentes:
#
#   1. `pack` e `grid` no mesmo master e' erro de Tk. Quem faz isso ganha
#      "cannot use geometry manager grid inside ... which already has
#      slaves managed by pack" em tempo de execucao.
#   2. O padding vira espacamento: cartao com pady=16 e vizinho com
#      pady=(0,12) soma 28px, e ninguem consegue prever a altura final.
#   3. Nada encolhe. `padx` e `pady` sao o minimo que o master exige, e
#      nunca o maximo, entao em 1040px o layout estoura em vez de encolher.
#
# A regra daqui: UM GEOMETRY MANAGER por frame (so `grid`), espacamento
# SEMPRE em `padx`/`pady` do grid, e largura/altura minima em
# `columnconfigure`/`rowconfigure`. Os containers abaixo ja nascem com o
# grid configurado, entao quem monta a tela so escreve `coluna`, `linha`
# e `peso`.
# ==================================================================


class Abas(tk.Frame):
    """Troca de pagina com `place`, sem a tira de abas do `ttk.Notebook`.

    O `ttk.Notebook` desenhava uma tira de abas no topo do conteudo — uma
    pasta com abas superiores, ao lado da sidebar que ja faz a mesma
    navegacao. Dois jeitos de escolher a tela, e o segundo parecia um
    navegador dos anos 90. Aqui as paginas ficam empilhadas na mesma
    celula e so uma aparece; quem navega e' a sidebar.

    Mantem o pedaco da API do `ttk.Notebook` que o app usa (`add`,
    `select`, `pack`), para `self.notebook` continuar funcionando.
    """

    def __init__(self, master, fundo=FUNDO, **kwargs):
        super().__init__(master, bg=fundo)
        self._paginas = []
        self._atual = None

    def add(self, frame, text="", **kwargs):
        frame.place_forget()
        self._paginas.append((frame, text))
        if self._atual is None:
            self.select(frame)
        return frame

    def select(self, alvo=None):
        """Sem argumento devolve a pagina visivel; com argumento troca."""
        if alvo is None:
            return self._atual
        if isinstance(alvo, str):
            alvo = self._paginas[int(alvo)][0]
        for outra, _ in self._paginas:
            if outra is not alvo:
                outra.place_forget()
        alvo.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._atual = alvo
        return alvo

    def tabs(self):
        return [pagina for pagina, _ in self._paginas]

    def tab(self, alvo, opcao=None):
        for pagina, texto in self._paginas:
            if pagina is alvo:
                if opcao == "text":
                    return texto
                return {"text": texto}
        raise tk.TclError(f"aba desconhecida: {alvo}")


class Tela(tk.Frame):
    """Raiz de uma aba: so grid, com a conta de linhas e colunas feita uma
    vez.

    Nao ha frame interno de proposito. O padding da pagina ja vem do
    `conteudo_pagina` (padx=ESPACO_4), e um frame a mais com `pack` aqui
    dentro conflitaria com o `grid` das celulas — que e' exatamente o erro
    "pack is already managing its content windows".

    Use:
        tela = ui.Tela(self.tab_etiquetas, linhas=3)
        tela.linha(1, peso=1)
        tela.celula(filtros, 0, 0)
        trabalho = tela.secao(1, 0, peso_linha=1)
        trabalho.coluna(0, peso=3, minima=420)
    """

    def __init__(self, master, linhas=0, colunas=1, fundo=FUNDO, espaco=0):
        super().__init__(master, bg=fundo)
        self._fundo = fundo
        self._espaco = espaco
        for linha in range(linhas):
            self.rowconfigure(linha, weight=0)
        for coluna in range(colunas):
            self.columnconfigure(coluna, weight=1)

    def fundo(self, cor):
        self._fundo = cor
        self.configure(bg=cor)
        return self

    def linha(self, indice, peso=0, minima=0):
        """Marca uma linha para esticar. `minima` impede esmagamento."""
        self.rowconfigure(indice, weight=peso, minsize=minima)
        return self

    def coluna(self, indice, peso=0, minima=0, uniforme=None):
        self.columnconfigure(indice, weight=peso, minsize=minima,
                             uniform=uniforme)
        return self

    def celula(self, widget, linha=0, coluna=0, span_linha=1, span_coluna=1,
               sticky="nsew", espaco=None):
        """Cola um widget que foi criado com `self` como master. O
        espacamento e' opcional e por padrao e' zero: respiro entre blocos
        vizinhos passa a ser escolha de quem monta, nao conta automatica."""
        pad = self._espaco if espaco is None else espaco
        widget.grid(row=linha, column=coluna, rowspan=span_linha,
                    columnspan=span_coluna, sticky=sticky,
                    padx=pad, pady=pad)
        return widget

    def secao(self, linha=0, coluna=0, span_linha=1, span_coluna=1,
              peso_linha=0, peso_coluna=0, minima_linha=0, minima_coluna=0):
        """Cria um sub-frame com o grid ja configurado e registra o peso dele
        na propria linha/coluna, para o chamador nao repetir numeros."""
        if peso_linha:
            self.rowconfigure(linha, weight=peso_linha, minsize=minima_linha)
        if peso_coluna or minima_coluna:
            self.columnconfigure(coluna, weight=peso_coluna,
                                 minsize=minima_coluna)
        # A Coluna e' gridada DIRETO, nao um Frame simples embrulhando
        # outra Coluna: se embrulhasse, o peso configurado em `trabalho`
        # iria para o frame de fora (que fica com 1px) e nao para o grid de
        # verdade. O sintoma era tabela e detalhe com largura 1.
        frame = Coluna(self, fundo=self._fundo, espaco=ESPACO_3)
        self.celula(frame, linha, coluna, span_linha, span_coluna)
        return frame

    def divisor(self, linha=0, coluna=0, span_coluna=1):
        """Filete de 1px: `sticky='ew'` sem peso, porque aqui a coluna e' o
        comprimento e a linha e' a dobra."""
        filete = tk.Frame(self, bg=BORDA, height=1)
        self.celula(filete, linha, coluna, 1, span_coluna, sticky="ew")
        return filete


class Coluna(tk.Frame):
    """Sub-frame com grid pronto: linhas/colunas numeradas de 0.

    Devolvido por `Tela.secao`. Faz `grid` ser a unica forma de colocar
    coisa dentro dele, o que mata a confusao pack-vs-grid na origem.
    """

    def __init__(self, master, fundo=FUNDO, espaco=ESPACO_4):
        super().__init__(master, bg=fundo)
        self._fundo = fundo
        self._espaco = espaco

    def fundo(self, cor):
        self._fundo = cor
        self.configure(bg=cor)
        return self

    def linha(self, indice, peso=0, minima=0):
        self.rowconfigure(indice, weight=peso, minsize=minima)
        return self

    def secao(self, linha=0, coluna=0, span_linha=1, span_coluna=1,
              peso_linha=0, peso_coluna=0, minima_linha=0, minima_coluna=0):
        """Cria um sub-frame com o grid ja configurado e registra o peso dele
        na propria linha/coluna, para o chamador nao repetir numeros."""
        if peso_linha:
            self.rowconfigure(linha, weight=peso_linha, minsize=minima_linha)
        if peso_coluna or minima_coluna:
            self.columnconfigure(coluna, weight=peso_coluna,
                                 minsize=minima_coluna)
        frame = Coluna(self, fundo=self._fundo, espaco=ESPACO_3)
        self.celula(frame, linha, coluna, span_linha, span_coluna)
        return frame

    def coluna(self, indice, peso=0, minima=0, uniforme=None):
        self.columnconfigure(indice, weight=peso, minsize=minima,
                             uniform=uniforme)
        return self

    def celula(self, widget, linha=0, coluna=0, span_linha=1, span_coluna=1,
               sticky="nsew", espaco=None, sem_espaco=False):
        pad = (0, 0) if sem_espaco else (
            espaco if espaco is not None else self._espaco)
        widget.grid(row=linha, column=coluna, rowspan=span_linha,
                    columnspan=span_coluna, sticky=sticky,
                    padx=pad, pady=pad)
        return widget

    def item(self, widget, linha=0, coluna=0, span_linha=1, span_coluna=1,
             sticky="new", espaco=None, sem_espaco=False):
        """Igual a `celula`, mas com sticky='new': o bloco fica na altura
        que precisa e NAO e esticado. Para cartao de formulario, que deve
        acompanhar o texto e nao a altura da janela."""
        return self.celula(widget, linha, coluna, span_linha, span_coluna,
                           sticky=sticky, espaco=espaco, sem_espaco=sem_espaco)

    def divisor(self, linha=0, coluna=0, span_coluna=1):
        filete = tk.Frame(self, bg=BORDA, height=1)
        self.celula(filete, linha, coluna, 1, span_coluna, sticky="ew",
                    espaco=0)
        return filete


class Cabecalho(tk.Frame):
    """Titulo + legenda + acoes, na linha de cima de um cartao.

    Antes cada tela montava isso na mao e o resultado variava: ora o titulo
    sumia sob os botoes, ora os botoes estouravam. Aqui o titulo tem
    peso e as acoes encolhem, entao em 1040px o titulo trunca em vez de
    empurrar o botao primario para fora.
    """

    def __init__(self, master, titulo="", legenda="", fundo=BRANCO,
                 tamanho=TEXTO_GRANDE):
        super().__init__(master, bg=fundo)
        textos = tk.Frame(self, bg=fundo)
        textos.grid(row=0, column=0, sticky="w")
        textos.columnconfigure(0, weight=1)
        self._titulo = tk.Label(textos, text=titulo, bg=fundo, fg=TINTA_TEXTO,
                                font=font(tamanho, "bold"), anchor="w")
        self._titulo.grid(row=0, column=0, sticky="w")
        self._legenda = tk.Label(textos, text=legenda, bg=fundo, fg=TEXTO_FRACO,
                                 font=font(TEXTO_MENOR), anchor="w")
        if legenda:
            self._legenda.grid(row=1, column=0, sticky="w")
        self.acoes = tk.Frame(self, bg=fundo)
        self.acoes.grid(row=0, column=1, sticky="e", padx=(ESPACO_3, 0))
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def definir_titulo(self, texto):
        self._titulo.configure(text=texto)

    def definir_legenda(self, texto):
        self._legenda.configure(text=texto)

    def titulo_widget(self):
        return self._titulo


class Kpi(tk.Frame):
    """Numero grande + rotulo + variacao, do jeito que painel de verdade
    mostra metrica.

    O valor usa fonte de 24px porque o numero e' a informacao; o rotulo e'
    texto miudo. Sem cartao em volta: a faixa de KPIs ja separa por
    espaco e filete, cartao em cada numero vira xadrez.
    """

    ALTURA = 84

    def __init__(self, master, rotulo="", valor="--", cor=TINTA_TEXTO,
                 fundo=BRANCO, dica=""):
        super().__init__(master, bg=fundo)
        self._fundo = fundo
        self._valor_widget = tk.Label(
            self, text=valor, bg=fundo, fg=cor,
            font=font(TEXTO_NUMERO, "bold"), anchor="w")
        self._valor_widget.pack(fill="x")
        self._rotulo_widget = tk.Label(self, text=rotulo, bg=fundo,
                                       fg=TEXTO_FRACO, anchor="w",
                                       font=font(TEXTO_MENOR))
        self._rotulo_widget.pack(fill="x")
        self._dica_widget = tk.Label(self, text=dica, bg=fundo, fg=MARCA,
                                     anchor="w", font=font(TEXTO_MENOR - 1))
        if dica:
            self._dica_widget.pack(fill="x")

    def definir_valor(self, valor, cor=None):
        self._valor_widget.configure(text=valor)
        if cor is not None:
            self._valor_widget.configure(fg=cor)

    def definir_legenda(self, texto):
        self._dica_widget.configure(text=texto)


class FaixaKpi(tk.Frame):
    """Linha de KPIs. Reparte o espaco igualmente e desenha filetes
    verticais entre eles, que e o que separa metricas sem virar xadrez.
    """

    def __init__(self, master, quantidade, fundo=BRANCO):
        super().__init__(master, bg=fundo)
        self._fundo = fundo
        self._n = max(1, quantidade)
        for indice in range(self._n):
            self.columnconfigure(indice, weight=1, uniform="kpi")
        self.cells = []
        for indice in range(self._n):
            celula = tk.Frame(self, bg=fundo)
            celula.grid(row=0, column=indice, sticky="nsew",
                        padx=ESPACO_4, pady=ESPACO_3)
            self.cells.append(celula)

    def montar(self, rotulo, valor, indice=0, cor=TINTA_TEXTO, dica=""):
        """Cria um KPI na posicao `indice` e devolve o widget."""
        celula = self.cells[indice]
        # o filete foi posicionado com place() e nao aparece em
        # winfo_children() como filho gerenciado, entao pode limpar tudo
        for filho in celula.winfo_children():
            filho.destroy()
        kpi = Kpi(celula, rotulo, valor, cor=cor, fundo=self._fundo,
                  dica=dica)
        kpi.grid(row=0, column=0, sticky="nsew")
        if indice:
            filete = tk.Frame(celula, bg=BORDA, width=1)
            filete.place(x=0, rely=0.08, relheight=0.84)
        self._kpis = getattr(self, "_kpis", {})
        self._kpis[indice] = kpi
        return kpi

    def definir(self, indice, valor, cor=None, legenda=None):
        kpi = getattr(self, "_kpis", {}).get(indice)
        if kpi is None:
            return None
        kpi.definir_valor(valor, cor)
        if legenda is not None:
            kpi.definir_legenda(legenda)
        return kpi


class Painel(tk.Frame):
    """Casca de uma tabela: cabecalho,Toolbar, tabela e rodape.

    Substitui as quatro linhas de codigo repetidas em cada aba (cartao +
    treeview + scrollbar + tres binds). Todo mundo usa grid, entao o
    scrollbar vertical e' sempre o mesmo e a tabela ocupa a largura
    restante em vez de depender de `expand=True` misturado com `pack`.
    """

    def __init__(self, master, colunas, titulo="", legenda="", fundo=BRANCO):
        super().__init__(master, bg=fundo)
        self._fundo = fundo
        self.colunas = tuple(colunas)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # linha 0: cabecalho com titulo, legenda e acoes
        if titulo or legenda:
            self.cabecalho = Cabecalho(self, titulo, legenda, fundo=fundo)
            self.cabecalho.grid(row=0, column=0, sticky="ew",
                                padx=ESPACO_4, pady=(ESPACO_4, ESPACO_2))
            self.acoes = self.cabecalho.acoes
        else:
            self.cabecalho = None
            self.acoes = tk.Frame(self, bg=fundo)
            self.acoes.grid(row=0, column=0, sticky="ew", padx=ESPACO_4,
                            pady=(ESPACO_4, ESPACO_2))

        # linha 1: toolbar opcional, cole o botao certo embaixo do cabecalho
        self._toolbar = None
        self.linha_toolbar = 1
        self._linha_tabela = 2
        self.rowconfigure(self._linha_tabela, weight=1)

    def toolbar(self, fundo=None):
        """Cria (uma vez) a faixa de acoes entre cabecalho e tabela."""
        if self._toolbar is None:
            self._toolbar = tk.Frame(
                self, bg=fundo or self._fundo)
            self._toolbar.grid(row=self.linha_toolbar, column=0, sticky="ew",
                               padx=ESPACO_4, pady=(0, ESPACO_2))
            self._linha_tabela = 2
            self.rowconfigure(self._linha_tabela, weight=1)
        return self._toolbar

    def montar_tabela(self, style="Tabela.Treeview", altura=10,
                      selectmode="extended", area=None):
        """Cria o Treeview e os dois scrollbars e devolve a arvore.

        `area` e' a AreaRolavel da pagina: e' ela que decide o espaco e
        quem repinta ao voltar para a aba.
        """
        interno = tk.Frame(self, bg=self._fundo)
        interno.grid(row=self._linha_tabela, column=0, sticky="nsew",
                     padx=ESPACO_4, pady=(0, ESPACO_4))
        interno.columnconfigure(0, weight=1)
        interno.rowconfigure(0, weight=1)

        self.arvore = ttk.Treeview(interno, columns=self.colunas,
                                   show="headings", selectmode=selectmode,
                                   style=style, height=altura)
        if area is not None:
            prender_tabela(self.arvore, area)

        self.barra_v = ttk.Scrollbar(interno, orient="vertical",
                                     command=self.arvore.yview)
        self.barra_h = ttk.Scrollbar(interno, orient="horizontal",
                                     command=self.arvore.xview)
        self.arvore.configure(yscrollcommand=self.barra_v.set,
                              xscrollcommand=self.barra_h.set)
        # grid: coluna 0 e' a tabela e ocupa tudo; coluna 1 e' a barra
        # vertical; linha 1 e' a horizontal. Sem `side=` e sem `expand`,
        # que era o que fazia a barra sumir quando a aba voltava.
        self.arvore.grid(row=0, column=0, sticky="nsew")
        self.barra_v.grid(row=0, column=1, sticky="ns")
        self.barra_h.grid(row=1, column=0, sticky="ew")
        return self.arvore

    def rodape(self):
        """Faixa de acao no rodape do painel (paginacao, exportar)."""
        faixa = tk.Frame(self, bg=self._fundo)
        faixa.grid(row=self._linha_tabela + 1, column=0, sticky="ew",
                   padx=ESPACO_4, pady=(0, ESPACO_4))
        return faixa

    def area_da_tabela(self):
        return self.arvore


class BarraFiltros(tk.Frame):
    """Linha de filtros com rotulo em cima do campo.

    Antes cada filtro era um rotulo a esquerda do campo, na mesma linha.
    Com tres filtros, o primeiro com rotulo longo empurrava os outros dois
    para fora em 1040px. Rotulo em cima resolve: o campo ganha largura
    inteira e a coluna de rotulos deixa de existir.
    """

    def __init__(self, master, colunas=1, fundo=FUNDO, espaco=ESPACO_3):
        super().__init__(master, bg=fundo)
        self._fundo = fundo
        self._espaco = espaco
        self._proximo = 0
        for indice in range(colunas):
            self.columnconfigure(indice, weight=1, uniform="filtro")

    def campo(self, rotulo, widget, linha=0, coluna=None, span=1,
              largura_minima=0, hint=""):
        """Rotulo em cima, `widget` embaixo. Devolve o widget.

        Rotulo e campo sao os DOIS filhos diretos da barra: o widget ja
        nasce com a barra como pai e Tk nao deixa trocar o pai de uma
        janela depois de criada. Embrulhar num `celula` e mandar o widget
        para la dentro deixava os quatro campos de Relatorios na mesma
        celula (row=1, col=0), todos desenhados um por cima do outro.
        """
        if coluna is None:
            coluna = self._proximo
            self._proximo += 1
        if largura_minima:
            self.columnconfigure(coluna, minsize=largura_minima)
        tk.Label(self, text=rotulo.upper(), bg=self._fundo, fg=TEXTO_FRACO,
                 font=font(TEXTO_MENOR - 1, "bold"),
                 anchor="w").grid(row=linha, column=coluna, columnspan=span,
                                  sticky="w", padx=self._espaco)
        widget.grid(row=linha + 1, column=coluna, columnspan=span,
                    sticky="ew", padx=self._espaco)
        if hint:
            tk.Label(self, text=hint, bg=self._fundo, fg=TEXTO_FRACO,
                     font=font(TEXTO_MENOR - 1), anchor="w").grid(
                         row=linha + 2, column=coluna, columnspan=span,
                         sticky="w", padx=self._espaco)
        return widget

    def acoes(self, linha=0, coluna=None, span=1):
        """Celula de botoes alinhada com a BASE dos campos, para a acao
        primaria ficar na mesma linha de base da tabela."""
        if coluna is None:
            coluna = self._proximo
            self._proximo += 1
        celula = tk.Frame(self, bg=self._fundo)
        # uma linha abaixo do rotulo: e' onde os campos ficam
        celula.grid(row=linha + 1, column=coluna, columnspan=span,
                    sticky="se", padx=self._espaco, pady=0)
        return celula

    def botao(self, texto, comando, variante="primario", linha=0,
              coluna=None, tamanho=TEXTO_BASE):
        celula = self.acoes(linha, coluna)
        botao = Botao(celula, texto, comando, variante=variante,
                      tamanho=tamanho, parent_bg=self._fundo)
        botao.pack(side="left")
        return botao


class Bloco(tk.Frame):
    """Cartao com cabecalho e corpo, sem tabela.

    E o irmao do Painel: mesma casca de cabecalho, mas o corpo e' livre e
    recebe o que a tela precisar. Antes o detalhe da fila, o ranking do
    dashboard e a previa de imagem usavam tres versoes diferentes de
    cartao, cada uma com o proprio espacamento, e por isso nenhum batia
    com os outros na mesma tela.
    """

    def __init__(self, master, titulo="", legenda="", fundo=BRANCO,
                 padding=ESPACO_4):
        super().__init__(master, bg=fundo)
        self._fundo = fundo
        self.columnconfigure(0, weight=1)
        self.cabecalho = None
        self.acoes = None
        linha = 0
        if titulo or legenda:
            self.cabecalho = Cabecalho(self, titulo, legenda, fundo=fundo,
                                       tamanho=TEXTO_MEDIO)
            self.cabecalho.grid(row=0, column=0, sticky="ew",
                                padx=padding, pady=(padding, ESPACO_2))
            self.acoes = self.cabecalho.acoes
            linha = 1
        self.corpo = tk.Frame(self, bg=fundo)
        self.corpo.grid(row=linha, column=0, sticky="nsew",
                        padx=padding, pady=(0, padding))
        self.corpo.columnconfigure(0, weight=1)
        # o corpo leva a altura que sobrar. Sem isto o `Bloco` fica com a
        # altura do texto: o canvas da foto e os blocos do dashboard ficavam
        # com o tamanho pedido e nao acompanhavam a janela.
        self.rowconfigure(linha, weight=1)
        self.linha = linha

    def fundo_corpo(self, cor):
        self.corpo.configure(bg=cor)
        return self

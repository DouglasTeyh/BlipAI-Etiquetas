"""Camada de curadoria de imagens do Painel AUTOMATA: fala com o servidor de
imagens (o mesmo que a automacao buscar-imagens sobe) e devolve a colecao e as
candidatas ja no formato que a tela usa.

Por que um modulo separado e nao dentro do app: da para exercitar a
curadoria (confirmar, rejeitar, recoletar) contra o servidor local sem abrir
janela do Tk.

O servidor responde as acoes com 303 para uma pagina HTML, sem JSON. Por isso
toda funcao de escrita devolve o estado novo em vez do corpo da resposta: o
cliente refaz o GET do detalhe. E o que mantem este modulo compativel com o
servidor atual, sem precisar alterar o outro projeto.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "Painel AUTOMATA/1.0"
URL_PADRAO = "http://127.0.0.1:5050"

PENDENTE = "pendente"
CONFIRMADA = "confirmada"
REJEITADA = "rejeitada"

# Rotulos do estado, na ordem em que a triagem aparece na tela.
ESTADOS = (PENDENTE, CONFIRMADA, REJEITADA)


class ErroCuradoria(Exception):
    """Falha de rede, HTTP ou formato na API de curadoria. A tela mostra o
    texto direto; a causa vem junto para o log."""


def normalizar_url(url):
    """Aceita o que o usuario digita no campo do servidor: sem http://, com
    barra no fim ou vazio."""
    alvo = (url or "").strip().rstrip("/")
    if not alvo:
        return URL_PADRAO
    if "://" not in alvo:
        alvo = f"http://{alvo}"
    return alvo


def _abrir(url, timeout, metodo="GET", corpo=None, aceita_json=True):
    """Chamada HTTP unica. Converte qualquer falha em ErroCuradoria com uma
    frase que diz o que fazer, em vez de despejar traceback na tela."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=dados, headers=headers,
                                     method=metodo)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resposta:
            bruto = resposta.read()
    except urllib.error.HTTPError as erro:
        raise ErroCuradoria(f"{metodo} {url} respondeu {erro.code}") from erro
    except urllib.error.URLError as erro:
        raise ErroCuradoria(
            f"nao consegui falar com {url} ({erro.reason}). "
            "o servidor de imagens esta rodando?") from erro
    except OSError as erro:
        raise ErroCuradoria(f"falha de rede em {metodo} {url}: {erro}") from erro
    if not aceita_json or not bruto.strip():
        return None
    try:
        return json.loads(bruto.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as erro:
        raise ErroCuradoria(
            f"resposta de {url} nao era JSON (o servidor devolveu HTML?)"
        ) from erro


def _sem_barra(caminho):
    return caminho.strip("/")


# ------------------------------------------------------------------- leitura
def listar_colecao(url, timeout=30):
    """Todos os produtos ja coletados, com a contagem por estado.
    /colecao devolve JSON quando o Accept pede JSON."""
    base = normalizar_url(url)
    corpo = _abrir(f"{base}/colecao", timeout)
    itens = (corpo or {}).get("data") or []
    return itens if isinstance(itens, list) else []


def detalhe(url, codigo, timeout=30):
    """Um produto com a lista completa de candidatas. O servidor so devolve
    JSON com ?json=1 nesta rota (diferente do /colecao, que respeita Accept)."""
    base = normalizar_url(url)
    caminho = urllib.parse.quote(codigo or "")
    corpo = _abrir(f"{base}/colecao/{caminho}?json=1", timeout)
    dados = (corpo or {}).get("data") or {}
    if not isinstance(dados, dict):
        dados = {}
    return {
        "codigo": dados.get("codigo") or codigo or "",
        "info": dados.get("info") or {},
        "imagens": dados.get("imagens") or [],
    }


def situacao(url, codigo, timeout=15):
    """Contagem por estado de um produto: total, pendentes, confirmadas,
    rejeitadas e sem_confirmada (que e o que trava o envio ao Bling)."""
    base = normalizar_url(url)
    caminho = urllib.parse.quote(codigo or "")
    corpo = _abrir(f"{base}/colecao/{caminho}/situacao", timeout)
    dados = (corpo or {}).get("data") or {}
    return dados if isinstance(dados, dict) else {}


def imagens_confirmadas(url, codigo, timeout=30):
    """Links das imagens aprovadas. E o que vai para o Bling, entao so as
    CONFIRMADAS saem daqui."""
    base = normalizar_url(url)
    caminho = urllib.parse.quote(codigo or "")
    corpo = _abrir(f"{base}/imagem?codigo={caminho}", timeout)
    itens = (corpo or {}).get("data") or []
    links = []
    for item in itens:
        if isinstance(item, dict) and isinstance(item.get("link"), str):
            links.append(item["link"])
    return links


def link_arquivo(url, codigo, arquivo):
    """URL publica de um arquivo guardado no servidor. Montada aqui porque o
    servidor devolve o caminho relativo dentro do JSON, nao a URL."""
    base = normalizar_url(url)
    return (f"{base}/arquivos/{urllib.parse.quote(codigo or '')}"
            f"/{urllib.parse.quote(arquivo or '')}")


# -------------------------------------------------------------------- escrita
def coletar(url, produtos, forcar=False, timeout=120):
    """Manda produtos para o servidor buscar candidatas. O servidor faz a
    busca web, o download e devolve o que aconteceu com cada um.

    ATENCAO: forcar=True apaga TODAS as imagens do produto, incluindo as ja
    confirmadas. Por isso a tela pede confirmacao antes de usar.
    """
    base = normalizar_url(url)
    corpo = _abrir(f"{base}/colecao", timeout, metodo="POST",
                   corpo={"produtos": produtos, "forcar": forcar})
    itens = (corpo or {}).get("data") or []
    return itens if isinstance(itens, list) else []


def confirmar(url, id_imagem, codigo, timeout=30):
    """Aprova uma candidata. O servidor responde 303 para uma pagina HTML, sem
    corpo uteis, entao devolvemos o detalhe recem-buscado."""
    base = normalizar_url(url)
    _abrir(f"{base}/imagens/{int(id_imagem)}/confirmar", timeout,
           metodo="POST", aceita_json=False)
    return detalhe(base, codigo)


def rejeitar(url, id_imagem, codigo, timeout=30):
    """Descarta uma candidata. Mesma caso do confirmar: refaz o GET depois."""
    base = normalizar_url(url)
    _abrir(f"{base}/imagens/{int(id_imagem)}/rejeitar", timeout,
           metodo="POST", aceita_json=False)
    return detalhe(base, codigo)


def buscar_novamente(url, codigo, timeout=120):
    """Refaz a busca do produto.

    O servidor descarta as candidatas nao aprovadas e recoleta, preservando as
    CONFIRMADAS (e o arquivo delas). A triagem em andamento se perde, por isso
    o painel pede confirmacao antes.
    """
    base = normalizar_url(url)
    _abrir(f"{base}/colecao/{urllib.parse.quote(codigo or '')}/buscar", timeout,
           metodo="POST", aceita_json=False)
    return detalhe(base, codigo)


# ------------------------------------------------------------- presentation
def resumir_colecao(itens):
    """Totais da colecao para o cabecalho da aba."""
    total = pendentes = confirmadas = rejeitadas = sem_confirmada = 0
    for item in itens or []:
        if not isinstance(item, dict):
            continue
        total += int(item.get("total") or 0)
        pendentes += int(item.get("pendentes") or 0)
        confirmadas += int(item.get("confirmadas") or 0)
        rejeitadas += int(item.get("rejeitadas") or 0)
        if item.get("sem_confirmada"):
            sem_confirmada += 1
    return {"total": total, "pendentes": pendentes, "confirmadas": confirmadas,
            "rejeitadas": rejeitadas, "sem_confirmada": sem_confirmada,
            "produtos": len(itens or [])}


def agrupar_por_estado(imagens):
    """Separa as candidatas por estado, mantendo a ordem de chegada."""
    grupos = {PENDENTE: [], CONFIRMADA: [], REJEITADA: []}
    for imagem in imagens or []:
        if not isinstance(imagem, dict):
            continue
        estado = imagem.get("status")
        if estado in grupos:
            grupos[estado].append(imagem)
    return grupos


def produto_para_coleta(produto):
    """Achata um produto do Bling no formato que /colecao espera.
    O servidor usa nome e gtin para montar a query de busca."""
    if not isinstance(produto, dict):
        return {}
    return {
        "codigo": str(produto.get("sku") or produto.get("codigo") or "").strip(),
        "id": produto.get("fila_id") or produto.get("id"),
        "nome": str(produto.get("name") or produto.get("nome") or "").strip(),
        "gtin": str(produto.get("barcode") or produto.get("gtin") or "").strip(),
    }
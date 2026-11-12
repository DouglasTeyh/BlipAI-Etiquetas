"""Camada de relatorios do Painel AUTOMATA: monta a consulta (fonte + colunas
+ filtros + agrupamento + agregacao), fala com a API do servidor e devolve
linhas ja formatadas para a tela e para a exportacao.

Por que um modulo separado e nao dentro do app: assim da para testar a
montagem de consulta e a agregacao sem abrir janela do Tk.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "Painel AUTOMATA/1.0"

# As colunas fixas sao as garantidas pelo financeiro_db. O servidor pode
# devolver outras (qualquer campo do JSON cru) e elas entram dinamicamente.
COLUNAS_FIXAS = {
    "id": "ID",
    "data": "Data",
    "data_alt": "Alterado em",
    "rotulo": "Descricao",
    "valor": "Valor",
    "saldo": "Saldo",
    "situacao_nome": "Situacao",
    "categoria_nome": "Categoria",
    "contato_nome": "Cliente / Fornecedor",
    "numero": "Numero",
    "serie": "Serie",
    "chave": "Chave de acesso",
    "total": "Total",
    "quantidade_itens": "Itens",
}

ENTIDADES = {
    "contas_receber": "Contas a Receber",
    "contas_pagar": "Contas a Pagar",
    "pedidos": "Pedidos de Venda",
    "notas_fiscais": "Notas Fiscais",
    "notas_entrada": "Notas de Entrada",
    "pedidos_compra": "Pedidos de Compra",
}

AGREGACOES = {
    "soma": "Soma",
    "media": "Media",
    "contagem": "Contagem",
    "minimo": "Minimo",
    "maximo": "Maximo",
}

LIMITES = {"csv": 200000, "xlsx": 60000, "pdf": 12000}


def eh_numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _config_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


MODELOS_FILE = os.path.join(_config_dir(), "painel_automata_relatorios.json")


# ------------------------------------------------------------------ modelos
def carregar_modelos():
    try:
        with open(MODELOS_FILE, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados if isinstance(dados, list) else []
    except (OSError, ValueError):
        return []


def salvar_modelos(modelos):
    with open(MODELOS_FILE, "w", encoding="utf-8") as arquivo:
        json.dump(modelos, arquivo, ensure_ascii=False, indent=2)


def salvar_modelo(nome, definicao):
    modelos = [m for m in carregar_modelos() if m.get("nome") != nome]
    definicao = dict(definicao)
    definicao["nome"] = nome
    modelos.append(definicao)
    salvar_modelos(modelos)
    return definicao


def apagar_modelo(nome):
    modelos = [m for m in carregar_modelos() if m.get("nome") != nome]
    salvar_modelos(modelos)


# ----------------------------------------------------------------- consulta
def _sem_acento(texto):
    """Maiusculas minusculas e sem acento, para comparar rotulo com chave.
    'Media', 'média' e 'MÉDIA' precisam dar a mesma coisa."""
    import unicodedata
    decomposto = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in decomposto
                   if not unicodedata.combining(c)).lower().strip()


def chave_agregacao(rotulo):
    """Traduz o rotulo da combobox ("Media") para a chave que o servidor
    entende ("media"). Aceita a chave direto, para nao quebrar modelo salvo."""
    if not rotulo:
        return ""
    if rotulo in AGREGACOES:
        return rotulo
    alvo = _sem_acento(rotulo).strip()
    for chave, texto in AGREGACOES.items():
        if _sem_acento(texto) == alvo:
            return chave
    return ""


def chave_coluna(rotulo):
    """Mesma ideia para colunas: "Valor" volta para "valor"."""
    if not rotulo:
        return ""
    if rotulo in COLUNAS_FIXAS:
        return rotulo
    for chave, texto in COLUNAS_FIXAS.items():
        if texto == rotulo:
            return chave
    return rotulo


def montar_query(entidade, colunas, filtros=None, agrupar=None, agregar=None,
                 ordem=None, limite=2000, deslocamento=0, operacao=None):
    """Monta a querystring da consulta. `colunas`, `agregar`, `agrupar` e
    `operacao` aceitam chave do banco (valor) ou rotulo da tela (Valor).
    `operacao` so vai junto quando existe agregacao."""
    filtros = filtros or {}
    params = {"entidade": entidade, "limite": str(max(1, int(limite or 2000))),
              "offset": str(max(0, int(deslocamento or 0)))}
    if colunas:
        params["colunas"] = ",".join(colunas)
    for chave in ("de", "ate", "termo"):
        valor = filtros.get(chave)
        if valor:
            params[chave] = valor
    situacoes = filtros.get("situacoes")
    if situacoes:
        if isinstance(situacoes, str):
            situacoes = [s for s in situacoes.split(",") if s.strip()]
        params["situacoes"] = ",".join(str(s).strip() for s in situacoes)
    if agrupar:
        params["agrupar"] = chave_coluna(agrupar)
    if agregar:
        campos = [chave_coluna(c) for c in agregar]
        params["agregar"] = ",".join(campos)
        op = chave_agregacao(operacao)
        if op:
            params["operacao"] = op
    if ordem:
        params["ordem"] = chave_coluna(ordem)
    return urllib.parse.urlencode(params, safe=",")


def consultar(api_url, api_token, query, timeout=60):
    """Chama /api/financeiro/consulta e devolve o corpo JSON."""
    base = (api_url or "").rstrip("/")
    url = f"{base}/api/financeiro/consulta?{query}"
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {api_token}",
                      "Accept": "application/json",
                      "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def catalogo(api_url, api_token, timeout=30):
    """Lista entidades e colunas disponiveis (traz tambem colunas dinamicas
    vindas do JSON cru do servidor)."""
    base = (api_url or "").rstrip("/")
    request = urllib.request.Request(
        f"{base}/api/financeiro/campos",
        headers={"Authorization": f"Bearer {api_token}",
                 "Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def rotulo_coluna(chave):
    if chave in COLUNAS_FIXAS:
        return COLUNAS_FIXAS[chave]
    return chave.replace("_", " ").strip().capitalize() or chave


# --------------------------------------------------------------- agregacao
def agregar_local(linhas, chaves_grupo, chave_valor, operacao="soma",
                  rotulo_grupo="Descricao"):
    """Agrega em memoria. Serve para o preview quando o servidor ainda nao
    agrupou, e como referencia para conferir o resultado do servidor."""
    if not chaves_grupo:
        chaves_grupo = [rotulo_grupo]
    grupos = {}
    ordem = []
    for linha in linhas:
        chave = tuple(linha.get(c) for c in chaves_grupo)
        if chave not in grupos:
            grupos[chave] = {"_linhas": 0, "_soma": 0.0, "_min": None,
                             "_max": None, "_valores": []}
            ordem.append(chave)
        alvo = grupos[chave]
        alvo["_linhas"] += 1
        valor = linha.get(chave_valor)
        if eh_numero(valor):
            alvo["_soma"] += valor
            alvo["_valores"].append(valor)
            alvo["_min"] = valor if alvo["_min"] is None else min(alvo["_min"], valor)
            alvo["_max"] = valor if alvo["_max"] is None else max(alvo["_max"], valor)

    resultado = []
    for chave in ordem:
        alvo = grupos[chave]
        linha = {c: (chave[i] if i < len(chave) else None)
                 for i, c in enumerate(chaves_grupo)}
        if operacao == "contagem":
            linha["_agregado"] = alvo["_linhas"]
        elif operacao == "media":
            linha["_agregado"] = (alvo["_soma"] / len(alvo["_valores"])
                                  if alvo["_valores"] else 0.0)
        elif operacao == "minimo":
            linha["_agregado"] = alvo["_min"]
        elif operacao == "maximo":
            linha["_agregado"] = alvo["_max"]
        else:
            linha["_agregado"] = alvo["_soma"]
        linha["_quantidade"] = alvo["_linhas"]
        resultado.append(linha)
    return resultado


# ------------------------------------------------------------- apresentacao
def preparar_linhas(colunas, linhas, totais=None):
    """Converte a resposta do servidor em {titulo, colunas, linhas, totais} no
    formato que o relatorio_export.py consome."""
    saida_colunas = [rotulo_coluna(c) for c in colunas]
    corpo = []
    for linha in linhas:
        corpo.append([linha.get(c) for c in colunas])
    saida_totais = {}
    for chave, valor in (totais or {}).items():
        saida_totais[rotulo_coluna(chave)] = valor
    return {"colunas": saida_colunas, "linhas": corpo, "totais": saida_totais}


def somar_colunas(colunas, linhas):
    totais = {}
    for indice, chave in enumerate(colunas):
        valores = [l[indice] for l in linhas if eh_numero(l[indice])]
        if valores:
            totais[chave] = sum(valores)
    return totais


def subtitulo_padrao(filtros, quantidade):
    partes = []
    if filtros.get("de") or filtros.get("ate"):
        partes.append(f"Periodo: {filtros.get('de') or 'inicio'} a "
                      f"{filtros.get('ate') or 'hoje'}")
    if filtros.get("situacoes"):
        partes.append(f"Situacao: {filtros['situacoes']}")
    if filtros.get("termo"):
        partes.append(f"Busca: {filtros['termo']}")
    partes.append(f"{quantidade} registro(s)")
    return " | ".join(partes)


def aviso_limite(formato, quantidade):
    teto = LIMITES.get((formato or "csv").lower(), 20000)
    if quantidade < teto:
        return ""
    return (f"O relatorio tem {quantidade} linhas. Para PDF e recommendavel "
            f"filtrar mais (o limite de leitura e {teto}).")

# -*- coding: utf-8 -*-
"""
3_monitor_precos.py
Monitor de Preços de Fornecedores

Le produtos.csv, acessa a pagina de cada produto, extrai o preco via seletor CSS,
compara com o ultimo preco salvo em historico_precos.csv e sinaliza mudancas.

Autor: Gustavo Paiva
"""

import csv
import logging
import os
import re
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------
# CONFIGURACOES
# ----------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQ_PRODUTOS = os.path.join(BASE_DIR, "produtos.csv")
ARQ_HISTORICO = os.path.join(BASE_DIR, "historico_precos.csv")
ARQ_LOG = os.path.join(BASE_DIR, "monitor.log")

# Variacao percentual minima para considerar "mudanca relevante"
LIMITE_ALERTA_PCT = 3.0

# Pausa entre requisicoes (segundos) - respeito ao servidor do fornecedor
PAUSA_ENTRE_REQUESTS = 2

# Timeout de cada requisicao
TIMEOUT = 15

# Webhook do Teams (deixe vazio "" para nao enviar alerta)
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# ----------------------------------------------------------------------
# LOG
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.FileHandler(ARQ_LOG, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("monitor")


# ----------------------------------------------------------------------
# FUNCOES
# ----------------------------------------------------------------------
def ler_produtos(caminho):
    """Le o produtos.csv (separador ;) e devolve lista de dicionarios."""
    if not os.path.exists(caminho):
        log.error("Arquivo nao encontrado: %s", caminho)
        sys.exit(1)

    with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f, delimiter=";")
        produtos = [linha for linha in leitor if linha.get("url")]

    log.info("Produtos carregados: %d", len(produtos))
    return produtos


def limpar_preco(texto):
    """
    Converte texto de preco brasileiro em float.
    'R$ 1.234,56' -> 1234.56 | 'R$1234.56' -> 1234.56
    """
    if not texto:
        return None

    # Mantem apenas digitos, ponto e virgula
    limpo = re.sub(r"[^\d,.]", "", texto.strip())
    if not limpo:
        return None

    # Padrao BR: 1.234,56 -> remove ponto de milhar, virgula vira ponto
    if "," in limpo and "." in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")

    try:
        return round(float(limpo), 2)
    except ValueError:
        return None


def coletar_preco(url, seletor):
    """Acessa a URL e extrai o preco usando o seletor CSS informado."""
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding

    soup = BeautifulSoup(resp.text, "lxml")
    elemento = soup.select_one(seletor)

    if elemento is None:
        raise ValueError("Seletor CSS nao encontrou nenhum elemento: %s" % seletor)

    # Tenta atributo content antes do texto (comum em sites com schema.org)
    texto = elemento.get("content") or elemento.get_text(strip=True)
    preco = limpar_preco(texto)

    if preco is None:
        raise ValueError("Nao foi possivel converter o texto em preco: %r" % texto)

    return preco


def carregar_ultimos_precos(caminho):
    """Le o historico e devolve {codigo: ultimo_preco}."""
    ultimos = {}
    if not os.path.exists(caminho):
        return ultimos

    with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            try:
                ultimos[linha["codigo"]] = float(linha["preco"])
            except (KeyError, ValueError, TypeError):
                continue

    return ultimos


def gravar_historico(caminho, registros):
    """Grava (append) os registros coletados no historico."""
    novo = not os.path.exists(caminho)

    with open(caminho, "a", encoding="utf-8-sig", newline="") as f:
        campos = [
            "data",
            "codigo",
            "nome",
            "fornecedor",
            "preco",
            "preco_anterior",
            "variacao_pct",
            "status",
        ]
        escritor = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        if novo:
            escritor.writeheader()
        escritor.writerows(registros)


def enviar_alerta_teams(webhook, alertas):
    """Envia um cartao simples ao Teams com os produtos que mudaram de preco."""
    if not webhook or not alertas:
        return

    linhas = []
    for a in alertas:
        seta = "ALTA" if a["variacao_pct"] > 0 else "QUEDA"
        linhas.append(
            "- **%s** (%s): R$ %.2f -> R$ %.2f  (%s %.2f%%)"
            % (
                a["nome"],
                a["fornecedor"],
                a["preco_anterior"],
                a["preco"],
                seta,
                abs(a["variacao_pct"]),
            )
        )

    corpo = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": "Monitor de Precos - mudancas detectadas",
        "title": "Monitor de Precos - %d alteracao(oes)" % len(alertas),
        "text": "\n\n".join(linhas),
    }

    try:
        r = requests.post(webhook, json=corpo, timeout=TIMEOUT)
        r.raise_for_status()
        log.info("Alerta enviado ao Teams (%d itens).", len(alertas))
    except Exception as e:
        log.error("Falha ao enviar alerta ao Teams: %s", e)


# ----------------------------------------------------------------------
# EXECUCAO
# ----------------------------------------------------------------------
def main():
    log.info("=" * 60)
    log.info("Iniciando monitor de precos")

    produtos = ler_produtos(ARQ_PRODUTOS)
    ultimos = carregar_ultimos_precos(ARQ_HISTORICO)

    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    registros = []
    alertas = []
    erros = 0

    for i, p in enumerate(produtos, start=1):
        codigo = p.get("codigo", "").strip()
        nome = p.get("nome", "").strip()
        fornecedor = p.get("fornecedor", "").strip()
        url = p.get("url", "").strip()
        seletor = p.get("seletor_css", "").strip()

        log.info("[%d/%d] %s | %s", i, len(produtos), codigo, nome)

        try:
            preco = coletar_preco(url, seletor)
        except Exception as e:
            erros += 1
            log.error("   FALHA: %s", e)
            registros.append(
                {
                    "data": agora,
                    "codigo": codigo,
                    "nome": nome,
                    "fornecedor": fornecedor,
                    "preco": "",
                    "preco_anterior": "",
                    "variacao_pct": "",
                    "status": "ERRO",
                }
            )
            time.sleep(PAUSA_ENTRE_REQUESTS)
            continue

        anterior = ultimos.get(codigo)

        if anterior is None:
            status = "NOVO"
            variacao = 0.0
            log.info("   Preco inicial: R$ %.2f", preco)
        else:
            variacao = ((preco - anterior) / anterior * 100) if anterior else 0.0
            if abs(variacao) >= LIMITE_ALERTA_PCT:
                status = "ALERTA"
                log.warning(
                    "   MUDANCA: R$ %.2f -> R$ %.2f (%.2f%%)", anterior, preco, variacao
                )
                alertas.append(
                    {
                        "nome": nome,
                        "fornecedor": fornecedor,
                        "preco": preco,
                        "preco_anterior": anterior,
                        "variacao_pct": variacao,
                    }
                )
            else:
                status = "ESTAVEL"
                log.info("   Estavel: R$ %.2f (%.2f%%)", preco, variacao)

        registros.append(
            {
                "data": agora,
                "codigo": codigo,
                "nome": nome,
                "fornecedor": fornecedor,
                "preco": "%.2f" % preco,
                "preco_anterior": "%.2f" % anterior if anterior is not None else "",
                "variacao_pct": "%.2f" % variacao,
                "status": status,
            }
        )

        time.sleep(PAUSA_ENTRE_REQUESTS)

    gravar_historico(ARQ_HISTORICO, registros)
    enviar_alerta_teams(TEAMS_WEBHOOK_URL, alertas)

    log.info("-" * 60)
    log.info(
        "Fim. Coletados: %d | Alertas: %d | Erros: %d",
        len(registros) - erros,
        len(alertas),
        erros,
    )
    log.info("Historico: %s", ARQ_HISTORICO)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("Interrompido pelo usuario.")
    except Exception as e:
        log.exception("Erro fatal: %s", e)
        sys.exit(1)

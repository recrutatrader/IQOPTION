"""Indicadores técnicos em Python puro (sem dependências).

Todas as funções recebem listas de floats em ordem cronológica e devolvem
listas do mesmo tamanho, com None onde ainda não há dados suficientes.
"""
from __future__ import annotations

from typing import Optional

Serie = list[Optional[float]]


def sma(valores: list[float], periodo: int) -> Serie:
    saida: Serie = [None] * len(valores)
    soma = 0.0
    for i, v in enumerate(valores):
        soma += v
        if i >= periodo:
            soma -= valores[i - periodo]
        if i >= periodo - 1:
            saida[i] = soma / periodo
    return saida


def ema(valores: list[float], periodo: int) -> Serie:
    saida: Serie = [None] * len(valores)
    if len(valores) < periodo:
        return saida
    k = 2 / (periodo + 1)
    atual = sum(valores[:periodo]) / periodo
    saida[periodo - 1] = atual
    for i in range(periodo, len(valores)):
        atual = valores[i] * k + atual * (1 - k)
        saida[i] = atual
    return saida


def rsi(valores: list[float], periodo: int = 14) -> Serie:
    saida: Serie = [None] * len(valores)
    if len(valores) <= periodo:
        return saida
    ganhos = perdas = 0.0
    for i in range(1, periodo + 1):
        d = valores[i] - valores[i - 1]
        ganhos += max(d, 0)
        perdas += max(-d, 0)
    media_g, media_p = ganhos / periodo, perdas / periodo
    saida[periodo] = _rsi_de(media_g, media_p)
    for i in range(periodo + 1, len(valores)):
        d = valores[i] - valores[i - 1]
        media_g = (media_g * (periodo - 1) + max(d, 0)) / periodo
        media_p = (media_p * (periodo - 1) + max(-d, 0)) / periodo
        saida[i] = _rsi_de(media_g, media_p)
    return saida


def _rsi_de(media_g: float, media_p: float) -> float:
    if media_p == 0:
        return 100.0
    return 100 - 100 / (1 + media_g / media_p)


def macd(valores: list[float], rapida: int = 12, lenta: int = 26, sinal: int = 9):
    """Devolve (linha_macd, linha_sinal, histograma)."""
    er, el = ema(valores, rapida), ema(valores, lenta)
    linha: Serie = [a - b if a is not None and b is not None else None for a, b in zip(er, el)]
    validos = [v for v in linha if v is not None]
    sinal_validos = ema(validos, sinal)
    linha_sinal: Serie = [None] * (len(linha) - len(validos)) + sinal_validos
    hist: Serie = [a - b if a is not None and b is not None else None for a, b in zip(linha, linha_sinal)]
    return linha, linha_sinal, hist


def bollinger(valores: list[float], periodo: int = 20, desvios: float = 2.0):
    """Devolve (superior, media, inferior)."""
    media = sma(valores, periodo)
    sup: Serie = [None] * len(valores)
    inf: Serie = [None] * len(valores)
    for i in range(periodo - 1, len(valores)):
        janela = valores[i - periodo + 1 : i + 1]
        m = media[i]
        dp = (sum((x - m) ** 2 for x in janela) / periodo) ** 0.5
        sup[i], inf[i] = m + desvios * dp, m - desvios * dp
    return sup, media, inf


def suportes_resistencias(maximas: list[float], minimas: list[float], janela: int = 3):
    """Topos e fundos locais (fractais) usados como resistências e suportes."""
    resist, suport = [], []
    for i in range(janela, len(maximas) - janela):
        if maximas[i] == max(maximas[i - janela : i + janela + 1]):
            resist.append(maximas[i])
        if minimas[i] == min(minimas[i - janela : i + janela + 1]):
            suport.append(minimas[i])
    return sorted(set(suport)), sorted(set(resist))

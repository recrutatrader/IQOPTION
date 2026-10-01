"""Análise técnica das velas: combina indicadores num placar de compra (CALL) / venda (PUT)."""
from __future__ import annotations

from . import indicadores as ind


def _padrao_ultimas_velas(velas: list[dict]) -> tuple[int, str | None]:
    """Detecta engolfo e martelo / estrela cadente na última vela fechada."""
    if len(velas) < 2:
        return 0, None
    a, b = velas[-2], velas[-1]
    corpo_b = abs(b["close"] - b["open"])
    faixa_b = (b["max"] - b["min"]) or 1e-12
    if a["close"] < a["open"] and b["close"] > b["open"] and b["close"] >= a["open"] and b["open"] <= a["close"]:
        return 1, "engolfo de alta"
    if a["close"] > a["open"] and b["close"] < b["open"] and b["close"] <= a["open"] and b["open"] >= a["close"]:
        return -1, "engolfo de baixa"
    pavio_inf = min(b["open"], b["close"]) - b["min"]
    pavio_sup = b["max"] - max(b["open"], b["close"])
    if corpo_b / faixa_b < 0.35 and pavio_inf > 2 * corpo_b and pavio_sup < corpo_b:
        return 1, "martelo"
    if corpo_b / faixa_b < 0.35 and pavio_sup > 2 * corpo_b and pavio_inf < corpo_b:
        return -1, "estrela cadente"
    return 0, None


def analisar(velas: list[dict]) -> dict:
    """Recebe velas ({open, close, min, max, from}) em ordem cronológica."""
    if len(velas) < 35:
        raise ValueError(f"São necessárias pelo menos 35 velas (recebidas {len(velas)}).")

    fech = [v["close"] for v in velas]
    maximas = [v["max"] for v in velas]
    minimas = [v["min"] for v in velas]
    preco = fech[-1]

    ema9, ema21 = ind.ema(fech, 9)[-1], ind.ema(fech, 21)[-1]
    rsi14 = ind.rsi(fech, 14)[-1]
    _, _, hist = ind.macd(fech)
    sup_bb, med_bb, inf_bb = (s[-1] for s in ind.bollinger(fech))
    suportes, resistencias = ind.suportes_resistencias(maximas, minimas)

    placar = 0
    motivos: list[str] = []

    if ema9 > ema21:
        placar += 1
        motivos.append("EMA9 acima da EMA21 (tendência de alta)")
    else:
        placar -= 1
        motivos.append("EMA9 abaixo da EMA21 (tendência de baixa)")

    if rsi14 < 30:
        placar += 2
        motivos.append(f"RSI {rsi14:.1f} sobrevendido")
    elif rsi14 > 70:
        placar -= 2
        motivos.append(f"RSI {rsi14:.1f} sobrecomprado")
    else:
        motivos.append(f"RSI {rsi14:.1f} neutro")

    if hist[-1] is not None and hist[-2] is not None:
        if hist[-1] > 0 and hist[-1] > hist[-2]:
            placar += 1
            motivos.append("MACD positivo e ganhando força")
        elif hist[-1] < 0 and hist[-1] < hist[-2]:
            placar -= 1
            motivos.append("MACD negativo e ganhando força")

    if preco <= inf_bb:
        placar += 1
        motivos.append("preço na banda inferior de Bollinger")
    elif preco >= sup_bb:
        placar -= 1
        motivos.append("preço na banda superior de Bollinger")

    pontos, padrao = _padrao_ultimas_velas(velas)
    if padrao:
        placar += pontos
        motivos.append(f"padrão de vela: {padrao}")

    suporte = max((s for s in suportes if s <= preco), default=None)
    resistencia = min((r for r in resistencias if r >= preco), default=None)

    if placar >= 3:
        sinal = "CALL"
    elif placar <= -3:
        sinal = "PUT"
    else:
        sinal = "NEUTRO"

    return {
        "preco": preco,
        "sinal": sinal,
        "placar": placar,
        "motivos": motivos,
        "ema9": ema9,
        "ema21": ema21,
        "rsi14": rsi14,
        "macd_hist": hist[-1],
        "bollinger": {"superior": sup_bb, "media": med_bb, "inferior": inf_bb},
        "suporte_proximo": suporte,
        "resistencia_proxima": resistencia,
    }

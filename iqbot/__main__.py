"""Linha de comando.

Exemplos:
  python -m iqbot login
  python -m iqbot saldo
  python -m iqbot capturar
  python -m iqbot analisar --ativo EURUSD-OTC --tempo 60
  python -m iqbot operar --ativo EURUSD-OTC --direcao call --valor 2 --minutos 1
  python -m iqbot robo --ativo EURUSD-OTC --valor 2
  python -m iqbot backtest --ativo EURUSD-OTC --tempo 60 --quantidade 1000
"""
from __future__ import annotations

import argparse
import json
import time

from . import config
from .analise import analisar, backtest
from .navegador import ATIVOS, IQNavegador, json_bonito

LOG_OPERACOES = config.PASTA_ESTADO / "operacoes.jsonl"


class Bloqueio(Exception):
    """Uma trava de segurança impediu a operação."""


def _ativo_id(args) -> int:
    if args.ativo_id:
        return args.ativo_id
    nome = args.ativo.upper()
    if nome not in ATIVOS:
        raise SystemExit(f"Ativo '{nome}' desconhecido. Use --ativo-id ou um destes: {', '.join(ATIVOS)}")
    return ATIVOS[nome]


def _operacoes_hoje() -> int:
    if not LOG_OPERACOES.exists():
        return 0
    hoje = time.strftime("%Y-%m-%d")
    return sum(1 for l in LOG_OPERACOES.read_text().splitlines() if json.loads(l).get("data") == hoje)


def _registrar(dados: dict) -> None:
    config.PASTA_ESTADO.mkdir(exist_ok=True)
    with LOG_OPERACOES.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"data": time.strftime("%Y-%m-%d"), "hora": time.strftime("%H:%M:%S"), **dados}, default=str) + "\n")


def _imprimir_analise(nome: str, tempo: int, r: dict) -> None:
    print(f"{nome} | vela {tempo}s | preço {r['preco']} | SINAL {r['sinal']} (placar {r['placar']:+d})")
    for m in r["motivos"]:
        print(f"  - {m}")
    print(f"  Suporte: {r['suporte_proximo']} | Resistência: {r['resistencia_proxima']}")


def _operar(nav: IQNavegador, cfg: config.Config, nome: str, ativo: int, direcao: str,
            valor: float, minutos: int, confirmar_real: bool) -> dict | None:
    if cfg.modo == "real" and not confirmar_real:
        raise Bloqueio("Modo REAL exige --confirmar-real. Nada foi enviado.")
    if valor > cfg.max_stake:
        raise Bloqueio(f"Valor {valor} acima do limite IQ_MAX_STAKE={cfg.max_stake}.")
    if _operacoes_hoje() >= cfg.max_trades:
        raise Bloqueio(f"Limite diário de {cfg.max_trades} operações atingido (IQ_MAX_TRADES).")

    r = nav.abrir_operacao(ativo, direcao, valor, minutos)
    resposta = r["resposta"] or {}
    id_op = resposta.get("id")
    expira = time.strftime("%H:%M:%S", time.localtime(r["expira"]))
    print(f"[{cfg.modo.upper()}] {direcao.upper()} {nome} valor {valor} expira {expira}")
    if not id_op:
        _registrar({"modo": cfg.modo, "ativo": nome, "direcao": direcao, "valor": valor, "erro": resposta})
        print(f"Operação recusada: {json_bonito(resposta)}")
        return None
    print(f"Operação aberta, id {id_op}. Aguardando resultado...")
    res = nav.aguardar_resultado(id_op, r["expira"])
    print(json_bonito(res) if res else "Resultado não recebido; confira no histórico da plataforma.")
    _registrar({"modo": cfg.modo, "ativo": nome, "direcao": direcao, "valor": valor, "id": id_op, "resultado": res})
    return res


def _robo(nav: IQNavegador, cfg: config.Config, args, ativo: int) -> None:
    """Analisa sem parar e opera quando o tempo maior (tendência) e o menor (entrada) concordam."""
    print(f"Robô ligado em {args.ativo} | conta {cfg.modo.upper()} | valor {args.valor} | Ctrl+C para parar")
    ultima_vela = None
    while True:
        try:
            tendencia = analisar(nav.velas(ativo, args.tempo_tendencia, 120))
            velas_entrada = nav.velas(ativo, args.tempo, 120)
            # Usa só velas fechadas e analisa uma vez por vela nova.
            fechadas = velas_entrada[:-1]
            if fechadas[-1]["from"] == ultima_vela:
                time.sleep(2)
                continue
            ultima_vela = fechadas[-1]["from"]
            entrada = analisar(fechadas)
        except TimeoutError as e:
            print(f"Aviso: {e}. Tentando de novo...")
            time.sleep(5)
            continue

        print("\n" + time.strftime("%H:%M:%S"))
        _imprimir_analise(f"{args.ativo} tendência", args.tempo_tendencia, tendencia)
        _imprimir_analise(f"{args.ativo} entrada", args.tempo, entrada)

        sinal = entrada["sinal"]
        mesma_direcao = (sinal == "CALL" and tendencia["placar"] > 0) or (sinal == "PUT" and tendencia["placar"] < 0)
        if sinal == "NEUTRO" or not mesma_direcao:
            print("=> Sem entrada: sinais não confirmam.")
            continue

        print(f"=> ENTRADA {sinal}")
        try:
            _operar(nav, cfg, args.ativo, ativo, sinal.lower(), args.valor, args.minutos, args.confirmar_real)
        except Bloqueio as e:
            print(f"Robô parado: {e}")
            return
        print(f"Print do gráfico: {nav.capturar(args.ativo)}")


def main() -> None:
    p = argparse.ArgumentParser(prog="iqbot", description="Análise gráfica e operações na IQ Option pelo navegador.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="faz login e salva a sessão")
    sub.add_parser("saldo", help="mostra os saldos demo e real")
    sub.add_parser("capturar", help="abre a sala de operações e salva um print do gráfico")

    for nome, ajuda in (("analisar", "análise técnica de um ativo"),
                        ("operar", "abre uma operação"),
                        ("robo", "analisa e opera automaticamente"),
                        ("backtest", "testa a estratégia no histórico")):
        s = sub.add_parser(nome, help=ajuda)
        s.add_argument("--ativo", default="EURUSD-OTC")
        s.add_argument("--ativo-id", type=int)
        if nome in ("analisar", "robo", "backtest"):
            s.add_argument("--tempo", type=int, default=60, help="tamanho da vela em segundos (60, 300, 900...)")
        if nome == "analisar":
            s.add_argument("--quantidade", type=int, default=120)
            s.add_argument("--json", action="store_true")
            continue
        if nome == "backtest":
            s.add_argument("--quantidade", type=int, default=1000)
            s.add_argument("--expiracao-velas", type=int, default=1)
            continue
        if nome == "operar":
            s.add_argument("--direcao", choices=["call", "put"], required=True)
        else:
            s.add_argument("--tempo-tendencia", type=int, default=300)
        s.add_argument("--valor", type=float, required=(nome == "operar"), default=None)
        s.add_argument("--minutos", type=int, default=1)
        s.add_argument("--confirmar-real", action="store_true", help="obrigatório para operar na conta REAL")

    args = p.parse_args()
    cfg = config.carregar()
    if args.cmd == "robo" and args.valor is None:
        args.valor = min(2.0, cfg.max_stake)

    with IQNavegador(cfg) as nav:
        nav.login()
        if args.cmd == "login":
            print("Login OK. Sessão salva em estado/sessao.json")
            return

        if args.cmd in ("capturar", "robo"):
            nav.abrir_sala()
        if args.cmd == "capturar":
            print(nav.capturar())
            return

        nav.conectar_ws()

        if args.cmd == "saldo":
            for s in nav.saldos():
                tipo = {1: "REAL", 4: "DEMO"}.get(s.get("type"), s.get("type"))
                print(f"{tipo}: {s.get('amount')} {s.get('currency')} (id {s.get('id')})")
            return

        ativo = _ativo_id(args)

        if args.cmd == "analisar":
            r = analisar(nav.velas(ativo, args.tempo, args.quantidade))
            if args.json:
                print(json_bonito(r))
            else:
                _imprimir_analise(f"{args.ativo} ({ativo})", args.tempo, r)
            return

        if args.cmd == "backtest":
            print(f"Baixando {args.quantidade} velas de {args.ativo}...")
            print(json_bonito(backtest(nav.velas(ativo, args.tempo, args.quantidade), args.expiracao_velas)))
            return

        if args.cmd == "robo":
            try:
                _robo(nav, cfg, args, ativo)
            except KeyboardInterrupt:
                print("\nRobô parado pelo usuário.")
            return

        try:
            _operar(nav, cfg, args.ativo, ativo, args.direcao, args.valor, args.minutos, args.confirmar_real)
        except Bloqueio as e:
            raise SystemExit(str(e))


if __name__ == "__main__":
    main()

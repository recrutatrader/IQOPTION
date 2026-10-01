"""Linha de comando.

Exemplos:
  python -m iqbot login
  python -m iqbot saldo
  python -m iqbot capturar
  python -m iqbot analisar --ativo EURUSD-OTC --tempo 60
  python -m iqbot operar --ativo EURUSD-OTC --direcao call --valor 2 --minutos 1
"""
from __future__ import annotations

import argparse
import json
import time

from . import config
from .analise import analisar
from .navegador import ATIVOS, IQNavegador, json_bonito

LOG_OPERACOES = config.PASTA_ESTADO / "operacoes.jsonl"


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


def main() -> None:
    p = argparse.ArgumentParser(prog="iqbot", description="Análise gráfica e operações na IQ Option pelo navegador.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="faz login e salva a sessão")
    sub.add_parser("saldo", help="mostra os saldos demo e real")
    sub.add_parser("capturar", help="abre a sala de operações e salva um print do gráfico")

    for nome in ("analisar", "operar"):
        s = sub.add_parser(nome)
        s.add_argument("--ativo", default="EURUSD-OTC")
        s.add_argument("--ativo-id", type=int)
        if nome == "analisar":
            s.add_argument("--tempo", type=int, default=60, help="tamanho da vela em segundos (60, 300, 900...)")
            s.add_argument("--quantidade", type=int, default=120)
            s.add_argument("--json", action="store_true")
        else:
            s.add_argument("--direcao", choices=["call", "put"], required=True)
            s.add_argument("--valor", type=float, required=True)
            s.add_argument("--minutos", type=int, default=1)
            s.add_argument("--confirmar-real", action="store_true", help="obrigatório para operar na conta REAL")

    args = p.parse_args()
    cfg = config.carregar()

    with IQNavegador(cfg) as nav:
        nav.login()
        if args.cmd == "login":
            print("Login OK. Sessão salva em estado/sessao.json")
            return

        if args.cmd == "capturar":
            nav.abrir_sala()
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
                return
            print(f"Ativo {args.ativo} ({ativo}) | vela {args.tempo}s | preço {r['preco']}")
            print(f"SINAL: {r['sinal']} (placar {r['placar']:+d})")
            for m in r["motivos"]:
                print(f"  - {m}")
            print(f"Suporte próximo: {r['suporte_proximo']} | Resistência próxima: {r['resistencia_proxima']}")
            return

        # operar
        if cfg.modo == "real" and not args.confirmar_real:
            raise SystemExit("Modo REAL exige --confirmar-real. Nada foi enviado.")
        if args.valor > cfg.max_stake:
            raise SystemExit(f"Valor {args.valor} acima do limite IQ_MAX_STAKE={cfg.max_stake}.")
        if _operacoes_hoje() >= cfg.max_trades:
            raise SystemExit(f"Limite diário de {cfg.max_trades} operações atingido (IQ_MAX_TRADES).")

        r = nav.abrir_operacao(ativo, args.direcao, args.valor, args.minutos)
        resposta = r["resposta"] or {}
        id_op = resposta.get("id")
        print(f"[{cfg.modo.upper()}] {args.direcao.upper()} {args.ativo} valor {args.valor} expira {time.strftime('%H:%M:%S', time.localtime(r['expira']))}")
        if not id_op:
            _registrar({"modo": cfg.modo, "ativo": args.ativo, "direcao": args.direcao, "valor": args.valor, "erro": resposta})
            raise SystemExit(f"Operação recusada: {json_bonito(resposta)}")
        print(f"Operação aberta, id {id_op}. Aguardando resultado...")
        res = nav.aguardar_resultado(id_op, r["expira"])
        print(json_bonito(res) if res else "Resultado não recebido; confira no histórico da plataforma.")
        _registrar({"modo": cfg.modo, "ativo": args.ativo, "direcao": args.direcao, "valor": args.valor, "id": id_op, "resultado": res})


if __name__ == "__main__":
    main()

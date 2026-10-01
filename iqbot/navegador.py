"""Controle do navegador (Chromium via Playwright) logado na IQ Option.

O navegador faz o login, abre a sala de operações (para capturas de tela do
gráfico) e, de dentro da própria página, conversa com o WebSocket da
corretora para buscar velas, saldos e abrir operações.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from .config import PASTA_CAPTURAS, PASTA_ESTADO, Config

URL_LOGIN_API = "https://auth.iqoption.com/api/v2/login"
URL_SALA = "https://iqoption.com/traderoom"
URL_WS = "wss://ws.iqoption.com/echo/websocket"
ARQUIVO_SESSAO = PASTA_ESTADO / "sessao.json"

# IDs de ativos conhecidos. Confira na plataforma; use --ativo-id para outros.
ATIVOS = {
    "EURUSD": 1, "EURGBP": 2, "GBPJPY": 3, "EURJPY": 4, "GBPUSD": 5, "USDJPY": 6,
    "AUDCAD": 7, "NZDUSD": 8,
    "EURUSD-OTC": 76, "EURGBP-OTC": 77, "USDCHF-OTC": 78, "EURJPY-OTC": 79,
    "NZDUSD-OTC": 80, "GBPUSD-OTC": 81, "GBPJPY-OTC": 84, "USDJPY-OTC": 85, "AUDCAD-OTC": 86,
}

TIPO_SALDO = {"real": 1, "demo": 4}

# Cliente WebSocket que roda dentro da página. Guarda as respostas em
# window.__iq.msgs para o Python ler.
_JS_CLIENTE = """
async (args) => {
  if (window.__iq && window.__iq.ws.readyState === 1) return true;
  const ws = new WebSocket(args.url);
  window.__iq = { ws, msgs: [], seq: 0 };
  ws.onmessage = (e) => {
    try {
      const m = JSON.parse(e.data);
      if (m.name !== 'heartbeat' && m.name !== 'timeSync') window.__iq.msgs.push(m);
      if (m.name === 'heartbeat') ws.send(JSON.stringify({name: 'heartbeat', msg: {userTime: Date.now(), heartbeatTime: m.msg}}));
    } catch (_) {}
  };
  await new Promise((ok, erro) => { ws.onopen = ok; ws.onerror = () => erro(new Error('falha ao abrir WebSocket')); });
  ws.send(JSON.stringify({name: 'authenticate', request_id: 'auth',
    msg: {ssid: args.ssid, protocol: 3, session_id: '', client_session_id: ''}}));
  return true;
}
"""


class IQNavegador:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self.contexto: BrowserContext | None = None
        self.pagina: Page | None = None
        self.ssid: str | None = None

    # ---------- ciclo de vida ----------
    def __enter__(self) -> "IQNavegador":
        PASTA_ESTADO.mkdir(exist_ok=True)
        self._pw = sync_playwright().start()
        executavel = os.environ.get("IQ_CHROMIUM") or (
            "/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None
        )
        self._browser = self._pw.chromium.launch(headless=self.cfg.headless, executable_path=executavel)
        estado = str(ARQUIVO_SESSAO) if ARQUIVO_SESSAO.exists() else None
        self.contexto = self._browser.new_context(
            storage_state=estado, viewport={"width": 1600, "height": 900}, locale="pt-BR"
        )
        self.pagina = self.contexto.new_page()
        return self

    def __exit__(self, *_):
        if self.contexto:
            self.contexto.storage_state(path=str(ARQUIVO_SESSAO))
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    # ---------- login ----------
    def _ssid_do_cookie(self) -> str | None:
        for c in self.contexto.cookies():
            if c["name"] == "ssid":
                return c["value"]
        return None

    def login(self) -> str:
        self.ssid = self._ssid_do_cookie()
        if self.ssid:
            return self.ssid
        if not self.cfg.email or not self.cfg.senha:
            raise SystemExit("Defina IQ_EMAIL e IQ_PASSWORD (no .env ou nos segredos do ambiente).")
        resp = self.contexto.request.post(
            URL_LOGIN_API, data={"identifier": self.cfg.email, "password": self.cfg.senha}
        )
        corpo = resp.json() if resp.ok else {}
        if corpo.get("code") == "verify":
            raise SystemExit("A conta pede verificação em 2 etapas. Desative-a ou faça login manual uma vez.")
        self.ssid = corpo.get("ssid") or self._ssid_do_cookie()
        if not self.ssid:
            raise SystemExit(f"Falha no login (HTTP {resp.status}): {resp.text()[:300]}")
        self.contexto.add_cookies([{"name": "ssid", "value": self.ssid, "domain": ".iqoption.com", "path": "/"}])
        self.contexto.storage_state(path=str(ARQUIVO_SESSAO))
        return self.ssid

    # ---------- sala de operações / capturas ----------
    def abrir_sala(self) -> None:
        self.pagina.goto(URL_SALA, wait_until="domcontentloaded", timeout=60_000)
        self.pagina.wait_for_timeout(8_000)  # o gráfico é desenhado em canvas e demora a carregar

    def capturar(self, nome: str = "grafico") -> Path:
        PASTA_CAPTURAS.mkdir(exist_ok=True)
        caminho = PASTA_CAPTURAS / f"{nome}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        self.pagina.screenshot(path=str(caminho))
        return caminho

    # ---------- WebSocket dentro da página ----------
    def conectar_ws(self) -> None:
        if self.pagina.url == "about:blank":
            self.pagina.goto("https://iqoption.com/", wait_until="domcontentloaded", timeout=60_000)
        self.pagina.evaluate(_JS_CLIENTE, {"url": URL_WS, "ssid": self.ssid})
        self._esperar(lambda m: m.get("name") == "authenticated", 15, "autenticação")

    def _enviar(self, nome: str, versao: str, corpo: dict) -> str:
        req_id = f"r{time.time_ns()}"
        msg = {"name": "sendMessage", "request_id": req_id, "msg": {"name": nome, "version": versao, "body": corpo}}
        self.pagina.evaluate("(m) => window.__iq.ws.send(JSON.stringify(m))", msg)
        return req_id

    def _esperar(self, filtro, timeout: float, oque: str) -> dict:
        limite = time.time() + timeout
        while time.time() < limite:
            msgs = self.pagina.evaluate("() => window.__iq.msgs.splice(0)")
            for m in msgs:
                if m.get("name") == "authenticated" and m.get("msg") is False:
                    raise SystemExit("ssid recusado. Apague estado/sessao.json e faça login de novo.")
                if filtro(m):
                    return m
            time.sleep(0.2)
        raise TimeoutError(f"Sem resposta da corretora para: {oque}")

    def velas(self, ativo_id: int, tamanho: int = 60, quantidade: int = 100) -> list[dict]:
        req = self._enviar("get-candles", "2.0", {
            "active_id": ativo_id, "size": tamanho, "to": int(time.time()), "count": quantidade, "": 1,
        })
        resp = self._esperar(lambda m: m.get("request_id") == req, 20, "velas")
        return sorted(resp["msg"]["candles"], key=lambda v: v["from"])

    def saldos(self) -> list[dict]:
        req = self._enviar("internal-billing.get-balances", "1.0", {"types_ids": [1, 4], "tournaments_statuses_ids": [3, 2]})
        return self._esperar(lambda m: m.get("request_id") == req, 15, "saldos")["msg"]

    def saldo_do_modo(self) -> dict:
        tipo = TIPO_SALDO[self.cfg.modo]
        for s in self.saldos():
            if s.get("type") == tipo:
                return s
        raise SystemExit(f"Saldo do modo '{self.cfg.modo}' não encontrado.")

    def abrir_operacao(self, ativo_id: int, direcao: str, valor: float, minutos: int) -> dict:
        """Abre uma opção turbo/binária. direcao = 'call' (sobe) ou 'put' (desce)."""
        saldo = self.saldo_do_modo()
        agora = int(time.time())
        # A expiração é sempre na virada do minuto; com menos de 30 s, pula para o próximo.
        base = (agora // 60 + 1) * 60
        if base - agora < 30:
            base += 60
        expira = base + (minutos - 1) * 60
        tipo_opcao = 3 if minutos <= 5 else 1  # 3 = turbo, 1 = binária
        req = self._enviar("binary-options.open-option", "1.0", {
            "user_balance_id": saldo["id"], "active_id": ativo_id, "option_type_id": tipo_opcao,
            "direction": direcao, "expired": expira, "refund_value": 0, "price": valor,
            "value": 0, "profit_percent": 0,
        })
        resp = self._esperar(lambda m: m.get("request_id") == req, 15, "abrir operação")
        return {"resposta": resp.get("msg"), "expira": expira, "saldo": saldo}

    def aguardar_resultado(self, id_operacao, expira: int) -> dict | None:
        try:
            m = self._esperar(
                lambda m: m.get("name") in ("option-closed", "option") and
                str((m.get("msg") or {}).get("option_id", (m.get("msg") or {}).get("id"))) == str(id_operacao)
                and (m.get("msg") or {}).get("result") is not None,
                max(expira - time.time(), 0) + 30, "resultado",
            )
            return m["msg"]
        except TimeoutError:
            return None


def json_bonito(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)

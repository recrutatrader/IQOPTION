import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_ESTADO = RAIZ / "estado"
PASTA_CAPTURAS = RAIZ / "capturas"


def _carregar_env() -> None:
    """Lê o arquivo .env (se existir) sem sobrescrever variáveis já definidas."""
    arquivo = RAIZ / ".env"
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip())


@dataclass(frozen=True)
class Config:
    email: str
    senha: str
    modo: str  # "demo" ou "real"
    max_stake: float
    max_trades: int
    headless: bool


def carregar() -> Config:
    _carregar_env()
    modo = os.environ.get("IQ_MODE", "demo").lower()
    if modo not in ("demo", "real"):
        raise SystemExit("IQ_MODE deve ser 'demo' ou 'real'.")
    return Config(
        email=os.environ.get("IQ_EMAIL", ""),
        senha=os.environ.get("IQ_PASSWORD", ""),
        modo=modo,
        max_stake=float(os.environ.get("IQ_MAX_STAKE", "5")),
        max_trades=int(os.environ.get("IQ_MAX_TRADES", "10")),
        headless=os.environ.get("IQ_HEADLESS", "true").lower() != "false",
    )

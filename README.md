# IQOPTION: análise gráfica e operações pelo navegador

Robô em Python que usa o **Chromium (Playwright)** logado na IQ Option para:

- buscar velas de qualquer ativo e calcular indicadores (EMA, RSI, MACD, Bollinger, suportes e resistências, padrões de vela);
- tirar print do gráfico da sala de operações para análise visual;
- abrir operações (CALL/PUT), por padrão **somente na conta DEMO**.

Inclui o agente do Claude Code **`analista-graficos`** (`.claude/agents/analista-graficos.md`), especialista em leitura de gráfico que usa essas ferramentas.

## Instalação

```bash
pip install -r requirements.txt
python -m playwright install chromium   # dispensável na nuvem do Claude Code
cp .env.example .env                     # preencha e-mail e senha
```

Na nuvem do Claude Code, prefira cadastrar `IQ_EMAIL` e `IQ_PASSWORD` como variáveis/segredos do ambiente em vez de criar o `.env`.

## Uso

```bash
python -m iqbot login
python -m iqbot saldo
python -m iqbot analisar --ativo EURUSD-OTC --tempo 60
python -m iqbot capturar
python -m iqbot operar --ativo EURUSD-OTC --direcao call --valor 2 --minutos 1
```

No Claude Code: *"use o agente analista-graficos para analisar EURUSD-OTC e operar na demo se houver sinal"*.

## Travas de segurança

| Variável | Padrão | Função |
|---|---|---|
| `IQ_MODE` | `demo` | `real` usa dinheiro de verdade e ainda exige `--confirmar-real` |
| `IQ_MAX_STAKE` | `5` | valor máximo por operação |
| `IQ_MAX_TRADES` | `10` | máximo de operações por dia |

Todas as operações ficam registradas em `estado/operacoes.jsonl`.

## Avisos

- A IQ Option não tem API oficial. O protocolo usado (WebSocket da própria plataforma) pode mudar sem aviso, e automatizar operações pode violar os termos de uso.
- Os IDs de ativos em `iqbot/navegador.py` devem ser conferidos. Use `--ativo-id` para outros ativos.
- Contas com verificação em 2 etapas precisam de um login manual antes.
- Opções binárias têm alto risco. Teste sempre na conta demo.

## Testes

```bash
python -m unittest discover -s tests
```

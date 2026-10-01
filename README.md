# IQOPTION: análise gráfica e operações pelo navegador

Robô em Python que usa o **Chromium (Playwright)** logado na IQ Option para:

- buscar velas de qualquer ativo e calcular indicadores (EMA, RSI, MACD, Bollinger, suportes e resistências, padrões de vela);
- tirar print do gráfico da sala de operações para análise visual;
- abrir operações (CALL/PUT), por padrão **somente na conta DEMO**.

Inclui o agente do Claude Code **`analista-graficos`** (`.claude/agents/analista-graficos.md`), especialista em leitura de gráfico que usa essas ferramentas.

## Instalação no Windows (2 cliques)

1. No GitHub, abra o branch do projeto, clique em **Code > Download ZIP** e extraia a pasta.
2. Dê dois cliques em **`INSTALAR.bat`**. Ele instala o Python (se faltar), as dependências e o navegador, e abre o `.env`: coloque seu e-mail e senha da IQ Option, salve e feche.
3. Dê dois cliques em **`INICIAR.bat`**. O navegador abre na sua tela e o robô começa a analisar e operar na conta **DEMO**.

## Instalação manual

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
python -m iqbot robo --ativo EURUSD-OTC          # automático
python -m iqbot backtest --ativo EURUSD-OTC --tempo 60 --quantidade 1000
```

## Como a estratégia é "treinada"

O robô não é uma IA que aprende sozinha: ele segue regras de análise técnica (veja `iqbot/analise.py`).
O ajuste é feito com dados:

1. **Backtest:** `python -m iqbot backtest` aplica as regras nas últimas velas do ativo e mostra a taxa de acerto, no geral e por força do sinal. Com payout de 80%, é preciso acertar mais de **55,6%** para ter lucro.
2. **Ajuste:** se a taxa estiver baixa, mude os pesos e limites em `iqbot/analise.py` (por exemplo, exigir placar 4 em vez de 3), troque o ativo ou o tempo gráfico, e rode o backtest de novo.
3. **Validação:** deixe o robô operando na DEMO e compare `estado/operacoes.jsonl` com o backtest antes de pensar em conta real.

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

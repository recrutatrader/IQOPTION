# Agente analista de gráficos: IQ Option ao vivo

O agente é o **Claude** rodando no seu computador e controlando o **seu Chrome ao vivo**
(Claude Code + extensão Claude in Chrome). Ele abre a IQ Option na janela que você está vendo,
lê o gráfico como um trader (tendência, suportes/resistências, padrões de vela), conversa com
você e faz as operações clicando na própria plataforma.

Não há robô nem script: todo o comportamento do agente está em [`CLAUDE.md`](CLAUDE.md).

## O que precisa

- Notebook ou PC com **Windows** ou **Mac**, com o **Google Chrome**.
- Plano do Claude (Pro ou superior).
- Conta na IQ Option (o login é você quem faz, no Chrome).

## Instalação (Windows)

1. No GitHub, clique em **Code > Download ZIP** e extraia a pasta.
2. Dê dois cliques em **`INSTALAR.bat`**. Ele instala o Claude Code e abre a página da extensão
   **Claude in Chrome**: clique em **Usar no Chrome** e entre com a sua conta do Claude.
3. Dê dois cliques em **`AGENTE.bat`**. Na primeira vez, o Claude pede para entrar na conta
   (`/login`) e mostra um aviso sobre o Chrome: aperte Enter.
4. Quando o Chrome perguntar "Claude in Chrome wants to...", escolha permitir as ações em
   **iqoption.com** durante a sessão.

No Mac, instale com `curl -fsSL https://claude.ai/install.sh | bash`, instale a extensão e rode
`claude --chrome` dentro desta pasta.

## Como usar

Fale com o agente na janela do Claude, por exemplo:

- "Analisa o EUR/USD OTC no gráfico de 1 minuto."
- "Opera na demo com R$ 2, expiração de 1 minuto, quando tiver entrada boa."
- "Fica acompanhando e me avisa a cada entrada."
- "Como estão os resultados de hoje?"

O agente opera na **conta de treinamento** e só usa a conta real se você escrever "conta real".
As regras completas (limites de valor, stop depois de 3 perdas, sem martingale) estão no `CLAUDE.md`.
Para mudar o jeito do agente analisar ou operar, edite esse arquivo.

Cada operação fica registrada em `historico/operacoes.csv`, no seu computador.

## Avisos

- Opções binárias têm alto risco. Leitura de gráfico não garante resultado. Teste na conta demo.
- Automatizar operações pode violar os termos de uso da IQ Option.
- A extensão pode pedir sua confirmação em algumas ações. Se a conexão cair, digite `/chrome`
  no Claude e escolha **Reconnect extension**.

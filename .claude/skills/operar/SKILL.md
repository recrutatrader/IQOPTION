---
name: operar
description: Abre a IQ Option no Chrome do usuário e começa a analisar o gráfico ao vivo e operar até uma regra de parada ou até o usuário mandar parar.
disable-model-invocation: true
argument-hint: "[ativo] [valor] [expiração em minutos]  ex.: EUR/USD OTC 2 1"
allowed-tools: mcp__claude-in-chrome Read Write Edit
---

# /operar

Pedido do usuário: **$ARGUMENTS**

Comece **agora**, sem pedir confirmação, seguindo o `CLAUDE.md` deste projeto.

1. **Abrir o navegador:** use as ferramentas do Claude in Chrome para abrir (ou trazer para a
   frente) `https://iqoption.com/traderoom`. Se o Chrome não estiver conectado, diga ao usuário
   para digitar `/chrome` e escolher **Reconnect extension**, e pare. Se aparecer login ou CAPTCHA,
   peça para o usuário resolver na janela e continue assim que ele avisar.
2. **Preparar:** confira a conta ativa (use a de **treinamento**, a menos que o usuário tenha
   escrito "conta real") e o saldo. Abra o ativo, o valor e a expiração pedidos. O que não foi
   dito usa o padrão: **EUR/USD (OTC)**, **R$ 2**, **expiração de 1 minuto**, gráfico de velas de
   1 minuto. Informe em uma linha: ativo, tempo gráfico, conta, saldo, valor e expiração.
3. **Operar ao vivo, em ciclo:**
   - Acompanhe o gráfico na tela e espere o fechamento de cada vela.
   - Leia o gráfico como descrito no `CLAUDE.md` (tendência, regiões, velas, movimento).
   - Sem entrada boa: escreva só uma linha curta (ex.: "13:42 sem entrada: lateral na resistência") e continue olhando.
   - Com entrada boa: escreva direção + motivo + invalidação em até duas linhas, clique em
     **acima** ou **abaixo**, confirme que a operação abriu, acompanhe até expirar e informe o
     resultado e o saldo.
   - Registre cada operação em `historico/operacoes.csv`.
4. **Parar** quando: o usuário mandar parar; completar **10 operações**; tiver **3 perdas
   seguidas**; ou algo estranho acontecer na plataforma (operação não abriu, conta trocada,
   erro). Ao parar, mostre o resumo da sessão: operações, acertos, taxa de acerto e saldo.

Nunca aumente o valor depois de uma perda (sem martingale).

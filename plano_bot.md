# Plano — Bot próprio de trading na Polymarket

**Base:** análise da carteira `0xb55fa1296...d4` (bot HFT, long-only, hold-to-resolution).
**Objetivo:** não copiar, e sim **corrigir os vazamentos** e construir um bot com edge real, saída, gestão de risco e backtest.

---

## 0. Diagnóstico honesto (por que "só copiar" não funciona)

O bot observado:

| Comportamento | Consequência |
|---|---|
| Compra "Up" e **segura até o vencimento** | 90% das posições viram **0** (−100%) |
| Sem stop-loss, sem take-profit | Perde até o último centavo nos erros |
| Tickets fixos ($145–$3.000) sem lógica de tamanho | Risco desproporcional ao edge |
| Compra "above X" a 0,001–0,015 "no escuro" | Loteria, sem modelo de probabilidade |
| Ordena a market (cruza o spread) dezenas de vezes | Paga spread + gas repetidamente |
| **Resultado:** lucro +$16,8K concentrado em ~1 vitória ($9.940) | Cauda direita pesada = alta variância, baixa consistência |

**Conclusão:** o que sustenta o lucro dele é **uma cauda, não uma taxa de acerto**. Nosso bot precisa transformar isso em algo com **expectativa positiva por trade**, não por sorte de cauda.

---

## 1. Os melhoramentos (em ordem de impacto)

### 🥇 #1 — Adicionar SAÍDA (stop-loss + take-profit)
A maior melhoria possível. Na Polymarket você pode **vender suas cotas de volta antes da resolução**. O bot atual joga fora esse direito.

- **Take-profit:** compra "Up" a 0,24 → vende a 0,40 (+67%).
- **Stop-loss:** vende a 0,10 (−58%).
- **Trailing stop:** sobe conforme o preço sobe (ex.: −0,05 do pico).

Efeito: transforma "0 ou 1" (binário) em um trade com saída gerenciada. Sozinho, isso já eliminaria a maioria das perdas de −100%.

### 🥈 #2 — Tamanho de posição (Kelly / fração fixa)
Substituir tickets fixos por tamanho proporcional ao edge:

```
fração = (p_modelo - preço) / (1 - preço)   # edge normalizado
ticket  = bankroll * fração * 0.25           # fração de Kelly conservadora
```

Regra dura: **nunca > 1–2% do bankroll por posição** quando a win rate é baixa.

### 🥉 #3 — Definir um SINAL (o edge real)
Sem isso, é roleta. Três fontes de edge possíveis na Polymarket:

| Edge | Descrição | Dificuldade |
|---|---|---|
| **Mean-reversion de curto prazo** | Compra "Up" quando cai X% no minuto anterior (o bot parece já fazer isso) | Baixa |
| **Mispricing de volatilidade** | Modela P(BTC sobe em 15 min) com vol. realizada; compra quando o mercado precifica probabilidade menor que a do modelo | Média |
| **Ladder "above X" com modelo** | Calcula P(cruzar strike) via vol + tempo; só compra quando o preço implícito < probabilidade do modelo | Média |

**Recomendação para começar:** mean-reversion simples com stop (o bot atual já "compra a queda" — nós vamos fazer isso **com saída e modelo**).

### #4 — Entrar com LIMIT, não market
Colocar ordens **limitadas no bid/mid** em vez de comprar no ask. Cada 1¢ de spread economizado por trade, multiplicado por milhares de trades, é o que separa lucro de prejuízo em HFT.

### #5 — Parar de fragmentar à toa
O bot atual divide 1 posição em 50 ordens no mesmo segundo (paga gas/spread 50×). Nós agregamos em **poucas ordens limitadas**.

### #6 — Gestão de risco sistêmica
- Limite diário de perda (kill switch).
- Exposição máxima por mercado e por cripto.
- Log de todo trade (journal) para auditar o edge.

---

## 2. Arquitetura do bot

```
┌─────────────────────────────────────────────────────────────┐
│  MARKET DATA                                                 │
│  gamma-api (mercados) + CLOB /book (spread) + spot (Binance) │
└───────────────┬─────────────────────────────────────────────┘
                ▼
┌──────────────────────────┐     ┌─────────────────────────────┐
│  SIGNAL ENGINE           │ ──▶ │  RISK / SIZING              │
│  P(up) = f(momentum, vol)│     │  Kelly, stops, exposição    │
└──────────────────────────┘     └──────────────┬──────────────┘
                                                ▼
                              ┌─────────────────────────────────┐
                              │  EXECUTION (py-clob-client)     │
                              │  ordens LIMIT, batch, retry     │
                              └──────────────┬──────────────────┘
                                             ▼
                    ┌──────────────────────────────────────────┐
                    │  MONITOR + TELEMETRIA (journal, PnL)     │
                    │  SQLite/logs + kill switch               │
                    └──────────────────────────────────────────┘
```

Fluxo lógico por mercado (janela 15m de BTC, por exemplo):

1. Busca mercado Up/Down aberto (gamma-api).
2. Lê preço "Up" no book (bid/ask).
3. Calcula sinal (ex.: variação do spot nos últimos N minutos).
4. Se edge > limiar → calcula ticket (Kelly) e manda **limit order**.
5. Loop de monitoramento: take-profit / stop-loss / trailing.
6. Se não bateu stop nem target → decide se sai antes da resolução ou deixa resolver.
7. Registra tudo no journal.

---

## 3. Stack recomendada

| Camada | Escolha |
|---|---|
| Linguagem | **Python 3.11+** (ecossistema quant maduro) |
| SDK Polymarket | [`py-clob-client`](https://github.com/Polymarket/py-clob-client) (oficial) |
| Spot data | `ccxt` (Binance/Kraken) ou `websockets` direto |
| Backtest | `pandas` + `numpy`; replay de `clob.polymarket.com/prices-history` |
| Persistência | `sqlite3` (journal de trades) |
| Execução | loop assíncrono (`asyncio`) ou job scheduler (cron) |

**Pré-requisitos da conta (você precisa ter):**
1. Conta Polymarket **fundada** (depósito USDC via Polygon).
2. **API key / private key** (Settings → API keys) para assinar ordens L2.
3. Carteira com fundos para o banco do bot.

> ⚠️ Eu **não** vou te pedir private key nem farei depósitos. A chave fica só no seu ambiente, em `.env` (fora do Git).

---

## 4. Roteiro de implementação (fases)

| Fase | Entrega | Validação |
|---|---|---|
| **F1 — Data feed** | Puxar mercados Up/Down + book + spot | Ver preços corretos |
| **F2 — Backtest** | Replay histórico do sinal (momentum/mean-reversion) | Sharpe/expectativa positiva **fora da amostra** |
| **F3 — Paper trading** | Rodar o bot **sem dinheiro** (ordens em modo dry-run) | Logs coerentes |
| **F4 — Execução real** | Ordens limitadas reais, stakes mínimos ($1–5) | PnL + journal |
| **F5 — Escalar** | Aumentar ticket com Kelly, adicionar ladder "above X" | Drawdown controlado |

**Regra de ouro:** só vai para a F4 depois que o backtest mostrar expectativa positiva e o paper trading funcionar. Nunca apostar dinheiro em sinal sem backtest.

---

## 5. Perguntas para eu começar a construir

Preciso alinhar 4 pontos antes de escrever código:

1. **Stack:** Python (recomendo) ou Node/TypeScript?
2. **Qual edge você quer atacar primeiro:** (a) mean-reversion "Up/Down" com stop, (b) ladder "above X" com modelo de vol, ou (c) os dois?
3. **Horizonte/mercado:** focar em BTC (mais líquido) ou multi-cripto (BTC/ETH/SOL/XRP)?
4. **Você já tem:** conta Polymarket fundada + API key + algum capital definido para o banco do bot?

Com essas respostas eu começo a montar o **F1 (data feed)** e o esqueleto do bot.

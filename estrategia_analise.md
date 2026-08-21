# Análise de estratégia — Polymarket

**Trader:** `0xb55fa1296e6ec55d0ce53d93b9237389f11764d4` (pseudônimo *Lively-Authenticity*)
**Perfil:** https://polymarket.com/pt/@0xb55fa1296e6ec55d0ce53d93b9237389f11764d4-1777575277609

---

## Conclusão (resumo)

A conta é operada por um **bot de alta frequência (HFT)** que faz **scalping direcional comprado-only (só BUY)** em mercados binários de **"Up or Down" de cripto** com janelas curtas (5m, 15m, 1h, 4h). O bot **fragmenta ordens** (dezenas de compras pequenas no mesmo mercado em segundos), **compra majoritariamente o lado "Up"** (viés altista) e **segura até a resolução** (resgata vencedores, perde os outros para 0).

> ⚠️ O que dá para identificar é o **padrão de execução** (a "assinatura" da estratégia), não o **sinal interno** do bot. O dado público mostra *o que* e *quando* ele compra, mas não *por que* (o modelo/sinal que dispara cada ordem).

---

## Evidências observadas (fatos dos dados)

### 1. É 100% BUY — nunca SELL
Em todo o histórico coletado **não há uma única ordem de venda**. Isso descarta market-making e arbitragem clássica (que exigem comprar e vender). É **aposta direcional**, não formador de mercado.

### 2. Execução em sub-segundo = bot
Vários timestamps idênticos (ex.: `1787318272`, `1787318275`, `1787318317`) com 3–4 ordens no mesmo segundo. Combinado com **106.852 previsões**, é impossível ser humano.

### 3. Fragmentação / "iceberg" de ordens
No mercado *"Bitcoin Up or Down — 21/08, 9AM ET"*, o bot comprou o lado **"Up"** dezenas de vezes em ~2 minutos, em tickets de $5 a $60:

| horário (rel.) | preço | USDC |
|---|---|---|
| ...8271 | 0.30 | $6.29 |
| ...8272 | 0.2899 | $6.30 |
| ...8272 | 0.2996 | $39.29 |
| ...8275 | 0.29 | $7.61 |
| ...8308 | 0.30 | $60.42 |
| ...8317 | 0.28 | $7.35 |

Padrão típico de **divisão de ordem grande em muitas ordens pequenas** (para não mover o book) — *order splitting*.

### 4. Viés altista claro
A esmagadora maioria das ordens é em `outcomeIndex: 0` = **"Up"**. Também aparecem apostas **"Yes"** em *"Bitcoin above 77,400 / 77,600"* a 0.18–0.25 — ou seja, o bot aposta que o BTC **sobe** dentro da janela.

### 5. Hold-to-resolution (não faz exit antecipado)
As posições antigas aparecem com `currentValue: 0` e `percentPnl: -100` (perdeu tudo), enquanto as vencedoras geram eventos `REDEEM` (resgate). O bot **não vende antes do vencimento** — espera o resultado e resgata.

### 6. Mercados-alvo
Só cripto de janela curta: **BTC, ETH, SOL, XRP** em *Up/Down* (5m/15m/1h/4h) e *"acima de X"* horários. Nada de política, esportes, etc.

---

## Classificação da estratégia

| Característica | Encaixe |
|---|---|
| Alta frequência, sub-segundo | Bot HFT |
| Só BUY, direcional | Scalping direcional |
| Janelas curtas (5m–4h) | Micro-scalping de volatilidade |
| Fragmentação de ordens | Order splitting / iceberg |
| Viés "Up" + "acima de X" (Yes) | Trend-following / momentum altista |
| Hold até resolução + REDEEM | Estratégia de "buy-and-resolve" |

**Nome técnico mais provável:** *high-frequency directional scalping bot* em mercados de volatilidade de curto prazo, com tendência/momentum altista e execução fragmentada.

---

## Sobre o desempenho (importante)

- Valor da carteira: **~$12.6K**
- Maior vitória: **$9,940.52**
- A **maioria** das posições fechadas está com **−100%** (virou 0).
- Há tanto vencedores grandes quanto muitas perdas totais.

Ou seja: **não há evidência de edge consistente** nos dados públicos — parece uma estratégia de alta rotatividade com retorno concentrado em poucos acertos grandes e muitas perdas pequenas/totais. Para medir a win rate real seria preciso baixar o histórico completo (milhares de registros) e comparar `REDEEM` vs. posições zeradas.

---

## O que eu NÃO consigo afirmar

1. O **sinal de entrada** exato (o que faz o bot escolher "Up" naquele segundo) — pode ser momentum de preço spot, order flow, volatilidade implícita vs. realizada, ou puro acaso.
2. Se é um **bot comercial** conhecido ou código próprio.
3. Se é **lucrativo no longo prazo** — precisaria do histórico integral + fees.

---

## Como confirmar / ir além

Se quiser, posso:
1. Baixar o **histórico completo** (paginar `activity` e `positions`) e calcular win rate, ticket médio, horário de atuação e PnL agregado.
2. Cruzar os timestamps com o **preço spot** de BTC/ETH/SOL/XRP para testar a hipótese de momentum (ex.: o bot compra "Up" após alta no minuto anterior?).
3. Montar um **notebook** com gráficos da distribuição de ordens.

Quer que eu rode a análise completa (item 1 + 2)?

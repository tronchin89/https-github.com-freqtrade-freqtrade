# Bot Polymarket — scalping direcional com saída gerenciada

Skeleton funcional (Fase F1) baseado na análise do bot `0xb55fa1296...d4`,
mas **corrigindo os vazamentos**: saída (stop/target), Kelly, limit orders e
journal — tudo em **dry-run por padrão**.

## Estrutura

```
bot/
  config.py               # settings via .env
  data/
    gamma.py              # catálogo de mercados (gamma-api)
    clob.py               # orderbook/preços (clob)
    spot.py               # preço spot via ccxt (opcional)
  signal/
    mean_reversion.py     # sinal (comprar 'Up' depreciado)
  risk/
    sizing.py             # Kelly fracionário + stop/target
  execution/
    client.py             # wrapper py-clob-client (F4)
  journal.py              # SQLite trade journal
  main.py                 # loop (dry-run)
```

## Como rodar (dry-run)

```bash
pip install -r requirements.txt
cp .env.example .env      # preencha só se for executar de verdade
python -m bot.main
```

> Sem credenciais, roda em `dry_run=True` — só coleta dados, gera sinal e
> grava o journal. Não envia ordem nenhuma.

## Fases

| Fase | Status |
|---|---|
| F1 Data feed + sinal + risco | ✅ este skeleton |
| F2 Backtest (replay `prices-history`) | ⬜ a fazer |
| F3 Paper trading | ⬜ a fazer |
| F4 Execução real (stakes mínimos) | ⬜ a fazer |

## Avisos

- **Fees:** a Polymarket reativou taxas de taker (ex.: 4% em alguns mercados,
  `takerOnly`). O backtest (F2) precisa descontar isso — entrar com **limit
  order** (maker) é essencial para a estratégia ser viável.
- **Não é aconselhamento financeiro.** Só habilite dinheiro real depois de
  backtest com expectativa positiva fora da amostra + paper trading.

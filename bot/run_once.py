#!/usr/bin/env bash
# Teste rápido do F1 (data feed + sinal) sem entrar no loop infinito.
# Roda UMA passada e imprime o que o bot faria (dry-run, nenhuma ordem enviada).
set -e
cd "$(dirname "$0")"
export PYTHONPATH="$PWD"
python3 - <<'PY'
from bot.config import get_settings
from bot.data import gamma, clob, spot
from bot.signal.mean_reversion import evaluate
from bot.risk.sizing import plan_trade

s = get_settings()
print(f"coin={s.coin}  dry_run={s.dry_run}")

markets = gamma.fetch_markets(s, coin=s.coin, kind="updown", limit=50)
print(f"mercados Up/Down ativos: {len(markets)}")
if not markets:
    raise SystemExit("Nenhum mercado encontrado — verifique rede/API.")

for m in markets[:5]:
    tok = gamma.token_id_for_outcome(m, "Up")
    if not tok:
        print(f"  (sem token 'Up') {m.question}")
        continue
    book = clob.get_book(s, tok)
    print(f"\n  {m.question}")
    print(f"    outcomes={m.outcomes}  prices={m.outcome_prices}")
    print(f"    bid={book.best_bid} ask={book.best_ask} mid={book.mid:.4f} "
          f"spread={book.spread:.4f}")
    print(f"    fees_enabled={m.fees_enabled} taker_fee={m.taker_fee_rate} "
          f"min_size={m.min_size} min_tick={m.min_tick}")

# sinal de exemplo com spot
sf = spot.SpotFeed(f"{s.coin.upper()}/USDT")
chg = sf.pct_change(s.mr_lookback_minutes)
print(f"\nspot {s.coin}/USDT variação {s.mr_lookback_minutes}m: "
      f"{chg:+.4%}" if chg is not None else "n/a")
PY

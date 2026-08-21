"""Teste rápido do F1 (data feed + sinal) — UMA passada, sem loop.

Rode com:
    python -m bot.run_once
ou
    python bot/run_once.py

É dry-run: não envia ordem nenhuma. Apenas busca mercados, lê o book,
gera sinal e imprime o que faria.
"""
from __future__ import annotations

from bot.config import get_settings
from bot.data import clob, gamma, spot


def main() -> None:
    s = get_settings()
    symbol = gamma.SYMBOL_BY_COIN.get(s.coin.strip().lower(), s.coin.upper())
    print(f"coin={s.coin}  symbol={symbol}  dry_run={s.dry_run}")

    markets = gamma.fetch_markets(s, coin=s.coin, kind="updown", limit=20)
    print(f"mercados 'Up or Down' ativos ({s.coin}): {len(markets)}")
    if not markets:
        print("  -> nenhum encontrado. Verifique rede/API ou tente outra moeda.")
        return

    for m in markets[:6]:
        tok = gamma.token_id_for_outcome(m, "Up")
        print(f"\n  [{m.timeframe}] {m.question}")
        print(f"    outcomes={m.outcomes}  prices={m.outcome_prices}")
        if tok:
            try:
                book = clob.get_book(s, tok)
                print(f"    bid={book.best_bid}  ask={book.best_ask}  "
                      f"mid={book.mid:.4f}  spread={book.spread:.4f}  "
                      f"last={book.last_trade_price}")
            except Exception as e:  # noqa: BLE001
                print(f"    (book indisponível: {e!r})")
        else:
            print("    (sem token 'Up')")
        print(f"    fees_enabled={m.fees_enabled}  taker_fee={m.taker_fee_rate:.0%}  "
              f"min_size={m.min_size}  min_tick={m.min_tick}")

    # sinal de exemplo com spot
    sf = spot.SpotFeed(f"{symbol}/USDT")
    chg = sf.pct_change(s.mr_lookback_minutes)
    if chg is not None:
        print(f"\nspot {symbol}/USDT variação {s.mr_lookback_minutes}m: {chg:+.4%}")
    else:
        print(f"\nspot {symbol}/USDT: indisponível (sinal vira 'skip', sem impacto no F1)")


if __name__ == "__main__":
    main()

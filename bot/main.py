"""Loop principal (F3/F4).

F1 (data feed) + F3 (paper) rodam agora em dry_run. O loop:
  1. busca mercados Up/Down do ativo alvo,
  2. lê o book,
  3. gera sinal (mean-reversion),
  4. se sinal = buy, calcula stake (Kelly) e registra no journal.

Saídas (stop/target) e execução real ficam nas fases seguintes — aqui o foco
é validar o pipeline de dados e o sinal.
"""
from __future__ import annotations

import time

from bot.config import get_settings
from bot.data import clob, gamma, spot
from bot.journal import Journal
from bot.risk.sizing import plan_trade
from bot.signal.mean_reversion import evaluate


def run_once(s, journal, spot_feed):
    markets = gamma.fetch_markets(s, coin=s.coin, kind="updown", limit=50)
    if not markets:
        print(f"[{s.coin}] nenhum mercado Up/Down ativo.")
        return

    for m in markets:
        token = gamma.token_id_for_outcome(m, "Up")
        if not token:
            continue
        book = clob.get_book(s, token)
        mid = book.mid or m.best_ask or 0
        if mid <= 0:
            continue

        sig = evaluate(
            mid_price=mid,
            spot_pct_change=spot_feed.pct_change(s.mr_lookback_minutes),
            lookback_minutes=s.mr_lookback_minutes,
            drop_threshold=s.mr_drop_threshold,
        )

        if sig.action == "buy" and sig.edge > 0:
            plan = plan_trade(
                model_probability=sig.model_probability,
                entry_price=mid,
                bankroll=s.bankroll_usd,
                max_frac_kelly=s.max_frac_kelly,
                max_per_position=s.max_per_position,
                take_profit_ratio=s.take_profit_ratio,
                stop_loss_ratio=s.stop_loss_ratio,
            )
            print(f"BUY  {m.question!r}  mid={mid:.3f}  "
                  f"P_model={sig.model_probability:.3f}  stake=${plan.stake_usd}  "
                  f"(dry_run={s.dry_run})")
            journal.log_trade(
                market_id=m.id, question=m.question, token_id=token,
                outcome="Up", entry_price=mid, stake_usd=plan.stake_usd,
                status="open", reason=sig.reason,
            )


def main():
    s = get_settings()
    journal = Journal(s.db_path)
    spot_feed = spot.SpotFeed(f"{s.coin.upper()}/USDT")
    print(f"Bot iniciado: coin={s.coin} dry_run={s.dry_run} "
          f"bankroll=${s.bankroll_usd}")
    try:
        while True:
            try:
                run_once(s, journal, spot_feed)
            except Exception as e:  # noqa: BLE001
                print(f"[erro] {e!r}")
            time.sleep(15)
    except KeyboardInterrupt:
        print("Encerrado.")
    finally:
        journal.close()


if __name__ == "__main__":
    main()

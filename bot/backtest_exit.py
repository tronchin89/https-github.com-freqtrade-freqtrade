"""Backtest (F2c) — otimizar a SAÍDA para a estratégia de momentum.

O F2b mostrou que momentum prevê bem (win 76-88%), mas comprar o favorito e
segurar perde dinheiro; sair cedo (TP/SL) vira positivo. Aqui varremos a
grade de take-profit e stop-loss para achar a combinação com melhor EV.

Estratégia fixa (a vencedora do F2b):
  - MOMENTUM: preço 'Up' subiu > thresh => compra 'Up'; caiu > thresh => compra 'Down'.
  - Sai por TP ou SL na trajetória de preço; senão segura até resolver.

Grade: tp em {25%,50%,75%,100%}, sl em {25%,50%,75%}.

USO:
    python -m bot.backtest_exit
    python -m bot.backtest_exit --timeframes 1h,15m --days 21 --limit 1000
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from bot.backtest import collect_samples, get_settings
from bot.backtest_direction import first_momentum, simulate_exit


def run(samples, fee: float = 0.07):
    lookback = 5
    thresh = 0.10
    tp_grid = [0.25, 0.50, 0.75, 1.00]
    sl_grid = [0.25, 0.50, 0.75]

    print("\n" + "=" * 72)
    print(f"OTIMIZAÇÃO DE SAÍDA — momentum (lookback={lookback}m, thresh=±{thresh:.2f})")
    print(f"amostra={len(samples)}  fee={fee:.0%}")
    print("=" * 72)

    # pré-computa as entradas de momentum
    entries = []  # (hist, i_entry, p_e, buy_up, wins)
    for s in samples:
        i, m = first_momentum(s.history, lookback, thresh)
        if i is None:
            continue
        p_e = s.history[i][1]
        buy_up = m > 0
        if not buy_up and p_e <= 0:
            continue
        entry = p_e if buy_up else (1 - p_e)
        if entry <= 0 or entry >= 1:
            continue
        wins = s.up_won if buy_up else (not s.up_won)
        entries.append((s.history, i, p_e, buy_up, wins, entry))

    print(f"\nentradas de momentum: {len(entries)}")

    best = (None, -1e9)
    print(f"\n{'TP':>6} {'SL':>6} | {'n':>5} {'TP#':>4} {'SL#':>4} {'hold':>4} | "
          f"{'EV(hold)':>9} {'EV(exit)':>9}")
    print("-" * 72)

    for tp in tp_grid:
        for sl in sl_grid:
            pnl_hold = 0.0
            pnl_exit = 0.0
            n_tp = n_sl = n_hold = 0
            for hist, i, p_e, buy_up, wins, entry in entries:
                # HOLD
                pnl_hold += (1 - entry * (1 + fee)) if wins else (-entry * (1 + fee))
                # EXIT
                if buy_up:
                    res = simulate_exit(hist, i, p_e, tp, sl)
                else:
                    res = simulate_exit([(t, 1 - p) for t, p in hist], i, 1 - p_e, tp, sl)
                if res == "tp":
                    n_tp += 1
                    pnl_exit += entry * tp - entry * fee
                elif res == "sl":
                    n_sl += 1
                    pnl_exit += -entry * sl - entry * fee
                else:
                    n_hold += 1
                    pnl_exit += (1 - entry * (1 + fee)) if wins else (-entry * (1 + fee))

            n = len(entries)
            ev_hold = pnl_hold / n
            ev_exit = pnl_exit / n
            if ev_exit > best[1]:
                best = ((tp, sl), ev_exit)
            print(f"{tp:>6.0%} {sl:>6.0%} | {n:>5} {n_tp:>4} {n_sl:>4} {n_hold:>4} | "
                  f"{ev_hold:>+9.4f} {ev_exit:>+9.4f}")

    if best[0]:
        tp, sl = best[0]
        print(f"\n>>> Melhor combinação: take-profit={tp:.0%}, stop-loss={sl:.0%}  "
              f"(EV={best[1]:+.4f} por $1)")
    print("\n(EV>0 = lucro líquido de fee. Compare EV(exit) com EV(hold)=base sem saída.)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coin", default="bitcoin")
    parser.add_argument("--timeframes", default="1h,15m")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--days", type=int, default=21)
    args = parser.parse_args()

    s = get_settings()
    timeframes = [t.strip() for t in args.timeframes.split(",")]
    now = datetime.now(timezone.utc)
    end_max = now.strftime("%Y-%m-%d")
    end_min = (now - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"Coletando mercados resolvidos de {args.coin} "
          f"({', '.join(timeframes)}) nos últimos {args.days} dias ...")
    samples = collect_samples(s, args.coin, timeframes, args.limit, end_min, end_max)
    print(f"amostra válida: {len(samples)} mercados")
    if not samples:
        print("Nada para avaliar.")
        return
    run(samples, fee=0.07)


if __name__ == "__main__":
    main()

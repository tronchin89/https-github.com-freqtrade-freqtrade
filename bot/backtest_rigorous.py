"""Backtest (F2d) — versão RIGOROSA da estratégia de momentum + saída.

Corrige os 3 pontos fracos dos backtests anteriores:

1. PREÇO REAL DO TOKEN 'DOWN': em vez de aproximar p_down = 1 - p_up, baixa o
   histórico de preço do token 'Down' (2º clobTokenId) e usa o preço real.

2. TAXA DINÂMICA: a taxa de taker da Polymarket por share é
       fee = rate * p * (1 - p)
   (confirmado em feeSchedule {rate:0.07, exponent:1}). Como fração do
   notional (p) pago, isso é  fee_frac = rate * (1 - p).
   => comprar favorito (p alto) paga MUITO menos que os 7% fixos usados antes.

3. BOOTSTRAP: intervalo de confiança do EV (amostra grande => robustez).

Estratégia (a vencedora do F2c):
   momentum do preço 'Up' (lookback 5min, ±0.10) => compra o lado que está
   subindo (Up se momentum>0, Down se momentum<0); saída por TP/SL.

USO:
    python -m bot.backtest_rigorous
    python -m bot.backtest_rigorous --days 30 --limit 3000
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone

from bot.backtest import (
    MarketSample,
    collect_samples,
    fetch_price_history,
    get_settings,
    token_id_for_outcome,
)
from bot.backtest_direction import first_momentum, simulate_exit


# --------------------------------------------------------------------------- #
# Taxa dinâmica
# --------------------------------------------------------------------------- #

def taker_fee_fraction(price: float, rate: float = 0.07) -> float:
    """Taxa de taker como fração do notional, para comprar a `price`.

    Polymarket: fee por share = rate * p * (1-p); notional = p.
    => fee/notional = rate * (1-p). Favorito (p alto) => taxa baixa.
    """
    p = max(0.0, min(1.0, price))
    return rate * (1 - p)


# --------------------------------------------------------------------------- #
# Coleta com AMBOS os tokens
# --------------------------------------------------------------------------- #

class Sample2:
    __slots__ = ("question", "timeframe", "up_won", "up_hist", "down_hist")

    def __init__(self, question, timeframe, up_won, up_hist, down_hist):
        self.question = question
        self.timeframe = timeframe
        self.up_won = up_won
        self.up_hist = up_hist
        self.down_hist = down_hist


def collect_samples2(s, coin, timeframes, limit, end_min, end_max) -> list[Sample2]:
    """Coleta com histórico dos DOIS tokens (Up e Down)."""
    from bot.backtest import fetch_closed_markets, up_won
    markets = fetch_closed_markets(s, coin, timeframes, limit, end_min, end_max)
    out: list[Sample2] = []
    for m, mjson in markets:
        won = up_won(mjson, m)
        if won is None:
            continue
        tok_up = token_id_for_outcome(m, "Up")
        tok_down = token_id_for_outcome(m, "Down")
        if not tok_up or not tok_down:
            continue
        try:
            h_up = fetch_price_history(s, tok_up)
            h_down = fetch_price_history(s, tok_down)
        except Exception:
            continue
        if len(h_up) < 5 or len(h_down) < 5:
            continue
        out.append(Sample2(m.question, m.timeframe, won, h_up, h_down))
    return out


# --------------------------------------------------------------------------- #
# Simulação rigorosa
# --------------------------------------------------------------------------- #

def run_rigorous(samples: list[Sample2], lookback=5, thresh=0.10,
                 tp=0.75, sl=0.25, rate=0.07, maker_exit=False):
    """Retorna (trades_pnl, stats) para momentum + TP/SL com taxa dinâmica."""
    trades: list[float] = []  # pnl por $1 de notional de entrada
    n_tp = n_sl = n_hold = 0
    wins = 0

    for s in samples:
        i, m = first_momentum(s.up_hist, lookback, thresh)
        if i is None:
            continue
        buy_up = m > 0
        hist = s.up_hist if buy_up else s.down_hist
        if i >= len(hist):
            continue
        p_e = hist[i][1]
        if p_e <= 0.02 or p_e >= 0.98:
            continue
        won = s.up_won if buy_up else (not s.up_won)

        fee_in = taker_fee_fraction(p_e, rate)          # fração do notional
        cost = 1 + fee_in                                # paga 1+fee por $1

        res = simulate_exit(hist, i, p_e, tp, sl)
        if res == "tp":
            q = p_e * (1 + tp)
            fee_out = 0.0 if maker_exit else taker_fee_fraction(q, rate)
            pnl = (q * (1 - fee_out)) - (p_e * cost)
            n_tp += 1
        elif res == "sl":
            q = p_e * (1 - sl)
            fee_out = 0.0 if maker_exit else taker_fee_fraction(q, rate)
            pnl = (q * (1 - fee_out)) - (p_e * cost)
            n_sl += 1
        else:  # hold até resolver
            pnl = (1 - (p_e * cost)) if won else (-(p_e * cost))
            n_hold += 1
        trades.append(pnl)
        if pnl > 0:
            wins += 1

    return trades, dict(n=len(trades), n_tp=n_tp, n_sl=n_sl, n_hold=n_hold,
                        win_pct=wins / len(trades) if trades else 0)


def bootstrap_ci(trades: list[float], n_iter=4000, seed=42):
    """Intervalo de confiança 95% do EV médio por bootstrap."""
    rng = random.Random(seed)
    n = len(trades)
    means = []
    for _ in range(n_iter):
        sample = [trades[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * n_iter)]
    hi = means[int(0.975 * n_iter)]
    return lo, hi


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coin", default="bitcoin")
    parser.add_argument("--timeframes", default="1h,15m")
    parser.add_argument("--limit", type=int, default=3000)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    s = get_settings()
    timeframes = [t.strip() for t in args.timeframes.split(",")]
    now = datetime.now(timezone.utc)
    end_max = now.strftime("%Y-%m-%d")
    end_min = (now - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"Coletando mercados resolvidos de {args.coin} "
          f"({', '.join(timeframes)}) nos últimos {args.days} dias "
          f"(histórico dos DOIS tokens) ...")
    samples = collect_samples2(s, args.coin, timeframes, args.limit, end_min, end_max)
    print(f"amostra válida: {len(samples)} mercados")
    if not samples:
        print("Nada para avaliar.")
        return

    lookback, thresh, tp, sl = 5, 0.10, 0.75, 0.25

    print("\n" + "=" * 72)
    print(f"RIGOROSO — momentum (lb={lookback}m, ±{thresh}) + TP{tp:.0%}/SL{sl:.0%}")
    print(f"amostra={len(samples)}  preço real dos 2 tokens  taxa dinâmica")
    print("=" * 72)

    # cenário 1: taxa dinâmica (real), saída via taker
    trades1, st1 = run_rigorous(samples, lookback, thresh, tp, sl, rate=0.07, maker_exit=False)
    ev1 = sum(trades1) / len(trades1) if trades1 else 0
    lo1, hi1 = bootstrap_ci(trades1)

    # cenário 2: saída como MAKER (limit) = 0 taxa na saída
    trades2, st2 = run_rigorous(samples, lookback, thresh, tp, sl, rate=0.07, maker_exit=True)
    ev2 = sum(trades2) / len(trades2) if trades2 else 0
    lo2, hi2 = bootstrap_ci(trades2)

    print(f"\n[taker exit]  trades={st1['n']:>5}  TP={st1['n_tp']:>4}  SL={st1['n_sl']:>4}  "
          f"hold={st1['n_hold']:>4}  win%={st1['win_pct']:>5.1%}")
    print(f"  EV = {ev1:+.4f}  (IC 95%: [{lo1:+.4f}, {hi1:+.4f}])")

    print(f"\n[maker exit]  trades={st2['n']:>5}  TP={st2['n_tp']:>4}  SL={st2['n_sl']:>4}  "
          f"hold={st2['n_hold']:>4}  win%={st2['win_pct']:>5.1%}")
    print(f"  EV = {ev2:+.4f}  (IC 95%: [{lo2:+.4f}, {hi2:+.4f}])")

    print("\n" + "-" * 72)
    print("Leitura:")
    print("  - EV > 0 e IC 95% todo > 0  => edge ROBUSTO (confiança estatística).")
    print("  - EV > 0 mas IC cruza 0     => edge provável mas não conclusivo.")
    print("  - IC todo <= 0              => sem edge (estratégia não compensa).")
    print("  - maker exit (limit) zera a taxa de saída e ainda pode dar rebate.")


if __name__ == "__main__":
    main()

"""Backtest (F2b) — prever DIREÇÃO + sair antes da resolução.

A pergunta que o F2 anterior não respondia: em vez de "comprar 'Up' barato"
(contrarian, que foi REFUTADO), dá para usar o momentum do próprio preço do
token para prever a direção, e/ou reduzir o prejuízo saindo antes do vencimento?

Testes:
  1. MOMENTUM (continuação): quando o preço 'Up' sobe > X pts, compra 'Up'
     (favorito); quando cai > X pts, compra 'Down'.
  2. CONTRARIAN (reversão): o inverso — compra a queda do 'Up', vende a alta.
  3. EXIT: para cada entrada, simula saída por take-profit / stop-loss na
     trajetória de preço posterior, comparando com 'segurar até resolver'.

Contabilidade (por share comprado):
  - HOLD:  vence -> +1 - p_e*(1+fee);  perde -> -p_e*(1+fee)
  - EXIT:  TP em p >= p_e*(1+tp) -> +p_e*tp - fee;  SL em p <= p_e*(1-sl) -> -p_e*sl - fee
  (fee de taker incide sobre o notional de entrada, ~7%)

Aproximação declarada: comprar 'Down' usa preço 1 - p_up (tokens são
complementares; o spread real é ignorado nesta 1ª ordem).

USO:
    python -m bot.backtest_direction
    python -m bot.backtest_direction --timeframes 1h,15m --days 14
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone

from bot.backtest import collect_samples, MarketSample, get_settings


def first_momentum(hist: list[tuple[int, float]], lookback: int, thresh: float):
    """Retorna (i, momentum) da 1ª barra i>=lookback com |p[i]-p[i-lookback]|>=thresh.

    momentum > 0 => preço 'Up' subiu; < 0 => caiu. None se nunca cruzar.
    """
    for i in range(lookback, len(hist)):
        p_i = hist[i][1]
        p_prev = hist[i - lookback][1]
        m = p_i - p_prev
        if abs(m) >= thresh:
            return i, m
    return None, 0.0


def simulate_exit(hist: list[tuple[int, float]], i_entry: int, p_e: float,
                  tp: float, sl: float):
    """Após entrar na barra i_entry a p_e, caminha até TP/SL (índices).

    Retorna 'tp', 'sl' ou 'hold' (nenhum atingido antes do fim).
    """
    for j in range(i_entry + 1, len(hist)):
        p = hist[j][1]
        if p >= p_e * (1 + tp):
            return "tp"
        if p <= p_e * (1 - sl):
            return "sl"
    return "hold"


def run(samples: list[MarketSample], fee: float = 0.07):
    lookbacks = [3, 5, 10]
    mom_thresholds = [0.05, 0.10, 0.20]
    tp, sl = 0.5, 0.5  # +50% take-profit, -50% stop (em preço)

    print("\n" + "=" * 70)
    print(f"DIRECTION + EXIT — amostra de {len(samples)} mercados resolvidos")
    print(f"fee taker = {fee:.0%} | take-profit = +{tp:.0%} | stop-loss = -{sl:.0%}")
    print("=" * 70)

    for lookback in lookbacks:
        for thresh in mom_thresholds:
            mom = {"trades": 0, "wins_hold": 0, "pnl_hold": 0.0,
                   "pnl_exit": 0.0, "tp": 0, "sl": 0}
            con = {"trades": 0, "wins_hold": 0, "pnl_hold": 0.0,
                   "pnl_exit": 0.0, "tp": 0, "sl": 0}

            for s in samples:
                i, m = first_momentum(s.history, lookback, thresh)
                if i is None:
                    continue
                p_e = s.history[i][1]

                # --- direção: momentum compra a tendência; contrarian compra contra
                buy_up_mom = m > 0
                buy_up_con = m < 0

                for bucket, buy_up in (("mom", buy_up_mom), ("con", buy_up_con)):
                    if not buy_up and p_e <= 0:   # evita dividir por zero
                        continue
                    entry = p_e if buy_up else (1 - p_e)
                    if entry <= 0 or entry >= 1:
                        continue
                    wins = s.up_won if buy_up else (not s.up_won)
                    b = bucket == "mom" and mom or con
                    b["trades"] += 1
                    # --- HOLD ---
                    if wins:
                        b["wins_hold"] += 1
                        b["pnl_hold"] += 1 - entry * (1 + fee)
                    else:
                        b["pnl_hold"] += -entry * (1 + fee)
                    # --- EXIT ---
                    if buy_up:
                        res = simulate_exit(s.history, i, p_e, tp, sl)
                    else:
                        # para 'Down', refletir: p_up sobe = p_down cai
                        res = simulate_exit(
                            [(t, 1 - p) for t, p in s.history], i, 1 - p_e, tp, sl)
                    if res == "tp":
                        b["tp"] += 1
                        b["pnl_exit"] += entry * tp - entry * fee
                    elif res == "sl":
                        b["sl"] += 1
                        b["pnl_exit"] += -entry * sl - entry * fee
                    else:  # hold
                        if wins:
                            b["pnl_exit"] += 1 - entry * (1 + fee)
                        else:
                            b["pnl_exit"] += -entry * (1 + fee)

            print(f"\nlookback={lookback}min  momentum>=±{thresh:.2f}")
            for label, b in (("MOMENTUM (continua)", mom), ("CONTRARIAN (reversa)", con)):
                if b["trades"] < 10:
                    print(f"  {label:<20}: trades={b['trades']} (insuficiente)")
                    continue
                wr = b["wins_hold"] / b["trades"]
                ev_hold = b["pnl_hold"] / b["trades"]
                ev_exit = b["pnl_exit"] / b["trades"]
                print(f"  {label:<20}: trades={b['trades']:>4}  win%(hold)={wr:>5.1%}  "
                      f"EV(hold)={ev_hold:+.4f}  EV(exit)={ev_exit:+.4f}  "
                      f"[TP={b['tp']} SL={b['sl']} hold_rest={b['trades']-b['tp']-b['sl']}]")

    print("\n(EV > 0 => lucro esperado por $1 de notional, líquido de fee.)")
    print("Comparação central: momentum vs contrarian, e hold vs exit.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coin", default="bitcoin")
    parser.add_argument("--timeframes", default="1h,15m")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--days", type=int, default=14)
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

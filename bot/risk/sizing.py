"""Dimensionamento de posição (Kelly fracionário) e saídas (stop/target).

Para um binário comprado a `price` (0..1), o payoff se vencer é (1 - price)
por dólar apostado; se perder, perde-se tudo (retorno -100%).

Kelly (binário): f = (b*p - q) / b, onde b = (1-price)/price, q = 1-p.
Aplicamos uma fração (max_frac_kelly) e um teto por posição.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TradePlan:
    outcome: str
    entry_price: float
    target_price: float     # take-profit
    stop_price: float       # stop-loss
    stake_usd: float        # quanto apostar nesta posição


def kelly_fraction(model_probability: float, entry_price: float) -> float:
    """Fraçção ótima de Kelly para o binário (pode ser negativa => não apostar)."""
    if entry_price <= 0 or entry_price >= 1:
        return 0.0
    b = (1 - entry_price) / entry_price
    q = 1 - model_probability
    return (b * model_probability - q) / b


def plan_trade(
    *,
    model_probability: float,
    entry_price: float,
    bankroll: float,
    max_frac_kelly: float = 0.25,
    max_per_position: float = 0.02,
    take_profit_ratio: float = 0.40,
    stop_loss_ratio: float = 0.10,
    outcome: str = "Up",
) -> TradePlan:
    """Monta o plano de trade (stake + stop + target) para um sinal de compra."""
    f_kelly = kelly_fraction(model_probability, entry_price)
    f_adj = max(0.0, f_kelly) * max_frac_kelly          # Kelly fracionário
    f_cap = min(f_adj, max_per_position)                 # teto de exposição
    stake = bankroll * f_cap
    return TradePlan(
        outcome=outcome,
        entry_price=entry_price,
        target_price=min(1.0, take_profit_ratio),
        stop_price=max(0.001, stop_loss_ratio),
        stake_usd=round(stake, 2),
    )

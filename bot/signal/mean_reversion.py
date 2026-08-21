"""Sinal de mean-reversion (primeira versão, para backtest + paper trading).

Hipótese (derivada do bot observado, que compra 'Up' depreciado):
  - quando o preço do lado 'Up' cai abaixo de um limiar (ou o spot cai),
    a probabilidade de reversão é maior que a precificada.
  - compramos 'Up' barato e vendemos na reversão (take-profit) ou cortamos
    a perda (stop-loss).

IMPORTANTE: este é um ponto de partida de demonstração. O backtest (F2) é
quem decide se a hipótese tem expectativa positiva antes de qualquer
dinheiro real.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    action: str            # "buy" | "hold" | "skip"
    outcome: str           # "Up" | "Down" | "Yes" | "No"
    model_probability: float  # P(outcome vence) segundo o modelo [0..1]
    entry_price: float     # preço de referência (mid)
    reason: str

    @property
    def edge(self) -> float:
        """Edge bruto = P_modelo - preço (para binário, preço ~ P_mercado)."""
        return self.model_probability - self.entry_price


def evaluate(
    *,
    mid_price: float,
    spot_pct_change: Optional[float],
    lookback_minutes: int = 5,
    drop_threshold: float = -0.004,
    buy_below: float = 0.40,
) -> Signal:
    """Gera sinal de mean-reversion para um mercado Up/Down.

    Regras simples (ajustáveis):
      - Se o spot caiu mais que `drop_threshold` nos últimos N minutos, e o
        lado 'Up' está barato (<= buy_below), compra 'Up'.
      - Senão, hold.
    """
    if spot_pct_change is None:
        return Signal("skip", "Up", mid_price, mid_price, "sem dado de spot")

    if spot_pct_change <= drop_threshold and mid_price <= buy_below:
        # modelo: reversão à média -> probabilidade 'Up' levemente acima do
        # preço implícito. Valor de demonstração; calibrar no backtest.
        p_model = min(0.60, max(mid_price, 0.45 + (buy_below - mid_price) * 0.3))
        return Signal(
            "buy",
            "Up",
            p_model,
            mid_price,
            f"spot {spot_pct_change:+.2%} em {lookback_minutes}m e Up a {mid_price:.3f}",
        )

    return Signal(
        "hold", "Up", mid_price, mid_price,
        f"spot {spot_pct_change:+.2%} — sem condição de entrada",
    )

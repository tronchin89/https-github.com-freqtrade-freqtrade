"""Dados de preço spot (para o sinal de momentum/mean-reversion).

Usa ccxt (Binance) para obter candles. Opcional — o sinal funciona sem isso
se você usar apenas o book da Polymarket como proxy de preço.
"""
from __future__ import annotations

from typing import Optional


class SpotFeed:
    """Wrapper mínimo sobre ccxt. Instancie com um exchange e um símbolo."""

    def __init__(self, symbol: str = "BTC/USDT"):
        self.symbol = symbol
        self._ex = None

    def _exchange(self):
        if self._ex is None:
            import ccxt  # import tardio para não obrigar dependência
            self._ex = ccxt.binance({"enableRateLimit": True})
        return self._ex

    def candles(self, timeframe: str = "1m", limit: int = 10) -> list[dict]:
        """Retorna candles OHLCV. Candles[i]['close'] é o fechamento."""
        return self._exchange().fetch_ohlcv(self.symbol, timeframe, limit=limit)

    def pct_change(self, minutes: int = 5) -> Optional[float]:
        """Variação percentual do close atual vs. o de `minutes` minutos atrás."""
        try:
            data = self.candles("1m", limit=minutes + 1)
            if len(data) < 2:
                return None
            first = float(data[0][4])
            last = float(data[-1][4])
            if first == 0:
                return None
            return (last - first) / first
        except Exception:
            return None

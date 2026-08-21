"""Acesso à Gamma API (catálogo de mercados) — sem autenticação.

Usa o endpoint /events com `series_slug` para achar com precisão os mercados
recorrentes de "Up or Down" de cripto (o /markets genérico fica dominado por
mercados de política e não acha os de cripto).

Séries confirmadas (2026-08):
  btc: 5m / 15m / hourly / 4h
  eth: 5m / 15m / hourly / 4h   (slugs no mesmo padrão)
  sol: 5m / 15m / hourly
  xrp: 5m / 15m / hourly
"""
from __future__ import annotations

import json as _json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests

from bot.config import Settings

# coin (lower) -> { timeframe -> series slug }
SERIES_BY_COIN: dict[str, dict[str, str]] = {
    "bitcoin": {
        "5m": "btc-up-or-down-5m",
        "15m": "btc-up-or-down-15m",
        "1h": "btc-up-or-down-hourly",
        "4h": "btc-up-or-down-4h",
    },
    "ethereum": {
        "5m": "eth-up-or-down-5m",
        "15m": "eth-up-or-down-15m",
        "1h": "eth-up-or-down-hourly",
        "4h": "eth-up-or-down-4h",
    },
    "solana": {
        "5m": "sol-up-or-down-5m",
        "15m": "sol-up-or-down-15m",
        "1h": "sol-up-or-down-hourly",
        "4h": "sol-up-or-down-4h",
    },
    "xrp": {
        "5m": "xrp-up-or-down-5m",
        "15m": "xrp-up-or-down-15m",
        "1h": "xrp-up-or-down-hourly",
        "4h": "xrp-up-or-down-4h",
    },
}

# coin (lower) -> símbolo spot (Binance/ccxt)
SYMBOL_BY_COIN: dict[str, str] = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "xrp": "XRP",
}


@dataclass
class Market:
    id: str
    question: str
    condition_id: str
    outcomes: list[str]
    token_ids: list[str]          # clobTokenIds, alinhado a outcomes
    outcome_prices: list[float]   # preço médio exibido
    best_bid: float
    best_ask: float
    end_date: Optional[datetime]
    accepting_orders: bool
    min_size: float               # orderMinSize (shares)
    min_tick: float               # orderPriceMinTickSize
    fees_enabled: bool
    taker_fee_rate: float         # fração (ex.: 0.07 = 7%)
    timeframe: str                # "5m" | "15m" | "1h" | "4h"

    @property
    def mid(self) -> float:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return self.best_ask or self.best_bid or 0.0


def _loads(value, default):
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return _json.loads(value)
    except (TypeError, ValueError):
        return default


def _parse_market(mjson: dict, timeframe: str) -> Market:
    outcomes = _loads(mjson.get("outcomes"), ["Up", "Down"])
    token_ids = _loads(mjson.get("clobTokenIds"), [])
    prices = _loads(mjson.get("outcomePrices"), [])
    fee = mjson.get("feeSchedule") or {}

    end_date = None
    if mjson.get("endDate"):
        try:
            end_date = datetime.fromisoformat(
                mjson["endDate"].replace("Z", "+00:00")
            )
        except ValueError:
            end_date = None

    return Market(
        id=str(mjson.get("id", "")),
        question=mjson.get("question", ""),
        condition_id=mjson.get("conditionId", ""),
        outcomes=[str(o) for o in outcomes],
        token_ids=[str(t) for t in token_ids],
        outcome_prices=[float(p) for p in prices if p not in (None, "")],
        best_bid=float(mjson.get("bestBid") or 0),
        best_ask=float(mjson.get("bestAsk") or 0),
        end_date=end_date,
        accepting_orders=bool(mjson.get("acceptingOrders", False)),
        min_size=float(mjson.get("orderMinSize", 5)),
        min_tick=float(mjson.get("orderPriceMinTickSize", 0.001)),
        fees_enabled=bool(mjson.get("feesEnabled", False)),
        taker_fee_rate=float(fee.get("rate", 0)),
        timeframe=timeframe,
    )


def _fetch_events(s: Settings, series_slug: str, limit: int = 20) -> list[dict]:
    resp = requests.get(
        f"{s.gamma_host}/events",
        params={
            "series_slug": series_slug,
            "active": "true",
            "closed": "false",
            "limit": limit,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_markets(
    s: Settings,
    coin: Optional[str] = None,
    kind: str = "updown",  # reservado (só "updown" por enquanto)
    limit: int = 20,
) -> list[Market]:
    """Retorna mercados 'Up or Down' ativos do ativo alvo, próximos de resolver.

    Filtra `acceptingOrders=true` e `endDate` no futuro; ordena pelo fim mais
    próximo (janela ativa/mais líquida primeiro).
    """
    coin = (coin or s.coin).strip().lower()
    slugs = SERIES_BY_COIN.get(coin)
    if not slugs:
        raise ValueError(f"Moeda não suportada: {coin!r}. Use bitcoin/ethereum/solana/xrp.")

    now = datetime.now(timezone.utc)
    out: list[Market] = []
    seen: set[str] = set()

    for timeframe, slug in slugs.items():
        try:
            events = _fetch_events(s, slug, limit=limit)
        except requests.RequestException:
            continue  # série inexistente para esse ativo — ignora
        for ev in events:
            for mjson in ev.get("markets", []):
                m = _parse_market(mjson, timeframe)
                if m.id in seen:
                    continue
                if not m.accepting_orders:
                    continue
                if m.end_date and m.end_date <= now:
                    continue
                seen.add(m.id)
                out.append(m)

    out.sort(key=lambda m: m.end_date or datetime.max.replace(tzinfo=timezone.utc))
    return out


def token_id_for_outcome(m: Market, outcome: str) -> Optional[str]:
    """Retorna o clobTokenId correspondente a um outcome (ex.: 'Up')."""
    for tok, out in zip(m.token_ids, m.outcomes):
        if out.lower() == outcome.lower():
            return tok
    return None

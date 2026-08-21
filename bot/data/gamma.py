"""Acesso à Gamma API (catálogo de mercados) — sem autenticação.

Fonte: https://gamma-api.polymarket.com
Retorna mercados binários com clobTokenIds, prices, book básico, fees, etc.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import requests

from bot.config import Settings

# "Bitcoin Up or Down - August 21, 9AM ET"  /  "Ethereum Up or Down ..."
_UP_DOWN_RE = re.compile(r"^\s*(Bitcoin|Ethereum|Solana|Xrp|XRP)\s+Up or Down\b", re.I)
# "Bitcoin above 76,600 on August 21, 10AM ET?"
_ABOVE_RE = re.compile(r"^\s*(Bitcoin|Ethereum|Solana|Xrp|XRP)\s+above\b", re.I)


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
    end_date_iso: str
    active: bool
    min_size: float               # orderMinSize (shares)
    min_tick: float               # orderPriceMinTickSize
    fees_enabled: bool
    taker_fee_rate: float         # fração (ex.: 0.04 = 4%)


def _parse(json_m: dict) -> Market:
    import json as _json
    outcomes = _json.loads(json_m.get("outcomes", '["Yes","No"]'))
    token_ids = _json.loads(json_m.get("clobTokenIds", "[]"))
    prices = _json.loads(json_m.get("outcomePrices", "[]"))
    fee = json_m.get("feeSchedule") or {}
    return Market(
        id=json_m.get("id", ""),
        question=json_m.get("question", ""),
        condition_id=json_m.get("conditionId", ""),
        outcomes=outcomes,
        token_ids=token_ids,
        outcome_prices=[float(p) for p in prices],
        best_bid=float(json_m.get("bestBid", 0) or 0),
        best_ask=float(json_m.get("bestAsk", 0) or 0),
        end_date_iso=json_m.get("endDateIso", ""),
        active=bool(json_m.get("active", False)),
        min_size=float(json_m.get("orderMinSize", 5)),
        min_tick=float(json_m.get("orderPriceMinTickSize", 0.001)),
        fees_enabled=bool(json_m.get("feesEnabled", False)),
        taker_fee_rate=float(fee.get("rate", 0)),
    )


def fetch_markets(
    s: Settings,
    coin: Optional[str] = None,
    kind: str = "updown",  # "updown" | "above" | "any"
    limit: int = 200,
) -> list[Market]:
    """Busca mercados ativos de cripto Up/Down (ou above) da Gamma API."""
    coin = coin or s.coin
    params = {"active": "true", "closed": "false", "limit": limit}
    resp = requests.get(f"{s.gamma_host}/markets", params=params, timeout=15)
    resp.raise_for_status()
    raw = resp.json()

    out: list[Market] = []
    for m in raw:
        q = m.get("question", "")
        if kind == "updown" and not _UP_DOWN_RE.match(q):
            continue
        if kind == "above" and not _ABOVE_RE.match(q):
            continue
        if coin.lower() not in q.lower():
            continue
        out.append(_parse(m))
    return out


def token_id_for_outcome(m: Market, outcome: str) -> Optional[str]:
    """Retorna o clobTokenId correspondente a um outcome (ex.: 'Up'/'Yes')."""
    for tok, out in zip(m.token_ids, m.outcomes):
        if out.lower() == outcome.lower():
            return tok
    return None

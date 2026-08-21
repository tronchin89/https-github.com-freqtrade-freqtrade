"""Acesso ao CLOB (orderbook / preços) — sem autenticação.

Fonte: https://clob.polymarket.com
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

from bot.config import Settings


@dataclass
class Book:
    token_id: str
    best_bid: float
    best_ask: float
    mid: float
    spread: float
    last_trade_price: float = 0.0


def get_book(s: Settings, token_id: str) -> Book:
    resp = requests.get(f"{s.clob_host}/book", params={"token_id": token_id}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    bids = data.get("bids") or []
    asks = data.get("asks") or []
    # IMPORTANTE: a API retorna os níveis em ordem "profunda primeiro", ou seja,
    # bids[0] é o MENOR bid e asks[0] é o MAIOR ask. O melhor bid é o MÁXIMO
    # preço de compra; o melhor ask é o MÍNIMO preço de venda.
    best_bid = max((float(b["price"]) for b in bids), default=0.0)
    best_ask = min((float(a["price"]) for a in asks), default=0.0)
    mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0
    last_trade = float(data.get("last_trade_price", 0) or 0)
    return Book(token_id, best_bid, best_ask, mid, best_ask - best_bid, last_trade)


def get_price(s: Settings, token_id: str, side: str = "buy") -> float:
    """Preço que você pagaria/receberia (cruza o spread) para uma side."""
    resp = requests.get(
        f"{s.clob_host}/price",
        params={"token_id": token_id, "side": side},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return float(data.get("price", 0) or 0)


def get_midpoint(s: Settings, token_id: str) -> float:
    resp = requests.get(
        f"{s.clob_host}/midpoint", params={"token_id": token_id}, timeout=10
    )
    resp.raise_for_status()
    return float(resp.json().get("mid", 0) or 0)

"""Backtest (F2) — testa se "comprar o lado 'Up' barato" tem edge.

HIPÓTESE (mean-reversion): quando o token 'Up' de um mercado Up/Down fica
depreciado (preço baixo), ele é temporariamente subprecificado e reverte.
Se isso for verdade, comprar 'Up' quando o preço cruza abaixo de um limiar T
deveria vencer com frequência MAIOR que T (preço implícito).

O que o backtest faz, para cada mercado já resolvido:
  1. identifica quem venceu (Up ou Down) via outcomePrices resolvido;
  2. baixa o histórico de preço do token 'Up' (prices-history, minuto a minuto);
  3. simula: "compra quando o preço cruza abaixo de T pela 1ª vez";
  4. para vários T, calcula win rate e valor esperado (EV), com e sem a
     taxa de taker (7%).

Resultado honesto: se win_rate(T) > T, há edge; se > T * (1 + fee), o edge
sobrevive às taxas.

USO (na sua máquina, com rede):
    python -m bot.backtest
    # opcional: python -m bot.backtest --coin bitcoin --timeframes 1h,15m --limit 200
"""
from __future__ import annotations

import argparse
import json as _json
import time
from dataclasses import dataclass
from typing import Optional

import requests

from bot.config import Settings, get_settings
from bot.data.gamma import SERIES_BY_COIN, token_id_for_outcome, _parse_market


# --------------------------------------------------------------------------- #
# Dados
# --------------------------------------------------------------------------- #

def _loads(value, default):
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return _json.loads(value)
    except (TypeError, ValueError):
        return default


def fetch_closed_markets(s: Settings, coin: str, timeframes, limit: int,
                         end_date_min: str, end_date_max: str):
    """Mercados já resolvidos (recentes), com token 'Up' e histórico de preço.

    Usa `end_date_min/max` para pegar só mercados que resolveram no período
    (sem filtro, `closed=true` retorna mercados antigos primeiro).
    Pagina com offset até atingir `limit` por série.
    """
    coin = coin.strip().lower()
    slugs = SERIES_BY_COIN.get(coin, {})
    out = []
    seen = set()
    # A API da Gamma cap ~100 eventos por página (independente do `limit` pedido).
    page_size = 100
    for tf in timeframes:
        slug = slugs.get(tf)
        if not slug:
            continue
        offset = 0
        collected = 0
        while collected < limit:
            params = {
                "series_slug": slug,
                "closed": "true",
                "end_date_min": end_date_min,
                "end_date_max": end_date_max,
                "limit": page_size,
                "offset": offset,
            }
            try:
                resp = requests.get(f"{s.gamma_host}/events", params=params, timeout=20)
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"  [aviso] série {slug}: {e!r}")
                break
            events = resp.json()
            if not events:
                break
            for ev in events:
                for mjson in ev.get("markets", []):
                    m = _parse_market(mjson, tf)
                    if m.id in seen or not m.token_ids:
                        continue
                    seen.add(m.id)
                    out.append((m, mjson))
                    collected += 1
            # página cheia => continua; senão terminou a série
            if len(events) < page_size:
                break
            offset += page_size
            time.sleep(0.1)  # gentileza com a API entre páginas
    return out


def up_won(mjson: dict, m) -> Optional[bool]:
    """Retorna True se 'Up' venceu, False se 'Down', None se não dá para saber."""
    prices = _loads(mjson.get("outcomePrices"), [])
    outcomes = _loads(mjson.get("outcomes"), ["Up", "Down"])
    if len(prices) == 2:
        try:
            p0, p1 = float(prices[0]), float(prices[1])
        except (TypeError, ValueError):
            p0 = p1 = -1
        # resolvido: um lado = 1, o outro = 0
        if p0 == 1 and p1 == 0:
            return outcomes[0].lower() == "up"
        if p0 == 0 and p1 == 1:
            return outcomes[1].lower() == "up"
    # fallback: eventMetadata finalPrice vs priceToBeat
    meta = ev_meta(mjson)
    if meta:
        final = meta.get("finalPrice")
        beat = meta.get("priceToBeat")
        if final is not None and beat is not None:
            return float(final) >= float(beat)
    return None


def ev_meta(mjson: dict) -> dict:
    ev = (mjson.get("events") or [{}])
    meta = ev[0].get("eventMetadata") if ev else None
    return meta or {}


def fetch_price_history(s: Settings, token_id: str) -> list[tuple[int, float]]:
    """Histórico de preço do token (t: timestamp, p: preço).

    Usa `interval=max` para pegar o histórico COMPLETO do token (com `1d`
    só vem a última janela, que fica vazia para mercados já resolvidos).
    """
    resp = requests.get(
        f"{s.clob_host}/prices-history",
        params={"market": token_id, "interval": "max", "fidelity": 1},
        timeout=20,
    )
    resp.raise_for_status()
    hist = resp.json().get("history") or []
    out = []
    for pt in hist:
        try:
            out.append((int(pt["t"]), float(pt["p"])))
        except (KeyError, ValueError):
            continue
    out.sort()
    return out


# --------------------------------------------------------------------------- #
# Simulação
# --------------------------------------------------------------------------- #

@dataclass
class MarketSample:
    question: str
    timeframe: str
    up_won: bool
    history: list[tuple[int, float]]  # (t, p) ordenado


def collect_samples(s: Settings, coin: str, timeframes, limit: int,
                    end_date_min: str, end_date_max: str) -> list[MarketSample]:
    markets = fetch_closed_markets(s, coin, timeframes, limit, end_date_min, end_date_max)
    samples: list[MarketSample] = []
    for m, mjson in markets:
        won = up_won(mjson, m)
        if won is None:
            continue
        tok = token_id_for_outcome(m, "Up")
        if not tok:
            continue
        try:
            hist = fetch_price_history(s, tok)
        except requests.RequestException:
            continue
        if len(hist) < 5:
            continue
        samples.append(MarketSample(m.question, m.timeframe, won, hist))
        time.sleep(0.03)  # gentileza com a API
    return samples


def first_cross_below(history: list[tuple[int, float]], threshold: float):
    """Retorna o índice da 1ª vez que o preço caiu <= threshold (ou None)."""
    for i, (_, p) in enumerate(history):
        if p <= threshold:
            return i
    return None


def run_backtest(samples: list[MarketSample], thresholds, taker_fee: float = 0.07):
    """Para cada limiar T, simula compra na 1ª queda <= T e segura até resolver."""
    print("\n" + "=" * 66)
    print(f"BACKTEST — amostra de {len(samples)} mercados resolvidos")
    print("Estratégia: comprar 'Up' quando preço <= T (1ª queda), segurar até resolver")
    print(f"Taxa de taker (compra): {taker_fee:.0%}")
    print("=" * 66)
    print(f"{'T':>6} | {'#trades':>7} | {'win%':>6} | {'EV(fee=0)':>9} | {'EV(fee)':>8} | veredito")

    for T in thresholds:
        wins = 0
        trades = 0
        for s in samples:
            i = first_cross_below(s.history, T)
            if i is None:
                continue
            trades += 1
            if s.up_won:
                wins += 1
        if trades < 10:
            continue
        win_rate = wins / trades
        # EV por $1 apostado, segurando até a resolução:
        #   ganha $1 com prob win_rate, perde tudo com prob (1-win_rate).
        #   Custo de comprar 1 share = T (+ fee de taker sobre o notional).
        ev_gross = win_rate - T
        ev_net = win_rate - T * (1 + taker_fee)
        verdict = "EDGE" if ev_net > 0 else ("marginal" if ev_gross > 0 else "sem edge")
        print(f"{T:>6.2f} | {trades:>7} | {win_rate:>6.1%} | "
              f"{ev_gross:>+9.4f} | {ev_net:>+8.4f} | {verdict}")

    print("\n(win% > T  => o 'Up' barato vence mais que o preço sugere = edge)")
    print("(EV(fee) > 0 => o edge sobrevive à taxa de 7% de taker)")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coin", default="bitcoin")
    parser.add_argument("--timeframes", default="1h,15m")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--days", type=int, default=14,
                        help="janela de mercados resolvidos (dias para trás)")
    args = parser.parse_args()

    from datetime import datetime, timedelta, timezone
    s = get_settings()
    timeframes = [t.strip() for t in args.timeframes.split(",")]
    thresholds = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]

    now = datetime.now(timezone.utc)
    end_date_max = now.strftime("%Y-%m-%d")
    end_date_min = (now - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"Coletando mercados resolvidos de {args.coin} "
          f"({', '.join(timeframes)}) nos últimos {args.days} dias ...")
    samples = collect_samples(s, args.coin, timeframes, args.limit,
                              end_date_min, end_date_max)
    print(f"amostra válida: {len(samples)} mercados")

    if not samples:
        print("Nada para avaliar — verifique rede/parâmetros.")
        return

    from collections import Counter
    tf = Counter(x.timeframe for x in samples)
    print("por timeframe:", dict(tf))

    run_backtest(samples, thresholds, taker_fee=0.07)


if __name__ == "__main__":
    main()

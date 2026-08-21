"""Backtest (F3) — testa o FAVORITE-LONGSHOT BIAS em Politics / Sports.

Hipótese (a mais documentada na literatura de prediction markets):
  - Longshots (preço 5-30¢) são SUPERPRECIFICADOS: vencem menos que o preço.
  - Favoritos (80-95¢) são SUBPRECIFICADOS: vencem mais que o preço.
  => Comprar o favorito e/ou comprar "No" no longshot deveria ter EV positivo.

Como testamos (sem dataset em disco, usando a Gamma API):
  1. Coleta mercados RESOLVIDOS da categoria (politics / sports) via tag_slug.
  2. Determina quem venceu (Yes/No) pelo outcomePrices resolvido.
  3. Baixa o histórico de preço do token "Yes" (prices-history, minuto a minuto).
  4. Toma o preço de referência `lookback` minutos ANTES da resolução
     (ponto realmente negociável, sem lookahead bias).
  5. Calibração: agrupa por decil de preço e compara win rate real vs preço.
  6. Estratégia: "comprar favorito (>= T_high)" e "comprar No em longshot
     (<= T_low)", segurando até resolver, com EV líquido de taxa dinâmica.

USO:
    python -m bot.backtest_flb                       # sports, 1h antes da resolução
    python -m bot.backtest_flb --tag politics
    python -m bot.backtest_flb --tag sports --lookback 360 --days 45
"""
from __future__ import annotations

import argparse
import json as _json
import time
from datetime import datetime, timedelta, timezone

import requests

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bot.config import Settings, get_settings

# Sessão com retry/backoff (Polymarket está atrás de Cloudflare e às vezes
# reseta conexões; retry aguenta resets transitórios na máquina do usuário).
def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
        "Accept": "application/json",
    })
    return s

# taxa de taker por categoria (pico, a $0.50). Fonte: fee schedule Polymarket.
TAG_FEE_RATE = {
    "politics": 0.04,
    "sports": 0.05,
    "economics": 0.05,
    "crypto": 0.07,
}


def _loads(value, default):
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return _json.loads(value)
    except (TypeError, ValueError):
        return default


def _day_range(start: str, end: str):
    from datetime import timedelta as _td
    d0 = datetime.strptime(start, "%Y-%m-%d")
    d1 = datetime.strptime(end, "%Y-%m-%d")
    cur = d0
    while cur <= d1:
        day = cur.strftime("%Y-%m-%d")
        yield day, day
        cur += _td(days=1)


def fetch_tag_markets(s: Settings, tag: str, end_min: str, end_max: str, limit: int):
    """Mercados resolvidos binários da tag, paginando por dia (evita offset alto)."""
    out = []
    seen = set()
    session = _session()
    for day_min, day_max in _day_range(end_min, end_max):
        if len(out) >= limit:
            break
        params = {
            "tag_slug": tag,
            "closed": "true",
            "end_date_min": day_min,
            "end_date_max": day_max,
            "limit": 100,
            "offset": 0,
        }
        try:
            resp = session.get(f"{s.gamma_host}/events", params=params, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [aviso] {tag} {day_min}: {e!r}")
            continue
        for ev in resp.json():
            for mjson in ev.get("markets", []):
                outcomes = _loads(mjson.get("outcomes"), [])
                tokens = _loads(mjson.get("clobTokenIds"), [])
                # só mercados binários simples (2 outcomes, 2 tokens)
                if len(outcomes) != 2 or len(tokens) != 2:
                    continue
                mid = mjson.get("id")
                if mid in seen:
                    continue
                seen.add(mid)
                out.append(mjson)
        time.sleep(0.05)
    return out


def yes_won(mjson: dict) -> bool | None:
    """True se 'Yes' venceu, False se 'No', None se indeterminado."""
    prices = _loads(mjson.get("outcomePrices"), [])
    outcomes = _loads(mjson.get("outcomes"), ["Yes", "No"])
    if len(prices) == 2:
        try:
            p0, p1 = float(prices[0]), float(prices[1])
        except (TypeError, ValueError):
            p0 = p1 = -1
        if p0 == 1 and p1 == 0:
            return outcomes[0].lower() == "yes"
        if p0 == 0 and p1 == 1:
            return outcomes[1].lower() == "yes"
    return None


def fetch_price_history(s: Settings, token_id: str) -> list[tuple[int, float]]:
    resp = _session().get(
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


def reference_price(hist: list[tuple[int, float]], lookback_min: int) -> float | None:
    """Preço `lookback_min` minutos antes do último ponto (ponto negociável)."""
    if not hist:
        return None
    target_t = hist[-1][0] - lookback_min * 60
    # pega o ponto mais próximo ANTES ou igual a target_t (sem lookahead)
    best = None
    for t, p in hist:
        if t <= target_t:
            best = p
        else:
            break
    if best is None:
        # histórico muito curto: usa o primeiro preço disponível
        best = hist[0][1]
    return best


def taker_fee_frac(price: float, rate: float) -> float:
    p = max(0.0, min(1.0, price))
    return rate * (1 - p)


def run(samples, tag, lookback_min, rate):
    """Calibração por decil + estratégias favorito/longshot."""
    n = len(samples)
    print("\n" + "=" * 72)
    print(f"FAVORITE-LONGSHOT BIAS — tag={tag}  amostra={n}  "
          f"ref={lookback_min}m antes da resolução")
    print(f"taxa taker (pico) = {rate:.0%}  (dinâmica: rate*(1-p))")
    print("=" * 72)

    # ---- calibração por decil ----
    buckets: dict[int, list] = {}
    for q, tf, won, ref in samples:
        if ref is None:
            continue
        dec = int(ref * 10)  # 0..9
        dec = min(9, max(0, dec))
        buckets.setdefault(dec, []).append((ref, won))

    print(f"\n{'decil':>6} | {'n':>5} | {'preço médio':>11} | {'win real':>9} | {'bias':>7}")
    print("-" * 72)
    for dec in range(10):
        if dec not in buckets:
            continue
        rows = buckets[dec]
        mean_p = sum(r[0] for r in rows) / len(rows)
        win = sum(1 for r in rows if r[1]) / len(rows)
        bias = win - mean_p
        print(f"{dec*10:>3}-{(dec+1)*10:>3} | {len(rows):>5} | {mean_p:>11.3f} | "
              f"{win:>9.2%} | {bias:>+7.3f}")

    print("\n(bias > 0 => vence MAIS que o preço [subprecificado]; bias < 0 => vence MENOS [superprecificado])")
    print("Longshot bias clássico: decil baixo com bias < 0, decil alto com bias > 0.")

    # ---- estratégias ----
    print("\n" + "-" * 72)
    print("ESTRATÉGIAS (segurar até resolver, EV líquido de taxa):")
    for name, lo, hi, buy_yes in (
        ("Comprar FAVORITO  (Yes >= 0.80)", 0.80, 0.95, True),
        ("Fadar LONGSHOT     (Yes <= 0.20 => compra No)", 0.05, 0.20, False),
        ("Comprar FAVORITO+  (Yes >= 0.90)", 0.90, 0.99, True),
    ):
        pnls = []
        wins = 0
        trades = 0
        for q, tf, won, ref in samples:
            if ref is None or ref < lo or ref > hi:
                continue
            # preço do lado que compramos
            entry = ref if buy_yes else (1 - ref)
            side_won = won if buy_yes else (not won)
            fee = taker_fee_frac(entry, rate)
            pnl = (1 - entry * (1 + fee)) if side_won else (-entry * (1 + fee))
            pnls.append(pnl)
            trades += 1
            if pnl > 0:
                wins += 1
        if trades < 10:
            print(f"  {name:<34}: trades={trades} (insuficiente)")
            continue
        ev = sum(pnls) / trades
        wr = wins / trades
        print(f"  {name:<34}: trades={trades:>4}  win%={wr:>5.1%}  EV={ev:+.4f}")

    print("\n(EV > 0 => estratégia lucrativa líquida de taxa, nesta amostra.)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="sports", choices=["sports", "politics", "economics", "crypto"])
    parser.add_argument("--lookback", type=int, default=60, help="minutos antes da resolução")
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--limit", type=int, default=1500)
    args = parser.parse_args()

    s = get_settings()
    now = datetime.now(timezone.utc)
    end_max = now.strftime("%Y-%m-%d")
    end_min = (now - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"Coletando mercados resolvidos [{args.tag}] nos últimos {args.days} dias ...")
    markets = fetch_tag_markets(s, args.tag, end_min, end_max, args.limit)
    print(f"mercados binários resolvidos: {len(markets)}")

    samples = []
    for mjson in markets:
        won = yes_won(mjson)
        if won is None:
            continue
        tokens = _loads(mjson.get("clobTokenIds"), [])
        yes_tok = tokens[0] if _loads(mjson.get("outcomes"), ["Yes", "No"])[0].lower() == "yes" else tokens[1]
        try:
            hist = fetch_price_history(s, yes_tok)
        except requests.RequestException:
            continue
        if len(hist) < 3:
            continue
        ref = reference_price(hist, args.lookback)
        samples.append((mjson.get("question", ""), None, won, ref))
        time.sleep(0.03)

    print(f"amostra com preço de referência válido: {len(samples)}")
    if not samples:
        print("Nada para avaliar.")
        return
    rate = TAG_FEE_RATE.get(args.tag, 0.05)
    run(samples, args.tag, args.lookback, rate)


if __name__ == "__main__":
    main()

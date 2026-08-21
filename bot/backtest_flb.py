"""Backtest (F3) — testa o FAVORITE-LONGSHOT BIAS em Politics / Sports.

Hipótese (a mais documentada na literatura de prediction markets):
  - Longshots (preço 5-30¢) são SUPERPRECIFICADOS: vencem menos que o preço.
  - Favoritos (80-95¢) são SUBPRECIFICADOS: vencem mais que o preço.
  => Comprar o favorito e/ou comprar "No" no longshot deveria ter EV positivo.

Como testamos (sem dataset em disco, usando a Gamma API):
  1. Coleta mercados RESOLVIDOS da categoria (politics / sports) via
     `order=closedTime&ascending=false` + offset (mais recentes primeiro).
     NOTA: filtrar por `end_date` NÃO serve — `endDate` é o prazo AGENDADO,
     não a data de resolução; e `end_date_min == end_date_max` dá 422.
  2. Determina quem venceu (Yes/No) pelo outcomePrices resolvido.
  3. Baixa o histórico de preço do token "Yes" (prices-history).
  4. Toma o preço de referência `lookback` minutos ANTES da resolução
     (ancorado no `closedTime` real, sem lookahead bias).
  5. Calibração: agrupa por decil de preço e compara win rate real vs preço.
  6. Estratégia: comprar favorito / fadar longshot, segurando até resolver,
     com taxa taker dinâmica correta: fee = feeRate * p * (1-p)  (exponent=1).

USO:
    python -m bot.backtest_flb                       # sports, 1h antes da resolução
    python -m bot.backtest_flb --tag politics
    python -m bot.backtest_flb --tag sports --lookback 360 --days 45
"""
from __future__ import annotations

import argparse
import json as _json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bot.config import Settings, get_settings

# taxa de taker por categoria (fallback; pico a $0.50). O ideal é ler
# feeSchedule.rate de cada mercado (V3 usa exponent=1 na maioria).
TAG_FEE_RATE = {
    "politics": 0.05,
    "sports": 0.05,
    "economics": 0.05,
    "crypto": 0.07,
}


def _session() -> requests.Session:
    """Sessão com retry/backoff (Polymarket está atrás de Cloudflare)."""
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


def _loads(value, default):
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return _json.loads(value)
    except (TypeError, ValueError):
        return default


def _parse_ts(value):
    """Timestamp unix (segundos) a partir de `closedTime` / `umaEndDate`."""
    if not value:
        return None
    value = str(value).strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S%z").timestamp()
    except ValueError:
        return None


def _outcomes(mjson):
    return [str(o).lower() for o in _loads(mjson.get("outcomes"), [])]


def _tokens(mjson):
    return [str(t) for t in _loads(mjson.get("clobTokenIds"), [])]


def is_yesno(mjson) -> bool:
    outs = _outcomes(mjson)
    return len(outs) == 2 and len(_tokens(mjson)) == 2 and "yes" in outs and "no" in outs


def yes_won(mjson) -> bool | None:
    """True se 'Yes' venceu, False se 'No', None se não-Yes/No ou indefinido."""
    if not is_yesno(mjson):
        return None
    prices = _loads(mjson.get("outcomePrices"), [])
    if len(prices) != 2:
        return None
    try:
        p0, p1 = float(prices[0]), float(prices[1])
    except (TypeError, ValueError):
        return None
    if p0 == 1 and p1 == 0:
        return _outcomes(mjson)[0] == "yes"
    if p0 == 0 and p1 == 1:
        return _outcomes(mjson)[1] == "yes"
    return None


def yes_token_id(mjson) -> str | None:
    outs = _outcomes(mjson)
    toks = _tokens(mjson)
    for tok, out in zip(toks, outs):
        if out == "yes":
            return tok
    return None


def market_fee(mjson, tag: str) -> tuple[float, float]:
    """(feeRate, exponent) do mercado; 0 se fee não habilitado."""
    if not mjson.get("feesEnabled"):
        return 0.0, 1.0
    fs = mjson.get("feeSchedule") or {}
    rate = float(fs.get("rate", TAG_FEE_RATE.get(tag, 0.05)))
    exponent = float(fs.get("exponent", 1.0))
    return rate, exponent


def fetch_tag_markets(s: Settings, tag: str, cutoff_ts: float, limit: int):
    """Mercados resolvidos Yes/No da tag, mais recentes primeiro, até `cutoff_ts`.

    Usa `order=closedTime&ascending=false` + offset (NÃO filtra por end_date:
    endDate é o prazo agendado, e ranges vazios dão 422). Para de paginar ao
    passar de `cutoff_ts` ou ao atingir `limit`.
    """
    session = _session()
    out = []
    seen = set()
    page = 100
    offset = 0
    max_offset = 10000  # trava de segurança; para gracefulmente se passar

    while offset <= max_offset and len(out) < limit:
        params = {
            "tag_slug": tag,
            "closed": "true",
            "order": "closedTime",
            "ascending": "false",
            "limit": page,
            "offset": offset,
        }
        try:
            resp = session.get(f"{s.gamma_host}/events", params=params, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [aviso] offset={offset}: {e!r}")
            break
        events = resp.json()
        if not events:
            break

        oldest_ts = None
        for ev in events:
            for mjson in ev.get("markets", []):
                if not is_yesno(mjson):
                    continue
                mid = mjson.get("id")
                if mid in seen:
                    continue
                res_ts = _parse_ts(mjson.get("umaEndDate") or mjson.get("closedTime"))
                if res_ts is None:
                    continue
                if oldest_ts is None or res_ts < oldest_ts:
                    oldest_ts = res_ts
                seen.add(mid)
                out.append((mjson, res_ts))
        # se a página mais antiga já é anterior ao cutoff, paramos
        if oldest_ts is not None and oldest_ts < cutoff_ts:
            break
        offset += page
        time.sleep(0.05)

    # filtra de fato pelo cutoff (só mercados resolvidos dentro da janela)
    filtered = [(m, t) for (m, t) in out if t >= cutoff_ts]
    filtered.sort(key=lambda x: -x[1])  # mais recente primeiro
    return filtered


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


def reference_price(hist: list[tuple[int, float]], res_ts: float, lookback_min: int,
                    max_stale_min: float | None = None) -> float | None:
    """Preço `lookback_min` minutos antes da resolução (ponto negociável).

    Se `max_stale_min` for dado, rejeita (retorna None) quando o último trade
    antes do ponto de referência é MAIS antigo que `max_stale_min` minutos —
    isto é, quando o preço está "stale" (mercado ilíquido, não negociável na
    prática). Sem esse filtro, favoritos/longshots ilíquidos perto da resolução
    viram "vencer 100%" / "vencer 0%", inflando o EV de forma irreal.
    """
    if not hist:
        return None
    target_t = res_ts - lookback_min * 60
    best_t = best_p = None
    for t, p in hist:
        if t <= target_t:
            best_t, best_p = t, p
        else:
            break
    if best_p is None:
        best_t, best_p = hist[0]
    if max_stale_min is not None and (target_t - best_t) > max_stale_min * 60:
        return None
    return best_p


class PriceCache:
    """Cache em disco do histórico de preço por token (evita re-baixar)."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, list] = {}
        if path and os.path.exists(path):
            try:
                with open(path) as fh:
                    raw = _json.load(fh)
                if isinstance(raw, dict):
                    self._data = {k: [[int(t), float(p)] for t, p in v] for k, v in raw.items()}
            except (ValueError, OSError):
                self._data = {}

    def get(self, token_id: str):
        with self._lock:
            return self._data.get(token_id)

    def set(self, token_id: str, hist):
        with self._lock:
            self._data[token_id] = [[int(t), float(p)] for t, p in hist]

    def save(self):
        if not self.path:
            return
        with self._lock:
            data = dict(self._data)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            _json.dump(data, fh)
        os.replace(tmp, self.path)


def fee_fraction(price: float, rate: float, exponent: float = 1.0) -> float:
    """Taxa taker como fração do notional (fórmula V3).

    fee = C * p * feeRate * (p*(1-p))^exponent  =>  fee/notional = rate*(p*(1-p))^exponent.
    """
    p = max(0.0, min(1.0, price))
    return rate * (p * (1 - p)) ** exponent


def simulate_hold(entry: float, won: bool, rate: float, exponent: float) -> float:
    """PnL (por $1 de face) de comprar a `entry` e segurar até resolver."""
    fee = fee_fraction(entry, rate, exponent)
    cost = entry * (1 + fee)
    return (1 - cost) if won else (-cost)


def run(samples, tag, lookback_min):
    """Calibração por decil + estratégias favorito/longshot."""
    n = len(samples)
    print("\n" + "=" * 72)
    print(f"FAVORITE-LONGSHOT BIAS — tag={tag}  amostra={n}  "
          f"ref={lookback_min}m antes da resolução")
    print("taxa taker dinâmica: fee = feeRate * p * (1-p)   (feeRate lida do feeSchedule)")
    print("=" * 72)

    # ---- calibração por decil (preço do 'Yes' vs win rate real do 'Yes') ----
    buckets: dict[int, list] = {}
    for s in samples:
        if s.ref is None:
            continue
        dec = int(s.ref * 10)
        dec = min(9, max(0, dec))
        buckets.setdefault(dec, []).append((s.ref, s.won))

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

    print("\n(bias > 0 => 'Yes' vence MAIS que o preço [subprecificado]; bias < 0 => vence MENOS [superprecificado])")
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
        for s in samples:
            if s.ref is None or s.ref < lo or s.ref > hi:
                continue
            entry = s.ref if buy_yes else (1 - s.ref)
            side_won = s.won if buy_yes else (not s.won)
            pnl = simulate_hold(entry, side_won, s.rate, s.exponent)
            pnls.append(pnl)
            if pnl > 0:
                wins += 1
        if len(pnls) < 10:
            print(f"  {name:<44}: trades={len(pnls)} (insuficiente)")
            continue
        ev = sum(pnls) / len(pnls)
        wr = wins / len(pnls)
        print(f"  {name:<44}: trades={len(pnls):>4}  win%={wr:>5.1%}  EV={ev:+.4f}")

    print("\n(EV > 0 => estratégia lucrativa líquida de taxa, nesta amostra.)")


def _process_one(item, s: Settings, tag: str, lookback: int, max_stale: float | None,
                 cache: PriceCache):
    """Processa um mercado. Retorna (kind, Sample|None); kind in {ok, stale, skip}."""
    mjson, res_ts = item
    won = yes_won(mjson)
    if won is None:
        return ("skip", None)
    tok = yes_token_id(mjson)
    if not tok:
        return ("skip", None)
    hist = cache.get(tok)
    if hist is None:
        try:
            hist = fetch_price_history(s, tok)
        except requests.RequestException:
            return ("skip", None)
        cache.set(tok, hist)
    if len(hist) < 3:
        return ("skip", None)
    ref = reference_price(hist, res_ts, lookback, max_stale)
    if ref is None:
        return ("stale", None)
    rate, exponent = market_fee(mjson, tag)
    return ("ok", Sample(mjson.get("question", ""), won, ref, rate, exponent))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="sports", choices=["sports", "politics", "economics", "crypto"])
    parser.add_argument("--lookback", type=int, default=60, help="minutos antes da resolução")
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--limit", type=int, default=3000)
    parser.add_argument("--workers", type=int, default=8, help="threads p/ baixar histórico de preço")
    parser.add_argument("--cache", default="flb_price_cache.json", help="cache de histórico ('' desliga)")
    parser.add_argument("--max-stale-min", type=float, default=30,
                        help="rejeita preço se o último trade é >N min antes do ponto de ref (0=desliga)")
    args = parser.parse_args()

    max_stale = args.max_stale_min if args.max_stale_min > 0 else None

    s = get_settings()
    now = datetime.now(timezone.utc)
    cutoff_ts = (now - timedelta(days=args.days)).timestamp()

    print(f"Coletando mercados resolvidos [{args.tag}] (últimos {args.days} dias) ...")
    markets = fetch_tag_markets(s, args.tag, cutoff_ts, args.limit)
    print(f"mercados Yes/No resolvidos na janela: {len(markets)}")

    cache = PriceCache(args.cache or "")
    if cache._data:
        print(f"cache de preço: {len(cache._data)} tokens já em disco")

    samples = []
    n_ok = n_stale = n_skip = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (kind, smp) in enumerate(pool.map(
            lambda it: _process_one(it, s, args.tag, args.lookback, max_stale, cache), markets
        )):
            if kind == "ok":
                samples.append(smp)
                n_ok += 1
            elif kind == "stale":
                n_stale += 1
            else:
                n_skip += 1
            if (i + 1) % 500 == 0:
                print(f"  ... {i + 1}/{len(markets)} processados (ok={n_ok} stale={n_stale} skip={n_skip})")

    cache.save()
    print(f"amostra válida: {n_ok}   descartados por preço stale: {n_stale}   outros: {n_skip}")
    if not samples:
        print("Nada para avaliar.")
        return
    run(samples, args.tag, args.lookback)


class Sample:
    __slots__ = ("question", "won", "ref", "rate", "exponent")

    def __init__(self, question, won, ref, rate, exponent):
        self.question = question
        self.won = won          # 'Yes' venceu?
        self.ref = ref          # preço do 'Yes' no ponto de referência
        self.rate = rate        # feeRate do mercado
        self.exponent = exponent


if __name__ == "__main__":
    main()

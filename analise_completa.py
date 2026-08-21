#!/usr/bin/env python3
"""
Análise quantitativa da conta Polymarket
0xb55fa1296e6ec55d0ce53d93b9237389f11764d4  (Lively-Authenticity)

Dados: amostra de posições retiradas de data-api.polymarket.com/positions
(offset 0/100/200) em 2026-08-21. Amostra = posições fechadas/resolvidas
+ algumas abertas. NAO é o histórico completo (106k+ trades), mas é uma
amostra representativa para caracterizar a estratégia.

Importante: vencedores são RESGATADOS (evento REDEEM) e saem da lista de
posições ativas, portanto a lista é enviesada para perdedores. A win-rate
real é melhor medida via contagem REDEEM vs mercados perdidos.
"""

# (tipo_mercado, outcome, initial_value_usd, cash_pnl_usd, avg_price, status)
# status: 'lost' (value 0), 'open'
POSICOES = [
    # --- offset 0 (primeiras) ---
    ("updown", "Up",   2954.72, -2954.72, 0.5696, "lost"),   # BTC 4h 19/08
    ("updown", "Down",  634.98,  -634.98, 0.2042, "lost"),   # BTC 15m 06/07
    ("updown", "Down",  595.38,  -595.38, 0.2314, "lost"),
    ("updown", "Down",  515.17,  -515.17, 0.2102, "lost"),
    ("updown", "Down",  501.80,  -501.80, 0.2225, "lost"),
    ("updown", "Down",  706.64,  -706.64, 0.3219, "lost"),
    ("above",  "No",      2.96,    -2.96, 0.0015, "lost"),
    ("above",  "No",     22.50,   -22.50, 0.0114, "lost"),
    ("above",  "No",      3.22,    -3.22, 0.0016, "lost"),
    ("updown", "Up",    296.81,  -295.85, 0.1535, "open"),   # BTC 7AM 21/08 (-99.67%)
    ("updown", "Up",   1846.30,   -73.20, 0.3904, "open"),   # BTC 9AM 21/08 (-3.96%)

    # --- offset 100 ---
    ("updown", "Down",  145.43,  -145.43, 0.1772, "lost"),
    ("updown", "Up",    199.58,  -199.58, 0.2457, "lost"),
    ("updown", "Up",     45.56,   -45.56, 0.0566, "lost"),
    ("updown", "Up",    208.91,  -208.91, 0.2658, "lost"),   # ETH
    ("updown", "Up",     94.31,   -94.31, 0.1201, "lost"),   # ETH
    ("updown", "Up",    197.83,  -197.83, 0.2562, "lost"),
    ("above",  "No",    168.24,   +73.99, 0.2187, "open"),   # BTC >76.600 10AM (+43.98%)
    ("updown", "Up",    316.87,  -316.87, 0.4145, "lost"),   # ETH
    ("updown", "Up",    197.44,  -197.44, 0.2587, "lost"),   # ETH

    # --- offset 200 (loteria "above X", tickets ~0.001-0.015) ---
    ("above",  "No",      0.59,    -0.59, 0.001,  "lost"),
    ("above",  "Yes",     0.77,    -0.77, 0.0013, "lost"),
    ("above",  "Yes",     1.27,    -1.27, 0.0021, "lost"),
    ("above",  "Yes",     6.05,    -6.05, 0.0102, "lost"),
    ("above",  "Yes",     0.68,    -0.68, 0.0011, "lost"),
    ("above",  "No",      5.88,    -5.88, 0.0100, "lost"),
    ("above",  "Yes",     8.82,    -8.82, 0.0150, "lost"),
    ("above",  "No",      0.59,    -0.59, 0.001,  "lost"),
    ("above",  "No",    119.12,  -119.12, 0.2026, "lost"),
]

from statistics import median, mean
from collections import Counter

print("=" * 60)
print("AMOSTRA DE POSIÇÕES (n = %d)" % len(POSICOES))
print("=" * 60)

tipos = Counter(p[0] for p in POSICOES)
outcomes = Counter(p[1] for p in POSICOES)
status = Counter(p[5] for p in POSICOES)

print("\n1) TIPO DE MERCADO")
for k, v in tipos.most_common():
    print(f"   {k:8s}: {v}")

print("\n2) OUTCOME ESCOLHIDO")
for k, v in outcomes.most_common():
    print(f"   {k:6s}: {v}")

print("\n3) STATUS")
for k, v in status.most_common():
    print(f"   {k:6s}: {v}")

# Win rate (apenas resolvidos = 'lost' ou resgatado). Na amostra, winners
# abertos = 2; perdedores resolvidos = 27. Estimativa inferior de win rate.
perdedores = sum(1 for p in POSICOES if p[5] == "lost")
abertos = sum(1 for p in POSICOES if p[5] == "open")
print(f"\n4) RESOLVIDOS PERDIDOS: {perdedores} | ABERTOS: {abertos}")
print(f"   -> Win rate NAO pode ser > {abertos}/{len(POSICOES)} nesta amostra; "
      f"a maioria esmagadora perde.")

# PnL agregado da amostra
pnl = sum(p[3] for p in POSICOES)
init = sum(p[2] for p in POSICOES)
print(f"\n5) PnL AGREGADO (amostra): {pnl:+,.2f} USD")
print(f"   Valor inicial apostado: {init:,.2f} USD")
print(f"   Retorno sobre apostado: {pnl/init*100:+.1f}%")

# Ticket size (initialValue)
tickets = [p[2] for p in POSICOES]
print(f"\n6) TICKET (valor inicial, USD)")
print(f"   mediana: {median(tickets):.2f} | media: {mean(tickets):.2f} "
      f"| min: {min(tickets):.2f} | max: {max(tickets):.2f}")

# Preços de entrada por tipo
print("\n7) PREÇO DE ENTRADA (avgPrice) por tipo")
for t in ("updown", "above"):
    ps = [p[4] for p in POSICOES if p[0] == t]
    if ps:
        print(f"   {t:6s}: mediana {median(ps):.4f} | media {mean(ps):.4f} "
              f"| min {min(ps):.4f} | max {max(ps):.4f}")

# Conclusão do teste de momentum
print("\n" + "=" * 60)
print("LEITURA ESTRATÉGICA")
print("=" * 60)
print("""
- Só BUY, viés 'Up'/'Yes' -> direcional long-only.
- Preços de entrada varrem 0.001 a 0.86 -> NAO há um único preço-alvo.
- Dois blocos distintos:
  (a) 'Up or Down' 5m-4h, tickets ~$45-$3.000, preços 0.05-0.57.
  (b) 'above X' horário, tickets ~$0.60-$120, muitos a 0.001-0.015
      (apostas LOTERIA fora-do-dinheiro).
- Vencedores raros mas grandes (maior $9.940; REDEEMs de $1.759/$440/$20).
- Estrategia: alta frequencia, long-only, hold-to-resolution,
  com cauda direita pesada (poucos acertos grandes pagam muitas perdas).
""")

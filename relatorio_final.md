# Relatório final — Estratégia de trading na Polymarket

**Carteira:** `0xb55fa1296e6ec55d0ce53d93b9237389f11764d4` — *Lively-Authenticity*
**Perfil:** https://polymarket.com/pt/@0xb55fa1296e6ec55d0ce53d93b9237389f11764d4-1777575277609
**Data da análise:** 2026-08-21

---

## 1. O que é a conta

| Métrica (do perfil) | Valor |
|---|---|
| Previsões | **106.852** |
| Valor das posições | ~$14,9K |
| Maior vitória | **$9.940,52** |
| Lucro/Prejuízo (all-time) | **~+$16.787** |
| Valor atual da carteira (API) | ~$13.576 (oscila) |
| Entrou | abr/2026 |

**É um bot de alta frequência.** Três ordens no mesmo segundo, dezenas de compras num mesmo mercado em ~2 minutos e 106 mil previsões — impossível para um humano.

---

## 2. Assinatura da estratégia (fatos observados)

1. **Só BUY — zero SELL.** Em todo o histórico coletado não há venda. Descarta market-making e arbitragem; é **aposta direcional long-only**.
2. **Viés altista:** a maioria dos "Up or Down" é comprada no lado **Up**; nos mercados "acima de X", aposta **Yes** (BTC sobe).
3. **Hold-to-resolution:** segura até o vencimento. Perdedores viram 0 (−100%); vencedores geram evento `REDEEM`. Não faz exit antecipado.
4. **Fragmentação de ordens:** divide uma posição em dezenas de tickets pequenos (ex.: $5–$60 repetidos em "BTC Up/Down 9AM").
5. **Mercados-alvo:** só cripto de janela curta — BTC, ETH, SOL, XRP em *Up/Down* (5m, 15m, 1h, 4h) e *"acima de X"* horário.

**Classificação:** *high-frequency directional scalping bot*, long-only, hold-to-resolution, em mercados binários de volatilidade de curto prazo.

---

## 3. Dois "blocos" de aposta distintos (achado da análise)

A análise das posições revela **não uma, mas duas linhas de aposta**:

| | Bloco A — "Up/Down" | Bloco B — "acima de X" |
|---|---|---|
| Mercado | Up/Down 5m–4h | "Bitcoin/Ethereum above X" horário/diário |
| Ticket (valor inicial) | mediana ~$145, até ~$3.000 | ~$0,60 a ~$120 |
| Preço de entrada | mediana **0,24** (0,06–0,57) | mediana **0,002** (0,001–0,22) |
| Natureza | aposta direcional moderada | **"loteria" fora-do-dinheiro** (Yes a 0,001–0,015) |

O bloco B é muito revelador: comprar "Yes" em "BTC acima de 66.000" pagando **0,001–0,015** é comprar opção de cauda — o bot paga centavos apostando que o BTC vai "explodir" e multiplicar o valor. A maioria desses vira pó, mas quando acerta, o payoff é gigante.

---

## 4. Resultado quantitativo (amostra de 29 posições)

> ⚠️ **Ressalva metodológica:** a lista `positions` da API é **enviesada para perdedores** — os vencedores são resgatados (`REDEEM`) e saem da lista. Logo, o PnL agregado abaixo subestima o desempenho real. O número oficial do perfil (lucro all-time ~+$16,8K) é a referência correta.

| Métrica | Valor |
|---|---|
| Posições na amostra | 29 |
| Perderam (value → 0) | 26 (90%) |
| Abertas | 3 |
| PnL agregado (só perdedores) | −$7.782 |
| Retorno sobre apostado (perdedores) | −79,4% |
| Ticket mediano | $145 |
| Ticket máximo | $2.955 |

**Leitura:** a taxa de acerto é **muito baixa** (a esmagadora maioria das posições fecha em −100%), mas o resultado final é **positivo (~+$16,8K)** porque os poucos acertos são desproporcionalmente grandes — a maior vitória ($9.940) sozinha representa ~59% de todo o lucro.

> Isso é o perfil clássico de **cauda direita pesada**: muitas perdas pequenas e frequentes, poucos ganhos grandes e raros. É o oposto de uma estratégia de "muitos pequenos ganhos consistentes".

---

## 5. Teste da hipótese de momentum

Pergunta: o bot compra "Up" **depois** de o preço subir (momentum) ou **depois** de cair (reversão à média)?

**Prova parcial (preços de entrada):** num mercado Up/Down justo, o lado "Up" deveria custar ~0,50. O bot compra "Up" com **preço mediano de 0,24** — ou seja, tipicamente quando o "Up" está **barato/depreciado**. Isso indica **reversão à média / compra de queda (dip-buying)**, não perseguição de alta.

**Ressalva:** também há compras de "Up" a 0,77–0,86 (favorito) no feed de atividade, então o comportamento não é 100% uniforme. Para confirmar de forma definitiva seria preciso cruzar os timestamps com a série de preço spot (BTC/ETH/SOL/XRP minuto a minuto), o que exigiria a API de preços da Polymarket (`clob.polymarket.com/prices-history`) token por token.

**Conclusão provisória:** predominância de **compra de "Up" depreciado** (contrarian/mean-reversion) + **opções de cauda baratas** ("above X" a centavos). Viés long + cauda longa.

---

## 6. O que NÃO dá para afirmar com os dados públicos

1. O **sinal exato** que dispara cada ordem (o "porquê" do segundo escolhido) — pode ser preço spot, order flow, vol. implícita vs. realizada, ou puro acaso.
2. Se é um **bot comercial** conhecido ou código próprio.
3. O **retorno líquido de fees** no longo prazo (a API não expõe o histórico integral facilmente; 106k trades precisariam de paginação exaustiva).
4. Se o +$16,8K é **consistente** ou fruto de poucos acertos de sorte.

---

## 7. Arquivos gerados

- `polymarket_profile.json` — perfil + primeiras posições/atividades (JSON).
- `analise_completa.py` — script Python reprodutível com a amostra e as métricas.
- `estrategia_analise.md` — identificação inicial da estratégia.
- `relatorio_final.md` — este documento.

---

## 8. Próximos passos possíveis (se quiser ir além)

1. **Win rate real:** paginar o `activity` inteiro e contar mercados vencidos (REDEEM) vs. perdidos.
2. **Momentum definitivo:** baixar `prices-history` dos tokens BTC/ETH/SOL/XRP e cruzar com os timestamps de entrada do bot.
3. **Curva de equity:** reconstruir o PnL diário a partir do histórico de REDEEM + posições.
4. **Detecção do sinal:** tentar reproduzir a regra (ex.: "compra Up quando cai X% no minuto anterior") e fazer backtest.

Quer que eu siga com algum desses (recomendo o **1** ou o **2**)?

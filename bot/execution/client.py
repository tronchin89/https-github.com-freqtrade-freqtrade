"""Camada de execução (F4) — wrapper sobre py-clob-client.

ATENÇÃO: só usar com dry_run=False e depois de F2 (backtest) + F3 (paper).
Requer:
  1. `pip install py-clob-client`
  2. POLY_FUNDER + POLY_PRIVATE_KEY no .env (chave derivada em Settings -> API keys)

A assinatura exata do SDK varia entre versões; este módulo isola isso para
você ajustar só aqui. Consulte:
  https://github.com/Polymarket/py-clob-client
"""
from __future__ import annotations

from typing import Optional

from bot.config import Settings


class ExecutionClient:
    """Cliente mínimo de ordens. Levanta erro se tentar rodar sem config."""

    def __init__(self, s: Settings):
        self.s = s
        self._client = None

    def _ensure(self):
        if self._client is not None:
            return self._client
        if not self.s.funder or not self.s.private_key:
            raise RuntimeError(
                "Credenciais ausentes: defina POLY_FUNDER e POLY_PRIVATE_KEY "
                "no .env (Settings -> API keys na Polymarket)."
            )
        from py_clob_client.client import ClobClient
        from py_clob_client.constants import POLYGON
        # Ajuste o signature_type conforme seu tipo de carteira:
        #  - POLY_PROXY (padrão atual da Polymarket) ou POLY_GNOSIS_SAFE.
        from py_clob_client.clob_types import SignatureType

        client = ClobClient(
            host=self.s.clob_host,
            key=self.s.private_key,
            chain_id=POLYGON.chain_id,
            signature_type=SignatureType.POLY_PROXY,
            funder=self.s.funder,
        )
        client.set_api_creds(client.create_or_derive_api_creds())
        self._client = client
        return client

    def buy(self, token_id: str, price: float, size: float) -> Optional[dict]:
        """Envia uma ordem LIMIT de compra (GTC). Retorna a resposta ou None."""
        if self.s.dry_run:
            return {"dry_run": True, "token_id": token_id,
                    "price": price, "size": size}
        client = self._ensure()
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY

        order = client.create_order(
            OrderArgs(price=price, size=size, side=BUY, token_id=token_id)
        )
        return client.post_order(order, OrderType.GTC)

    def sell(self, token_id: str, price: float, size: float) -> Optional[dict]:
        """Envia uma ordem LIMIT de venda (GTC)."""
        if self.s.dry_run:
            return {"dry_run": True, "token_id": token_id,
                    "price": price, "size": size}
        client = self._ensure()
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import SELL

        order = client.create_order(
            OrderArgs(price=price, size=size, side=SELL, token_id=token_id)
        )
        return client.post_order(order, OrderType.GTC)

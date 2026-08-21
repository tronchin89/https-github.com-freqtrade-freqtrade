"""Configuração central via variáveis de ambiente (.env).

Nunca commite o .env real. Copie .env.example -> .env e preencha.
A chave privada fica SOMENTE aqui, fora do controle de versão.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv opcional
    pass


@dataclass
class Settings:
    # ---- APIs (somente leitura, sem auth) ----
    gamma_host: str = "https://gamma-api.polymarket.com"
    clob_host: str = "https://clob.polymarket.com"
    data_host: str = "https://data-api.polymarket.com"

    # ---- Credenciais de execução (F4) ----
    # Address da sua carteira Polymarket (não é segredo).
    funder: str = field(default_factory=lambda: os.getenv("POLY_FUNDER", ""))
    # Chave privada da carteira OU API key derivada. SEGREDO — só no .env.
    private_key: str = field(default_factory=lambda: os.getenv("POLY_PRIVATE_KEY", ""))
    chain_id: int = 137  # Polygon mainnet

    # ---- Estratégia ----
    coin: str = os.getenv("BOT_COIN", "Bitcoin").title()
    dry_run: bool = os.getenv("BOT_DRY_RUN", "1") == "1"  # default: sem dinheiro

    # Sinal mean-reversion
    mr_lookback_minutes: int = int(os.getenv("BOT_MR_LOOKBACK", "5"))
    mr_drop_threshold: float = float(os.getenv("BOT_MR_DROP", "0.004"))  # -0.4%

    # Gestão de risco
    bankroll_usd: float = float(os.getenv("BOT_BANKROLL", "1000"))
    max_frac_kelly: float = float(os.getenv("BOT_MAX_KELLY", "0.25"))
    max_per_position: float = float(os.getenv("BOT_MAX_PCT", "0.02"))  # 2% do bankroll

    # Saída (stop / target) — em pontos de preço de 0 a 1
    take_profit_ratio: float = float(os.getenv("BOT_TP", "0.40"))  # vende a 0.40
    stop_loss_ratio: float = float(os.getenv("BOT_SL", "0.10"))    # vende a 0.10

    # ---- Persistência ----
    db_path: str = os.getenv("BOT_DB", "bot_journal.sqlite3")

    @property
    def is_configured_for_live(self) -> bool:
        return bool(self.funder and self.private_key) and not self.dry_run


def get_settings() -> Settings:
    return Settings()

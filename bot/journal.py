"""Journal de trades em SQLite — audita sinal, entrada, saída e PnL."""
from __future__ import annotations

import sqlite3
import time


SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    market_id TEXT,
    question TEXT,
    token_id TEXT,
    outcome TEXT,
    entry_price REAL,
    exit_price REAL,
    stake_usd REAL,
    pnl_usd REAL,
    status TEXT,           -- open | won | lost | stopped | target
    reason TEXT
);
"""


class Journal:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def log_trade(self, *, market_id, question, token_id, outcome,
                  entry_price, stake_usd, status="open", reason=""):
        self.conn.execute(
            "INSERT INTO trades (ts, market_id, question, token_id, outcome, "
            "entry_price, stake_usd, status, reason) VALUES (?,?,?,?,?,?,?,?,?)",
            (time.time(), market_id, question, token_id, outcome,
             entry_price, stake_usd, status, reason),
        )
        self.conn.commit()

    def update_exit(self, trade_id: int, exit_price: float, pnl_usd: float, status: str):
        self.conn.execute(
            "UPDATE trades SET exit_price=?, pnl_usd=?, status=? WHERE id=?",
            (exit_price, pnl_usd, status, trade_id),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()

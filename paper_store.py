"""PT-30: offline-only synthetic paper ledger for two separate strategy accounts.

NO NETWORK, BROKER, STREAMLIT INTEGRATION, LIVE PRICES, C3 OR SCANNER EXECUTION.
This module is not imported by the hosted app. SQLite writes are only performed
by explicit calls to initialize_store/record_synthetic_fill in a local context.
This is NOT a production-grade cloud persistence design.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3

INITIAL_CASH_CENTS = 1_000_000
ACCOUNT_STRATEGIES = {
    "trend_scanner": "SYNTHETIC_TRENDSCANNER",
    "c3_agent": "SYNTHETIC_C3",
}
_ID_RE = re.compile(r"[A-Z0-9][A-Z0-9_-]{2,63}\Z")
_SYMBOL_RE = re.compile(r"DEMO-[A-Z0-9]{2,16}\Z")


@dataclass(frozen=True)
class SyntheticFill:
    """An invented accounting event, never an instruction to trade."""
    event_id: str
    account_id: str
    strategy: str
    symbol: str
    side: str
    quantity: int
    price_cents: int
    fee_cents: int = 0


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: int
    cost_basis_cents: int


@dataclass(frozen=True)
class Snapshot:
    account_id: str
    strategy: str
    initial_cash_cents: int
    cash_cents: int
    realized_pnl_cents: int
    positions: tuple[Position, ...]


@dataclass(frozen=True)
class RecordedFill:
    event_id: str
    account_id: str
    strategy: str
    symbol: str
    side: str
    quantity: int
    price_cents: int
    fee_cents: int
    realized_pnl_cents: int
    created_at_utc: str


def _db_path(db_path: str | Path) -> Path:
    if not isinstance(db_path, (str, Path)) or not str(db_path):
        raise ValueError("A local database file path is required")
    if str(db_path) == ":memory:":
        raise ValueError("Use an explicit file path for auditable persistence")
    return Path(db_path).expanduser().resolve()


def _open(db_path: str | Path, *, read_only: bool = False) -> sqlite3.Connection:
    path = _db_path(db_path)
    if read_only:
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    else:
        conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _account_strategy(account_id: str) -> str:
    try:
        return ACCOUNT_STRATEGIES[account_id]
    except (KeyError, TypeError) as exc:
        raise ValueError("Unknown or unauthorized demo strategy account") from exc


def _validate_fill(fill: SyntheticFill) -> None:
    if not isinstance(fill, SyntheticFill):
        raise TypeError("Expected SyntheticFill")
    if not isinstance(fill.event_id, str) or not _ID_RE.fullmatch(fill.event_id):
        raise ValueError("Invalid event id")
    if not isinstance(fill.symbol, str) or not _SYMBOL_RE.fullmatch(fill.symbol):
        raise ValueError("Only fictional DEMO- symbols are allowed")
    if fill.strategy != _account_strategy(fill.account_id):
        raise ValueError("Cross-strategy write rejected")
    if fill.side not in ("BUY", "SELL"):
        raise ValueError("Only synthetic BUY/SELL ledger entries allowed")
    for label, value, minimum, maximum in (
        ("quantity", fill.quantity, 1, 1_000_000),
        ("price_cents", fill.price_cents, 1, 100_000_000),
        ("fee_cents", fill.fee_cents, 0, 100_000_000),
    ):
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"Invalid {label}")


def initialize_store(db_path: str | Path) -> None:
    """Explicitly create an independent local ledger. Never called by hosted UI."""
    with closing(_open(db_path)) as conn:
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    strategy TEXT NOT NULL,
                    initial_cash_cents INTEGER NOT NULL CHECK(initial_cash_cents > 0),
                    cash_cents INTEGER NOT NULL CHECK(cash_cents >= 0),
                    realized_pnl_cents INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS positions (
                    account_id TEXT NOT NULL REFERENCES accounts(account_id),
                    symbol TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    cost_basis_cents INTEGER NOT NULL CHECK(cost_basis_cents >= 0),
                    PRIMARY KEY(account_id, symbol)
                );
                CREATE TABLE IF NOT EXISTS fills (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    account_id TEXT NOT NULL REFERENCES accounts(account_id),
                    strategy TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    price_cents INTEGER NOT NULL CHECK(price_cents > 0),
                    fee_cents INTEGER NOT NULL CHECK(fee_cents >= 0),
                    realized_pnl_cents INTEGER NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
            """)
            for account, strategy in ACCOUNT_STRATEGIES.items():
                conn.execute(
                    "INSERT OR IGNORE INTO accounts "
                    "(account_id, strategy, initial_cash_cents, cash_cents) "
                    "VALUES (?, ?, ?, ?)",
                    (account, strategy, INITIAL_CASH_CENTS, INITIAL_CASH_CENTS),
                )


def record_synthetic_fill(db_path: str | Path, fill: SyntheticFill) -> bool:
    """Atomically record a FAKE accounting event. Return False for exact replay.

    Caller must initialize explicitly. The event id is unique across accounts.
    No orders are sent, no external market prices or user data are consulted.
    """
    _validate_fill(fill)
    with closing(_open(db_path)) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute(
                "SELECT account_id, strategy, symbol, side, quantity, price_cents, fee_cents "
                "FROM fills WHERE event_id=?", (fill.event_id,),
            ).fetchone()
            fingerprint = (
                fill.account_id, fill.strategy, fill.symbol, fill.side,
                fill.quantity, fill.price_cents, fill.fee_cents,
            )
            if previous is not None:
                if previous != fingerprint:
                    raise ValueError("Conflicting event id; no accounting change permitted")
                conn.commit()
                return False

            acct = conn.execute(
                "SELECT strategy, cash_cents, realized_pnl_cents "
                "FROM accounts WHERE account_id=?", (fill.account_id,),
            ).fetchone()
            if acct is None or acct[0] != fill.strategy:
                raise ValueError("Account is missing or strategy mismatch")
            cash, cumulative_realized = acct[1], acct[2]
            old = conn.execute(
                "SELECT quantity, cost_basis_cents FROM positions "
                "WHERE account_id=? AND symbol=?", (fill.account_id, fill.symbol),
            ).fetchone()
            gross = fill.quantity * fill.price_cents
            realized = 0
            if fill.side == "BUY":
                debit = gross + fill.fee_cents
                if debit > cash:
                    raise ValueError("Insufficient artificial cash")
                new_qty = fill.quantity + (old[0] if old else 0)
                new_cost = debit + (old[1] if old else 0)
                conn.execute(
                    "INSERT INTO positions(account_id, symbol, quantity, cost_basis_cents) "
                    "VALUES(?, ?, ?, ?) ON CONFLICT(account_id, symbol) DO UPDATE "
                    "SET quantity=excluded.quantity, cost_basis_cents=excluded.cost_basis_cents",
                    (fill.account_id, fill.symbol, new_qty, new_cost),
                )
                cash -= debit
            else:
                if old is None or old[0] < fill.quantity:
                    raise ValueError("Insufficient artificial position")
                proceeds = gross - fill.fee_cents
                if proceeds < 0:
                    raise ValueError("Fees exceed synthetic sale proceeds")
                # Deterministic average cost; closing trade releases rounding remainder.
                released_cost = (
                    old[1] if fill.quantity == old[0]
                    else old[1] * fill.quantity // old[0]
                )
                remaining_qty = old[0] - fill.quantity
                if remaining_qty == 0:
                    conn.execute(
                        "DELETE FROM positions WHERE account_id=? AND symbol=?",
                        (fill.account_id, fill.symbol),
                    )
                else:
                    conn.execute(
                        "UPDATE positions SET quantity=?, cost_basis_cents=? "
                        "WHERE account_id=? AND symbol=?",
                        (remaining_qty, old[1] - released_cost, fill.account_id, fill.symbol),
                    )
                realized = proceeds - released_cost
                cash += proceeds
                cumulative_realized += realized

            conn.execute(
                "UPDATE accounts SET cash_cents=?, realized_pnl_cents=? "
                "WHERE account_id=?",
                (cash, cumulative_realized, fill.account_id),
            )
            conn.execute(
                "INSERT INTO fills "
                "(event_id, account_id, strategy, symbol, side, quantity, price_cents, "
                "fee_cents, realized_pnl_cents, created_at_utc) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fill.event_id, fill.account_id, fill.strategy, fill.symbol,
                    fill.side, fill.quantity, fill.price_cents, fill.fee_cents,
                    realized, datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return True
        except BaseException:
            conn.rollback()
            raise


def read_snapshot(db_path: str | Path, account_id: str) -> Snapshot:
    """Read an account only; never mutate or create the database."""
    strategy = _account_strategy(account_id)
    with closing(_open(db_path, read_only=True)) as conn:
        row = conn.execute(
            "SELECT strategy, initial_cash_cents, cash_cents, realized_pnl_cents "
            "FROM accounts WHERE account_id=?", (account_id,),
        ).fetchone()
        if row is None or row[0] != strategy:
            raise ValueError("Unknown account in store")
        positions = tuple(Position(*p) for p in conn.execute(
            "SELECT symbol, quantity, cost_basis_cents FROM positions "
            "WHERE account_id=? ORDER BY symbol", (account_id,),
        ).fetchall())
        return Snapshot(account_id, strategy, row[1], row[2], row[3], positions)


def read_history(db_path: str | Path, account_id: str) -> tuple[RecordedFill, ...]:
    """Read ledger history for exactly one strategy account."""
    _account_strategy(account_id)
    with closing(_open(db_path, read_only=True)) as conn:
        rows = conn.execute(
            "SELECT event_id, account_id, strategy, symbol, side, quantity, "
            "price_cents, fee_cents, realized_pnl_cents, created_at_utc "
            "FROM fills WHERE account_id=? ORDER BY sequence", (account_id,),
        ).fetchall()
        return tuple(RecordedFill(*row) for row in rows)

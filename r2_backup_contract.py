"""PT-31: offline, synthetic-only R2-style immutable backup contract.

No Cloudflare SDK, keys, network, writes to R2, Streamlit, market data or orders.
Consumes the PT-30 local test ledger only. The resulting object can later be
stored in private R2 using an independently audited create-if-absent adapter.
SHA-256 detects corruption; it does NOT authenticate the writer or prevent
replaying an old, internally valid backup.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Protocol

from paper_store import ACCOUNT_STRATEGIES, INITIAL_CASH_CENTS

SCHEMA = "PT31_SYNTHETIC_PAPER_BACKUP_V1"
MAX_BYTES = 2_000_000
MAX_EVENTS = 10_000
MAX_POSITIONS = 1_000
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"DEMO-[A-Z0-9]{2,16}\Z")
_EVENT_ID = re.compile(r"[A-Z0-9][A-Z0-9_-]{2,63}\Z")


@dataclass(frozen=True)
class VerifiedBackup:
    account_id: str
    key: str
    sha256: str
    event_count: int
    cash_cents: int
    realized_pnl_cents: int


@dataclass(frozen=True)
class BackupObject:
    key: str
    data: bytes
    verified: VerifiedBackup


class CreateOnlyObjectStore(Protocol):
    """Future private R2 adapter MUST provide atomic If-None-Match: * semantics."""

    def put_if_absent(self, key: str, data: bytes) -> bool:
        """True if newly stored, False on identical existing object; no overwrite."""
        ...


def _account(account_id: object) -> str:
    if type(account_id) is not str or account_id not in ACCOUNT_STRATEGIES:
        raise ValueError("PT31_ACCOUNT_BLOCKED")
    return ACCOUNT_STRATEGIES[account_id]


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def _clock(now: datetime | None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("PT31_CLOCK_BLOCKED")
    return now.astimezone(timezone.utc).isoformat()


def _read_consistent_ledger(db_path: str | Path, account_id: str) -> tuple[dict, list, list]:
    """One SQLite read transaction: accounts, positions, and history aligned."""
    _account(account_id)
    if type(db_path) not in (str, Path) or not str(db_path) or str(db_path) == ":memory:":
        raise ValueError("PT31_LOCAL_FILE_REQUIRED")
    file = Path(db_path).expanduser().resolve()
    if not file.is_file():
        raise ValueError("PT31_LEDGER_MISSING")
    try:
        with closing(sqlite3.connect(file.as_uri() + "?mode=ro", uri=True, timeout=5)) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            account = conn.execute(
                "SELECT strategy, initial_cash_cents, cash_cents, realized_pnl_cents "
                "FROM accounts WHERE account_id=?", (account_id,),
            ).fetchone()
            if account is None or account[0] != _account(account_id):
                raise ValueError("PT31_LEDGER_ACCOUNT_MISMATCH")
            positions = conn.execute(
                "SELECT symbol, quantity, cost_basis_cents FROM positions "
                "WHERE account_id=? ORDER BY symbol LIMIT ?",
                (account_id, MAX_POSITIONS + 1),
            ).fetchall()
            events = conn.execute(
                "SELECT event_id, account_id, strategy, symbol, side, quantity, "
                "price_cents, fee_cents, realized_pnl_cents, created_at_utc "
                "FROM fills WHERE account_id=? ORDER BY sequence LIMIT ?",
                (account_id, MAX_EVENTS + 1),
            ).fetchall()
            conn.rollback()
    except sqlite3.Error as exc:
        raise ValueError("PT31_LEDGER_READ_BLOCKED") from exc
    if len(positions) > MAX_POSITIONS or len(events) > MAX_EVENTS:
        raise ValueError("PT31_LEDGER_SIZE_BLOCKED")
    summary = dict(
        initial_cash_cents=account[1], cash_cents=account[2],
        realized_pnl_cents=account[3],
    )
    positions_out = [
        dict(symbol=s, quantity=q, cost_basis_cents=c)
        for s, q, c in positions
    ]
    labels = (
        "event_id", "account_id", "strategy", "symbol", "side", "quantity",
        "price_cents", "fee_cents", "realized_pnl_cents", "created_at_utc",
    )
    return summary, positions_out, [dict(zip(labels, event)) for event in events]


def _reconcile(payload: object) -> tuple[str, int, int, int]:
    """Independent full-history replay; fail closed on any inconsistency."""
    if type(payload) is not dict or set(payload) != {
        "schema", "account_id", "strategy", "created_at_utc",
        "snapshot", "events",
    } or payload["schema"] != SCHEMA:
        raise ValueError("PT31_PAYLOAD_SCHEMA_BLOCKED")
    account_id = payload["account_id"]
    strategy = _account(account_id)
    if payload["strategy"] != strategy:
        raise ValueError("PT31_STRATEGY_BLOCKED")
    if type(payload["created_at_utc"]) is not str:
        raise ValueError("PT31_CLOCK_BLOCKED")
    try:
        time = datetime.fromisoformat(payload["created_at_utc"])
        if time.tzinfo is None or time.utcoffset() is None:
            raise ValueError("missing UTC")
    except ValueError as exc:
        raise ValueError("PT31_CLOCK_BLOCKED") from exc
    snapshot, events = payload["snapshot"], payload["events"]
    if type(snapshot) is not dict or set(snapshot) != {
        "initial_cash_cents", "cash_cents", "realized_pnl_cents", "positions",
    } or type(events) is not list or len(events) > MAX_EVENTS:
        raise ValueError("PT31_SNAPSHOT_SCHEMA_BLOCKED")
    if type(snapshot["positions"]) is not list or len(snapshot["positions"]) > MAX_POSITIONS:
        raise ValueError("PT31_POSITION_SIZE_BLOCKED")
    if type(snapshot["initial_cash_cents"]) is not int or snapshot["initial_cash_cents"] != INITIAL_CASH_CENTS:
        raise ValueError("PT31_START_CAPITAL_BLOCKED")
    for position in snapshot["positions"]:
        if (type(position) is not dict or set(position) != {
            "symbol", "quantity", "cost_basis_cents",
        } or type(position["symbol"]) is not str
                or _SYMBOL.fullmatch(position["symbol"]) is None
                or type(position["quantity"]) is not int
                or not 1 <= position["quantity"] <= 1_000_000
                or type(position["cost_basis_cents"]) is not int
                or position["cost_basis_cents"] < 0):
            raise ValueError("PT31_POSITION_SCHEMA_BLOCKED")
    cash = INITIAL_CASH_CENTS
    realized_total = 0
    held: dict[str, tuple[int, int]] = {}
    seen_ids: set[str] = set()
    for event in events:
        if type(event) is not dict or set(event) != {
            "event_id", "account_id", "strategy", "symbol", "side",
            "quantity", "price_cents", "fee_cents",
            "realized_pnl_cents", "created_at_utc",
        }:
            raise ValueError("PT31_EVENT_SCHEMA_BLOCKED")
        event_id, symbol = event["event_id"], event["symbol"]
        if (type(event_id) is not str or _EVENT_ID.fullmatch(event_id) is None
                or event_id in seen_ids or event["account_id"] != account_id
                or event["strategy"] != strategy or type(symbol) is not str
                or _SYMBOL.fullmatch(symbol) is None):
            raise ValueError("PT31_EVENT_IDENTITY_BLOCKED")
        seen_ids.add(event_id)
        for k, low, high in (("quantity", 1, 1_000_000),
                             ("price_cents", 1, 100_000_000),
                             ("fee_cents", 0, 100_000_000)):
            if type(event[k]) is not int or not low <= event[k] <= high:
                raise ValueError("PT31_EVENT_AMOUNT_BLOCKED")
        if type(event["created_at_utc"]) is not str:
            raise ValueError("PT31_EVENT_TIME_BLOCKED")
        try:
            timestamp = datetime.fromisoformat(event["created_at_utc"])
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("naive")
        except ValueError as exc:
            raise ValueError("PT31_EVENT_TIME_BLOCKED") from exc
        qty, price, fee = event["quantity"], event["price_cents"], event["fee_cents"]
        gross = qty * price
        realized = 0
        if event["side"] == "BUY":
            if gross + fee > cash:
                raise ValueError("PT31_FAKE_CASH_BLOCKED")
            old_qty, old_cost = held.get(symbol, (0, 0))
            held[symbol] = (old_qty + qty, old_cost + gross + fee)
            cash -= gross + fee
        elif event["side"] == "SELL":
            old_qty, old_cost = held.get(symbol, (0, 0))
            if qty > old_qty or gross < fee:
                raise ValueError("PT31_FAKE_POSITION_BLOCKED")
            release = old_cost if qty == old_qty else old_cost * qty // old_qty
            remain = old_qty - qty
            if remain:
                held[symbol] = (remain, old_cost - release)
            else:
                del held[symbol]
            realized = gross - fee - release
            cash += gross - fee
            realized_total += realized
        else:
            raise ValueError("PT31_FAKE_SIDE_BLOCKED")
        if type(event["realized_pnl_cents"]) is not int or event["realized_pnl_cents"] != realized:
            raise ValueError("PT31_EVENT_PNL_BLOCKED")
    expected = [
        {"symbol": symbol, "quantity": q, "cost_basis_cents": cost}
        for symbol, (q, cost) in sorted(held.items())
    ]
    if (snapshot["positions"] != expected
            or type(snapshot["cash_cents"]) is not int or snapshot["cash_cents"] != cash
            or type(snapshot["realized_pnl_cents"]) is not int
            or snapshot["realized_pnl_cents"] != realized_total):
        raise ValueError("PT31_LEDGER_RECONCILIATION_BLOCKED")
    return account_id, len(events), cash, realized_total


def _key(account_id: str, digest: str) -> str:
    return f"synthetic-paper-backups/pt31/v1/{account_id}/sha256-{digest}.json"


def verify_backup(data: bytes, *, expected_account: str) -> VerifiedBackup:
    """Offline-only validation and restore PREVIEW. Never writes a ledger."""
    _account(expected_account)
    if type(data) is not bytes or not 0 < len(data) <= MAX_BYTES:
        raise ValueError("PT31_BACKUP_SIZE_BLOCKED")
    try:
        envelope = json.loads(data)
        if type(envelope) is not dict or set(envelope) != {"sha256", "payload"}:
            raise ValueError("PT31_ENVELOPE_BLOCKED")
        digest, payload = envelope["sha256"], envelope["payload"]
        if type(digest) is not str or _DIGEST.fullmatch(digest) is None:
            raise ValueError("PT31_DIGEST_BLOCKED")
        if _canonical(envelope) != data or hashlib.sha256(_canonical(payload)).hexdigest() != digest:
            raise ValueError("PT31_HASH_MISMATCH")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, OverflowError) as exc:
        raise ValueError("PT31_CORRUPT_BACKUP") from exc
    account_id, count, cash, realized = _reconcile(payload)
    if account_id != expected_account:
        raise ValueError("PT31_FOREIGN_ACCOUNT_BLOCKED")
    return VerifiedBackup(account_id, _key(account_id, digest), digest, count, cash, realized)


def make_backup(db_path: str | Path, account_id: str, *,
                now: datetime | None = None) -> BackupObject:
    """Read a consistent local SQLite snapshot and encode a verifiable object."""
    strategy = _account(account_id)
    summary, positions, events = _read_consistent_ledger(db_path, account_id)
    payload = {
        "schema": SCHEMA, "account_id": account_id, "strategy": strategy,
        "created_at_utc": _clock(now),
        "snapshot": {**summary, "positions": positions},
        "events": events,
    }
    _reconcile(payload)
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    data = _canonical({"sha256": digest, "payload": payload})
    proof = verify_backup(data, expected_account=account_id)
    return BackupObject(proof.key, data, proof)


def preview_restore(data: bytes, *, expected_account: str) -> VerifiedBackup:
    """Only validate a candidate recovery artifact; no automatic restore."""
    return verify_backup(data, expected_account=expected_account)

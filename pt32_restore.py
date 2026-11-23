"""PT-32: strictly offline restore rehearsal for verified synthetic PT-31 backups.

Creates one NEW, local SQLite test ledger from a verified single-account backup.
No network, cloud, Streamlit, agent, real data, or broker connection.
Publication uses a same-directory hard link: create-only, never replace.
The source backup is not trusted to be authentic or the newest version.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from paper_store import ACCOUNT_STRATEGIES, initialize_store, read_history, read_snapshot
from r2_backup_contract import VerifiedBackup, verify_backup


def _new_local_target(target_path: str | Path) -> Path:
    if not isinstance(target_path, (str, Path)) or not str(target_path):
        raise ValueError("PT32_TARGET_PATH_BLOCKED")
    path = Path(target_path).expanduser()
    if str(path) == ":memory:" or path.suffix != ".sqlite3":
        raise ValueError("PT32_TARGET_PATH_BLOCKED")
    parent = path.parent
    if not parent.is_dir():
        raise ValueError("PT32_TARGET_PARENT_MISSING")
    target = parent.resolve() / path.name
    if os.path.lexists(target):
        raise ValueError("PT32_TARGET_ALREADY_EXISTS")
    return target


def _verify_local_replay(db_path: Path, payload: dict, expected_account: str) -> None:
    """Re-read all persisted rows, compare each value, and run SQLite integrity check."""
    snapshot = read_snapshot(db_path, expected_account)
    expected = payload["snapshot"]
    if (snapshot.account_id != expected_account
            or snapshot.strategy != ACCOUNT_STRATEGIES[expected_account]
            or snapshot.initial_cash_cents != expected["initial_cash_cents"]
            or snapshot.cash_cents != expected["cash_cents"]
            or snapshot.realized_pnl_cents != expected["realized_pnl_cents"]
            or [asdict(p) for p in snapshot.positions] != expected["positions"]
            or [asdict(event) for event in read_history(db_path, expected_account)]
            != payload["events"]):
        raise ValueError("PT32_RESTORE_RECONCILIATION_BLOCKED")
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("PT32_SQLITE_INTEGRITY_BLOCKED")
        other = [name for name in ACCOUNT_STRATEGIES if name != expected_account]
        for name in other:
            record = read_snapshot(db_path, name)
            if (record.cash_cents != record.initial_cash_cents
                    or record.realized_pnl_cents != 0 or record.positions
                    or read_history(db_path, name)):
                raise ValueError("PT32_CROSS_ACCOUNT_BLOCKED")


def restore_to_new_local_ledger(
    backup_data: bytes, *, expected_account: str, target_path: str | Path,
) -> VerifiedBackup:
    """Restore a verified synthetic account into a NEW file, atomically create-only.

    A temporary SQLite file is built beside the target, verified, then published
    with os.link (which fails if target exists). Failure leaves target absent.
    No existing target, including a symlink, is ever replaced. This is NOT a
    durable cloud restore, a signed backup, or a multi-writer protocol.
    """
    proof = verify_backup(backup_data, expected_account=expected_account)
    target = _new_local_target(target_path)
    payload = json.loads(backup_data)["payload"]  # already fully verified
    snap = payload["snapshot"]
    with TemporaryDirectory(prefix=".pt32-rehearsal-", dir=target.parent) as directory:
        staging = Path(directory) / "restored.sqlite3"
        initialize_store(staging)
        with closing(sqlite3.connect(staging)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE accounts SET initial_cash_cents=?, cash_cents=?, "
                    "realized_pnl_cents=? WHERE account_id=? AND strategy=?",
                    (snap["initial_cash_cents"], snap["cash_cents"],
                     snap["realized_pnl_cents"], expected_account,
                     ACCOUNT_STRATEGIES[expected_account]),
                )
                if conn.execute("SELECT changes()").fetchone()[0] != 1:
                    raise ValueError("PT32_ACCOUNT_UPDATE_BLOCKED")
                for position in snap["positions"]:
                    conn.execute(
                        "INSERT INTO positions(account_id, symbol, quantity, "
                        "cost_basis_cents) VALUES(?, ?, ?, ?)",
                        (expected_account, position["symbol"],
                         position["quantity"], position["cost_basis_cents"]),
                    )
                for event in payload["events"]:
                    conn.execute(
                        "INSERT INTO fills(event_id, account_id, strategy, symbol, "
                        "side, quantity, price_cents, fee_cents, realized_pnl_cents, "
                        "created_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (event["event_id"], event["account_id"], event["strategy"],
                         event["symbol"], event["side"], event["quantity"],
                         event["price_cents"], event["fee_cents"],
                         event["realized_pnl_cents"], event["created_at_utc"]),
                    )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        _verify_local_replay(staging, payload, expected_account)
        # Hard linking creates a directory entry ONLY when absent, including
        # protection against a competing writer creating the target meanwhile.
        # Any unsupported filesystem fails closed rather than overwriting.
        try:
            os.link(staging, target)
        except FileExistsError as exc:
            raise ValueError("PT32_TARGET_ALREADY_EXISTS") from exc
    return proof

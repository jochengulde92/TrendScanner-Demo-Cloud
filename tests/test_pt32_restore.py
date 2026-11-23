"""PT-32 synthetic, offline-only restore rehearsal; no real cloud/broker IO."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_store import (ACCOUNT_STRATEGIES, SyntheticFill, initialize_store,
                         read_history, read_snapshot, record_synthetic_fill)
from r2_backup_contract import make_backup, verify_backup
from pt32_restore import restore_to_new_local_ledger

CLOCK = datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc)


class OfflineRestoreRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.source = self.folder / "original.sqlite3"
        self.dest = self.folder / "recovered.sqlite3"
        initialize_store(self.source)

    def fill(self, event_id="FAKE_BUY_001", account="trend_scanner", *,
             symbol="DEMO-TS1", side="BUY", quantity=2, price=10000, fee=50):
        record_synthetic_fill(self.source, SyntheticFill(
            event_id, account, ACCOUNT_STRATEGIES[account], symbol,
            side, quantity, price, fee,
        ))

    def backup(self, account="trend_scanner"):
        return make_backup(self.source, account, now=CLOCK)

    def restore(self, data, account="trend_scanner", dest=None):
        return restore_to_new_local_ledger(
            data, expected_account=account,
            target_path=dest if dest is not None else self.dest,
        )

    def test_01_empty_account_round_trip(self):
        backup = self.backup()
        proof = self.restore(backup.data)
        self.assertEqual(proof, backup.verified)
        self.assertEqual(read_snapshot(self.dest, "trend_scanner"),
                         read_snapshot(self.source, "trend_scanner"))
        self.assertEqual(read_history(self.dest, "trend_scanner"), ())

    def test_02_buy_sell_fees_costs_and_timestamps_exact(self):
        self.fill()
        self.fill("FAKE_SELL_001", side="SELL", quantity=1, price=11000, fee=10)
        self.fill("FAKE_BUY_002", symbol="DEMO-TS2", price=9500, fee=25)
        backup = self.backup()
        self.restore(backup.data)
        self.assertEqual(read_snapshot(self.dest, "trend_scanner"),
                         read_snapshot(self.source, "trend_scanner"))
        self.assertEqual(read_history(self.dest, "trend_scanner"),
                         read_history(self.source, "trend_scanner"))

    def test_03_other_account_starts_untouched(self):
        self.fill()
        self.fill("FAKE_BUY_C31", "c3_agent", symbol="DEMO-C31", fee=0)
        self.restore(self.backup().data)
        other = read_snapshot(self.dest, "c3_agent")
        self.assertEqual(other.cash_cents, other.initial_cash_cents)
        self.assertFalse(other.positions)
        self.assertEqual(read_history(self.dest, "c3_agent"), ())

    def test_04_c3_restore_keeps_trend_scanner_empty(self):
        self.fill("FAKE_BUY_C31", "c3_agent", symbol="DEMO-C31", fee=0)
        self.restore(self.backup("c3_agent").data, account="c3_agent")
        self.assertEqual(read_snapshot(self.dest, "c3_agent"),
                         read_snapshot(self.source, "c3_agent"))
        self.assertEqual(read_history(self.dest, "trend_scanner"), ())

    def test_05_two_accounts_restore_to_separate_files(self):
        self.fill()
        self.fill("FAKE_BUY_C31", "c3_agent", symbol="DEMO-C31", fee=0)
        other_path = self.folder / "c3.sqlite3"
        self.restore(self.backup().data)
        self.restore(self.backup("c3_agent").data,
                     account="c3_agent", dest=other_path)
        self.assertEqual(read_snapshot(self.dest, "trend_scanner"),
                         read_snapshot(self.source, "trend_scanner"))
        self.assertEqual(read_snapshot(other_path, "c3_agent"),
                         read_snapshot(self.source, "c3_agent"))

    def test_06_foreign_backup_rejected_without_target(self):
        with self.assertRaisesRegex(ValueError, "FOREIGN_ACCOUNT"):
            self.restore(self.backup("c3_agent").data)
        self.assertFalse(self.dest.exists())

    def test_07_corrupt_backup_rejected_without_target(self):
        with self.assertRaises(ValueError):
            self.restore(self.backup().data[:-1])
        self.assertFalse(self.dest.exists())

    def test_08_rehashed_inconsistent_snapshot_rejected(self):
        payload = json.loads(self.backup().data)
        payload["payload"]["snapshot"]["cash_cents"] += 10
        canonical = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=True,
                                         separators=(",", ":"), allow_nan=False).encode("ascii")
        payload["sha256"] = hashlib.sha256(canonical(payload["payload"])).hexdigest()
        with self.assertRaises(ValueError):
            self.restore(canonical(payload))
        self.assertFalse(self.dest.exists())

    def test_09_existing_target_never_overwritten(self):
        self.dest.write_bytes(b"important-preexisting-content")
        with self.assertRaisesRegex(ValueError, "PT32_TARGET_ALREADY_EXISTS"):
            self.restore(self.backup().data)
        self.assertEqual(self.dest.read_bytes(), b"important-preexisting-content")

    def test_10_existing_sqlite_with_history_never_overwritten(self):
        self.fill()
        self.dest.write_bytes(self.source.read_bytes())
        original_bytes = self.dest.read_bytes()
        with self.assertRaises(ValueError):
            self.restore(self.backup().data)
        self.assertEqual(self.dest.read_bytes(), original_bytes)

    def test_11_broken_symlink_not_followed_or_replaced(self):
        try:
            self.dest.symlink_to(self.folder / "nonexistent.sqlite3")
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on this platform")
        with self.assertRaisesRegex(ValueError, "PT32_TARGET_ALREADY_EXISTS"):
            self.restore(self.backup().data)
        self.assertTrue(self.dest.is_symlink())

    def test_12_competing_writer_link_failure_leaves_no_target(self):
        with patch("pt32_restore.os.link", side_effect=FileExistsError("race")):
            with self.assertRaisesRegex(ValueError, "PT32_TARGET_ALREADY_EXISTS"):
                self.restore(self.backup().data)
        self.assertFalse(self.dest.exists())
        self.assertFalse(list(self.folder.glob(".pt32-rehearsal-*")))

    def test_13_staged_reconciliation_failure_no_partial_target(self):
        with patch("pt32_restore._verify_local_replay", side_effect=ValueError("induced")):
            with self.assertRaisesRegex(ValueError, "induced"):
                self.restore(self.backup().data)
        self.assertFalse(self.dest.exists())
        self.assertFalse(list(self.folder.glob(".pt32-rehearsal-*")))

    def test_14_missing_parent_never_created(self):
        missing = self.folder / "no-new-directory"
        with self.assertRaisesRegex(ValueError, "PT32_TARGET_PARENT_MISSING"):
            self.restore(self.backup().data, dest=missing / "output.sqlite3")
        self.assertFalse(missing.exists())

    def test_15_target_path_validation(self):
        for candidate in ("", ":memory:", self.folder / "output.txt", 123, None):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.restore(self.backup().data, dest=candidate if candidate is not None else 123)
        self.assertFalse(self.dest.exists())

    def test_16_invalid_account_rejected(self):
        with self.assertRaises(ValueError):
            self.restore(self.backup().data, account="unknown")
        self.assertFalse(self.dest.exists())

    def test_17_recovered_database_readable_by_pt31_backup(self):
        self.fill()
        original = self.backup()
        self.restore(original.data)
        new = make_backup(self.dest, "trend_scanner", now=CLOCK)
        self.assertEqual(new.data, original.data)
        self.assertEqual(verify_backup(new.data, expected_account="trend_scanner"),
                         original.verified)

    def test_18_second_restore_same_target_fails_closed(self):
        data = self.backup().data
        self.restore(data)
        with self.assertRaises(ValueError):
            self.restore(data)
        self.assertEqual(read_history(self.dest, "trend_scanner"), ())

    def test_19_readonly_verification_does_not_change_source(self):
        self.fill()
        state = read_snapshot(self.source, "trend_scanner")
        history = read_history(self.source, "trend_scanner")
        self.restore(self.backup().data)
        self.assertEqual(read_snapshot(self.source, "trend_scanner"), state)
        self.assertEqual(read_history(self.source, "trend_scanner"), history)


if __name__ == "__main__":
    unittest.main()

"""PT-31 offline tests. Synthetic local sqlite + in-memory R2 double ONLY."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper_store import SyntheticFill, initialize_store, record_synthetic_fill
from r2_backup_contract import (
    BackupObject, MAX_BYTES, make_backup, preview_restore, verify_backup,
)
from r2_object_contract import (
    InMemoryTestObjectStore, inspect_stored_backup, store_backup,
)

CLOCK = datetime(2026, 11, 23, 17, 0, tzinfo=timezone.utc)


def canonical(obj):
    return json.dumps(
        obj, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def rewrite(backup, change):
    item = json.loads(backup.data)
    change(item["payload"])
    item["sha256"] = hashlib.sha256(canonical(item["payload"])).hexdigest()
    return canonical(item)


class PT31R2BackupTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.file = Path(self.directory.name) / "only-fake-ledger.sqlite3"
        initialize_store(self.file)

    def buy(self, event="FAKE_BUY_001", account="trend_scanner",
            ticker="DEMO-TS1", qty=2, price=10000, fee=50):
        strategy = "SYNTHETIC_TRENDSCANNER" if account == "trend_scanner" else "SYNTHETIC_C3"
        record_synthetic_fill(
            self.file,
            SyntheticFill(event, account, strategy, ticker, "BUY", qty, price, fee),
        )

    def sell(self, event="FAKE_SELL_001", account="trend_scanner",
             ticker="DEMO-TS1", qty=1, price=11000, fee=10):
        strategy = "SYNTHETIC_TRENDSCANNER" if account == "trend_scanner" else "SYNTHETIC_C3"
        record_synthetic_fill(
            self.file,
            SyntheticFill(event, account, strategy, ticker, "SELL", qty, price, fee),
        )

    def backup(self, account="trend_scanner"):
        return make_backup(self.file, account, now=CLOCK)

    def test_01_empty_account_roundtrip(self):
        backup = self.backup()
        self.assertEqual(backup.verified.account_id, "trend_scanner")
        self.assertEqual(backup.verified.event_count, 0)
        self.assertEqual(backup.verified.cash_cents, 1_000_000)
        self.assertEqual(preview_restore(backup.data, expected_account="trend_scanner"),
                         backup.verified)

    def test_02_two_accounts_have_distinct_scopes(self):
        trend = self.backup()
        c3 = self.backup("c3_agent")
        self.assertNotEqual(trend.key, c3.key)
        self.assertIn("/trend_scanner/", trend.key)
        self.assertIn("/c3_agent/", c3.key)

    def test_03_buy_and_sale_reconcile(self):
        self.buy()
        self.sell()
        item = self.backup()
        self.assertEqual(item.verified.event_count, 2)
        self.assertEqual(item.verified.cash_cents, 990940)
        self.assertEqual(item.verified.realized_pnl_cents, 965)
        self.assertEqual(verify_backup(item.data, expected_account="trend_scanner"),
                         item.verified)

    def test_04_multiple_strategies_never_mix(self):
        self.buy()
        self.buy("FAKE_BUY_C31", account="c3_agent", ticker="DEMO-C31")
        self.assertEqual(self.backup().verified.event_count, 1)
        self.assertEqual(self.backup("c3_agent").verified.event_count, 1)
        self.assertNotEqual(self.backup().verified.sha256, self.backup("c3_agent").verified.sha256)

    def test_05_deterministic_bytes_with_injected_utc_clock(self):
        self.buy()
        a, b = self.backup(), self.backup()
        self.assertEqual(a.key, b.key)
        self.assertEqual(a.data, b.data)

    def test_06_create_only_first_store_succeeds(self):
        store = InMemoryTestObjectStore()
        backup = self.backup()
        self.assertTrue(store_backup(store, backup))
        self.assertEqual(store.read(backup.key), backup.data)

    def test_07_duplicate_store_is_idempotent(self):
        store = InMemoryTestObjectStore()
        item = self.backup()
        self.assertTrue(store_backup(store, item))
        self.assertFalse(store_backup(store, item))

    def test_08_stored_backup_can_be_checked_read_only(self):
        store, item = InMemoryTestObjectStore(), self.backup()
        store_backup(store, item)
        self.assertEqual(inspect_stored_backup(
            store, item.key, expected_account="trend_scanner"), item.verified)

    def test_09_foreign_account_restore_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "FOREIGN_ACCOUNT"):
            verify_backup(self.backup().data, expected_account="c3_agent")

    def test_10_corrupted_bytes_are_blocked(self):
        item = self.backup()
        with self.assertRaises(ValueError):
            verify_backup(item.data[:-1], expected_account="trend_scanner")

    def test_11_wrong_hash_is_blocked(self):
        item = json.loads(self.backup().data)
        item["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            verify_backup(canonical(item), expected_account="trend_scanner")

    def test_12_forged_cash_with_rehashed_payload_is_blocked(self):
        self.buy()
        forged = rewrite(self.backup(), lambda p: p["snapshot"].__setitem__("cash_cents", 99))
        with self.assertRaisesRegex(ValueError, "RECONCILIATION"):
            verify_backup(forged, expected_account="trend_scanner")

    def test_13_forged_position_with_rehashed_payload_is_blocked(self):
        self.buy()
        forged = rewrite(
            self.backup(),
            lambda p: p["snapshot"]["positions"][0].__setitem__("quantity", 99),
        )
        with self.assertRaisesRegex(ValueError, "RECONCILIATION"):
            verify_backup(forged, expected_account="trend_scanner")

    def test_14_wrong_account_in_event_even_when_rehashed_is_blocked(self):
        self.buy()
        forged = rewrite(
            self.backup(), lambda p: p["events"][0].__setitem__("account_id", "c3_agent"),
        )
        with self.assertRaisesRegex(ValueError, "IDENTITY"):
            verify_backup(forged, expected_account="trend_scanner")

    def test_15_duplicate_event_id_even_when_rehashed_is_blocked(self):
        self.buy()
        forged = rewrite(self.backup(), lambda p: p["events"].append(dict(p["events"][0])))
        with self.assertRaisesRegex(ValueError, "IDENTITY"):
            verify_backup(forged, expected_account="trend_scanner")

    def test_16_forged_event_profit_even_when_rehashed_is_blocked(self):
        self.buy()
        forged = rewrite(
            self.backup(), lambda p: p["events"][0].__setitem__("realized_pnl_cents", 42),
        )
        with self.assertRaisesRegex(ValueError, "EVENT_PNL"):
            verify_backup(forged, expected_account="trend_scanner")

    def test_17_non_demo_market_symbol_is_blocked(self):
        self.buy()
        forged = rewrite(self.backup(), lambda p: p["events"][0].__setitem__("symbol", "AAPL"))
        with self.assertRaisesRegex(ValueError, "IDENTITY"):
            verify_backup(forged, expected_account="trend_scanner")

    def test_18_wrong_order_side_is_blocked(self):
        self.buy()
        forged = rewrite(self.backup(), lambda p: p["events"][0].__setitem__("side", "REAL_ORDER"))
        with self.assertRaisesRegex(ValueError, "SIDE"):
            verify_backup(forged, expected_account="trend_scanner")

    def test_19_schema_with_extra_hidden_field_is_blocked(self):
        forged = rewrite(self.backup(), lambda p: p.__setitem__("broker_token", "fake"))
        with self.assertRaisesRegex(ValueError, "SCHEMA"):
            verify_backup(forged, expected_account="trend_scanner")

    def test_20_noncanonical_json_is_blocked(self):
        item = self.backup()
        with self.assertRaises(ValueError):
            verify_backup(item.data + b" ", expected_account="trend_scanner")

    def test_21_naive_timestamp_is_blocked(self):
        forged = rewrite(
            self.backup(), lambda p: p.__setitem__("created_at_utc", "2026-11-23T12:00:00"),
        )
        with self.assertRaisesRegex(ValueError, "CLOCK"):
            verify_backup(forged, expected_account="trend_scanner")

    def test_22_wrong_verified_key_is_blocked_before_storage(self):
        store, item = InMemoryTestObjectStore(), self.backup()
        altered = BackupObject(key="public/example", data=item.data, verified=item.verified)
        with self.assertRaisesRegex(ValueError, "KEY_MISMATCH"):
            store_backup(store, altered)
        self.assertEqual(store._objects, {})

    def test_23_fake_object_collision_is_fail_closed(self):
        store, item = InMemoryTestObjectStore(), self.backup()
        store._objects[item.key] = b"forged-data"
        with self.assertRaisesRegex(ValueError, "OBJECT_CONFLICT"):
            store_backup(store, item)
        self.assertEqual(store._objects[item.key], b"forged-data")

    def test_24_cannot_read_another_key_with_proof(self):
        store, item = InMemoryTestObjectStore(), self.backup()
        store._objects["other-key"] = item.data
        with self.assertRaisesRegex(ValueError, "KEY_MISMATCH"):
            inspect_stored_backup(store, "other-key", expected_account="trend_scanner")

    def test_25_oversized_backup_rejected(self):
        with self.assertRaisesRegex(ValueError, "SIZE_BLOCKED"):
            verify_backup(b"x" * (MAX_BYTES + 1), expected_account="trend_scanner")

    def test_26_nonexistent_ledger_is_not_created(self):
        missing = Path(self.directory.name) / "missing.sqlite"
        with self.assertRaisesRegex(ValueError, "LEDGER_MISSING"):
            make_backup(missing, "trend_scanner", now=CLOCK)
        self.assertFalse(missing.exists())

    def test_27_unknown_account_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "ACCOUNT_BLOCKED"):
            make_backup(self.file, "unknown", now=CLOCK)

    def test_28_naive_clock_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "CLOCK_BLOCKED"):
            make_backup(self.file, "trend_scanner", now=datetime(2026, 11, 23))

    def test_29_no_cloud_or_order_sdk_dependencies(self):
        import ast
        for path in (ROOT / "r2_backup_contract.py", ROOT / "r2_object_contract.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports = []
            for item in ast.walk(tree):
                if isinstance(item, ast.Import):
                    imports.extend(a.name for a in item.names)
                if isinstance(item, ast.ImportFrom) and item.module:
                    imports.append(item.module)
            for blocked in ("boto3", "requests", "httpx", "streamlit", "cloudflare",
                            "alpaca", "yfinance", "openai"):
                self.assertFalse(any(name == blocked or name.startswith(blocked + ".")
                                     for name in imports), (blocked, imports))

    def test_30_cloud_hosted_ui_remains_isolated(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("r2_backup_contract", source)
        self.assertNotIn("r2_object_contract", source)
        self.assertNotIn("paper_store", source)


if __name__ == "__main__":
    unittest.main()

"""Offline PT-30 safety and accounting contract tests. No Streamlit/cloud."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_store import (
    ACCOUNT_STRATEGIES,
    SyntheticFill,
    initialize_store,
    read_history,
    read_snapshot,
    record_synthetic_fill,
)


class OfflinePaperLedgerTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.db = Path(self.folder.name) / "pt30_local_only.sqlite3"
        initialize_store(self.db)

    def tearDown(self):
        self.folder.cleanup()

    def fill(self, id="EVENT_001", account="trend_scanner", strategy=None,
             symbol="DEMO-TS1", side="BUY", qty=2, price=10000, fee=100):
        return SyntheticFill(id, account, strategy or ACCOUNT_STRATEGIES[account],
                             symbol, side, qty, price, fee)

    def test_accounts_are_independent(self):
        self.assertEqual(read_snapshot(self.db, "trend_scanner").cash_cents, 1_000_000)
        self.assertEqual(read_snapshot(self.db, "c3_agent").cash_cents, 1_000_000)
        self.assertEqual(read_history(self.db, "trend_scanner"), ())

    def test_buy_changes_only_its_account(self):
        self.assertTrue(record_synthetic_fill(self.db, self.fill()))
        self.assertEqual(read_snapshot(self.db, "trend_scanner").cash_cents, 979900)
        self.assertEqual(read_snapshot(self.db, "c3_agent").cash_cents, 1_000_000)
        self.assertEqual(read_snapshot(self.db, "trend_scanner").positions[0].cost_basis_cents, 20100)
        self.assertEqual(len(read_history(self.db, "c3_agent")), 0)

    def test_purchase_fee_included_in_cost_basis(self):
        record_synthetic_fill(self.db, self.fill(fee=500))
        self.assertEqual(read_snapshot(self.db, "trend_scanner").positions[0].cost_basis_cents, 20500)

    def test_sell_realized_profit_after_all_fees(self):
        record_synthetic_fill(self.db, self.fill())
        record_synthetic_fill(self.db, self.fill(id="EVENT_002", side="SELL", price=12000, fee=100))
        snapshot = read_snapshot(self.db, "trend_scanner")
        self.assertEqual(snapshot.cash_cents, 1_003_800)
        self.assertEqual(snapshot.realized_pnl_cents, 3800)
        self.assertEqual(snapshot.positions, ())
        self.assertEqual(read_history(self.db, "trend_scanner")[-1].realized_pnl_cents, 3800)

    def test_partial_sell_keeps_remainder_basis(self):
        record_synthetic_fill(self.db, self.fill(qty=3, fee=2, price=100))
        record_synthetic_fill(self.db, self.fill(id="EVENT_002", side="SELL", qty=1, fee=0, price=120))
        pos = read_snapshot(self.db, "trend_scanner").positions[0]
        self.assertEqual(pos.quantity, 2)
        self.assertEqual(pos.cost_basis_cents, 202)
        self.assertEqual(read_snapshot(self.db, "trend_scanner").realized_pnl_cents, 20)

    def test_reinitialize_does_not_reset_ledger(self):
        record_synthetic_fill(self.db, self.fill())
        initialize_store(self.db)
        self.assertEqual(read_snapshot(self.db, "trend_scanner").cash_cents, 979900)
        self.assertEqual(len(read_history(self.db, "trend_scanner")), 1)

    def test_reopening_database_preserves_history(self):
        record_synthetic_fill(self.db, self.fill())
        self.assertEqual(read_history(self.db, "trend_scanner")[0].event_id, "EVENT_001")

    def test_exact_idempotent_replay_is_noop(self):
        event = self.fill()
        self.assertTrue(record_synthetic_fill(self.db, event))
        self.assertFalse(record_synthetic_fill(self.db, event))
        self.assertEqual(len(read_history(self.db, "trend_scanner")), 1)

    def test_conflicting_replay_rolls_back(self):
        record_synthetic_fill(self.db, self.fill())
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            record_synthetic_fill(self.db, self.fill(price=11000))
        self.assertEqual(read_snapshot(self.db, "trend_scanner").cash_cents, 979900)
        self.assertEqual(len(read_history(self.db, "trend_scanner")), 1)

    def test_event_id_cannot_cross_accounts(self):
        record_synthetic_fill(self.db, self.fill())
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            record_synthetic_fill(self.db, self.fill(account="c3_agent", symbol="DEMO-C31"))
        self.assertEqual(read_snapshot(self.db, "c3_agent").cash_cents, 1_000_000)

    def test_strategy_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "Cross-strategy"):
            record_synthetic_fill(self.db, self.fill(strategy="SYNTHETIC_C3"))

    def test_unknown_account_rejected(self):
        with self.assertRaises(ValueError):
            record_synthetic_fill(self.db, SyntheticFill("EVENT_001", "intruder", "SYNTHETIC_C3", "DEMO-XX", "BUY", 1, 100))

    def test_real_ticker_rejected(self):
        with self.assertRaisesRegex(ValueError, "Only fictional"):
            record_synthetic_fill(self.db, self.fill(symbol="AAPL"))

    def test_overbuy_rejected_atomically(self):
        with self.assertRaisesRegex(ValueError, "Insufficient artificial cash"):
            record_synthetic_fill(self.db, self.fill(qty=200))
        self.assertEqual(len(read_history(self.db, "trend_scanner")), 0)

    def test_oversell_rejected_atomically(self):
        record_synthetic_fill(self.db, self.fill(qty=2))
        with self.assertRaisesRegex(ValueError, "Insufficient artificial position"):
            record_synthetic_fill(self.db, self.fill(id="EVENT_002", side="SELL", qty=3))
        self.assertEqual(read_snapshot(self.db, "trend_scanner").positions[0].quantity, 2)
        self.assertEqual(len(read_history(self.db, "trend_scanner")), 1)

    def test_over_fee_sell_rejected(self):
        record_synthetic_fill(self.db, self.fill())
        with self.assertRaisesRegex(ValueError, "Fees exceed"):
            record_synthetic_fill(self.db, self.fill(id="EVENT_002", side="SELL", qty=1, price=1, fee=100))
        self.assertEqual(len(read_history(self.db, "trend_scanner")), 1)

    def test_malformed_amounts_rejected(self):
        for kwargs in ({"qty": 0}, {"qty": True}, {"price": 0}, {"fee": -1}, {"side": "PLACE_ORDER"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                record_synthetic_fill(self.db, self.fill(**kwargs))

    def test_database_is_not_created_on_read(self):
        missing = Path(self.folder.name) / "missing.sqlite3"
        with self.assertRaises(Exception):
            read_snapshot(missing, "trend_scanner")
        self.assertFalse(missing.exists())

    def test_events_are_tagged_fake_and_utc(self):
        record_synthetic_fill(self.db, self.fill())
        row = read_history(self.db, "trend_scanner")[0]
        self.assertEqual(row.strategy, "SYNTHETIC_TRENDSCANNER")
        self.assertIn("+00:00", row.created_at_utc)

    def test_two_accounts_keep_separate_history(self):
        record_synthetic_fill(self.db, self.fill())
        record_synthetic_fill(self.db, self.fill(id="EVENT_002", account="c3_agent", symbol="DEMO-C31", fee=0))
        self.assertEqual(len(read_history(self.db, "trend_scanner")), 1)
        self.assertEqual(len(read_history(self.db, "c3_agent")), 1)
        self.assertNotEqual(read_history(self.db, "trend_scanner")[0].account_id, read_history(self.db, "c3_agent")[0].account_id)


if __name__ == "__main__":
    unittest.main()

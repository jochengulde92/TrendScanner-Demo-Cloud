"""Unittest checks for the isolated, invented PT-29 portfolios."""
from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from demo_model import DEMO_ACCOUNTS, INITIAL_CAPITAL_CENTS, eur, position_rows


class TwoPortfolioOfflineTests(unittest.TestCase):
    def test_exactly_two_independent_accounts(self):
        self.assertEqual(len(DEMO_ACCOUNTS), 2)
        self.assertEqual({a.key for a in DEMO_ACCOUNTS}, {"trend_scanner", "c3_agent"})

    def test_strategy_separation(self):
        self.assertIn("TrendScanner", DEMO_ACCOUNTS[0].title)
        self.assertIn("C3", DEMO_ACCOUNTS[1].title)
        self.assertNotEqual(DEMO_ACCOUNTS[0].strategy, DEMO_ACCOUNTS[1].strategy)

    def test_independent_start_capital(self):
        for account in DEMO_ACCOUNTS:
            self.assertEqual(account.initial_capital_cents, INITIAL_CAPITAL_CENTS)

    def test_cash_and_equity_reconcile(self):
        for account in DEMO_ACCOUNTS:
            self.assertEqual(account.cash_cents, INITIAL_CAPITAL_CENTS - sum(p.cost_cents for p in account.positions))
            self.assertEqual(account.equity_cents, account.cash_cents + sum(p.market_value_cents for p in account.positions))
            self.assertEqual(account.pnl_cents, sum(p.unrealized_pnl_cents for p in account.positions))
            self.assertGreaterEqual(account.cash_cents, 0)

    def test_static_values_expected(self):
        self.assertEqual([a.pnl_cents for a in DEMO_ACCOUNTS], [200, 900])
        self.assertEqual([a.equity_cents for a in DEMO_ACCOUNTS], [1000200, 1000900])

    def test_all_fake_symbols_unique(self):
        tickers = [p.ticker for a in DEMO_ACCOUNTS for p in a.positions]
        self.assertEqual(len(tickers), len(set(tickers)))
        self.assertTrue(all(t.startswith("DEMO-") for t in tickers))

    def test_no_real_market_or_account_data(self):
        for account in DEMO_ACCOUNTS:
            self.assertTrue(all(p.shares > 0 and p.entry_cents > 0 and p.example_mark_cents > 0 for p in account.positions))
            self.assertIn("keine", account.limitation.lower())

    def test_rows_match_positions(self):
        for account in DEMO_ACCOUNTS:
            rows = position_rows(account)
            self.assertEqual(len(rows), len(account.positions))
            self.assertEqual([r["Symbol (erfunden)"] for r in rows], [p.ticker for p in account.positions])
            self.assertEqual([r["Positionswert"] for r in rows], [eur(p.market_value_cents) for p in account.positions])

    def test_eur_formatting(self):
        self.assertEqual(eur(1000200), "10.002,00 €")
        self.assertEqual(eur(-600), "−6,00 €")
        self.assertEqual(eur(7), "0,07 €")

    def test_no_network_or_runtime_model_imports(self):
        for filename in ("app.py", "demo_model.py"):
            source = (ROOT / filename).read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports += [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module.split(".")[0])
            self.assertTrue(set(imports) <= {"__future__", "dataclasses", "streamlit", "demo_model"})
            for forbidden in ("st.secrets", "st.login(", "st.button(", "st.form_submit_button(", "requests.", "httpx.", "subprocess", "socket.", "yfinance", "alpaca", "openai", "st.write_stream"):
                self.assertNotIn(forbidden, source)

    def test_ui_default_off_and_tab_driven(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("value=False", source)
        self.assertIn("st.tabs([account.title for account in DEMO_ACCOUNTS])", source)
        self.assertIn("st.dataframe(", source)

    def test_only_one_external_dependency(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        pins = [line.strip() for line in requirements.splitlines() if line.strip() and not line.startswith("#")]
        self.assertEqual(pins, ["streamlit==1.59.2"])


if __name__ == "__main__":
    unittest.main()

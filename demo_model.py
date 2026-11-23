"""Offline-only demonstration of separated synthetic paper portfolios.

All prices, symbols and positions are deliberately invented constants.
There is no scanner, C3 model inference, data provider, network access,
order execution, persistence, secrets or background scheduler in this module.
"""
from __future__ import annotations

from dataclasses import dataclass

INITIAL_CAPITAL_CENTS = 1_000_000


@dataclass(frozen=True)
class DemoPosition:
    ticker: str
    shares: int
    entry_cents: int
    example_mark_cents: int

    @property
    def cost_cents(self) -> int:
        return self.shares * self.entry_cents

    @property
    def market_value_cents(self) -> int:
        return self.shares * self.example_mark_cents

    @property
    def unrealized_pnl_cents(self) -> int:
        return self.market_value_cents - self.cost_cents


@dataclass(frozen=True)
class DemoAccount:
    key: str
    title: str
    strategy: str
    limitation: str
    positions: tuple[DemoPosition, ...]
    initial_capital_cents: int = INITIAL_CAPITAL_CENTS

    @property
    def cash_cents(self) -> int:
        return self.initial_capital_cents - sum(p.cost_cents for p in self.positions)

    @property
    def positions_value_cents(self) -> int:
        return sum(p.market_value_cents for p in self.positions)

    @property
    def equity_cents(self) -> int:
        return self.cash_cents + self.positions_value_cents

    @property
    def pnl_cents(self) -> int:
        return self.equity_cents - self.initial_capital_cents

    @property
    def pnl_pct(self) -> float:
        return 100 * self.pnl_cents / self.initial_capital_cents


# All positions are invented UI examples, not records.
# Future strategies can become further DemoAccount entries after approval.
DEMO_ACCOUNTS: tuple[DemoAccount, ...] = (
    DemoAccount(
        key="trend_scanner",
        title="Depot A · TrendScanner",
        strategy="Später: Originalsignale aus TrendScore, TQI und Confluence",
        limitation="Noch keine Verbindung zum echten Scanner; keine berechneten Signale.",
        positions=(
            DemoPosition("DEMO-TS1", 4, 4000, 4200),
            DemoPosition("DEMO-TS2", 3, 6500, 6300),
        ),
    ),
    DemoAccount(
        key="c3_agent",
        title="Depot B · KI-Modell C3",
        strategy="Später: unabhängige KI-C3-Strategie",
        limitation="Das C3-Modell wird hier NICHT ausgeführt; keine Agentenentscheidungen.",
        positions=(
            DemoPosition("DEMO-C31", 5, 9200, 9700),
            DemoPosition("DEMO-C32", 2, 13000, 12200),
        ),
    ),
)


def eur(cents: int) -> str:
    """Format exact integer cents in German EUR notation without locale deps."""
    sign = "−" if cents < 0 else ""
    absolute = abs(cents)
    whole, fractional = divmod(absolute, 100)
    return f"{sign}{whole:,}".replace(",", ".") + f",{fractional:02d} €"


def position_rows(account: DemoAccount) -> list[dict[str, object]]:
    """Return rows for display; no state changes or external calls."""
    return [
        {
            "Symbol (erfunden)": pos.ticker,
            "Stück (Demo)": pos.shares,
            "Einstand (Demo)": eur(pos.entry_cents),
            "Beispielkurs": eur(pos.example_mark_cents),
            "Positionswert": eur(pos.market_value_cents),
            "Unrealisierter Effekt": eur(pos.unrealized_pnl_cents),
        }
        for pos in account.positions
    ]

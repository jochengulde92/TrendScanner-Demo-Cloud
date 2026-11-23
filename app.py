"""PT-29: isolated Streamlit preview with two *synthetic* virtual depots.

No authentic TrendScanner signals, C3 inference, user accounts, APIs,
prices, order routing, persistence, scheduled jobs or external networking.
The only dependency is Streamlit; the sample data are static in memory.
"""
from __future__ import annotations

import streamlit as st

from demo_model import DEMO_ACCOUNTS, eur, position_rows

st.set_page_config(
    page_title="TrendScanner · Zwei Demo-Depots",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("TrendScanner · Paper-Trading-Vorschau")
st.warning(
    "ISOLIERTE TESTUMGEBUNG · Alle Symbole, Kurse, Depotwerte und Positionen "
    "sind erfunden. Keine echten Scanner-Signale, KI-Entscheidungen oder Orders."
)
st.caption(
    "PT-29 · Zwei getrennte, synthetische Beispieldepots auf iPad und iPhone. "
    "Kein Backend, kein Broker, kein Datenabruf und keine Speicherung."
)
show = st.toggle(
    "Künstliche Demo-Depots anzeigen",
    value=False,
    key="pt29_demo_enabled",
)

if not show:
    st.info(
        "Die Beispieldaten sind ausgeschaltet. Zum Ansehen der vollständig "
        "erfundenen Werte den Schalter aktivieren."
    )
else:
    st.subheader("Getrennte Strategie-Depots")
    st.caption(
        "Jedes Depot startet unabhängig mit 10.000 € Spielgeld. "
        "Alle Bestände und Wertänderungen sind feste Beispielzahlen."
    )
    tabs = st.tabs([account.title for account in DEMO_ACCOUNTS])
    for tab, account in zip(tabs, DEMO_ACCOUNTS):
        with tab:
            st.markdown(f"### {account.title}")
            st.write(account.strategy)
            st.info(account.limitation)
            balance, depot_value, result = st.columns(3)
            balance.metric("Spielgeld frei", eur(account.cash_cents))
            depot_value.metric("Virtueller Gesamtwert", eur(account.equity_cents))
            result.metric("Rechnerischer Demo-Effekt", eur(account.pnl_cents))
            st.caption(f"Demo-Veränderung gegenüber Start: {account.pnl_pct:+.2f} %")
            st.markdown("#### Künstliche Beispielpositionen")
            st.dataframe(
                position_rows(account),
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                "Positionen sind vorgegebene Beispieldaten; es werden keine "
                "Transaktionen angenommen, ausgelöst oder protokolliert."
            )

    st.divider()
    st.subheader("Später erweiterbar")
    st.write(
        "Die Ansicht kann später Depot C, Depot D oder weitere Strategien "
        "ergänzen. Dafür braucht jedes Setup eine getrennte Datenquelle, "
        "unabhängige Bewertung und eigene Freigabe."
    )
    st.warning(
        "Die echten TrendScore-/TQI-/Confluence-Signale und das C3-Modell "
        "sind bewusst NICHT angebunden. Hier können keine Orders "
        "ausgeführt oder gespeichert werden."
    )

st.divider()
st.caption(
    "Nur UI-Prototyp. Kein Live-Scan, keine KI-Agentenaktivität, "
    "kein Paper-Order-System, keine Handelsfreigabe."
)

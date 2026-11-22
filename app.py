"""PT-28: standalone, synthetic-only Streamlit Community Cloud preview.

A separate cloud pilot, NOT the live TrendScanner or private scanner.
No backend, login, real account, provider, API, market data, broker,
paper order, file I/O, external networking, or background worker.
The UI is empty by default until the user explicitly opts in.
"""
from __future__ import annotations

import streamlit as st

SYNTHETIC = (
    {
        "ticker": "DEMO01",
        "trend_score": 82,
        "tqi": 76,
        "confluence": 71,
        "final_score": 79,
        "status": "NUR DEMO – KEINE HANDELSFREIGABE",
    },
    {
        "ticker": "DEMO02",
        "trend_score": 64,
        "tqi": 59,
        "confluence": 43,
        "final_score": 58,
        "status": "NUR DEMO – KEINE HANDELSFREIGABE",
    },
)

st.set_page_config(
    page_title="TrendScanner · Isolierte Cloud-Vorschau",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("TrendScanner · Cloud-Vorschau")
st.warning(
    "REINE TESTUMGEBUNG: Keine echten Aktien, Kurse, "
    "TrendScanner-Signale, Depots oder Orders."
)
st.caption(
    "PT-28: Isolierte iPad-/iPhone-Demo für ein künftiges "
    "Hosting-Konzept. Keine Verbindung zum echten TrendScanner."
)

show = st.toggle("Künstliche Beispielwerte anzeigen", value=False, key="pt28_demo_enabled")

if not show:
    st.info(
        "Demodaten sind ausgeschaltet. Es werden weder Scanner-Daten "
        "noch Depot- oder Marktdaten abgefragt."
    )
else:
    st.warning(
        "Nur künstlich erfundene Zahlen! Kein Kaufvorschlag, "
        "kein Signal aus dem echten TrendScanner."
    )
    st.subheader("Künstliche Scanner-Evidenz")
    st.dataframe(
        SYNTHETIC,
        hide_index=True,
        use_container_width=True,
    )
    st.subheader("Künstliches virtuelles Depot")
    st.metric("Beispiel-Startwert", "10.000,00 €")
    st.metric("Künstliche Orders", "0")
    st.caption("Keine Anmeldung und keine Handelsfunktion vorhanden.")

st.divider()
st.caption(
    "Private GitHub-Repositories, Cloud-Freigaben, Authentifizierung "
    "und echtes Hosting sind nicht Bestandteil dieser Vorschau. "
    "PT-28 ist kein produktiver Trading-Agent."
)

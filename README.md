# TrendScanner · künstliche Cloud-Demo

**PT-29 — Zwei getrennte Demo-Depots (nur Prototyp, nicht live auf der veröffentlichten App).**

Dieses **öffentliche GitHub-Repository** enthält ausschließlich fiktive Anschauungsdaten. Die zugehörige Streamlit-App ist separat in den Streamlit-Cloud-Einstellungen auf **Only specific people can view this app** gestellt; die private Sichtbarkeit muss nach jeder Neuerstellung erneut kontrolliert werden. Der Quellcode hier bleibt öffentlich.

## Zwei unabhängig betrachtete Depots

- **Depot A – TrendScanner**: vorgesehene spätere Originalstrategie mit TrendScore, TQI und Confluence. Aktuell zwei vollständig erfundene Positionen und rein fiktive Bewertungen.
- **Depot B – KI-Modell C3**: vorgesehene eigenständige C3-Strategie. Aktuell zwei andere vollständig erfundene Positionen und rein fiktive Bewertungen. **C3 läuft hier nicht.**

Beide Konten starten separat mit **10.000 € Spielgeld**, enthalten unterschiedliche erfundene Symbole, führen eigene Cash-/Positions-/Gesamtwert- und rechnerische P&L-Summen und sind als getrennte Tabs dargestellt. Später kann ein weiteres Konto durch einen separaten `DemoAccount` erweitert werden, aber erst nach eigener Freigabe und eigenständigen Sicherheitsprüfungen.

## Dateien

- `app.py` – responsive Streamlit-Darstellung, standardmäßig **ausgeschalteter** Demo-Schalter
- `demo_model.py` – eingefrorene künstliche Datensätze, isolierte Portfolios und ganzzahlige Euro-Cent-Berechnung
- `requirements.txt` – einzige Python-Paketabhängigkeit `streamlit==1.59.2`
- `tests/test_demo_model.py` – lokale Standardbibliothek-Unittests für Trennung, Buchhaltung, Sicherheitsgrenzen und Datenformat

Lokal ohne Streamlit zu installieren testen:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python -m py_compile app.py demo_model.py
```

## Sicherheits- und Freigabegrenzen

**Keine** echten Aktien, Kurse, Scannerberechnungen, C3-Inferenz, Depoteinblicke, Zugangsdaten, API-Schlüssel, Brokerverbindung, Serverprozesse, automatischen Jobs, Dateipersistenz, Ordererstellung oder Käufe. Keine Datenverbindung zum privaten TrendScanner-Hauptprojekt, dessen Alpha-Gate oder echten Paper-Trading-Backend. Sämtliche Zahlen sind ausdrücklich erfunden.

Das Haupt-Repository `jochengulde92/TrendScanner` bleibt **privat**. Dieser PT-29-Branch wird ausschließlich per **Draft-PR** geprüft. **Kein Merge auf `main` ohne gesonderte Zustimmung**, weil die laufende Streamlit-App durch Änderungen an `main` automatisch aktualisiert werden kann.

Die echten Strategien, die Unterscheidung von Signalen und eine später sichere Paper-Order-Verwaltung müssen separat implementiert und freigegeben werden. `PT29_SOURCE_PREPARED` ist **nicht** `LIVE_PAPER_TRADING`.

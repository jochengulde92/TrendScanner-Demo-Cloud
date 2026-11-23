# PT-30 — Zwei getrennte virtuelle Strategiekonten: isolierter Offline-Ledger

**STATUS: SOURCE-ONLY / DRAFT / NICHT DEPLOYT / KEINE PAPER-ORDER-FREIGABE**

## Was ist implementiert?

- Eine reine Python-/SQLite-Komponente `paper_store.py` für zwei voneinander getrennte **synthetische** Konten:
  - `trend_scanner` (`SYNTHETIC_TRENDSCANNER`): späterer TrendScore-/TQI-/Confluence-Kanal;
  - `c3_agent` (`SYNTHETIC_C3`): späterer unabhängiger KI-C3-Kanal.
- Je Konto 10.000 € **Spielgeld**; getrennte Kassenbestände, Positionsmengen, Kostenbasen, realisierte Beispiel-Ergebnisse und vollständige lokale Transaktionshistorie.
- Rein rechnerische Fake-Buchungen `SyntheticFill` mit erfundenen Symbolen `DEMO-…`, Gebühren in ganzen Cent und UTC-Zeitstempel. Echte Wertpapiersymbole werden abgewiesen.
- Atomare SQLite-Transaktionen, globale Ereignis-ID gegen Doppelbuchung, Ablehnung von unzureichendem Spielgeld, ungedeckten Verkäufen, Strategie-Verwechslungen und widersprüchlichen Wiederholungen.
- Getrennte, nur lesende `read_snapshot`- und `read_history`-Schnittstellen. Künftige Depotkanäle C/D können erst nach gezielter Erweiterung der erlaubten Strategien ergänzt werden.
- Die Daten bleiben **nur in einer explizit angelegten lokalen SQLite-Datei** erhalten, solange diese Datei existiert. Kein automatischer Datenbankstart beim Import und **keine Anbindung an die Streamlit-App**.

## Was ist ausdrücklich NICHT implementiert?

**Keine echten historischen, aktuellen oder verzögerten Marktdaten, Scanner-/C3-Signale, KI-Aktionen, Broker-Schnittstellen, echten oder Paper-Orders, API-Abfragen, Datenbank-Accounts für Benutzer, OAuth, Secrets, Agenten, Hintergrundjobs oder Cloud-Persistenz.** Das Python-Modul ist ein Daten- und Abrechnungsvertrag, keine freigegebene Trading-Engine.

**Wichtige Speichergrenze:** Streamlit Community Cloud hat kein verlässliches dauerhaftes lokales Dateisystem für Depotdaten. Eine lokal dort erzeugte SQLite-Datei kann bei Restart/Rebuild verschwinden; bei mehreren Benutzern besteht ohne echte Authentifizierung und serverseitige Mandantentrennung außerdem ein Sicherheitsrisiko. Deshalb wird dieser Ledger bewusst **nicht** im Cloud-Frontend aktiviert. Für sichere dauerhafte Speicherung sind später gesonderte Architekturprüfung, Identitäts-/Rechteprüfung, Backups und ggf. ein externer Dienst nötig. **Keine externen Ressourcen oder kostenpflichtigen Angebote ohne erneute Freigabe.**

## Testvertrag

Ohne Netzwerk oder zusätzliche Python-Pakete auf einer lokalen isolierten Kopie ausführbar:

```bash
python -m unittest discover -s tests -p 'test_paper_store.py' -v
python -m py_compile paper_store.py
```

20 Offline-Tests decken Isolation, neutrale Bestandsrechnung, Kauf, vollständigen/anteiligen Verkauf, Gebühren, Neustart derselben lokalen Datenbankdatei, unveränderte Wiederholungen, doppelte ID in anderem Depot, Abweisung ungültiger Daten, ungedeckte Transaktionen, Abweisung realer Symbole und No-Create-On-Read ab.

## Strikte Release-Grenzen

- Verändern **nur** dieses öffentliche künstliche Demo-Repository, nicht das private `jochengulde92/TrendScanner`.
- **Nur GitHub-Draft-PR**; kein Merge, Streamlit-Deployment, Datenbankdienst, Codespace, Actions oder weitere Kosten.
- Die bereits privat freigegebene PT-29-Oberfläche auf `main` bleibt unverändert.
- Die Schnittstellen für TrendScanner und C3 sind **Namen/Strategie-IDs**, nicht die tatsächlichen Entscheidungsmodelle.
- Nächste Etappe vor einer Cloud-Aktivierung: persistente und mandantengetrennte Speicherung, Privatzugriff und Wiederanlauftests mit einem explizit genehmigten Betriebsmodell.

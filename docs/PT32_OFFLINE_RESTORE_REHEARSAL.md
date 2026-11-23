# PT-32 – Isolierte Offline-Wiederherstellungsprobe

**Status: NUR DRAFT / NICHT GEMERGT / NICHT DEPLOYT / NEUE TESTS NOCH NICHT AUF DEM GITHUB-STAND AUSGEFÜHRT.**

## Umfang
- Ausschließlich die neue Datei `pt32_restore.py`: `restore_to_new_local_ledger(backup_data, expected_account=..., target_path=...)` stellt ein von PT-31 verifiziertes *synthetisches* Strategiekonto in einer **neuen** lokalen SQLite-Datei wieder her.
- Die bestehenden PT-30-/PT-31-Module, die laufende Streamlit-App und das private TrendScanner-Projekt bleiben unverändert.
- Der Zielordner muss bereits vorhanden sein. Zielname endet auf `.sqlite3`. Vorhandene Dateien, Verzeichnisse und auch defekte Symlinks werden nicht überschrieben.
- PT-31 prüft vor jeder lokalen Dateierstellung Konto, Strategie, alle Ereignisse, Cash, Kostenbasis, Gebühren, P&L, Hash, Größe und kanonische Daten.
- Die wiederhergestellte SQLite-Datei entsteht zuerst in einem temporären Unterordner desselben Zielordners. Erst nach Transaktion, vollständigem Read-back aller Ereignisse/Positionen und `PRAGMA integrity_check` wird sie via `os.link` **create-only** unter dem endgültigen Dateinamen veröffentlicht.
- Fehler vor diesem Schritt hinterlassen keine Ziel-Datenbank. Ein konkurrierender Dateiname wird niemals ersetzt. Wenn Hardlinks auf dem Dateisystem nicht unterstützt sind, wird der Restore abgelehnt (fail-closed).
- Es wird **ein** Konto aus dem PT-31-Backup wiederhergestellt; das zweite, ebenfalls künstliche Konto bleibt leer. Getrennte Konten können in **getrennte neue Dateien** wiederhergestellt werden. Keine atomare Zwei-Konten-Transaktion und kein cloudfähiger Multi-Writer-Mechanismus.

## Neue Testfälle
- `tests/test_pt32_restore.py` enthält 19 Tests für leeres Konto, Kauf/Verkauf, Gebühren, exakte UTC-Ereigniszeit, Strategietrennung, Manipulation/Hash, vorhandene Daten, defekte Symlinks, Restore-Rennen, induzierte Fehler, ungültige Dateipfade, Wiederholung und unveränderte Quelldaten.
- PT-29 12 + PT-30 20 + PT-31 30 = 62 zuvor nachgewiesene Tests. **PT-32 fügt 19 neue hinzu; 81 Tests sind nur das Ziel, kein derzeitiger PASS-Nachweis.**

## Offline-Prüfung (ohne Neuinstallation oder externe Aufrufe)
1. `python -m unittest discover -s tests -p 'test_pt32_restore.py' -v`
2. Nur bei PASS: `python -m unittest discover -s tests -p 'test_*.py' -v`
3. Nur bei PASS: `python -m py_compile pt32_restore.py paper_store.py r2_backup_contract.py r2_object_contract.py`
Bei Fehler: STOP, keine automatischen Korrekturen und keine Freigabe zum Merge.

## Sicherheits- und Freigabegrenzen
- Nur komplett erfundene Symbole `DEMO-...`, je Strategie separat 10.000 € Spielgeld. Kein echtes Paper Trading, keine Broker- oder Marktpreis-API, keine Hintergrundjobs, keine Authentifizierung, keine echten Depotdaten.
- Kein Cloudflare-Bucket, SDK, Token, R2-Upload, externes Internet oder kostenpflichtige Ressource.
- Ein SHA-256-Backup ist **nicht authentifiziert**. Ein altes, inhaltlich korrektes Backup kann wiederholt werden; der Code hat **keinen Anti-Rollback-/Monotonic-Head-Schutz**. Kein Signing, kein Key-Management, keine dauerhafte Cloud-Persistenz, keine Multi-Writer-Garantie.
- Die Link-Publikation ist eine atomare **lokale create-only Dateioperation**, keine stromausfallsichere Cloud-Transaktion und keine verteilte Datenbank.
- Keine Änderungen an `app.py`, `requirements.txt`, `main`, Alpha-Gate, TSK5/TSK6 oder dem privaten Repo. **Draft-PR nur auf PT-31**, kein Merge/Deploy/Workflow/Codespace ohne weitere ausdrückliche Freigabe.

**PT32_SOURCE_PREPARED != PT32_TEST_PASS != CLOUD_RESTORE_ACTIVE != PAPER_AGENT_RUNNING.**

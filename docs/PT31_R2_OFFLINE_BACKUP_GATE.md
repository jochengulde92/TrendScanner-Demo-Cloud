# PT-31 — R2-Backup-Vertrag für zwei synthetische Paper-Trading-Depots

**Status: NUR GITHUB-DRAFT / KEIN CLOUD-ZUGRIFF / NICHT GEMERGT / OFFLINE-TESTS NOCH NICHT AUSGEFÜHRT.**

## Ziel und technischer Vertrag

Der vorhandene lokale PT-30-SQLite-Ledger soll irgendwann kontrollierbar in unserem **bestehenden Cloudflare-Konto** gesichert werden können, **ohne** einen weiteren Cloud-Anbieter zu kaufen oder Zugriff auf private Depotdaten aus dem öffentlichen Demo-Repository zu öffnen.

PT-31 enthält **nur neue, isolierte Dateien** und hat keinerlei Einfluss auf die auf dem iPad erreichbare PT-29-Demo:

1. `r2_backup_contract.py`: Liest einen explizit angegebenen **lokalen synthetischen** PT-30-SQLite-Ledger in einer einzigen read-only Transaktion, Konto und Transaktionen konsistent. Erzeugt ein strikt schematisiertes kanonisches JSON-Backup und dessen SHA-256-Summe. Der Objekt-Key ist in einem konto-getrennten Namespace nach dem vollständigen Content-Hash benannt. Größenlimit 2 MB, maximal 10.000 fiktive Buchungsereignisse bzw. 1.000 Beispielpositionen.
2. Dieselbe Datei verifiziert Backups vor jeder eventuellen Rücksicherung **lesend**, inklusive Konto-/Strategie-Identität, Schema, Kanonizität, Prüfsumme und **erneuter unabhängiger Buchungsrekonstruktion aller Ereignisse**: Cash, Positionskosten, Gebühren, realisierte Gewinne/Verluste. Fremdkonten, Manipulation, fehlende Events, ungedeckte Bewegungen und inkonsistente Positionen werden abgewiesen. `preview_restore` schreibt **keine** Datenbank.
3. `r2_object_contract.py`: Beschreibt den zukünftigen Cloud-Speichervertrag mit atomarem `put_if_absent()` und `read()`. Der allein enthaltene `InMemoryTestObjectStore` speichert **nur flüchtig im Arbeitsspeicher**. Schreibt ein Key bereits, wird nur der identische Inhalt als idempotente Wiederholung akzeptiert; ein anderer Inhalt ist ein harter Fehler. **Kein Cloudflare-SDK, kein boto3, kein Token, keine URL, kein HTTP.**
4. `tests/test_r2_backup_contract.py`: 30 neue rein synthetische Offline-Testmethoden; zu prüfen in einer echten Python-Umgebung, **noch kein Test-PASS behaupten**.

**Wichtig zur Versionskontrolle:** Die Backup-Dateien sind inhaltlich adressiert. Das verhindert Überschreiben auf demselben Key nur dann, wenn der spätere R2-Adapter `PutObject` **mit `If-None-Match: *`** aufruft. Ein zweites, widersprüchliches Backup kann auf einem **anderen** Content-Key entstehen. PT-31 enthält bewusst noch **keine vertrauenswürdige monotone Versions-/Head-Verwaltung, keine Schlüssel-/Signaturverwaltung und keine Multi-Writer-Lease**. Ein SHA-256-Hash schützt vor zufälliger Beschädigung, **nicht** vor einem Angreifer, der Daten *und* Prüfsumme austauschen kann, und nicht vor einem Rollback auf einen alten gültigen Datenstand.

## Cloudflare R2: bestätigte API-Grenzen

- R2 unterstützt atomische **bedingte `PutObject`-Writes** über die S3-API mit `If-None-Match: *`. Bei vorhandenen Keys: **HTTP 412** statt Überschreiben.
  - https://developers.cloudflare.com/r2/api/s3/conditional-operations/
- R2 bietet Free-Kontingente, aber die Nutzung ist **mengenabhängig**. Eine rein textliche Anweisung „keine Kosten“ setzt **keine technische Ausgabenbegrenzung** durch.
  - https://developers.cloudflare.com/r2/pricing/
- Streamlit Community Cloud ist für einen **dauerhaft laufenden Ledger-/Agentenprozess** nicht zuverlässig. Lokales SQLite dort kann durch Neustarts verloren gehen.
- Das bereits vorhandene Cloudflare-R2-Setup für historische Research-Backups wird **nicht automatisch** für persönliche Paper-Depotdaten freigegeben. Vor realer Nutzung prüfen wir Bucket-Privatheit, Zugriffsbereich, Standort/Datenschutz, Kosten-/Quoten-Kontrolle, Aufbewahrungs-/Backupregeln und getrennte Prefixe bzw. neue Buckets.

## Offline-Tests (erst nach tatsächlichem Lauf als PASS melden)

In einer **bereits vorhandenen kostenfreien** Python-/Codex-Umgebung, nur wenn **keine zusätzlichen Credits, Installationen oder Gebühren** anfallen:

```bash
python -m unittest discover -s tests -p 'test_r2_backup_contract.py' -v
# nur bei PASS:
python -m unittest discover -s tests -p 'test_*.py' -v
python -m py_compile paper_store.py r2_backup_contract.py r2_object_contract.py
```

Die 30 neuen PT-31-Testmethoden sind **in der vollständigen Testsuche enthalten**. PT29 hatte 12, PT30 20; mit PT31 ergibt sich ein erwartetes **62-Methoden-Ziel**, aber der tatsächliche Teststatus muss erst bestätigt werden.

Tests dürfen nur lokale Temp-Verzeichnisse und Test-Doubles benutzen; **keine echten R2-Uploads**, kein Bucket-Listing, keine realen Daten, keine Cloudflare-Konsole und keine Secrets. Beim ersten Fehler STOP, Traceback berichten, keine selbstständigen Codeänderungen.

## Freigabegrenzen

PT-31 darf **nicht** in die öffentliche Demo-`app.py` eingebunden werden. Das Demo-Repo enthält weiterhin ausschließlich **fiktive** Daten. Keine Änderungen am privaten `jochengulde92/TrendScanner`, Alpha-Gate/TSK5/TSK6, echten Signalen, C3-Modell oder Orderkomponenten. Kein Merge, kein GitHub Action/Codespace-Start, kein neuer Bucket, kein Abrechnungsschalter, kein Auth-Token, kein API-Key, keine zusätzlichen Kosten oder Online-Buchungen.

**Nächster gesondert freizugebender Schritt:** Cloudflare-Kontozustand/Bucket-Privatheit/Kostenmodus/regionale Datenschutzanforderungen prüfen. Danach einen streng begrenzten R2-Adapter in **privatem** Code mit verschlüsselten Secrets und kontrollierten Read/Write/Restore-Tests entwickeln; ggf. D1 für atomare Depot-Transaktionen prüfen.

**PT31_DRAFT_SOURCE_PREPARED ≠ PT31_TEST_PASS ≠ CLOUD_BACKUP_ACTIVE ≠ DURABLE_TRADING_LEDGER ≠ AUTOMATED_PAPER_AGENT.**

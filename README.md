# Speiseplan Burgschule Nieder-Olm (inoffiziell)

Mobile-first-PWA, die öffentlich verlinkte Speiseplan-PDFs der Schule **einmal täglich** einliest und als statische Netlify-Seite bereitstellt.

**Stand 29.09.2026:** Die geprüfte PDF umfasst 10.08.–02.10.2026 (40 Tage). Der 12.08. ist gesperrt, weil Menü II im Original-PDF unvollständig geklammert ist; alle anderen 39 Tage wurden positionsbasiert extrahiert. Der Parser prüft alle Tage automatisch, aber ohne unabhängige Referenz ist eine plausibel wirkende Fehlzuordnung nicht völlig auszuschließen. Allergenkürzel werden originalgetreu angezeigt, nicht interpretiert.

## Lokal starten

Python 3.13+ und Node 22+ empfohlen. Mit `uv`:

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
npm ci --ignore-scripts
.venv/bin/python -m unittest discover -s tests -v
npm test
.venv/bin/python -m scripts.update
python3 -m http.server 8080 -d site
```

Dann `http://localhost:8080` öffnen. Ohne `uv` geht auch eine normale Python-Venv mit `pip install -r requirements.txt`. Die Seite selbst hat weder Bundler noch externe JavaScript-Abhängigkeiten; `npm ci` installiert nur die DOM-Testumgebung. Die erste Aktualisierung benötigt Internet, der bereits erzeugte Datenstand liegt in `site/data/menu.json`. Der PWA-Offline-Modus funktioniert nach dem ersten erfolgreichen Laden auf `localhost` oder HTTPS.

## Veröffentlichung auf Netlify – noch gesperrt

**Vor der öffentlichen Veröffentlichung** muss der Betreiber `site/impressum.html` und `site/datenschutz.html` eigenverantwortlich ausfüllen und jeweils die Markierung `RECHTLICHE_ANGABEN_FEHLEN` entfernen. Die Datenschutzhinweise sind ein technischer Entwurf, keine Rechtsprüfung. Vor dem Start Netlify-Konto/DPA, konkrete Datenstandorte, Protokollierung und Aufbewahrungsfristen prüfen; keine ungeprüfte Frist behaupten. `netlify.toml` bricht Produktions-Builds solange bewusst ab (`python3 scripts/check_launch.py`). Die Prüfung erkennt bestimmte offene Platzhalter, **nicht** rechtliche Vollständigkeit oder inhaltliche Richtigkeit. Es gibt keine Freigabe der Schule/des Rechteinhabers zur Wiedergabe der Speiseplantexte; Quellenangabe allein behebt das nicht. Neutrale, inoffizielle Darstellung ohne Schul-Logo beibehalten.

Danach:

1. Dieses Repository als **öffentliches** GitHub-Repository anlegen; `.github/workflows/update-menu.yml` auf den Default-Branch bringen. Unter **Settings → Actions → General** dem `GITHUB_TOKEN` Schreibrechte für `contents` und `issues` ermöglichen und Issues für das Repository einschalten.
2. Repository in Netlify über **Add new site → Import an existing project** verbinden. `netlify.toml` legt Publikationsordner (`site`) und den Prüf-Build fest. Zunächst die kostenlose `*.netlify.app`-Adresse verwenden.
3. Workflow **Speiseplan täglich aktualisieren** einmal über `workflow_dispatch` manuell starten. Danach läuft er täglich um 06:00 UTC (GitHub kann geplante Starts verzögern). Ein aktualisierter Daten-Commit auf dem Default-Branch löst regulär den Netlify-Git-Deploy aus. Falls nicht, Netlify-Git-Integration und Push-Webhooks prüfen. https://docs.netlify.com/deploy/create-deploys/ 
4. Testweise PDF-Link, Tagesnavigation, PWA-Installation, Offline-Nutzung, Rechtsseiten und Mobilansicht auf iPhone/Android prüfen. GitHub-Benachrichtigungen für Issues aktivieren, damit Warnungen tatsächlich ankommen.

## Verarbeitung und Fehlerverhalten

- Scrapling sucht nach PDF-Links auf „Aktuelles“, bei fehlendem/bald ablaufendem Plan zusätzlich auf begrenzt vielen internen Seiten aus der Schul-Sitemap. Zugelassen sind nur HTTPS-PDFs auf `burgschule-nieder-olm.de`; alte Pläne werden nicht als aktuelle Kandidaten behandelt.
- PyMuPDF nutzt **Koordinaten statt PDF-Lesereihenfolge**. Jede Seite braucht fünf aufeinanderfolgende Wochentage, Menü I, Menü II und Dessert. Texte außerhalb erkannter Zellen, fehlende Felder oder unvollständige Klammern sperren den betreffenden Tag. Unbekanntes Layout bzw. Scan wird nicht ungeprüft publiziert. Das Original-PDF ist per Tag verlinkt.
- Nur noch gültige veröffentlichte Pläne werden als Tagesdaten gehalten. Wenn kein Plan für heute vorliegt oder eine aktualisierte PDF nicht sicher lesbar ist, keine Gerichte erfinden und niemals einen abgelaufenen Tag als „heute“ zeigen. Offline-Daten sind mit dem Zeitpunkt des letzten Abrufs gekennzeichnet.
- Warnungen – auch wenn ein Nachfolgeplan binnen sieben Tagen fehlt – werden als **ein aktualisiertes GitHub-Issue** geführt und bei Entwarnung geschlossen. Der Betreiber muss bei neuem PDF-Layout den Parser korrigieren; ein manueller Datenimport ist nicht vorgesehen. Sind Issues deaktiviert oder fehlen Actions-Berechtigungen, kann diese Benachrichtigung fehlschlagen.
- PDFs werden nicht ins Repo kopiert. `site/data/menu.json` enthält nur die aus öffentlichen PDFs gelesenen Texte, Quellenadressen und Prüfsummen. `import-warnings.json` wird lokal erzeugt und nicht veröffentlicht. Die Webseite ruft die Schulwebsite nicht bei jedem Besuch ab.

## Struktur

- `scripts/pdf_menu.py`: fail-closed PDF-Tabellenparser
- `scripts/update.py`: Scrapling-Linksuche, Validierung, Datenimport
- `scripts/notify.py`: GitHub-Issue für Warnungen
- `site/`: statische PWA samt generiertem `data/menu.json`
- `.github/workflows/update-menu.yml`: täglicher Import und Tests
- `tests/`: synthetischer 40-Tage-PDF-Test, Datums-/Fehlerfalltests und DOM-Test der Tagesansicht

Weitere Funktionen (Bestellung, Push, Logins, manuelle Redaktion) gehören nicht zu Version 1.

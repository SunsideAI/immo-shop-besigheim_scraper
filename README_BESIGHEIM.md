# Immobilien Besigheim Scraper

Automatischer Scraper für https://www.immo-shop-besigheim.de/immobilienangebote/

Basierend auf dem heyen-immobilien Scraper

## 🎯 Features

- ✅ **Smart Sync** mit Airtable (create/update/delete)
- ✅ **Keine Duplikate** (eindeutige URL-basierte Identifikation)
- ✅ **Kategorie** = "Kaufen" (Website hat nur Kaufangebote)
- ✅ **Vollständige Beschreibung** von Detailseiten
- ✅ **Standort-Extraktion** (Ort, teilweise mit PLZ)
- ✅ **Robuste Preis-Extraktion** (Kaufpreis)
- ✅ **CSV Export** als Backup

## 📊 Airtable-Struktur

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| Titel | Text | Immobilientitel |
| Kategorie | Single select | **"Kaufen"** (immer) |
| Webseite | URL | Link zur Detailseite |
| Objektnummer | Text | URL-Slug als eindeutige ID |
| Beschreibung | Long text | Beschreibung von Detailseite |
| Bild | URL | Hauptbild |
| Preis | Number | Numerischer Preis |
| Standort | Text | Ort (z.B. "Löchgau", "Besigheim") |

## 🚀 Installation & Verwendung

### Lokal

```bash
# 1. Installiere Dependencies
pip install requests beautifulsoup4 lxml

# 2. Setze Environment Variables
export AIRTABLE_TOKEN="patXXXXXXXXXXXXXX"
export AIRTABLE_BASE="appXXXXXXXXXXXXXX"
export AIRTABLE_TABLE_ID="tblXXXXXXXXXXXXX"

# 3. Starte Scraper
python besigheim_scraper.py
```

### GitHub Actions (Automatisch)

1. **Repository erstellen** und Code hochladen
2. **Secrets einrichten** in Settings → Secrets and variables → Actions:
   - `BESIGHEIM_AIRTABLE_TOKEN` = dein Airtable Personal Access Token
   - `BESIGHEIM_AIRTABLE_BASE` = Base ID (z.B. `appXXXXXX`)
   - `BESIGHEIM_AIRTABLE_TABLE_ID` = Table ID (z.B. `tblXXXXXX`)
3. **Workflow-Datei** platzieren: `.github/workflows/scrape-besigheim.yml`
4. **Automatisch**: Läuft täglich um 08:00 UTC (09:00 MEZ)
5. **Manuell**: Actions Tab → "Scrape Besigheim Immobilien" → "Run workflow"

## 📝 Output

```
besigheim_immobilien.csv
- Alle Immobilien als CSV-Backup
- Encoding: UTF-8
- Felder: Titel, Kategorie, Webseite, Objektnummer, Beschreibung, Bild, Preis, Standort
```

## 🔧 Konfiguration

```python
# besigheim_scraper.py

BASE = "https://www.immo-shop-besigheim.de"
LIST_URL = f"{BASE}/immobilienangebote/"

# Rate Limiting
REQUEST_DELAY = 1.5  # Sekunden zwischen Requests
```

## 📋 Airtable Setup

### 1. Erstelle eine neue Base (oder nutze bestehende)

In Airtable → Create → Start from scratch

### 2. Erstelle Felder

| Feldname | Feldtyp | Optionen |
|----------|---------|----------|
| Titel | Single line text | - |
| Kategorie | Single select | Optionen: "Kaufen" |
| Webseite | URL | - |
| Objektnummer | Single line text | - |
| Beschreibung | Long text | Enable rich text formatting |
| Bild | URL | - |
| Preis | Number | Format: Euro (€), Precision: 0 |
| Standort | Single line text | - |

### 3. API Zugriff einrichten

1. Gehe zu https://airtable.com/create/tokens
2. Erstelle einen neuen Token mit:
   - **Scopes**: `data.records:read`, `data.records:write`
   - **Access**: Deine Base auswählen
3. Kopiere den Token (beginnt mit `pat...`)

## 📖 Beispiel Output

```
[BESIGHEIM] Starte Scraper für immo-shop-besigheim.de
[LIST] Hole https://www.immo-shop-besigheim.de/immobilienangebote/
[LIST] Gefunden: 13 Immobilien

[SCRAPE] 1/13 | https://www.immo-shop-besigheim.de/immobilie/altersgerechtes-wohnen-im-ortskern-von-loechgau-4/
  → Kaufen   | *KFW-40* Modernes Wohnen in Löchgau für jede Lebensphase | Löchgau | Preis: 489250.0

[SCRAPE] 2/13 | https://www.immo-shop-besigheim.de/immobilie/exklusive-villa-in-begehrter-lage-mit-wellnessbereich/
  → Kaufen   | Exklusive Villa in begehrter Lage mit Wellnessbereich | Gerlingen | Preis: 1450000.0

...

[CSV] Gespeichert: besigheim_immobilien.csv (13 Zeilen)

[AIRTABLE] Starte Synchronisation...
[SYNC] Gesamt → create: 13, update: 0, delete: 0
[Airtable] Erstelle 13 neue Records...
[Airtable] Synchronisation abgeschlossen.
```

## 🔍 Besonderheiten der Besigheim-Website

- **Nur Kaufangebote**: Website hat keine Mietangebote
- **WordPress-basiert**: Ähnliche Struktur wie Heyen
- **Strukturierte Daten**: Preis, Wohnfläche direkt sichtbar auf Übersichtsseite
- **Ortsnamen**: Oft nur Stadt (z.B. "Löchgau"), selten mit PLZ
- **Optimierte Bilder**: Bilder über phastpress Plugin

## 🛠 Troubleshooting

### "Keine Links gefunden"
→ Prüfe ob die Website erreichbar ist
→ Eventuell Rate Limiting erhöhen

### "Airtable ENV nicht gesetzt"
→ Prüfe Environment Variables
→ Token muss mit `pat` beginnen

### "Standort fehlt"
→ Der Scraper extrahiert oft nur Ortsnamen ohne PLZ
→ Das ist bei dieser Website normal

### "Preis fehlt"
→ Preis-Pattern: "Kaufpreis: XXX.XXX €"
→ Wird von Übersichtsseite und Detailseite extrahiert

## 📚 Basiert auf

- **heyen-immobilien Scraper**
- Bewährte Patterns für:
  - Standort-Extraktion
  - Duplikat-Vermeidung
  - Beschreibungs-Parsing
  - Airtable Sync-Logik

## 🔧 Support

Bei Fragen oder Problemen → Issue erstellen

---

**Version:** 1.0  
**Letzte Aktualisierung:** 20.11.2024  
**Kompatibilität:** Python 3.8+

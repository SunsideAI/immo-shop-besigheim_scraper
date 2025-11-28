#!/usr/bin/env python3
"""
Scraper für https://www.immo-shop-besigheim.de/immobilienangebote/
Extrahiert Immobilienangebote und synct mit Airtable

Basierend auf heyen-immobilien Scraper
"""

import os
import re
import sys
import csv
import json
import time
import base64
import urllib.parse
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Optional

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("[ERROR] Fehlende Module. Bitte installieren:")
    print("  pip install requests beautifulsoup4 lxml")
    sys.exit(1)

# ===========================================================================
# KONFIGURATION
# ===========================================================================

BASE = "https://www.immo-shop-besigheim.de"
LIST_URL = f"{BASE}/immobilienangebote/"

# Airtable
AIRTABLE_TOKEN = os.getenv("AIRTABLE_TOKEN", "")
AIRTABLE_BASE = os.getenv("AIRTABLE_BASE", "")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID", "")

# Rate Limiting
REQUEST_DELAY = 1.5

# ===========================================================================
# REGEX PATTERNS
# ===========================================================================

RE_PLZ_ORT = re.compile(r"\b(\d{5})\s+([A-ZÄÖÜ][a-zäöüß\-\s/]+)")
RE_PRICE = re.compile(r"([\d.,]+)\s*€")

# ===========================================================================
# STOPWORDS
# ===========================================================================

STOP_STRINGS = [
    "Cookie", "Datenschutz", "Impressum", "Sie haben Fragen",
    "kontakt@", "Tel:", "Fax:", "E-Mail:", "www.", "http",
    "© ", "JavaScript", "Alle Rechte", "Rufen Sie uns an",
    "Kontaktieren Sie mich", "IMMO-SHOP", "Wasilios Totsikas"
]

# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================

def decode_phastpress_url(phast_url: str) -> str:
    """Dekodiere phastpress-URL um echte Bild-URL zu erhalten"""
    if "phastpress/phast.php/" not in phast_url:
        return phast_url
    
    try:
        import base64
        import urllib.parse
        
        # Extrahiere Base64-Teil
        parts = phast_url.split("/phast.php/")
        if len(parts) < 2:
            return phast_url
        
        encoded = parts[1]
        
        # Entferne Dateiendung (.q.jpg, .jpg, etc.)
        encoded = encoded.split(".q.jpg")[0]
        encoded = encoded.split(".jpg")[0]
        encoded = encoded.split(".jpeg")[0]
        encoded = encoded.split(".png")[0]
        encoded = encoded.split(".webp")[0]
        
        # Entferne Slashes die bei der Kodierung hinzugefügt wurden
        encoded = encoded.replace("/", "")
        
        # Füge Base64-Padding hinzu falls nötig
        missing_padding = len(encoded) % 4
        if missing_padding:
            encoded += '=' * (4 - missing_padding)
        
        # Dekodiere
        decoded = base64.b64decode(encoded).decode('utf-8')
        
        # Extrahiere echte URL aus "service=images&src=URL_ENCODED&..."
        if "src=" in decoded:
            match = re.search(r'src=([^&]+)', decoded)
            if match:
                url_encoded = match.group(1)
                real_url = urllib.parse.unquote(url_encoded)
                return real_url
    except Exception as e:
        print(f"[DEBUG] Failed to decode phastpress URL: {e}")
    
    return phast_url

def _norm(s: str) -> str:
    """Normalisiere String"""
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _clean_desc_lines(lines: List[str]) -> List[str]:
    """Bereinige Beschreibungszeilen"""
    cleaned = []
    seen = set()
    
    for line in lines:
        line = _norm(line)
        if not line or len(line) < 10:
            continue
        
        # Filtere Stopwords
        if any(stop in line for stop in STOP_STRINGS):
            continue
        
        # Dedupliziere
        line_lower = line.lower()
        if line_lower in seen:
            continue
        seen.add(line_lower)
        cleaned.append(line)
    
    return cleaned

def soup_get(url: str, delay: float = REQUEST_DELAY) -> BeautifulSoup:
    """Hole HTML und parse mit BeautifulSoup"""
    time.sleep(delay)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

# ===========================================================================
# AIRTABLE FUNCTIONS
# ===========================================================================

def airtable_table_segment() -> str:
    """Gibt base/table Segment für Airtable API zurück"""
    if not AIRTABLE_BASE or not AIRTABLE_TABLE_ID:
        return ""
    return f"{AIRTABLE_BASE}/{AIRTABLE_TABLE_ID}"

def airtable_headers() -> dict:
    """Airtable API Headers"""
    return {
        "Authorization": f"Bearer {AIRTABLE_TOKEN}",
        "Content-Type": "application/json"
    }

def airtable_list_all() -> tuple:
    """Liste alle Records aus Airtable"""
    url = f"https://api.airtable.com/v0/{airtable_table_segment()}"
    headers = airtable_headers()
    
    all_records = []
    offset = None
    
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    
    ids = [rec["id"] for rec in all_records]
    fields = [rec.get("fields", {}) for rec in all_records]
    return ids, fields

def airtable_existing_fields() -> set:
    """Ermittle existierende Felder"""
    _, all_fields = airtable_list_all()
    if not all_fields:
        return set()
    return set(all_fields[0].keys())

def airtable_batch_create(records: List[dict]):
    """Erstelle Records in Batches"""
    url = f"https://api.airtable.com/v0/{airtable_table_segment()}"
    headers = airtable_headers()
    
    for i in range(0, len(records), 10):
        batch = records[i:i+10]
        payload = {"records": [{"fields": r} for r in batch]}
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        time.sleep(0.2)

def airtable_batch_update(updates: List[dict]):
    """Update Records in Batches"""
    url = f"https://api.airtable.com/v0/{airtable_table_segment()}"
    headers = airtable_headers()
    
    for i in range(0, len(updates), 10):
        batch = updates[i:i+10]
        payload = {"records": batch}
        r = requests.patch(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        time.sleep(0.2)

def airtable_batch_delete(record_ids: List[str]):
    """Lösche Records in Batches"""
    url = f"https://api.airtable.com/v0/{airtable_table_segment()}"
    headers = airtable_headers()
    
    for i in range(0, len(record_ids), 10):
        batch = record_ids[i:i+10]
        params = {"records[]": batch}
        r = requests.delete(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        time.sleep(0.2)

def sanitize_record_for_airtable(record: dict, allowed_fields: set) -> dict:
    """Bereinige Record für Airtable"""
    if not allowed_fields:
        return record
    return {k: v for k, v in record.items() if k in allowed_fields}

# ===========================================================================
# EXTRACTION FUNCTIONS
# ===========================================================================

def extract_price(page_text: str) -> str:
    """Extrahiere Preis aus dem Seitentext"""
    # Suche nach verschiedenen Preis-Patterns
    patterns = [
        r"Kaufpreis[:\s]+€?\s*([\d.]+(?:,\d+)?)\s*€",
        r"Preis[:\s]+€?\s*([\d.]+(?:,\d+)?)\s*€",
    ]
    
    for pattern in patterns:
        m = re.search(pattern, page_text, re.IGNORECASE)
        if m:
            preis_str = m.group(1)
            # Entferne Punkte (Tausendertrennzeichen) und ersetze Komma durch Punkt
            preis_clean = preis_str.replace(".", "").replace(",", ".")
            try:
                preis_num = float(preis_clean)
                if preis_num > 100:  # Plausibilitätsprüfung
                    return f"€{int(preis_num):,}".replace(",", ".")
            except:
                continue
    
    return ""

def parse_price_to_number(preis_str: str) -> Optional[float]:
    """Konvertiere Preis-String zu Nummer für Airtable"""
    if not preis_str:
        return None
    
    # Entferne Euro-Symbol und Whitespace
    clean = preis_str.replace("€", "").strip()
    
    # Deutsche Zahlenformate: 489.250 €
    # Entferne Punkte (Tausendertrennzeichen) und ersetze Komma durch Punkt
    clean = clean.replace(".", "").replace(",", ".")
    
    try:
        return float(clean)
    except:
        return None

def extract_plz_ort(text: str, title: str = "") -> str:
    """Extrahiere PLZ und Ort aus Text"""
    # Zuerst im kompletten Text suchen
    matches = list(RE_PLZ_ORT.finditer(text))
    
    if matches:
        m = matches[0]
        plz = m.group(1)
        ort = m.group(2).strip()
        
        # Bereinige Ort
        ort = re.split(r'\s*[-–/]\s*', ort)[0].strip()
        ort = re.sub(r'\s+(angeboten|von|der|die|das|GmbH|Immobilien).*$', '', ort, flags=re.IGNORECASE).strip()
        ort = re.sub(r"\s+", " ", ort).strip()
        
        if len(ort.split()) > 2:
            ort = " ".join(ort.split()[:2])
        
        return f"{plz} {ort}"
    
    # Fallback: Nur Ortsname (bei Besigheim Website oft der Fall)
    # Titel enthält oft nur den Ortsnamen
    if title:
        # Suche nach bekannten Orten in der Region
        for match in re.finditer(r'\b([A-ZÄÖÜ][a-zäöüß]{3,})\b', title):
            ort = match.group(1)
            if ort not in ["Wohnung", "Haus", "Villa", "Modernes"]:
                return ort
    
    return ""

def extract_objektnummer(url: str) -> str:
    """Extrahiere Objektnummer aus URL"""
    # URL format: /immobilie/altersgerechtes-wohnen-im-ortskern-von-loechgau-4/
    parts = url.rstrip("/").split("/")
    if len(parts) > 0:
        slug = parts[-1]
        return slug
    return ""

def extract_description(soup: BeautifulSoup) -> str:
    """Extrahiere Beschreibung von Detailseite"""
    lines = []
    
    # Suche nach Beschreibungstexten
    for p in soup.find_all("p"):
        text = _norm(p.get_text(" ", strip=True))
        if text and len(text) > 50:
            if not any(skip in text for skip in STOP_STRINGS):
                lines.append(text)
    
    lines = _clean_desc_lines(lines)
    
    if lines:
        return "\n\n".join(lines[:10])[:12000]
    
    return ""

# ===========================================================================
# SCRAPING FUNCTIONS
# ===========================================================================

def collect_detail_links_with_images() -> List[tuple]:
    """Sammle alle Detailseiten-Links MIT Bildern von der Übersichtsseite"""
    all_data = []
    page = 1
    
    while True:
        if page == 1:
            page_url = LIST_URL
        else:
            page_url = f"{LIST_URL}page/{page}/"
        
        print(f"[LIST] Hole Seite {page}: {page_url}")
        
        try:
            soup = soup_get(page_url)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"[LIST] Seite {page} nicht gefunden - Ende der Pagination")
                break
            raise
        
        page_data = []
        
        # Suche nach Immobilien-Artikeln
        # Verschiedene Ansätze probieren
        articles = []
        
        # Ansatz 1: Suche nach class="frymo-listing-item"
        articles = soup.find_all("article", class_="frymo-listing-item")
        
        if not articles:
            # Ansatz 2: Suche nach article mit beliebiger class die "frymo" enthält
            articles = soup.find_all("article", class_=lambda x: x and "frymo" in str(x).lower())
        
        if not articles:
            # Ansatz 3: Alle articles, dann filtern
            all_articles = soup.find_all("article")
            articles = [a for a in all_articles if a.find("a", href=lambda h: h and "/immobilie/" in h)]
        
        print(f"[DEBUG] Gefunden: {len(articles)} Artikel-Elemente")
        
        for article in articles:
            # Suche Link im Artikel
            link = article.find("a", href=True)
            if not link:
                continue
            
            href = link["href"]
            if "/immobilie/" not in href or href.count("/") < 3:
                continue
            if href.strip("/") == "immobilie":
                continue
            
            full_url = urljoin(BASE, href)
            
            # Suche Bild im gleichen Artikel
            image_url = ""
            img = article.find("img")
            if img:
                # Hole srcset (bevorzugt) oder src
                srcset = img.get("srcset", "")
                if srcset:
                    # Parse srcset: "url1 768w, url2 1024w, url3 1920w"
                    # Nimm größte Auflösung (letzter Eintrag)
                    srcset_parts = [s.strip() for s in srcset.split(",")]
                    if srcset_parts:
                        last_part = srcset_parts[-1].strip()
                        if " " in last_part:
                            image_url = last_part.split()[0]
                        else:
                            image_url = last_part
                
                if not image_url:
                    src = img.get("src", "")
                    if src:
                        image_url = src
                
                # Mache URL absolut
                if image_url and not image_url.startswith("http"):
                    image_url = urljoin(BASE, image_url)
                
                # Dekodiere phastpress-URL
                if image_url and "phastpress" in image_url:
                    decoded_url = decode_phastpress_url(image_url)
                    if decoded_url != image_url:
                        print(f"[DEBUG]   Decoded phastpress URL")
                        image_url = decoded_url
            
            # Debug-Output
            slug = full_url.split("/")[-2] if "/" in full_url else "unknown"
            img_status = "✅" if image_url else "❌"
            print(f"[DEBUG]   {slug[:40]:<40} | Image: {img_status}")
            
            # Nur hinzufügen wenn noch nicht vorhanden
            if not any(data[0] == full_url for data in all_data):
                all_data.append((full_url, image_url))
                page_data.append(full_url)
        
        print(f"[LIST] Seite {page}: {len(page_data)} neue Immobilien gefunden")
        
        if len(page_data) == 0:
            print(f"[LIST] Keine neuen Links auf Seite {page} - Ende der Pagination")
            break
        
        # Prüfe ob es eine nächste Seite gibt
        has_next_page = False
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if f"/page/{page + 1}/" in href or "next" in href.lower():
                has_next_page = True
                break
        
        if not has_next_page and len(page_data) < 12:
            print(f"[LIST] Weniger als 12 Links und kein 'Next' Link - letzte Seite erreicht")
            break
        
        page += 1
        
        if page > 20:
            print(f"[WARN] Sicherheits-Break bei Seite 20")
            break
    
    print(f"[LIST] Gesamt gefunden: {len(all_data)} Immobilien über {page} Seite(n)")
    return all_data

def parse_detail(detail_url: str, overview_image: str = "") -> dict:
    """Parse Detailseite"""
    soup = soup_get(detail_url)
    page_text = soup.get_text("\n", strip=True)
    
    # Titel - meist in H1
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = _norm(h1.get_text(strip=True))
    
    # Fallback: Suche nach Muster im Text
    if not title or len(title) < 10:
        m = re.search(r"(Wohnung|Haus|Villa|Doppelhaushälfte|Einfamilienhaus|Mehrfamilienhaus)\s+(?:in|im)\s+[A-Z][\w\s-]+", page_text)
        if m:
            title = m.group(0)
    
    # Objektnummer aus URL
    objektnummer = extract_objektnummer(detail_url)
    
    # Preis
    preis = extract_price(page_text)
    
    # PLZ/Ort - bei Besigheim oft nur Ortsname
    ort = extract_plz_ort(page_text, title)
    
    # Bild-URL - verwende Bild von Übersichtsseite falls vorhanden
    image_url = overview_image if overview_image else ""
    
    # Nur wenn kein Bild von Übersichtsseite, suche auf Detailseite
    if not image_url:
        print(f"[DEBUG] No overview image, searching on detail page...")
        for img in soup.find_all("img"):
            src = img.get("src", "")
            srcset = img.get("srcset", "")
            alt = img.get("alt", "").lower()
            
            # Verwende srcset falls vorhanden (bessere Qualität)
            if srcset:
                srcset_urls = [s.strip().split()[0] for s in srcset.split(",")]
                if srcset_urls:
                    src = srcset_urls[-1]  # Größtes Bild
            
            if not src:
                continue
            
            # Ignoriere Logos, Icons, Avatare
            skip_keywords = ["logo", "icon", "avatar", "favicon"]
            if any(keyword in alt for keyword in skip_keywords):
                continue
            if any(keyword in src.lower() for keyword in skip_keywords):
                continue
            
            # Akzeptiere Bilder die Property-Bilder sein könnten
            if any(indicator in src for indicator in ["/wp-content/uploads/", "phastpress", "phast.php"]):
                image_url = src if src.startswith("http") else urljoin(BASE, src)
                print(f"[DEBUG] Found image on detail page: {image_url[:100]}...")
                break
    else:
        print(f"[DEBUG] Using overview image: {image_url[:100]}...")
    
    if not image_url:
        print(f"[DEBUG] No suitable image found for {detail_url}")
    
    # Kategorie - immo-shop-besigheim hat nur Kaufangebote
    kategorie = "Kaufen"
    
    # Beschreibung
    description = extract_description(soup)
    
    return {
        "Titel": title,
        "URL": detail_url,
        "Beschreibung": description,
        "Objektnummer": objektnummer,
        "Kategorie": kategorie,
        "Preis": preis,
        "Ort": ort,
        "Bild_URL": image_url,
    }

def make_record(row: dict) -> dict:
    """Erstelle Airtable-Record"""
    # Konvertiere Preis zu Number für Airtable
    preis_value = parse_price_to_number(row["Preis"])
    
    record = {
        "Titel": row["Titel"],
        "Kategorie": row["Kategorie"],
        "Webseite": row["URL"],
        "Objektnummer": row["Objektnummer"],
        "Beschreibung": row["Beschreibung"],
        "Bild": row["Bild_URL"],
        "Standort": row["Ort"],
    }
    
    # Nur Preis hinzufügen wenn vorhanden
    if preis_value is not None:
        record["Preis"] = preis_value
    
    return record

def unique_key(fields: dict) -> str:
    """Eindeutiger Key für Record"""
    obj = (fields.get("Objektnummer") or "").strip()
    if obj:
        return f"obj:{obj}"
    url = (fields.get("Webseite") or "").strip()
    if url:
        return f"url:{url}"
    return f"hash:{hash(json.dumps(fields, sort_keys=True))}"

# ===========================================================================
# MAIN
# ===========================================================================

def run():
    """Hauptfunktion"""
    print("[BESIGHEIM] Starte Scraper für immo-shop-besigheim.de")
    
    # Sammle Links MIT Bildern von Übersichtsseite
    detail_data = collect_detail_links_with_images()
    
    if not detail_data:
        print("[WARN] Keine Links gefunden!")
        return
    
    # Scrape Details
    all_rows = []
    for i, (url, image_url) in enumerate(detail_data, 1):
        try:
            print(f"\n[SCRAPE] {i}/{len(detail_data)} | {url}")
            row = parse_detail(url, overview_image=image_url)
            record = make_record(row)
            
            # Zeige Vorschau
            preis_display = record.get('Preis', 'N/A')
            has_image = "✅" if record.get('Bild') else "❌"
            print(f"  → {record['Kategorie']:8} | {record['Titel'][:60]} | {record.get('Standort', 'N/A')} | Preis: {preis_display} | Bild: {has_image}")
            
            all_rows.append(record)
        except Exception as e:
            print(f"[ERROR] Fehler bei {url}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if not all_rows:
        print("[WARN] Keine Datensätze gefunden.")
        return
    
    # Speichere CSV
    csv_file = "besigheim_immobilien.csv"
    cols = ["Titel", "Kategorie", "Webseite", "Objektnummer", "Beschreibung", "Bild", "Preis", "Standort"]
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(all_rows)
    print(f"\n[CSV] Gespeichert: {csv_file} ({len(all_rows)} Zeilen)")
    
    # Airtable Sync
    if AIRTABLE_TOKEN and AIRTABLE_BASE and airtable_table_segment():
        print("\n[AIRTABLE] Starte Synchronisation...")
        
        allowed = airtable_existing_fields()
        all_ids, all_fields = airtable_list_all()
        
        existing = {}
        for rec_id, f in zip(all_ids, all_fields):
            k = unique_key(f)
            existing[k] = (rec_id, f)
        
        desired = {}
        for r in all_rows:
            k = unique_key(r)
            if k in desired:
                if len(r.get("Beschreibung", "")) > len(desired[k].get("Beschreibung", "")):
                    desired[k] = sanitize_record_for_airtable(r, allowed)
            else:
                desired[k] = sanitize_record_for_airtable(r, allowed)
        
        to_create, to_update, keep = [], [], set()
        for k, fields in desired.items():
            if k in existing:
                rec_id, old = existing[k]
                diff = {fld: val for fld, val in fields.items() if old.get(fld) != val}
                if diff:
                    to_update.append({"id": rec_id, "fields": diff})
                keep.add(k)
            else:
                to_create.append(fields)
        
        to_delete_ids = [rec_id for k, (rec_id, _) in existing.items() if k not in keep]
        
        print(f"\n[SYNC] Gesamt → create: {len(to_create)}, update: {len(to_update)}, delete: {len(to_delete_ids)}")
        
        if to_create:
            print(f"[Airtable] Erstelle {len(to_create)} neue Records...")
            airtable_batch_create(to_create)
        if to_update:
            print(f"[Airtable] Aktualisiere {len(to_update)} Records...")
            airtable_batch_update(to_update)
        if to_delete_ids:
            print(f"[Airtable] Lösche {len(to_delete_ids)} Records...")
            airtable_batch_delete(to_delete_ids)
        
        print("[Airtable] Synchronisation abgeschlossen.\n")
    else:
        print("[Airtable] ENV nicht gesetzt – Upload übersprungen.")

if __name__ == "__main__":
    run()

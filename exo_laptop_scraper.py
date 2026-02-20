#!/usr/bin/env python3
"""
Exo.ir Laptop Scraper — All-in-One

Phase 1: Catalog
  Crawls exo.ir/category/laptop page by page (120/page).
  Stops when the FIRST out-of-stock laptop ("ناموجود") is found on a page.
  Only in-stock laptops are cataloged.

Phase 2: Detail Scraper
  Scrapes each cataloged laptop's detail page for full specs + price.
  - Resumes from where it left off
  - Writes data to DB immediately
  - 8 parallel workers
  - Retries with exponential backoff
  - Graceful Ctrl+C shutdown

Usage:
  python3 exo_laptop_scraper.py              # full run (catalog + scrape)
  python3 exo_laptop_scraper.py --catalog    # phase 1 only
  python3 exo_laptop_scraper.py --scrape     # phase 2 only (resume)
"""

import sqlite3
import json
import time
import re
import sys
import signal
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── Config ──────────────────────────────────────────────────────────────────
BASE_URL = "https://exo.ir/category/laptop"
DB_PATH = "laptops.db"
ITEMS_PER_PAGE = 120
MAX_WORKERS = 8
MAX_RETRIES = 3
RETRY_BACKOFF = 2
REQUEST_TIMEOUT = 30
DELAY_BETWEEN_PAGES = 2
DELAY_BETWEEN_REQUESTS = 0.3
MAX_PAGES = 50  # safety cap

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
}

# Graceful shutdown
shutdown_event = threading.Event()


def signal_handler(sig, frame):
    print("\n\n⚠ Shutdown requested. Finishing current jobs…")
    shutdown_event.set()


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════════════
def init_db(db_path: str = DB_PATH) -> None:
    """Create both tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS laptops (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            slug            TEXT    UNIQUE NOT NULL,
            name            TEXT    NOT NULL,
            url             TEXT    NOT NULL,
            scraped_details INTEGER DEFAULT 0,
            created_at      TEXT    DEFAULT (datetime('now'))
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS laptop_details (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            laptop_id           INTEGER NOT NULL REFERENCES laptops(id),
            slug                TEXT    NOT NULL,
            title               TEXT,
            model_code          TEXT,
            price               INTEGER,
            cpu_model           TEXT,
            cpu_cores           TEXT,
            ram                 TEXT,
            gpu_model           TEXT,
            hdd                 TEXT,
            ssd                 TEXT,
            screen_size         TEXT,
            laptop_series       TEXT,
            weight              TEXT,
            ram_mb              INTEGER,
            ssd_gb              INTEGER,
            hdd_gb              INTEGER,
            screen_inches       REAL,
            weight_kg           REAL,
            cpu_core_count      INTEGER,
            cpu_thread_count    INTEGER,
            full_specs_json     TEXT,
            scraped_at          TEXT DEFAULT (datetime('now')),
            UNIQUE(laptop_id)
        );
        """
    )
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 1 — CATALOG
# ══════════════════════════════════════════════════════════════════════════════
def extract_slug(url: str) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "product":
        return parts[1]
    return parts[-1] if parts else url


def scrape_catalog_page(page_num: int, session: requests.Session) -> tuple[list[dict], bool]:
    """
    Fetch one category page.
    Returns (laptops_list, should_continue).
    should_continue is False when an out-of-stock laptop is found.
    """
    params = {"limit": ITEMS_PER_PAGE}
    if page_num > 1:
        params["page"] = page_num

    print(f"  📄 Page {page_num} … ", end="", flush=True)

    resp = session.get(BASE_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    print(f"HTTP {resp.status_code}  ", end="", flush=True)

    soup = BeautifulSoup(resp.text, "lxml")

    laptops = []
    should_continue = True

    # Each product card is in div.grid-product
    product_cards = soup.select("div.grid-product")

    if not product_cards:
        print("→ 0 products (empty page)")
        return [], False

    for card in product_cards:
        # Check if out of stock: h5.text-danger with "ناموجود"
        unavailable = card.find("h5", class_="text-danger")
        if unavailable and "ناموجود" in unavailable.get_text(strip=True):
            should_continue = False
            break

        # Get the product link
        link = card.select_one("a.font-latin-yekan.text-truncate-2")
        if not link:
            # fallback: any link to /product/
            link = card.find("a", href=re.compile(r"/product/"))
        if not link:
            continue

        href = link.get("href", "")
        if "/product/" not in href:
            continue

        full_url = urljoin("https://exo.ir", href)
        slug = extract_slug(full_url)
        name = link.get_text(strip=True) or slug.replace("-", " ").title()

        laptops.append({"slug": slug, "name": name, "url": full_url})

    status = "→" if should_continue else "→ ⛔"
    print(f"{status} {len(laptops)} in-stock laptops")
    return laptops, should_continue


def run_catalog(db_path: str = DB_PATH) -> int:
    """Phase 1: Crawl pages until out-of-stock found. Returns total cataloged."""
    print("\n" + "─" * 60)
    print("PHASE 1: Catalog in-stock laptops")
    print("─" * 60)

    conn = sqlite3.connect(db_path)
    before = conn.execute("SELECT COUNT(*) FROM laptops").fetchone()[0]
    print(f"  Existing in DB: {before}")
    print(f"  Crawling pages until out-of-stock found…\n")

    session = requests.Session()
    total_found = 0

    for page in range(1, MAX_PAGES + 1):
        if shutdown_event.is_set():
            break

        try:
            laptops, should_continue = scrape_catalog_page(page, session)
        except requests.RequestException as e:
            print(f"  ⚠ Error on page {page}: {e}. Retrying…")
            time.sleep(5)
            try:
                laptops, should_continue = scrape_catalog_page(page, session)
            except requests.RequestException as e2:
                print(f"  ✗ Page {page} failed again: {e2}. Stopping catalog.")
                break

        # Insert into DB
        for lap in laptops:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO laptops (slug, name, url) VALUES (?, ?, ?)",
                    (lap["slug"], lap["name"], lap["url"]),
                )
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        total_found += len(laptops)

        if not should_continue:
            print(f"\n  ⛔ Out-of-stock product found on page {page}. Stopping catalog.")
            break

        if page < MAX_PAGES:
            time.sleep(DELAY_BETWEEN_PAGES)

    after = conn.execute("SELECT COUNT(*) FROM laptops").fetchone()[0]
    new = after - before
    conn.close()

    print(f"\n  Total found this run:  {total_found}")
    print(f"  New added to DB:      {new}")
    print(f"  Total in DB:          {after}")
    return after


# ══════════════════════════════════════════════════════════════════════════════
#  NUMERIC PROCESSING
# ══════════════════════════════════════════════════════════════════════════════
def parse_ram_mb(text: str) -> int | None:
    if not text or text == "ندارد":
        return None
    m = re.search(r"([\d.]+)", text)
    if not m:
        return None
    val = float(m.group(1))
    if "ترابایت" in text or "TB" in text.upper():
        return int(val * 1024 * 1024)
    if "مگابایت" in text or "MB" in text.upper():
        return int(val)
    return int(val * 1024)  # default GB


def parse_storage_gb(text: str) -> int | None:
    if not text or text == "ندارد":
        return 0
    m = re.search(r"([\d.]+)", text)
    if not m:
        return None
    val = float(m.group(1))
    if "ترابایت" in text or "TB" in text.upper():
        return int(val * 1024)
    if "مگابایت" in text or "MB" in text.upper():
        return max(1, int(val / 1024))
    return int(val)  # default GB


def parse_screen_inches(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"([\d.]+)", text)
    return float(m.group(1)) if m else None


def parse_weight_kg(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"([\d.]+)", text)
    if not m:
        return None
    val = float(m.group(1))
    if "گرم" in text and "کیلو" not in text:
        return round(val / 1000, 3)
    return val


def parse_cpu_cores(text: str) -> int | None:
    if not text:
        return None
    m = re.search(r"(\d+)\s*هسته", text)
    return int(m.group(1)) if m else None


def parse_cpu_threads(text: str) -> int | None:
    if not text:
        return None
    m = re.search(r"(\d+)\s*رشته", text)
    return int(m.group(1)) if m else None


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 2 — DETAIL SCRAPER
# ══════════════════════════════════════════════════════════════════════════════
def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def extract_key_specs(soup: BeautifulSoup) -> dict:
    specs = {}
    h = soup.find("h6", string=re.compile(r"خصوصیات کلیدی"))
    if not h:
        return specs
    container = h.find_parent("div")
    if not container:
        return specs
    for div in container.find_all("div", class_="d-flex"):
        label_el = div.find("span", class_="text-black-50")
        if not label_el:
            continue
        label = label_el.get_text(strip=True).rstrip(": \u200c\u200b").strip()
        value_el = div.find("span", class_="text-dark")
        if value_el:
            value = value_el.get_text(strip=True)
        else:
            value = div.get_text(strip=True).replace(label_el.get_text(strip=True), "").strip()
        if label and value:
            specs[label] = value
    return specs


def extract_full_specs(soup: BeautifulSoup) -> dict:
    specs = {}
    tab = soup.find(id="tab-specification")
    if not tab:
        return specs
    table = tab.find("table")
    if not table:
        return specs
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 2:
            k = cells[0].get_text(strip=True)
            v = cells[1].get_text(strip=True)
            if k:
                specs[k] = v
    return specs


KEY_SPEC_MAP = {
    "مدل پردازنده": "cpu_model",
    "تعداد هسته پردازنده": "cpu_cores",
    "ظرفیت RAM": "ram",
    "مدل پردازنده گرافیکی": "gpu_model",
    "HDD": "hdd",
    "SSD": "ssd",
    "سایز صفحه نمایش": "screen_size",
    "سری لپ تاپ": "laptop_series",
    "وزن لپ تاپ": "weight",
    "وزن لپ ‌تاپ": "weight",
}

FULL_SPEC_FALLBACK = {
    "مدل پردازنده": "cpu_model",
    "تعداد هسته پردازنده": "cpu_cores",
    "ظرفیت RAM": "ram",
    "مدل پردازنده گرافیکی": "gpu_model",
    "HDD": "hdd",
    "SSD": "ssd",
    "سایز صفحه نمایش": "screen_size",
    "سری لپ تاپ": "laptop_series",
    "وزن": "weight",
}


def scrape_laptop_detail(laptop: dict, session: requests.Session) -> dict:
    resp = session.get(laptop["url"], headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    details = {"slug": laptop["slug"]}

    # Title
    title_el = soup.find("h1", class_="fw-bold")
    if title_el:
        details["title"] = title_el.get_text(strip=True)

    # Model code
    model_el = soup.find("h6", class_="text-secondary", string=re.compile(r"مدل کالا"))
    if model_el:
        m = re.search(r"مدل کالا:\s*(.+)", model_el.get_text(strip=True))
        if m:
            details["model_code"] = m.group(1).strip()

    # Price
    price_el = soup.find("h2", class_="fw-bold")
    if price_el:
        pt = price_el.get_text(strip=True)
        if "تومان" in pt:
            details["price"] = parse_price(pt)

    # Key specs
    key_specs = extract_key_specs(soup)
    for fk, dk in KEY_SPEC_MAP.items():
        if fk in key_specs:
            details[dk] = key_specs[fk]

    # Full spec table
    full_specs = extract_full_specs(soup)
    if full_specs:
        details["full_specs_json"] = json.dumps(full_specs, ensure_ascii=False)

    # Fallback from full specs
    for sk, dk in FULL_SPEC_FALLBACK.items():
        if dk not in details or details[dk] is None:
            if sk in full_specs:
                details[dk] = full_specs[sk]

    # Numeric processing
    details["ram_mb"] = parse_ram_mb(details.get("ram"))
    details["ssd_gb"] = parse_storage_gb(details.get("ssd"))
    details["hdd_gb"] = parse_storage_gb(details.get("hdd"))
    details["screen_inches"] = parse_screen_inches(details.get("screen_size"))
    details["weight_kg"] = parse_weight_kg(details.get("weight"))
    details["cpu_core_count"] = parse_cpu_cores(details.get("cpu_cores"))
    details["cpu_thread_count"] = parse_cpu_threads(details.get("cpu_cores"))

    return details


def save_detail(laptop_id: int, details: dict, db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO laptop_details
                (laptop_id, slug, title, model_code, price,
                 cpu_model, cpu_cores, ram, gpu_model, hdd, ssd,
                 screen_size, laptop_series, weight,
                 ram_mb, ssd_gb, hdd_gb, screen_inches, weight_kg,
                 cpu_core_count, cpu_thread_count, full_specs_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                laptop_id, details.get("slug", ""), details.get("title"),
                details.get("model_code"), details.get("price"),
                details.get("cpu_model"), details.get("cpu_cores"),
                details.get("ram"), details.get("gpu_model"),
                details.get("hdd"), details.get("ssd"),
                details.get("screen_size"), details.get("laptop_series"),
                details.get("weight"),
                details.get("ram_mb"), details.get("ssd_gb"),
                details.get("hdd_gb"), details.get("screen_inches"),
                details.get("weight_kg"),
                details.get("cpu_core_count"), details.get("cpu_thread_count"),
                details.get("full_specs_json"),
            ),
        )
        conn.execute("UPDATE laptops SET scraped_details = 1 WHERE id = ?", (laptop_id,))
        conn.commit()
    finally:
        conn.close()


# Thread-local sessions
_tl = threading.local()
_stats_lock = threading.Lock()
_stats = {"success": 0, "failed": 0}


def _get_session() -> requests.Session:
    if not hasattr(_tl, "session"):
        _tl.session = requests.Session()
    return _tl.session


def _worker(laptop: dict, db_path: str = DB_PATH) -> tuple[int, bool, str]:
    if shutdown_event.is_set():
        return (laptop["id"], False, "shutdown")

    session = _get_session()
    last_err = ""

    for attempt in range(1, MAX_RETRIES + 1):
        if shutdown_event.is_set():
            return (laptop["id"], False, "shutdown")
        try:
            time.sleep(DELAY_BETWEEN_REQUESTS)
            details = scrape_laptop_detail(laptop, session)
            save_detail(laptop["id"], details, db_path)
            with _stats_lock:
                _stats["success"] += 1
            return (laptop["id"], True, f"OK (price={details.get('price')})")
        except requests.RequestException as e:
            last_err = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF ** attempt)
        except Exception as e:
            last_err = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF)

    with _stats_lock:
        _stats["failed"] += 1
    return (laptop["id"], False, f"FAILED: {last_err}")


def run_scrape(db_path: str = DB_PATH) -> None:
    """Phase 2: Scrape detail pages for all pending laptops."""
    print("\n" + "─" * 60)
    print("PHASE 2: Scrape laptop details")
    print("─" * 60)

    conn = sqlite3.connect(db_path)
    pending = conn.execute(
        "SELECT id, slug, url FROM laptops WHERE scraped_details = 0 ORDER BY id"
    ).fetchall()
    conn.close()
    pending = [{"id": r[0], "slug": r[1], "url": r[2]} for r in pending]

    if not pending:
        conn = sqlite3.connect(db_path)
        total = conn.execute("SELECT COUNT(*) FROM laptops").fetchone()[0]
        print(f"\n  ✓ All {total} laptops already scraped. Nothing to do.")
        conn.close()
        return

    print(f"\n  Pending: {len(pending)}  |  Workers: {MAX_WORKERS}  |  Retries: {MAX_RETRIES}")
    print()

    from functools import partial

    _stats["success"] = 0
    _stats["failed"] = 0
    start = time.time()

    worker_fn = partial(_worker, db_path=db_path)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(worker_fn, lap): lap for lap in pending}
        for future in as_completed(futures):
            if shutdown_event.is_set():
                for f in futures:
                    f.cancel()
                break
            laptop = futures[future]
            try:
                lid, ok, msg = future.result()
                sym = "✓" if ok else "✗"
                with _stats_lock:
                    done = _stats["success"] + _stats["failed"]
                print(f"  [{done}/{len(pending)}] {sym} #{lid} {laptop['slug'][:50]}  {msg}")
            except Exception as e:
                print(f"  ✗ #{laptop['id']} {laptop['slug'][:50]}  ERROR: {e}")

    elapsed = time.time() - start
    conn = sqlite3.connect(db_path)
    total = conn.execute("SELECT COUNT(*) FROM laptops").fetchone()[0]
    done = conn.execute("SELECT COUNT(*) FROM laptops WHERE scraped_details = 1").fetchone()[0]
    remaining = total - done

    print(f"\n  Elapsed:   {elapsed:.1f}s")
    print(f"  Success:   {_stats['success']}")
    print(f"  Failed:    {_stats['failed']}")
    print(f"  Remaining: {remaining}")

    if remaining > 0:
        print(f"  → Re-run to retry the remaining {remaining}.")

    # Sample
    rows = conn.execute(
        """
        SELECT d.title, d.price, d.cpu_model, d.ram_mb, d.ssd_gb,
               d.screen_inches, d.weight_kg, d.gpu_model
        FROM laptop_details d
        WHERE d.price IS NOT NULL AND d.cpu_model IS NOT NULL
        ORDER BY d.id LIMIT 3
        """
    ).fetchall()
    if rows:
        print(f"\n  Sample:")
        for r in rows:
            print(f"    {r[0]}")
            print(f"      price={r[1]:,}  cpu={r[2]}  ram={r[3]}MB  ssd={r[4]}GB  "
                  f"screen={r[5]}\"  weight={r[6]}kg  gpu={r[7]}")
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Exo.ir Laptop Scraper")
    parser.add_argument("--catalog", action="store_true", help="Run Phase 1 only (catalog)")
    parser.add_argument("--scrape", action="store_true", help="Run Phase 2 only (details)")
    parser.add_argument("--db", default=DB_PATH, help=f"Database path (default: {DB_PATH})")
    args = parser.parse_args()

    db = args.db

    print("═" * 60)
    print("  Exo.ir Laptop Scraper — All-in-One")
    print("═" * 60)

    init_db(db)

    run_phase1 = args.catalog or (not args.catalog and not args.scrape)
    run_phase2 = args.scrape or (not args.catalog and not args.scrape)

    if run_phase1 and not shutdown_event.is_set():
        run_catalog(db)

    if run_phase2 and not shutdown_event.is_set():
        run_scrape(db)

    print("\n" + "═" * 60)
    print("  All done!")
    print("═" * 60)


if __name__ == "__main__":
    main()

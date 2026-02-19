#!/usr/bin/env python3
"""
Step 2: Scrape detailed specs and price for each laptop in the catalog.

Features:
  - Resumes from where it left off (skips already-scraped laptops)
  - Writes data to DB immediately as each laptop is scraped
  - Runs multiple parallel workers using ThreadPoolExecutor
  - Retries failed requests with exponential backoff
  - Graceful shutdown on Ctrl+C
  - Extracts laptop title from h1
  - Processes semi-numeric data into dedicated integer/float columns
"""

import sqlite3
import json
import time
import re
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

# ── Config ──────────────────────────────────────────────────────────────────
DB_PATH = "laptops.db"
MAX_WORKERS = 8           # parallel requests
MAX_RETRIES = 3           # retries per laptop
RETRY_BACKOFF = 2         # base seconds for exponential backoff
REQUEST_TIMEOUT = 30      # seconds
DELAY_BETWEEN_REQUESTS = 0.3  # small delay per worker to avoid hammering

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
}

# Graceful shutdown flag
shutdown_event = threading.Event()


def signal_handler(sig, frame):
    print("\n\n⚠ Shutdown requested. Finishing current jobs…")
    shutdown_event.set()


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ── Numeric Processing ─────────────────────────────────────────────────────
def parse_ram_mb(text: str) -> int | None:
    """Convert RAM text to MB.  '64 گیگابایت' -> 65536, '16 گیگابایت' -> 16384."""
    if not text or text == "ندارد":
        return None
    m = re.search(r"([\d.]+)", text)
    if not m:
        return None
    val = float(m.group(1))
    if "گیگابایت" in text or "GB" in text.upper():
        return int(val * 1024)
    if "مگابایت" in text or "MB" in text.upper():
        return int(val)
    if "ترابایت" in text or "TB" in text.upper():
        return int(val * 1024 * 1024)
    # Default: assume GB
    return int(val * 1024)


def parse_storage_gb(text: str) -> int | None:
    """Convert storage text to GB.  '1 ترابایت' -> 1024, '512 گیگابایت' -> 512."""
    if not text or text == "ندارد":
        return 0
    m = re.search(r"([\d.]+)", text)
    if not m:
        return None
    val = float(m.group(1))
    if "ترابایت" in text or "TB" in text.upper():
        return int(val * 1024)
    if "گیگابایت" in text or "GB" in text.upper():
        return int(val)
    if "مگابایت" in text or "MB" in text.upper():
        return max(1, int(val / 1024))
    # Default: assume GB
    return int(val)


def parse_screen_inches(text: str) -> float | None:
    """Convert screen size to inches. '16 اینچ' -> 16.0, '14.2 اینچ' -> 14.2."""
    if not text:
        return None
    m = re.search(r"([\d.]+)", text)
    return float(m.group(1)) if m else None


def parse_weight_kg(text: str) -> float | None:
    """Convert weight to kg. '2.4 کیلوگرم' -> 2.4, '1360 گرم' -> 1.36."""
    if not text:
        return None
    m = re.search(r"([\d.]+)", text)
    if not m:
        return None
    val = float(m.group(1))
    if "گرم" in text and "کیلو" not in text:
        return round(val / 1000, 3)
    # Default: kg
    return val


def parse_cpu_cores(text: str) -> int | None:
    """Extract core count. '24 هسته / 32 رشته' -> 24, '8 هسته / 12 رشته' -> 8."""
    if not text:
        return None
    m = re.search(r"(\d+)\s*هسته", text)
    return int(m.group(1)) if m else None


def parse_cpu_threads(text: str) -> int | None:
    """Extract thread count. '24 هسته / 32 رشته' -> 32."""
    if not text:
        return None
    m = re.search(r"(\d+)\s*رشته", text)
    return int(m.group(1)) if m else None


# ── Database ────────────────────────────────────────────────────────────────
def ensure_details_table(db_path: str = DB_PATH) -> None:
    """Create the laptop_details table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS laptop_details (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            laptop_id           INTEGER NOT NULL REFERENCES laptops(id),
            slug                TEXT    NOT NULL,
            title               TEXT,
            model_code          TEXT,
            price               INTEGER,

            -- Raw text specs
            cpu_model           TEXT,
            cpu_cores           TEXT,
            ram                 TEXT,
            gpu_model           TEXT,
            hdd                 TEXT,
            ssd                 TEXT,
            screen_size         TEXT,
            laptop_series       TEXT,
            weight              TEXT,

            -- Processed numeric columns
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


def get_pending_laptops(db_path: str = DB_PATH) -> list[dict]:
    """Get all laptops that haven't been scraped yet."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT l.id, l.slug, l.url
        FROM laptops l
        WHERE l.scraped_details = 0
        ORDER BY l.id
        """
    ).fetchall()
    conn.close()
    return [{"id": r[0], "slug": r[1], "url": r[2]} for r in rows]


def save_laptop_details(laptop_id: int, details: dict, db_path: str = DB_PATH) -> None:
    """Save scraped details to DB and mark as done. Thread-safe via per-call connection."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO laptop_details
                (laptop_id, slug, title, model_code, price,
                 cpu_model, cpu_cores, ram, gpu_model, hdd, ssd,
                 screen_size, laptop_series, weight,
                 ram_mb, ssd_gb, hdd_gb, screen_inches, weight_kg,
                 cpu_core_count, cpu_thread_count,
                 full_specs_json)
            VALUES (?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?,
                    ?)
            """,
            (
                laptop_id,
                details.get("slug", ""),
                details.get("title"),
                details.get("model_code"),
                details.get("price"),
                details.get("cpu_model"),
                details.get("cpu_cores"),
                details.get("ram"),
                details.get("gpu_model"),
                details.get("hdd"),
                details.get("ssd"),
                details.get("screen_size"),
                details.get("laptop_series"),
                details.get("weight"),
                details.get("ram_mb"),
                details.get("ssd_gb"),
                details.get("hdd_gb"),
                details.get("screen_inches"),
                details.get("weight_kg"),
                details.get("cpu_core_count"),
                details.get("cpu_thread_count"),
                details.get("full_specs_json"),
            ),
        )
        conn.execute(
            "UPDATE laptops SET scraped_details = 1 WHERE id = ?", (laptop_id,)
        )
        conn.commit()
    finally:
        conn.close()


# ── Parsing ─────────────────────────────────────────────────────────────────
def parse_price(text: str) -> int | None:
    """Extract integer price from text like '137,250,000  تومان'."""
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def extract_key_specs(soup: BeautifulSoup) -> dict:
    """Extract key specs from the 'خصوصیات کلیدی' section."""
    specs = {}

    key_specs_header = soup.find("h6", string=re.compile(r"خصوصیات کلیدی"))
    if not key_specs_header:
        return specs

    container = key_specs_header.find_parent("div")
    if not container:
        return specs

    spec_divs = container.find_all("div", class_="d-flex")
    for div in spec_divs:
        label_el = div.find("span", class_="text-black-50")
        if not label_el:
            continue
        label = label_el.get_text(strip=True).rstrip(": \u200c\u200b").strip()

        value_el = div.find("span", class_="text-dark")
        if value_el:
            value = value_el.get_text(strip=True)
        else:
            full_text = div.get_text(strip=True)
            value = full_text.replace(label_el.get_text(strip=True), "").strip()

        if label and value:
            specs[label] = value

    return specs


def extract_full_specs(soup: BeautifulSoup) -> dict:
    """Extract all specs from the #tab-specification table."""
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
            key = cells[0].get_text(strip=True)
            val = cells[1].get_text(strip=True)
            if key:
                specs[key] = val

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
    "وزن لپ ‌تاپ": "weight",  # alternate spacing (zero-width space)
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


def scrape_laptop(laptop: dict, session: requests.Session) -> dict:
    """Scrape a single laptop page. Returns details dict."""
    resp = session.get(laptop["url"], headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    details = {"slug": laptop["slug"]}

    # 1. Title — h1 with class fs-2 font-latin-yekan fw-bold
    title_el = soup.find("h1", class_="fw-bold")
    if title_el:
        details["title"] = title_el.get_text(strip=True)

    # 2. Model code
    model_el = soup.find("h6", class_="text-secondary", string=re.compile(r"مدل کالا"))
    if model_el:
        text = model_el.get_text(strip=True)
        match = re.search(r"مدل کالا:\s*(.+)", text)
        if match:
            details["model_code"] = match.group(1).strip()

    # 3. Price — h2.fw-bold with تومان
    price_el = soup.find("h2", class_="fw-bold")
    if price_el:
        price_text = price_el.get_text(strip=True)
        if "تومان" in price_text:
            details["price"] = parse_price(price_text)

    # 4. Key specs
    key_specs = extract_key_specs(soup)
    for farsi_key, db_key in KEY_SPEC_MAP.items():
        if farsi_key in key_specs:
            details[db_key] = key_specs[farsi_key]

    # 5. Full spec table as JSON
    full_specs = extract_full_specs(soup)
    if full_specs:
        details["full_specs_json"] = json.dumps(full_specs, ensure_ascii=False)

    # 6. Fallback: fill key columns from full spec table if still missing
    for spec_key, db_key in FULL_SPEC_FALLBACK.items():
        if db_key not in details or details[db_key] is None:
            if spec_key in full_specs:
                details[db_key] = full_specs[spec_key]

    # 7. Process numeric columns
    details["ram_mb"] = parse_ram_mb(details.get("ram"))
    details["ssd_gb"] = parse_storage_gb(details.get("ssd"))
    details["hdd_gb"] = parse_storage_gb(details.get("hdd"))
    details["screen_inches"] = parse_screen_inches(details.get("screen_size"))
    details["weight_kg"] = parse_weight_kg(details.get("weight"))
    details["cpu_core_count"] = parse_cpu_cores(details.get("cpu_cores"))
    details["cpu_thread_count"] = parse_cpu_threads(details.get("cpu_cores"))

    return details


# ── Worker ──────────────────────────────────────────────────────────────────
_thread_local = threading.local()


def get_session() -> requests.Session:
    """Get a thread-local requests session."""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = requests.Session()
    return _thread_local.session


_stats_lock = threading.Lock()
_stats = {"success": 0, "failed": 0}


def worker(laptop: dict) -> tuple[int, bool, str]:
    """Scrape one laptop with retries. Returns (laptop_id, success, message)."""
    if shutdown_event.is_set():
        return (laptop["id"], False, "shutdown")

    session = get_session()
    last_error = ""

    for attempt in range(1, MAX_RETRIES + 1):
        if shutdown_event.is_set():
            return (laptop["id"], False, "shutdown")

        try:
            time.sleep(DELAY_BETWEEN_REQUESTS)
            details = scrape_laptop(laptop, session)
            save_laptop_details(laptop["id"], details)

            with _stats_lock:
                _stats["success"] += 1

            return (laptop["id"], True, f"OK (price={details.get('price')})")

        except requests.RequestException as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF ** attempt
                time.sleep(wait)
        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF)

    with _stats_lock:
        _stats["failed"] += 1

    return (laptop["id"], False, f"FAILED after {MAX_RETRIES} retries: {last_error}")


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Exo.ir Laptop Scraper — Step 2: Detail Scraper")
    print("=" * 60)

    ensure_details_table()
    pending = get_pending_laptops()

    if not pending:
        print("\n✓ All laptops have been scraped! Nothing to do.")
        conn = sqlite3.connect(DB_PATH)
        total = conn.execute("SELECT COUNT(*) FROM laptops").fetchone()[0]
        done = conn.execute("SELECT COUNT(*) FROM laptops WHERE scraped_details = 1").fetchone()[0]
        print(f"  Total in catalog: {total}")
        print(f"  Scraped: {done}")
        conn.close()
        return

    print(f"\n  Pending laptops: {len(pending)}")
    print(f"  Workers: {MAX_WORKERS}")
    print(f"  Max retries: {MAX_RETRIES}")
    print(f"\n  Starting…\n")

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(worker, lap): lap for lap in pending}

        for i, future in enumerate(as_completed(futures), 1):
            if shutdown_event.is_set():
                for f in futures:
                    f.cancel()
                break

            laptop = futures[future]
            try:
                lap_id, success, msg = future.result()
                status = "✓" if success else "✗"
                with _stats_lock:
                    done = _stats["success"] + _stats["failed"]
                print(
                    f"  [{done}/{len(pending)}] {status} #{lap_id} {laptop['slug'][:50]}  {msg}"
                )
            except Exception as e:
                print(f"  [{i}/{len(pending)}] ✗ #{laptop['id']} {laptop['slug'][:50]}  ERROR: {e}")

    elapsed = time.time() - start_time

    print(f"\n{'=' * 60}")
    print(f"Done! (elapsed: {elapsed:.1f}s)")
    with _stats_lock:
        print(f"  Successful: {_stats['success']}")
        print(f"  Failed:     {_stats['failed']}")

    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM laptops").fetchone()[0]
    done = conn.execute("SELECT COUNT(*) FROM laptops WHERE scraped_details = 1").fetchone()[0]
    remaining = total - done
    print(f"  Total in catalog:  {total}")
    print(f"  Scraped so far:    {done}")
    print(f"  Remaining:         {remaining}")

    if remaining > 0:
        print(f"\n  Re-run this script to retry the remaining {remaining} laptops.")
    print(f"{'=' * 60}")

    # Show sample
    print(f"\nSample details (first 3 with data):")
    rows = conn.execute(
        """
        SELECT d.slug, d.title, d.model_code, d.price,
               d.cpu_model, d.ram, d.ram_mb, d.ssd, d.ssd_gb,
               d.screen_size, d.screen_inches, d.weight, d.weight_kg,
               d.cpu_core_count, d.cpu_thread_count, d.gpu_model
        FROM laptop_details d
        WHERE d.price IS NOT NULL AND d.cpu_model IS NOT NULL
        ORDER BY d.id LIMIT 3
        """
    ).fetchall()
    for r in rows:
        print(f"  {r[0]}")
        print(f"    title:  {r[1]}")
        print(f"    model:  {r[2]}  price: {r[3]:,}")
        print(f"    cpu:    {r[4]}  cores: {r[13]}  threads: {r[14]}")
        print(f"    ram:    {r[5]} ({r[6]} MB)  gpu: {r[15]}")
        print(f"    ssd:    {r[7]} ({r[8]} GB)  screen: {r[9]} ({r[10]}\")")
        print(f"    weight: {r[11]} ({r[12]} kg)")
    conn.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Step 1: Catalog all laptops from exo.ir
Visits pages 1-7 of the laptop category (120 items/page),
extracts each laptop's name, URL, and slug ID,
and stores them in a SQLite database.
"""

import sqlite3
import time
import re
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── Config ──────────────────────────────────────────────────────────────────
BASE_URL = "https://exo.ir/category/laptop"
PARAMS_TEMPLATE = {"limit": 120}
MAX_PAGE = 7
DB_PATH = "laptops.db"
DELAY_BETWEEN_PAGES = 2  # seconds, be polite

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
}


# ── Database ────────────────────────────────────────────────────────────────
def create_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Create (or open) the SQLite database and ensure the laptops table exists."""
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
    conn.commit()
    return conn


# ── Scraper ─────────────────────────────────────────────────────────────────
def extract_slug(url: str) -> str:
    """Extract the slug from a product URL like /product/some-laptop-slug."""
    path = urlparse(url).path  # e.g. /product/some-laptop-slug
    # Remove trailing slash, take last segment
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "product":
        return parts[1]
    return parts[-1] if parts else url


def scrape_page(page_num: int, session: requests.Session) -> list[dict]:
    """
    Fetch one category page and return a list of laptop dicts:
    [{"slug": ..., "name": ..., "url": ...}, ...]
    """
    params = {**PARAMS_TEMPLATE}
    if page_num > 1:
        params["page"] = page_num

    url = BASE_URL
    print(f"  Fetching page {page_num} … ", end="", flush=True)

    resp = session.get(url, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    print(f"HTTP {resp.status_code}  ", end="", flush=True)

    soup = BeautifulSoup(resp.text, "lxml")

    laptops = []

    # Find product cards — look for links that point to /product/...
    product_links = soup.select("a[href*='/product/']")

    seen_slugs = set()
    for link in product_links:
        href = link.get("href", "")
        if "/product/" not in href:
            continue

        full_url = urljoin("https://exo.ir", href)
        slug = extract_slug(full_url)

        # Skip duplicates within same page (same product may appear in multiple links)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Get name: prefer the link text, fall back to slug
        name = link.get_text(strip=True)
        if not name or len(name) < 3:
            # Try parent card's title element
            card = link.find_parent(class_=re.compile(r"product", re.I))
            if card:
                title_el = card.select_one("a.text-truncate-2, .product-name, h4, h3")
                if title_el:
                    name = title_el.get_text(strip=True)
        if not name or len(name) < 3:
            name = slug.replace("-", " ").title()

        laptops.append({
            "slug": slug,
            "name": name,
            "url": full_url,
        })

    print(f"→ {len(laptops)} laptops found")
    return laptops


def save_laptops(conn: sqlite3.Connection, laptops: list[dict]) -> int:
    """Insert laptops into DB, skipping duplicates. Returns count of new inserts."""
    inserted = 0
    for lap in laptops:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO laptops (slug, name, url) VALUES (?, ?, ?)",
                (lap["slug"], lap["name"], lap["url"]),
            )
            if conn.total_changes:  # rough check
                inserted += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    return inserted


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Exo.ir Laptop Scraper — Step 1: Catalog")
    print("=" * 60)

    conn = create_db()

    # Count existing before scraping
    before_count = conn.execute("SELECT COUNT(*) FROM laptops").fetchone()[0]
    print(f"\nExisting laptops in DB: {before_count}")
    print(f"Scraping pages 1–{MAX_PAGE} (limit=120 per page)\n")

    session = requests.Session()
    total_found = 0

    for page in range(1, MAX_PAGE + 1):
        try:
            laptops = scrape_page(page, session)
            total_found += len(laptops)
            save_laptops(conn, laptops)
        except requests.RequestException as e:
            print(f"  ⚠ Error on page {page}: {e}")
            print(f"  Retrying in 5s …")
            time.sleep(5)
            try:
                laptops = scrape_page(page, session)
                total_found += len(laptops)
                save_laptops(conn, laptops)
            except requests.RequestException as e2:
                print(f"  ✗ Page {page} failed again: {e2}. Skipping.")

        if page < MAX_PAGE:
            time.sleep(DELAY_BETWEEN_PAGES)

    # Final stats
    after_count = conn.execute("SELECT COUNT(*) FROM laptops").fetchone()[0]
    new_count = after_count - before_count

    print(f"\n{'=' * 60}")
    print(f"Done!")
    print(f"  Total laptops found across pages:  {total_found}")
    print(f"  New laptops added to DB:           {new_count}")
    print(f"  Total laptops in DB:               {after_count}")
    print(f"  Database: {DB_PATH}")
    print(f"{'=' * 60}")

    # Show a sample
    print(f"\nSample (first 5 entries):")
    rows = conn.execute(
        "SELECT id, slug, name, url FROM laptops ORDER BY id LIMIT 5"
    ).fetchall()
    for row in rows:
        print(f"  [{row[0]}] {row[2]}")
        print(f"       slug: {row[1]}")
        print(f"       url:  {row[3]}")

    conn.close()


if __name__ == "__main__":
    main()

# Exo.ir Laptop Scraper & Analyzer

A Python toolkit that scrapes laptop listings from [exo.ir](https://exo.ir), stores them in a SQLite database, and produces a price-to-performance analysis with both terminal and HTML reports.

## Features

- **All-in-One Scraper** (`exo_laptop_scraper.py`) — Catalogs in-stock laptops from exo.ir and scrapes detailed specs in two phases:
  - **Phase 1 — Catalog**: Crawls category pages (120 items/page), stops at the first out-of-stock item.
  - **Phase 2 — Detail Scrape**: Fetches full specifications for each cataloged laptop using 8 parallel workers.
  - Supports retries with exponential backoff, graceful shutdown (Ctrl+C), and resume from where it left off.

- **Price-to-Performance Analyzer** (`analyze_laptops.py`) — Reads the database (read-only) and scores each laptop on a 0–100 composite scale based on:
  - CPU (30%) — tier-based + core/thread bonuses
  - GPU (30%) — tier-based + VRAM bonus
  - RAM (15%) — log-scale capacity + DDR generation bonus
  - Display (15%) — panel type, resolution, refresh rate
  - Storage (10%) — log-scale SSD capacity
  - Outputs a ranked terminal table and a styled interactive HTML report.

## Project Structure

```
35exoScraper/
├── exo_laptop_scraper.py        # All-in-one scraper (catalog + details)
├── analyze_laptops.py           # Price-to-performance analyzer
├── requirements.txt             # Python dependencies
├── laptops.db                   # SQLite database (scraped data)
├── laptop_analysis_report.html  # Generated HTML analysis report
└── README.md
```

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`:
  - `requests` ≥ 2.31.0
  - `beautifulsoup4` ≥ 4.12.0
  - `lxml` ≥ 5.0.0

## Setup

```bash
# Clone the repository
git clone git@github.com:YOUR_USERNAME/35exoScraper.git
cd 35exoScraper

# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### 1. Scrape Laptops

```bash
python3 exo_laptop_scraper.py
```

This runs both phases automatically:
1. Catalogs all in-stock laptops from exo.ir
2. Scrapes detailed specifications for each laptop

The scraper is resumable — re-run it to pick up where it left off. Press `Ctrl+C` for a graceful shutdown.

### 2. Analyze & Generate Report

```bash
python3 analyze_laptops.py
```

This produces:
- A formatted table in the terminal with rankings by price-to-performance ratio
- An HTML report saved as `laptop_analysis_report.html`

Open the HTML report in your browser for an interactive, sortable view.

## Configuration

Key constants at the top of `exo_laptop_scraper.py`:

| Constant              | Default | Description                          |
|-----------------------|---------|--------------------------------------|
| `ITEMS_PER_PAGE`      | 120     | Items per category page              |
| `MAX_WORKERS`         | 8       | Parallel scraping threads            |
| `MAX_RETRIES`         | 3       | Retry attempts per request           |
| `RETRY_BACKOFF`       | 2       | Backoff multiplier between retries   |
| `REQUEST_TIMEOUT`     | 30      | HTTP request timeout (seconds)       |
| `DELAY_BETWEEN_PAGES` | 2       | Delay between catalog pages (seconds)|

## License

This project is for personal/educational use.

#!/usr/bin/env python3
"""
Laptop Price-to-Performance Analyzer
=====================================
Reads laptops.db (READ-ONLY) and scores each laptop on a 0-100 composite
performance scale, then ranks by price/performance ratio.

Outputs:
  - Terminal report with tables
  - laptop_analysis_report.html (styled HTML report)

Dependencies: Python stdlib only (sqlite3, json, math, html, re)
"""

import sqlite3
import json
import math
import re
import html as html_mod
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "laptops.db"
REPORT_PATH = Path(__file__).parent / "laptop_analysis_report.html"

# ─── Weight configuration ────────────────────────────────────────────
W_CPU = 0.30
W_GPU = 0.30
W_RAM = 0.15
W_DISPLAY = 0.15
W_STORAGE = 0.10

# ─── GPU Tier Scores (0-100 base) ────────────────────────────────────
GPU_TIERS = {
    # NVIDIA RTX 50-series
    "RTX 5090": 100, "RTX 5080": 90, "RTX 5070 Ti": 83,
    "RTX 5070": 78, "RTX 5060": 68, "RTX 5050": 58,
    # NVIDIA RTX 40-series
    "RTX 4090": 92, "RTX 4080": 85, "RTX 4070 Ti": 78,
    "RTX 4070": 72, "RTX 4060": 62, "RTX 4050": 52,
    # NVIDIA RTX 30-series
    "RTX 3080 Ti": 70, "RTX 3080": 68, "RTX 3070 Ti": 62,
    "RTX 3070": 58, "RTX 3060": 48, "RTX 3050 Ti": 40,
    "RTX 3050": 38,
    # NVIDIA GTX
    "GTX 1650": 25, "GTX 1660 Ti": 32, "MX550": 18, "MX450": 15,
    # AMD Radeon discrete
    "Radeon RX 7600M": 55, "Radeon RX 7600S": 52,
    "Radeon RX 6700M": 48, "Radeon RX 6600M": 42,
    # Apple M-series GPU (integrated but powerful)
    "M4 Pro 20-Core": 72, "M4 Pro 16-Core": 65,
    "M4 10-Core": 50, "M4 8-Core": 42,
    "M3 Pro 18-Core": 60, "M3 Pro 14-Core": 52,
    "M3 10-Core": 45, "M3 8-Core": 38,
    # Integrated
    "Intel Arc": 22, "Intel Iris Xe": 15, "Intel UHD": 10,
    "Radeon 780M": 25, "Radeon 760M": 22, "Radeon 680M": 20,
    "Radeon 610M": 8, "Radeon Vega 8": 12, "Radeon Vega 7": 10,
    "Radeon Graphics": 10,
}

# ─── CPU Tier Scores (0-100 base) ────────────────────────────────────
CPU_TIERS = {
    # Intel Arrow Lake (Ultra)
    "Core Ultra 9 285HX": 98, "Core Ultra 9 275HX": 96,
    "Core Ultra 7 265HX": 85, "Core Ultra 7 255HX": 83,
    "Core Ultra 7 265H": 80, "Core Ultra 7 255H": 78,
    "Core Ultra 5 235H": 68, "Core Ultra 5 225H": 66,
    "Core Ultra 5 225U": 55, "Core Ultra 5 235U": 56,
    # Intel 14th Gen
    "Core i9 14900HX": 92, "Core i9 14900H": 88,
    "Core i7 14700HX": 82, "Core i7 14650HX": 80,
    "Core i7 14700H": 78, "Core i5 14500HX": 65,
    "Core i5 14450HX": 62,
    # Intel 13th Gen
    "Core i9 13900HX": 88, "Core i9 13980HX": 90,
    "Core i7 13700HX": 78, "Core i7 13650HX": 75,
    "Core i7 13620H": 70, "Core i7 1355U": 55,
    "Core i5 13500H": 60, "Core i5 13420H": 52,
    "Core i3 1315U": 35, "Core i3 13100H": 38,
    # Intel 12th Gen
    "Core i7 12700H": 68, "Core i7 1265U": 50,
    "Core i5 12500H": 55, "Core i5 1240P": 48,
    "Core i5 1235U": 42, "Core i3 1215U": 30,
    # AMD Ryzen
    "Ryzen 9 9955HX": 95, "Ryzen 9 9955HX3D": 97,
    "Ryzen 9 8945HX": 88, "Ryzen 9 8940HX": 86,
    "Ryzen 9 7945HX": 85, "Ryzen 9 7945HX3D": 87,
    "Ryzen 7 9800H3D": 82, "Ryzen 7 8845HX": 78,
    "Ryzen 7 8845H": 75, "Ryzen 7 8840H": 73,
    "Ryzen 7 8840U": 60, "Ryzen 7 8845HS": 72,
    "Ryzen 7 7840H": 72, "Ryzen 7 7840HS": 70,
    "Ryzen 7 7735HS": 65, "Ryzen 7 7840U": 58,
    "Ryzen 5 8640HS": 55, "Ryzen 5 7530U": 42,
    "Ryzen 5 7520U": 38, "Ryzen 3 7320U": 28,
    # Apple M-series
    "M4 Pro": 88, "M4": 75, "M4 Max": 96,
    "M3 Pro": 82, "M3": 68, "M3 Max": 92,
    "M2 Pro": 75, "M2": 60, "M2 Max": 85,
}

# ─── Panel quality scores ────────────────────────────────────────────
PANEL_SCORES = {
    "OLED": 100, "Mini LED": 90,
    "Liquid Retina XDR": 92, "Liquid Retina IPS": 70,
    "Retina IPS": 68, "IPS": 60, "TN": 30,
}


def parse_float(text: str, pattern: str = r"([\d.]+)") -> float | None:
    """Extract first float from a Farsi/English string."""
    if not text:
        return None
    m = re.search(pattern, str(text))
    return float(m.group(1)) if m else None


def parse_gpu_vram_gb(specs: dict) -> float:
    """Extract GPU VRAM in GB from spec JSON."""
    raw = specs.get("ظرفیت حافظه گرافیکی", "")
    if "فاقد" in raw or not raw:
        return 0
    val = parse_float(raw)
    return val if val else 0


def parse_refresh_rate(specs: dict) -> int:
    """Extract refresh rate in Hz."""
    raw = specs.get("نرخ به روزرسانی تصویر", "60")
    val = parse_float(raw)
    return int(val) if val else 60


def parse_resolution_pixels(specs: dict) -> int:
    """Extract total pixel count from resolution string like '2560x1600'."""
    raw = specs.get("حداکثر وضوح تصویر", "1920x1080")
    m = re.search(r"(\d+)\s*[xX×]\s*(\d+)", str(raw))
    if m:
        return int(m.group(1)) * int(m.group(2))
    return 1920 * 1080


def parse_panel_type(specs: dict) -> str:
    return specs.get("نوع پنل صفحه نمایش", "IPS")


def parse_ram_type(specs: dict) -> str:
    return specs.get("نوع RAM", "DDR5")


# ─── Scoring Functions ───────────────────────────────────────────────

def score_cpu(row: dict, specs: dict) -> float:
    """Score CPU 0-100."""
    model = row.get("cpu_model") or ""
    # Try exact match first
    base = CPU_TIERS.get(model)
    if base is None:
        # Try partial match
        for tier_key, tier_val in CPU_TIERS.items():
            if tier_key in model or model in tier_key:
                base = tier_val
                break
    if base is None:
        # Fallback heuristics
        ml = model.lower()
        if "ultra 9" in ml:
            base = 90
        elif "i9" in ml or "ryzen 9" in ml:
            base = 82
        elif "ultra 7" in ml:
            base = 78
        elif "i7" in ml or "ryzen 7" in ml:
            base = 68
        elif "ultra 5" in ml:
            base = 60
        elif "i5" in ml or "ryzen 5" in ml:
            base = 50
        elif "m4" in ml:
            base = 75
        elif "m3" in ml:
            base = 65
        elif "i3" in ml or "ryzen 3" in ml:
            base = 30
        else:
            base = 40  # unknown

    # Boost by core count (up to +10)
    cores = row.get("cpu_core_count") or 0
    core_boost = min(10, (cores / 24) * 10)

    # Boost by max frequency (up to +5)
    freq_str = specs.get("محدوده فرکانس پردازنده", "")
    freq = parse_float(freq_str)
    freq_boost = 0
    if freq:
        freq_boost = min(5, ((freq - 3.0) / 3.0) * 5)  # 3-6 GHz range

    return min(100, base * 0.85 + core_boost + freq_boost)


def score_gpu(row: dict, specs: dict) -> float:
    """Score GPU 0-100."""
    model = row.get("gpu_model") or ""
    base = GPU_TIERS.get(model)
    if base is None:
        for tier_key, tier_val in GPU_TIERS.items():
            if tier_key in model or model in tier_key:
                base = tier_val
                break
    if base is None:
        ml = model.lower()
        if "rtx" in ml:
            base = 50
        elif "gtx" in ml:
            base = 25
        elif "arc" in ml:
            base = 20
        elif "radeon" in ml:
            base = 15
        elif "uhd" in ml or "iris" in ml:
            base = 10
        elif "m4" in ml or "m3" in ml:
            base = 45
        else:
            base = 10

    # Boost by VRAM (up to +8)
    vram = parse_gpu_vram_gb(specs)
    vram_boost = min(8, (vram / 24) * 8)

    return min(100, base * 0.90 + vram_boost)


def score_ram(row: dict, specs: dict) -> float:
    """Score RAM 0-100 using log-scale."""
    ram_mb = row.get("ram_mb") or 8192
    # Log scale: 4GB=0, 8GB≈30, 16GB≈50, 32GB≈70, 64GB≈85, 128GB≈95, 192GB=100
    if ram_mb <= 0:
        return 0
    log_score = (math.log2(ram_mb / 1024) - 2) / (math.log2(192) - 2) * 90
    log_score = max(0, min(90, log_score))

    # DDR5/LPDDR5X bonus
    ram_type = parse_ram_type(specs)
    type_bonus = 0
    if "DDR5" in ram_type or "LPDDR5" in ram_type:
        type_bonus = 10
    elif "DDR4" in ram_type or "LPDDR4" in ram_type:
        type_bonus = 4

    return min(100, log_score + type_bonus)


def score_storage(row: dict) -> float:
    """Score storage 0-100 using log-scale on SSD GB."""
    ssd_gb = row.get("ssd_gb") or 256
    if ssd_gb <= 0:
        return 0
    # Log scale: 256=30, 512=50, 1TB=65, 2TB=80, 4TB=90, 8TB=100
    log_score = (math.log2(ssd_gb) - math.log2(128)) / (math.log2(8192) - math.log2(128)) * 100
    return max(0, min(100, log_score))


def score_display(specs: dict) -> float:
    """Score display 0-100 from panel type, resolution, refresh rate."""
    # Panel quality (0-40)
    panel = parse_panel_type(specs)
    panel_score = PANEL_SCORES.get(panel, 50) / 100 * 40

    # Resolution (0-35): 1080p=15, 1440p=25, 2K+=35
    pixels = parse_resolution_pixels(specs)
    if pixels >= 2560 * 1600:
        res_score = 35
    elif pixels >= 2560 * 1440:
        res_score = 30
    elif pixels >= 1920 * 1200:
        res_score = 22
    elif pixels >= 1920 * 1080:
        res_score = 15
    else:
        res_score = 8

    # Refresh rate (0-25): 60=5, 120=12, 144=16, 165=18, 240=25
    hz = parse_refresh_rate(specs)
    if hz >= 240:
        hz_score = 25
    elif hz >= 165:
        hz_score = 18
    elif hz >= 144:
        hz_score = 16
    elif hz >= 120:
        hz_score = 12
    else:
        hz_score = 5

    return min(100, panel_score + res_score + hz_score)


def composite_score(cpu: float, gpu: float, ram: float, storage: float, display: float) -> float:
    """Weighted composite performance score."""
    return (cpu * W_CPU + gpu * W_GPU + ram * W_RAM +
            storage * W_STORAGE + display * W_DISPLAY)


# ─── Data Loading ────────────────────────────────────────────────────

def load_laptops() -> list[dict]:
    """Load all laptops from the DB (read-only)."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM laptop_details")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def analyze(rows: list[dict]) -> list[dict]:
    """Score every laptop and return enriched dicts sorted by composite score."""
    results = []
    for row in rows:
        specs = {}
        if row.get("full_specs_json"):
            try:
                specs = json.loads(row["full_specs_json"])
            except json.JSONDecodeError:
                pass

        cpu = score_cpu(row, specs)
        gpu = score_gpu(row, specs)
        ram = score_ram(row, specs)
        stor = score_storage(row)
        disp = score_display(specs)
        comp = composite_score(cpu, gpu, ram, stor, disp)

        price = row.get("price") or 0
        price_m = price / 1_000_000 if price > 0 else 0  # millions of Rials
        ppr = comp / price_m if price_m > 0 else None     # performance per M-Rial

        results.append({
            "title": row.get("title", ""),
            "model_code": row.get("model_code", ""),
            "cpu_model": row.get("cpu_model", ""),
            "gpu_model": row.get("gpu_model", ""),
            "ram_mb": row.get("ram_mb", 0),
            "ssd_gb": row.get("ssd_gb", 0),
            "screen_inches": row.get("screen_inches", 0),
            "weight_kg": row.get("weight_kg", 0),
            "price": price,
            "price_m": round(price_m, 1),
            "cpu_score": round(cpu, 1),
            "gpu_score": round(gpu, 1),
            "ram_score": round(ram, 1),
            "storage_score": round(stor, 1),
            "display_score": round(disp, 1),
            "perf_score": round(comp, 1),
            "ppr": round(ppr, 3) if ppr else None,
        })

    results.sort(key=lambda x: x["perf_score"], reverse=True)
    return results


# ─── Terminal Report ─────────────────────────────────────────────────

def fmt_price(price: int) -> str:
    if price <= 0:
        return "N/A"
    return f"{price / 1_000_000:,.1f}M"


def truncate(text: str, length: int) -> str:
    if not text:
        return ""
    # Remove Farsi text for terminal display, keep the model info
    clean = text.strip()
    if len(clean) > length:
        return clean[:length - 1] + "…"
    return clean


def print_table(title: str, headers: list[str], rows: list[list], widths: list[int]):
    """Print a formatted ASCII table to stdout."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")

    # Header
    header_line = " │ ".join(h.ljust(w) if i == 0 else h.rjust(w)
                             for i, (h, w) in enumerate(zip(headers, widths)))
    print(f" {header_line}")
    print(f" {'─┼─'.join('─' * w for w in widths)}")

    # Rows
    for row in rows:
        line = " │ ".join(str(v).ljust(w) if i == 0 else str(v).rjust(w)
                          for i, (v, w) in enumerate(zip(row, widths)))
        print(f" {line}")


def print_terminal_report(results: list[dict]):
    """Print the full analysis report to terminal."""
    total = len(results)
    with_price = [r for r in results if r["ppr"] is not None]
    by_ppr = sorted(with_price, key=lambda x: x["ppr"], reverse=True)

    print(f"\n{'#' * 80}")
    print(f"#  LAPTOP PRICE-TO-PERFORMANCE ANALYSIS")
    print(f"#  {total} laptops analyzed  |  {len(with_price)} with valid prices")
    print(f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#' * 80}")

    # ── Summary stats ──
    scores = [r["perf_score"] for r in results]
    print(f"\n  Performance Score Range: {min(scores):.1f} – {max(scores):.1f}")
    print(f"  Average Performance Score: {sum(scores)/len(scores):.1f}")
    if with_price:
        prices = [r["price"] for r in with_price]
        print(f"  Price Range: {fmt_price(min(prices))} – {fmt_price(max(prices))} Rials")
        pprs = [r["ppr"] for r in with_price]
        print(f"  Price/Perf Ratio Range: {min(pprs):.3f} – {max(pprs):.3f}")

    # ── Top 20 by Performance ──
    headers = ["#", "Model", "CPU", "GPU", "RAM", "SSD", "Perf", "Price"]
    widths = [3, 28, 18, 12, 6, 5, 5, 10]
    table_rows = []
    for i, r in enumerate(results[:20], 1):
        table_rows.append([
            i,
            truncate(r["model_code"] or r["title"], 28),
            truncate(r["cpu_model"], 18),
            truncate(r["gpu_model"], 12),
            f"{(r['ram_mb'] or 0) // 1024}G",
            f"{r['ssd_gb'] or 0}",
            f"{r['perf_score']:.1f}",
            fmt_price(r["price"]),
        ])
    print_table("TOP 20 – HIGHEST PERFORMANCE", headers, table_rows, widths)

    # ── Top 20 by Price/Performance ──
    headers2 = ["#", "Model", "CPU", "GPU", "Perf", "Price", "P/P"]
    widths2 = [3, 28, 18, 12, 5, 10, 7]
    table_rows2 = []
    for i, r in enumerate(by_ppr[:20], 1):
        table_rows2.append([
            i,
            truncate(r["model_code"] or r["title"], 28),
            truncate(r["cpu_model"], 18),
            truncate(r["gpu_model"], 12),
            f"{r['perf_score']:.1f}",
            fmt_price(r["price"]),
            f"{r['ppr']:.3f}",
        ])
    print_table("TOP 20 – BEST PRICE/PERFORMANCE (higher P/P = better value)", headers2, table_rows2, widths2)

    # ── Bottom 10 by Price/Performance (most overpriced) ──
    table_rows3 = []
    for i, r in enumerate(by_ppr[-10:], 1):
        table_rows3.append([
            i,
            truncate(r["model_code"] or r["title"], 28),
            truncate(r["cpu_model"], 18),
            truncate(r["gpu_model"], 12),
            f"{r['perf_score']:.1f}",
            fmt_price(r["price"]),
            f"{r['ppr']:.3f}",
        ])
    print_table("BOTTOM 10 – WORST PRICE/PERFORMANCE (most overpriced)", headers2, table_rows3, widths2)

    # ── GPU Tier Averages ──
    gpu_groups: dict[str, list] = {}
    for r in with_price:
        gpu = r["gpu_model"] or "Unknown"
        gpu_groups.setdefault(gpu, []).append(r)

    gpu_avg = []
    for gpu, items in gpu_groups.items():
        if len(items) < 2:
            continue
        avg_perf = sum(x["perf_score"] for x in items) / len(items)
        avg_price = sum(x["price"] for x in items) / len(items)
        avg_ppr = sum(x["ppr"] for x in items) / len(items)
        gpu_avg.append((gpu, len(items), avg_perf, avg_price, avg_ppr))

    gpu_avg.sort(key=lambda x: x[2], reverse=True)
    headers4 = ["GPU", "Count", "AvgPerf", "AvgPrice", "AvgP/P"]
    widths4 = [16, 5, 7, 12, 7]
    table_rows4 = [[g[0], g[1], f"{g[2]:.1f}", fmt_price(int(g[3])), f"{g[4]:.3f}"]
                   for g in gpu_avg[:15]]
    print_table("GPU TIER AVERAGES (≥2 laptops)", headers4, table_rows4, widths4)

    print(f"\n  Full HTML report saved to: {REPORT_PATH}")
    print()


# ─── HTML Report ─────────────────────────────────────────────────────

def generate_html_report(results: list[dict]):
    """Generate a styled HTML report."""
    with_price = [r for r in results if r["ppr"] is not None]
    by_ppr = sorted(with_price, key=lambda x: x["ppr"], reverse=True)
    scores = [r["perf_score"] for r in results]

    def esc(t):
        return html_mod.escape(str(t)) if t else ""

    def perf_bar(score, max_w=200):
        w = int(score / 100 * max_w)
        if score >= 80:
            color = "#22c55e"
        elif score >= 60:
            color = "#3b82f6"
        elif score >= 40:
            color = "#f59e0b"
        else:
            color = "#ef4444"
        return (f'<div style="background:#1e293b;border-radius:4px;width:{max_w}px;height:18px;display:inline-block;vertical-align:middle">'
                f'<div style="background:{color};width:{w}px;height:18px;border-radius:4px"></div></div>'
                f' <span style="font-weight:600">{score:.1f}</span>')

    def price_fmt(p):
        if p <= 0:
            return '<span style="color:#64748b">N/A</span>'
        return f"{p / 1_000_000:,.1f}M"

    # Build score distribution histogram (10 bins)
    bins = [0] * 10
    for s in scores:
        idx = min(9, int(s / 10))
        bins[idx] += 1
    max_bin = max(bins) if bins else 1

    hist_html = '<div style="display:flex;align-items:flex-end;gap:4px;height:120px;margin:20px 0">'
    for i, count in enumerate(bins):
        h = int(count / max_bin * 100) if max_bin > 0 else 0
        label = f"{i*10}-{i*10+9}"
        hist_html += (f'<div style="display:flex;flex-direction:column;align-items:center;flex:1">'
                      f'<span style="font-size:11px;color:#94a3b8">{count}</span>'
                      f'<div style="width:100%;height:{h}px;background:linear-gradient(180deg,#6366f1,#3b82f6);'
                      f'border-radius:4px 4px 0 0;min-height:2px"></div>'
                      f'<span style="font-size:10px;color:#64748b;margin-top:4px">{label}</span>'
                      f'</div>')
    hist_html += '</div>'

    def make_table(data: list[dict], show_ppr=False, limit=20):
        rows_html = ""
        for i, r in enumerate(data[:limit], 1):
            bg = "#1e293b" if i % 2 == 0 else "#0f172a"
            rows_html += f"""<tr style="background:{bg}">
                <td style="padding:8px 12px;color:#94a3b8">{i}</td>
                <td style="padding:8px 12px;font-weight:500">{esc(r['model_code'] or r['title'][:40])}</td>
                <td style="padding:8px 12px;color:#93c5fd">{esc(r['cpu_model'])}</td>
                <td style="padding:8px 12px;color:#a78bfa">{esc(r['gpu_model'])}</td>
                <td style="padding:8px 12px;text-align:right">{(r['ram_mb'] or 0)//1024}GB</td>
                <td style="padding:8px 12px;text-align:right">{r['ssd_gb'] or 0}GB</td>
                <td style="padding:8px 6px">{perf_bar(r['perf_score'])}</td>
                <td style="padding:8px 12px;text-align:right;color:#fbbf24">{price_fmt(r['price'])}</td>"""
            if show_ppr:
                ppr_val = f"{r['ppr']:.3f}" if r['ppr'] else "N/A"
                ppr_color = "#22c55e" if (r['ppr'] or 0) > 0.3 else "#f59e0b" if (r['ppr'] or 0) > 0.15 else "#ef4444"
                rows_html += f'<td style="padding:8px 12px;text-align:right;color:{ppr_color};font-weight:700">{ppr_val}</td>'
            rows_html += "</tr>\n"
        return rows_html

    def sub_scores_table(data: list[dict], limit=20):
        rows_html = ""
        for i, r in enumerate(data[:limit], 1):
            bg = "#1e293b" if i % 2 == 0 else "#0f172a"
            rows_html += f"""<tr style="background:{bg}">
                <td style="padding:6px 10px;color:#94a3b8">{i}</td>
                <td style="padding:6px 10px;font-weight:500">{esc(r['model_code'] or r['title'][:35])}</td>
                <td style="padding:6px 10px;text-align:center;color:#60a5fa">{r['cpu_score']}</td>
                <td style="padding:6px 10px;text-align:center;color:#a78bfa">{r['gpu_score']}</td>
                <td style="padding:6px 10px;text-align:center;color:#34d399">{r['ram_score']}</td>
                <td style="padding:6px 10px;text-align:center;color:#fbbf24">{r['storage_score']}</td>
                <td style="padding:6px 10px;text-align:center;color:#f472b6">{r['display_score']}</td>
                <td style="padding:6px 10px;text-align:center;font-weight:700;color:#e2e8f0">{r['perf_score']}</td>
            </tr>\n"""
        return rows_html

    # GPU tier averages
    gpu_groups: dict[str, list] = {}
    for r in with_price:
        g = r["gpu_model"] or "Unknown"
        gpu_groups.setdefault(g, []).append(r)

    gpu_tier_rows = ""
    gpu_avgs = []
    for gpu, items in gpu_groups.items():
        if len(items) < 2:
            continue
        avg_perf = sum(x["perf_score"] for x in items) / len(items)
        avg_price = sum(x["price"] for x in items) / len(items)
        avg_ppr = sum(x["ppr"] for x in items) / len(items)
        gpu_avgs.append((gpu, len(items), avg_perf, avg_price, avg_ppr))
    gpu_avgs.sort(key=lambda x: x[2], reverse=True)
    for i, (gpu, cnt, ap, apr, appr) in enumerate(gpu_avgs):
        bg = "#1e293b" if i % 2 == 0 else "#0f172a"
        gpu_tier_rows += f"""<tr style="background:{bg}">
            <td style="padding:6px 10px;color:#a78bfa;font-weight:500">{esc(gpu)}</td>
            <td style="padding:6px 10px;text-align:center">{cnt}</td>
            <td style="padding:6px 10px">{perf_bar(ap, 150)}</td>
            <td style="padding:6px 10px;text-align:right;color:#fbbf24">{price_fmt(int(apr))}</td>
            <td style="padding:6px 10px;text-align:right;font-weight:600;color:#22c55e">{appr:.3f}</td>
        </tr>\n"""

    th_style = 'style="padding:10px 12px;text-align:left;color:#94a3b8;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #334155"'
    th_r = 'style="padding:10px 12px;text-align:right;color:#94a3b8;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #334155"'
    th_c = 'style="padding:10px 12px;text-align:center;color:#94a3b8;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #334155"'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Laptop Price-to-Performance Analysis</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: #0f172a; color: #e2e8f0; line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
        .header {{
            background: linear-gradient(135deg, #1e1b4b 0%, #1e3a5f 100%);
            border-radius: 16px; padding: 40px; margin-bottom: 32px;
            border: 1px solid #334155;
        }}
        .header h1 {{
            font-size: 28px; font-weight: 700;
            background: linear-gradient(90deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        .header p {{ color: #94a3b8; font-size: 14px; }}
        .stats {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px; margin-bottom: 32px;
        }}
        .stat-card {{
            background: #1e293b; border-radius: 12px; padding: 20px;
            border: 1px solid #334155;
        }}
        .stat-card .label {{ color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-card .value {{ font-size: 24px; font-weight: 700; color: #f1f5f9; margin-top: 4px; }}
        .section {{
            background: #0f172a; border: 1px solid #1e293b;
            border-radius: 12px; margin-bottom: 32px; overflow: hidden;
        }}
        .section-title {{
            padding: 20px 24px; font-size: 18px; font-weight: 600;
            border-bottom: 1px solid #1e293b;
            background: linear-gradient(90deg, rgba(99,102,241,0.1), transparent);
        }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        td {{ white-space: nowrap; }}
        tr:hover {{ background: #334155 !important; }}
        .methodology {{
            background: #1e293b; border-radius: 12px; padding: 24px;
            border: 1px solid #334155; margin-bottom: 32px; font-size: 14px;
        }}
        .methodology h3 {{ color: #a78bfa; margin-bottom: 12px; }}
        .methodology table {{ font-size: 13px; }}
        .methodology td, .methodology th {{ padding: 8px 12px; border-bottom: 1px solid #334155; }}
        .bar-chart {{ margin: 20px 24px; }}
    </style>
</head>
<body>
<div class="container">

    <div class="header">
        <h1>📊 Laptop Price-to-Performance Analysis</h1>
        <p>{len(results)} laptops analyzed &bull; {len(with_price)} with valid prices &bull;
           Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="label">Total Laptops</div>
            <div class="value">{len(results)}</div>
        </div>
        <div class="stat-card">
            <div class="label">Avg Performance</div>
            <div class="value">{sum(scores)/len(scores):.1f}</div>
        </div>
        <div class="stat-card">
            <div class="label">Price Range</div>
            <div class="value" style="font-size:18px">{price_fmt(min(r['price'] for r in with_price))} – {price_fmt(max(r['price'] for r in with_price))}</div>
        </div>
        <div class="stat-card">
            <div class="label">Best P/P Ratio</div>
            <div class="value" style="color:#22c55e">{by_ppr[0]['ppr']:.3f}</div>
        </div>
    </div>

    <div class="methodology">
        <h3>📐 Scoring Methodology</h3>
        <table>
            <tr><th {th_style}>Component</th><th {th_c}>Weight</th><th {th_style}>Approach</th></tr>
            <tr><td style="padding:8px 12px;color:#60a5fa">CPU</td><td style="padding:8px 12px;text-align:center">30%</td><td style="padding:8px 12px">Tiered by model family + core count & frequency boost</td></tr>
            <tr><td style="padding:8px 12px;color:#a78bfa">GPU</td><td style="padding:8px 12px;text-align:center">30%</td><td style="padding:8px 12px">Tiered by model + VRAM boost</td></tr>
            <tr><td style="padding:8px 12px;color:#34d399">RAM</td><td style="padding:8px 12px;text-align:center">15%</td><td style="padding:8px 12px">Log-scaled capacity + DDR5 bonus</td></tr>
            <tr><td style="padding:8px 12px;color:#fbbf24">Storage</td><td style="padding:8px 12px;text-align:center">10%</td><td style="padding:8px 12px">Log-scaled SSD capacity</td></tr>
            <tr><td style="padding:8px 12px;color:#f472b6">Display</td><td style="padding:8px 12px;text-align:center">15%</td><td style="padding:8px 12px">Panel type + resolution + refresh rate</td></tr>
        </table>
        <p style="margin-top:12px;color:#64748b">Price/Performance (P/P) = Performance Score ÷ Price in Millions of Rials. Higher = better value.</p>
    </div>

    <div class="section">
        <div class="section-title">📈 Score Distribution</div>
        <div class="bar-chart">{hist_html}</div>
    </div>

    <div class="section">
        <div class="section-title">🏆 Top 25 – Highest Performance</div>
        <table>
            <thead><tr>
                <th {th_style}>#</th><th {th_style}>Model</th><th {th_style}>CPU</th>
                <th {th_style}>GPU</th><th {th_r}>RAM</th><th {th_r}>SSD</th>
                <th {th_style}>Performance</th><th {th_r}>Price</th>
            </tr></thead>
            <tbody>{make_table(results, show_ppr=False, limit=25)}</tbody>
        </table>
    </div>

    <div class="section">
        <div class="section-title">🔍 Top 25 – Sub-Score Breakdown</div>
        <table>
            <thead><tr>
                <th {th_style}>#</th><th {th_style}>Model</th>
                <th {th_c}>CPU</th><th {th_c}>GPU</th><th {th_c}>RAM</th>
                <th {th_c}>Storage</th><th {th_c}>Display</th><th {th_c}>Total</th>
            </tr></thead>
            <tbody>{sub_scores_table(results, limit=25)}</tbody>
        </table>
    </div>

    <div class="section">
        <div class="section-title">💰 Top 25 – Best Price/Performance (Best Value)</div>
        <table>
            <thead><tr>
                <th {th_style}>#</th><th {th_style}>Model</th><th {th_style}>CPU</th>
                <th {th_style}>GPU</th><th {th_r}>RAM</th><th {th_r}>SSD</th>
                <th {th_style}>Performance</th><th {th_r}>Price</th><th {th_r}>P/P Ratio</th>
            </tr></thead>
            <tbody>{make_table(by_ppr, show_ppr=True, limit=25)}</tbody>
        </table>
    </div>

    <div class="section">
        <div class="section-title">⚠️ Bottom 15 – Worst Price/Performance (Overpriced)</div>
        <table>
            <thead><tr>
                <th {th_style}>#</th><th {th_style}>Model</th><th {th_style}>CPU</th>
                <th {th_style}>GPU</th><th {th_r}>RAM</th><th {th_r}>SSD</th>
                <th {th_style}>Performance</th><th {th_r}>Price</th><th {th_r}>P/P Ratio</th>
            </tr></thead>
            <tbody>{make_table(list(reversed(by_ppr[-15:])), show_ppr=True, limit=15)}</tbody>
        </table>
    </div>

    <div class="section">
        <div class="section-title">🎮 GPU Tier Analysis (≥2 laptops per tier)</div>
        <table>
            <thead><tr>
                <th {th_style}>GPU</th><th {th_c}>Count</th><th {th_style}>Avg Performance</th>
                <th {th_r}>Avg Price</th><th {th_r}>Avg P/P</th>
            </tr></thead>
            <tbody>{gpu_tier_rows}</tbody>
        </table>
    </div>

    <div style="text-align:center;padding:32px;color:#475569;font-size:12px">
        Generated by analyze_laptops.py &bull; Data from laptops.db (read-only) &bull; {datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>

</div>
</body>
</html>"""

    REPORT_PATH.write_text(html, encoding="utf-8")


# ─── Main ────────────────────────────────────────────────────────────

def main():
    print("Loading laptops from DB (read-only)...")
    rows = load_laptops()
    print(f"  Loaded {len(rows)} laptops")

    print("Scoring laptops...")
    results = analyze(rows)
    print(f"  Scored {len(results)} laptops")

    print_terminal_report(results)
    generate_html_report(results)
    print("Done!")


if __name__ == "__main__":
    main()

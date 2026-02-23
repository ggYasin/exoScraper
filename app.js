/* ═══════════════════════════════════════════════════════════
   Exo Laptop Explorer — Dynamic Scoring & Data Explorer
   ═══════════════════════════════════════════════════════════ */

// ─── Tier dictionaries (ported from analyze_laptops.py) ──────

const DEFAULT_CPU_TIERS = {
    // Intel Arrow Lake (Ultra)
    "Core Ultra 9 285HX": 98, "Core Ultra 9 275HX": 96,
    "Core Ultra 7 265HX": 85, "Core Ultra 7 255HX": 83,
    "Core Ultra 7 265H": 80, "Core Ultra 7 255H": 78,
    "Core Ultra 5 235H": 68, "Core Ultra 5 225H": 66,
    "Core Ultra 5 225U": 55, "Core Ultra 5 235U": 56,
    // Intel 14th Gen
    "Core i9 14900HX": 92, "Core i9 14900H": 88,
    "Core i7 14700HX": 82, "Core i7 14650HX": 80,
    "Core i7 14700H": 78, "Core i5 14500HX": 65,
    "Core i5 14450HX": 62,
    // Intel 13th Gen
    "Core i9 13900HX": 88, "Core i9 13980HX": 90,
    "Core i7 13700HX": 78, "Core i7 13650HX": 75,
    "Core i7 13620H": 70, "Core i7 1355U": 55,
    "Core i5 13500H": 60, "Core i5 13420H": 52,
    "Core i3 1315U": 35, "Core i3 13100H": 38,
    // Intel 12th Gen
    "Core i7 12700H": 68, "Core i7 1265U": 50,
    "Core i5 12500H": 55, "Core i5 1240P": 48,
    "Core i5 1235U": 42, "Core i3 1215U": 30,
    // AMD Ryzen
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
    // Apple M-series
    "M4 Pro": 88, "M4": 75, "M4 Max": 96,
    "M3 Pro": 82, "M3": 68, "M3 Max": 92,
    "M2 Pro": 75, "M2": 60, "M2 Max": 85,
};

const DEFAULT_GPU_TIERS = {
    // NVIDIA RTX 50-series
    "RTX 5090": 100, "RTX 5080": 90, "RTX 5070 Ti": 83,
    "RTX 5070": 78, "RTX 5060": 68, "RTX 5050": 58,
    // NVIDIA RTX 40-series
    "RTX 4090": 92, "RTX 4080": 85, "RTX 4070 Ti": 78,
    "RTX 4070": 72, "RTX 4060": 62, "RTX 4050": 52,
    // NVIDIA RTX 30-series
    "RTX 3080 Ti": 70, "RTX 3080": 68, "RTX 3070 Ti": 62,
    "RTX 3070": 58, "RTX 3060": 48, "RTX 3050 Ti": 40,
    "RTX 3050": 38,
    // NVIDIA GTX
    "GTX 1650": 25, "GTX 1660 Ti": 32, "MX550": 18, "MX450": 15,
    // AMD Radeon discrete
    "Radeon RX 7600M": 55, "Radeon RX 7600S": 52,
    "Radeon RX 6700M": 48, "Radeon RX 6600M": 42,
    // Apple M-series GPU
    "M4 Pro 20-Core": 72, "M4 Pro 16-Core": 65,
    "M4 10-Core": 50, "M4 8-Core": 42,
    "M3 Pro 18-Core": 60, "M3 Pro 14-Core": 52,
    "M3 10-Core": 45, "M3 8-Core": 38,
    // Integrated
    "Intel Arc": 22, "Intel Iris Xe": 15, "Intel UHD": 10,
    "Radeon 780M": 25, "Radeon 760M": 22, "Radeon 680M": 20,
    "Radeon 610M": 8, "Radeon Vega 8": 12, "Radeon Vega 7": 10,
    "Radeon Graphics": 10,
};

const DEFAULT_PANEL_SCORES = {
    "OLED": 100, "Mini LED": 90,
    "Liquid Retina XDR": 92, "Liquid Retina IPS": 70,
    "Retina IPS": 68, "IPS": 60, "TN": 30,
};

// ─── Utility helpers ─────────────────────────────────────────

function parseFloat2(text) {
    if (!text) return null;
    const m = String(text).match(/([\d.]+)/);
    return m ? parseFloat(m[1]) : null;
}

function escHtml(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// ─── Scoring functions (mirroring Python logic exactly) ──────

function scoreCPU(row) {
    const model = row.cpu_model || '';
    const specs = row.full_specs || {};
    const tiers = state.tiers.cpu;
    let base = tiers[model];
    if (base === undefined) {
        for (const [k, v] of Object.entries(tiers)) {
            if (model.includes(k) || k.includes(model)) { base = v; break; }
        }
    }
    if (base === undefined) {
        const ml = model.toLowerCase();
        if (ml.includes('ultra 9')) base = 90;
        else if (ml.includes('i9') || ml.includes('ryzen 9')) base = 82;
        else if (ml.includes('ultra 7')) base = 78;
        else if (ml.includes('i7') || ml.includes('ryzen 7')) base = 68;
        else if (ml.includes('ultra 5')) base = 60;
        else if (ml.includes('i5') || ml.includes('ryzen 5')) base = 50;
        else if (ml.includes('m4')) base = 75;
        else if (ml.includes('m3')) base = 65;
        else if (ml.includes('i3') || ml.includes('ryzen 3')) base = 30;
        else base = 40;
    }
    const cores = row.cpu_core_count || 0;
    const coreBoost = Math.min(10, (cores / 24) * 10);
    const freqStr = specs['محدوده فرکانس پردازنده'] || '';
    const freq = parseFloat2(freqStr);
    let freqBoost = 0;
    if (freq) freqBoost = Math.min(5, ((freq - 3.0) / 3.0) * 5);
    return Math.min(100, base * 0.85 + coreBoost + freqBoost);
}

function scoreGPU(row) {
    const model = row.gpu_model || '';
    const specs = row.full_specs || {};
    const tiers = state.tiers.gpu;
    let base = tiers[model];
    if (base === undefined) {
        for (const [k, v] of Object.entries(tiers)) {
            if (model.includes(k) || k.includes(model)) { base = v; break; }
        }
    }
    if (base === undefined) {
        const ml = model.toLowerCase();
        if (ml.includes('rtx')) base = 50;
        else if (ml.includes('gtx')) base = 25;
        else if (ml.includes('arc')) base = 20;
        else if (ml.includes('radeon')) base = 15;
        else if (ml.includes('uhd') || ml.includes('iris')) base = 10;
        else if (ml.includes('m4') || ml.includes('m3')) base = 45;
        else base = 10;
    }
    // VRAM boost
    const vramRaw = specs['ظرفیت حافظه گرافیکی'] || '';
    let vram = 0;
    if (vramRaw && !vramRaw.includes('فاقد')) {
        vram = parseFloat2(vramRaw) || 0;
    }
    const vramBoost = Math.min(8, (vram / 24) * 8);
    return Math.min(100, base * 0.90 + vramBoost);
}

function scoreRAM(row) {
    const specs = row.full_specs || {};
    const ramMb = row.ram_mb || 8192;
    if (ramMb <= 0) return 0;
    let logScore = (Math.log2(ramMb / 1024) - 2) / (Math.log2(192) - 2) * 90;
    logScore = Math.max(0, Math.min(90, logScore));
    const ramType = specs['نوع RAM'] || 'DDR5';
    let typeBonus = 0;
    if (ramType.includes('DDR5') || ramType.includes('LPDDR5')) typeBonus = 10;
    else if (ramType.includes('DDR4') || ramType.includes('LPDDR4')) typeBonus = 4;
    return Math.min(100, logScore + typeBonus);
}

function scoreStorage(row) {
    const ssdGb = row.ssd_gb || 256;
    if (ssdGb <= 0) return 0;
    const logScore = (Math.log2(ssdGb) - Math.log2(128)) / (Math.log2(8192) - Math.log2(128)) * 100;
    return Math.max(0, Math.min(100, logScore));
}

function scoreDisplay(row) {
    const specs = row.full_specs || {};
    const panel = specs['نوع پنل صفحه نمایش'] || 'IPS';
    const tiers = state.tiers.panel;
    const panelScore = (tiers[panel] ?? 50) / 100 * 40;

    const resRaw = specs['حداکثر وضوح تصویر'] || '1920x1080';
    const resMatch = String(resRaw).match(/(\d+)\s*[xX×]\s*(\d+)/);
    const pixels = resMatch ? parseInt(resMatch[1]) * parseInt(resMatch[2]) : 1920 * 1080;
    let resScore;
    if (pixels >= 2560 * 1600) resScore = 35;
    else if (pixels >= 2560 * 1440) resScore = 30;
    else if (pixels >= 1920 * 1200) resScore = 22;
    else if (pixels >= 1920 * 1080) resScore = 15;
    else resScore = 8;

    const hzRaw = specs['نرخ به روزرسانی تصویر'] || '60';
    const hz = parseFloat2(hzRaw) || 60;
    let hzScore;
    if (hz >= 240) hzScore = 25;
    else if (hz >= 165) hzScore = 18;
    else if (hz >= 144) hzScore = 16;
    else if (hz >= 120) hzScore = 12;
    else hzScore = 5;

    return Math.min(100, panelScore + resScore + hzScore);
}

// ─── Application State ──────────────────────────────────────

const state = {
    raw: [],           // original JSON data
    processed: [],     // data with dynamic scores
    filtered: [],      // after filters applied
    weights: { cpu: 0.30, gpu: 0.30, ram: 0.15, display: 0.15, storage: 0.10 },
    sort: { key: 'perf_score', dir: 'desc' },
    page: 1,
    perPage: 50,
    brands: [],
    tiers: { cpu: {}, gpu: {}, panel: {} }, // Will be loaded from localStorage or defaults
    selectedLaptops: new Set(),
};

// ─── DOM refs ───────────────────────────────────────────────

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const dom = {
    tableBody: $('#table-body'),
    pagination: $('#pagination'),
    pageInfo: $('#page-info'),
    statTotal: $('#stat-total'),
    statShowing: $('#stat-showing'),
    statAvgScore: $('#stat-avg-score'),
    statAvgPrice: $('#stat-avg-price'),
    statBestPP: $('#stat-best-pp'),
    weightSum: $('#weight-sum'),
    weightSumVal: $('#weight-sum-val'),
    modalOverlay: $('#modal-overlay'),
    modalContent: $('#modal-content'),
    sidebar: $('#sidebar'),
};

// ─── Initialization ─────────────────────────────────────────

async function init() {
    // Load tiers from localStorage or use defaults
    const savedTiers = localStorage.getItem('exo_tiers');
    if (savedTiers) {
        try {
            state.tiers = JSON.parse(savedTiers);
            // Validate and fallback if stored data is empty or corrupt
            if (!state.tiers.cpu || Object.keys(state.tiers.cpu).length === 0) state.tiers.cpu = { ...DEFAULT_CPU_TIERS };
            if (!state.tiers.gpu || Object.keys(state.tiers.gpu).length === 0) state.tiers.gpu = { ...DEFAULT_GPU_TIERS };
            if (!state.tiers.panel || Object.keys(state.tiers.panel).length === 0) state.tiers.panel = { ...DEFAULT_PANEL_SCORES };
        } catch (e) {
            console.warn("Failed to load tiers from local storage, using defaults", e);
            state.tiers = {
                cpu: { ...DEFAULT_CPU_TIERS },
                gpu: { ...DEFAULT_GPU_TIERS },
                panel: { ...DEFAULT_PANEL_SCORES }
            };
        }
    } else {
        state.tiers = {
            cpu: { ...DEFAULT_CPU_TIERS },
            gpu: { ...DEFAULT_GPU_TIERS },
            panel: { ...DEFAULT_PANEL_SCORES }
        };
    }

    try {
        const resp = await fetch('laptops.json');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        state.raw = await resp.json();
    } catch (e) {
        dom.tableBody.innerHTML = `<tr><td colspan="10" class="loading-cell"><span style="color:var(--red)">Failed to load data: ${escHtml(e.message)}</span></td></tr>`;
        return;
    }

    // Pre-compute sub-scores (these don't change with weights)
    state.raw.forEach(r => {
        r._cpu = round1(scoreCPU(r));
        r._gpu = round1(scoreGPU(r));
        r._ram = round1(scoreRAM(r));
        r._display = round1(scoreDisplay(r));
        r._storage = round1(scoreStorage(r));
        r.ram_gb = Math.round((r.ram_mb || 0) / 1024);
        r.price_m = r.price ? round1(r.price / 1e6) : 0;
    });

    // Extract brands
    const seriesSet = new Set();
    state.raw.forEach(r => {
        const s = r.laptop_series;
        if (s) seriesSet.add(s);
    });
    state.brands = [...seriesSet].sort();
    const brandSelect = $('#f-brand');
    state.brands.forEach(b => {
        const opt = document.createElement('option');
        opt.value = b;
        opt.textContent = b;
        brandSelect.appendChild(opt);
    });

    bindEvents();
    recalculate();
}

function round1(n) { return Math.round(n * 10) / 10; }

// ─── Recalculate dynamic scores ─────────────────────────────

function recalculate() {
    const w = state.weights;
    state.processed = state.raw.map(r => {
        const perf = round1(r._cpu * w.cpu + r._gpu * w.gpu + r._ram * w.ram + r._display * w.display + r._storage * w.storage);
        const ppr = r.price_m > 0 ? round1((perf / r.price_m) * 100) / 100 : null;
        return { ...r, perf_score: perf, ppr };
    });
    applyFilters();
}

// ─── Filtering ──────────────────────────────────────────────

function applyFilters() {
    const search = ($('#f-search').value || '').toLowerCase();
    const minRam = parseInt($('#f-ram').value) || 0;
    const minSsd = parseInt($('#f-ssd').value) || 0;
    const minPrice = parseFloat($('#f-price-min').value) || 0;
    const maxPrice = parseFloat($('#f-price-max').value) || Infinity;
    const gpuFilter = $('#f-gpu').value;
    const brandFilter = $('#f-brand').value;

    state.filtered = state.processed.filter(r => {
        if (search) {
            const hay = [r.title, r.model_code, r.cpu_model, r.gpu_model, r.laptop_series, r.slug].join(' ').toLowerCase();
            if (!hay.includes(search)) return false;
        }
        if (r.ram_gb < minRam) return false;
        if ((r.ssd_gb || 0) < minSsd) return false;
        if (r.price_m > 0 && r.price_m < minPrice) return false;
        if (r.price_m > 0 && r.price_m > maxPrice) return false;
        if (minPrice > 0 && r.price_m === 0) return false;
        if (gpuFilter && !(r.gpu_model || '').includes(gpuFilter)) return false;
        if (brandFilter && r.laptop_series !== brandFilter) return false;
        return true;
    });

    applySorting();
}

// ─── Sorting ────────────────────────────────────────────────

function applySorting() {
    const { key, dir } = state.sort;
    const mult = dir === 'asc' ? 1 : -1;
    state.filtered.sort((a, b) => {
        let va = a[key], vb = b[key];
        if (va == null) va = dir === 'asc' ? Infinity : -Infinity;
        if (vb == null) vb = dir === 'asc' ? Infinity : -Infinity;
        if (typeof va === 'string') return mult * va.localeCompare(vb);
        return mult * (va - vb);
    });
    state.page = 1;
    render();
}

// ─── Render ─────────────────────────────────────────────────

function render() {
    renderStats();
    renderTable();
    renderPagination();
    updateMethodology();
}

function renderStats() {
    dom.statTotal.textContent = state.processed.length;
    dom.statShowing.textContent = state.filtered.length;

    if (state.filtered.length > 0) {
        const scores = state.filtered.map(r => r.perf_score);
        dom.statAvgScore.textContent = round1(scores.reduce((a, b) => a + b, 0) / scores.length);

        const withPrice = state.filtered.filter(r => r.price_m > 0);
        if (withPrice.length > 0) {
            dom.statAvgPrice.textContent = round1(withPrice.reduce((a, r) => a + r.price_m, 0) / withPrice.length) + 'M';
            const best = withPrice.reduce((best, r) => (r.ppr || 0) > (best.ppr || 0) ? r : best, withPrice[0]);
            dom.statBestPP.textContent = best.ppr != null ? best.ppr.toFixed(3) : '—';
        } else {
            dom.statAvgPrice.textContent = '—';
            dom.statBestPP.textContent = '—';
        }
    } else {
        dom.statAvgScore.textContent = '—';
        dom.statAvgPrice.textContent = '—';
        dom.statBestPP.textContent = '—';
    }
}

function renderTable() {
    const start = (state.page - 1) * state.perPage;
    const end = Math.min(start + state.perPage, state.filtered.length);
    const slice = state.filtered.slice(start, end);

    if (slice.length === 0) {
        dom.tableBody.innerHTML = `<tr><td colspan="10" class="loading-cell"><span>No laptops match your filters.</span></td></tr>`;
        dom.pageInfo.textContent = '';
        return;
    }

    dom.pageInfo.textContent = `Showing ${start + 1}–${end} of ${state.filtered.length}`;

    let html = '';
    slice.forEach((r, i) => {
        const rank = start + i + 1;
        const tierClass = r.perf_score >= 70 ? 'tier-s' : r.perf_score >= 50 ? 'tier-a' : r.perf_score >= 30 ? 'tier-b' : 'tier-c';
        const pprClass = (r.ppr || 0) > 0.3 ? 'ppr-good' : (r.ppr || 0) > 0.15 ? 'ppr-mid' : 'ppr-bad';
        const pprText = r.ppr != null ? r.ppr.toFixed(3) : '—';
        const priceText = r.price_m > 0 ? r.price_m.toFixed(1) : '—';
        const name = escHtml(r.model_code || (r.title || '').substring(0, 50));
        const imgSrc = r.image_url || '';
        const thumbHtml = imgSrc
            ? `<img class="thumb-img" src="${escHtml(imgSrc)}" alt="" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'thumb-placeholder\\'>💻</div>'">`
            : `<div class="thumb-placeholder">💻</div>`;

        html += `<tr data-idx="${state.processed.indexOf(r)}">
      <td class="cell-rank">${rank}</td>
      <td class="cell-thumb">${thumbHtml}</td>
      <td class="cell-name"><a href="https://exo.ir/product/${escHtml(r.slug)}" target="_blank" rel="noopener">${name}</a></td>
      <td class="cell-cpu">${escHtml(r.cpu_model)}</td>
      <td class="cell-gpu">${escHtml(r.gpu_model)}</td>
      <td class="cell-num">${r.ram_gb}GB</td>
      <td class="cell-num">${r.ssd_gb || 0}GB</td>
      <td class="score-cell"><div class="score-bar-wrap"><div class="score-bar-track"><div class="score-bar-fill ${tierClass}" style="width:${r.perf_score}%"></div></div><span class="score-value">${r.perf_score}</span></div></td>
      <td class="cell-num cell-price">${priceText}</td>
      <td class="cell-num cell-ppr ${pprClass}">${pprText}</td>
    </tr>`;
    });
    dom.tableBody.innerHTML = html;
}

function renderPagination() {
    const total = Math.ceil(state.filtered.length / state.perPage);
    if (total <= 1) { dom.pagination.innerHTML = ''; return; }

    let html = `<button ${state.page <= 1 ? 'disabled' : ''} data-page="${state.page - 1}">&larr;</button>`;

    const pages = [];
    const range = 2;
    for (let i = 1; i <= total; i++) {
        if (i === 1 || i === total || (i >= state.page - range && i <= state.page + range)) {
            pages.push(i);
        } else if (pages[pages.length - 1] !== '...') {
            pages.push('...');
        }
    }

    pages.forEach(p => {
        if (p === '...') {
            html += `<span class="page-ellipsis">…</span>`;
        } else {
            html += `<button ${p === state.page ? 'class="active"' : ''} data-page="${p}">${p}</button>`;
        }
    });

    html += `<button ${state.page >= total ? 'disabled' : ''} data-page="${state.page + 1}">&rarr;</button>`;
    dom.pagination.innerHTML = html;
}

function updateMethodology() {
    const w = state.weights;
    $('#meth-cpu').textContent = Math.round(w.cpu * 100) + '%';
    $('#meth-gpu').textContent = Math.round(w.gpu * 100) + '%';
    $('#meth-ram').textContent = Math.round(w.ram * 100) + '%';
    $('#meth-display').textContent = Math.round(w.display * 100) + '%';
    $('#meth-storage').textContent = Math.round(w.storage * 100) + '%';
}

// ─── Detail Modal ───────────────────────────────────────────

function showDetail(idx) {
    const r = state.processed[idx];
    if (!r) return;

    const imgHtml = r.image_url
        ? `<img class="modal-img" src="${escHtml(r.image_url)}" alt="" onerror="this.style.display='none'">`
        : '';

    const specs = r.full_specs || {};
    let specsHtml = '';
    const specEntries = Object.entries(specs);
    if (specEntries.length > 0) {
        specsHtml = `<div class="modal-specs"><h3>Full Specifications</h3><div class="spec-grid">`;
        specEntries.forEach(([k, v]) => {
            specsHtml += `<div class="spec-row"><div class="spec-key">${escHtml(k)}</div><div class="spec-val">${escHtml(v)}</div></div>`;
        });
        specsHtml += `</div></div>`;
    }

    const priceText = r.price_m > 0 ? r.price_m.toFixed(1) + 'M Rials' : 'N/A';
    const pprText = r.ppr != null ? r.ppr.toFixed(3) : 'N/A';

    dom.modalContent.innerHTML = `
    ${imgHtml}
    <h2>${escHtml(r.title || r.model_code || r.slug)}</h2>
    <a class="modal-link" href="https://exo.ir/product/${escHtml(r.slug)}" target="_blank" rel="noopener">View on exo.ir →</a>
    <div class="modal-scores">
      <div class="modal-score-card"><div class="msc-label">CPU</div><div class="msc-value" style="color:var(--blue)">${r._cpu}</div></div>
      <div class="modal-score-card"><div class="msc-label">GPU</div><div class="msc-value" style="color:var(--purple)">${r._gpu}</div></div>
      <div class="modal-score-card"><div class="msc-label">RAM</div><div class="msc-value" style="color:var(--green)">${r._ram}</div></div>
      <div class="modal-score-card"><div class="msc-label">Display</div><div class="msc-value" style="color:var(--pink)">${r._display}</div></div>
      <div class="modal-score-card"><div class="msc-label">Storage</div><div class="msc-value" style="color:var(--gold)">${r._storage}</div></div>
      <div class="modal-score-card"><div class="msc-label">Overall</div><div class="msc-value" style="color:var(--accent)">${r.perf_score}</div></div>
      <div class="modal-score-card"><div class="msc-label">Price</div><div class="msc-value" style="color:var(--gold)">${priceText}</div></div>
      <div class="modal-score-card"><div class="msc-label">Value (P/P)</div><div class="msc-value" style="color:var(--green)">${pprText}</div></div>
    </div>
    ${specsHtml}
  `;

    dom.modalOverlay.classList.add('open');
}

function closeModal() { dom.modalOverlay.classList.remove('open'); }

// ─── Event Binding ──────────────────────────────────────────

function bindEvents() {
    // Weight sliders
    ['cpu', 'gpu', 'ram', 'display', 'storage'].forEach(id => {
        const slider = $(`#w-${id}`);
        slider.addEventListener('input', () => {
            state.weights[id] = parseInt(slider.value) / 100;
            $(`#val-${id}`).textContent = slider.value + '%';
            updateWeightSum();
            recalculate();
        });
    });

    $('#btn-reset-weights').addEventListener('click', () => {
        const defaults = { cpu: 30, gpu: 30, ram: 15, display: 15, storage: 10 };
        Object.entries(defaults).forEach(([id, val]) => {
            $(`#w-${id}`).value = val;
            $(`#val-${id}`).textContent = val + '%';
            state.weights[id] = val / 100;
        });
        updateWeightSum();
        recalculate();
    });

    // Filters
    let searchTimeout;
    $('#f-search').addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => applyFilters(), 200);
    });
    ['f-ram', 'f-ssd', 'f-price-min', 'f-price-max', 'f-gpu', 'f-brand'].forEach(id => {
        $(`#${id}`).addEventListener('change', () => applyFilters());
    });
    // Also listen for 'input' on price fields for live filtering
    ['f-price-min', 'f-price-max'].forEach(id => {
        $(`#${id}`).addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => applyFilters(), 300);
        });
    });

    $('#btn-clear-filters').addEventListener('click', () => {
        $('#f-search').value = '';
        $('#f-ram').value = '0';
        $('#f-ssd').value = '0';
        $('#f-price-min').value = '';
        $('#f-price-max').value = '';
        $('#f-gpu').value = '';
        $('#f-brand').value = '';
        applyFilters();
    });

    // Sorting
    $$('.data-table th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const key = th.dataset.key;
            if (state.sort.key === key) {
                state.sort.dir = state.sort.dir === 'desc' ? 'asc' : 'desc';
            } else {
                state.sort.key = key;
                state.sort.dir = 'desc';
            }
            // Update header classes
            $$('.data-table th.sortable').forEach(h => {
                h.classList.remove('active-sort', 'sort-asc', 'sort-desc');
            });
            th.classList.add('active-sort', state.sort.dir === 'asc' ? 'sort-asc' : 'sort-desc');
            applySorting();
        });
    });

    // Pagination
    dom.pagination.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-page]');
        if (!btn || btn.disabled) return;
        state.page = parseInt(btn.dataset.page);
        renderTable();
        renderPagination();
        // Scroll to table top
        document.querySelector('.table-wrapper').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });

    // Rows per page
    $('#rows-per-page').addEventListener('change', (e) => {
        state.perPage = parseInt(e.target.value);
        state.page = 1;
        renderTable();
        renderPagination();
    });

    // Table row click → modal
    dom.tableBody.addEventListener('click', (e) => {
        const link = e.target.closest('a');
        if (link) return; // don't open modal if clicking external link
        const row = e.target.closest('tr[data-idx]');
        if (row) showDetail(parseInt(row.dataset.idx));
    });

    // Modal close
    $('#modal-close').addEventListener('click', closeModal);
    dom.modalOverlay.addEventListener('click', (e) => {
        if (e.target === dom.modalOverlay) closeModal();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });

    // Sidebar toggle (mobile)
    $('#sidebar-toggle').addEventListener('click', () => {
        dom.sidebar.classList.toggle('open');
    });

    bindConfigEvents();
}

function updateWeightSum() {
    const sum = Math.round((state.weights.cpu + state.weights.gpu + state.weights.ram + state.weights.display + state.weights.storage) * 100);
    dom.weightSumVal.textContent = sum + '%';
    dom.weightSum.classList.toggle('invalid', sum !== 100);
}

// ─── Config UI Logic ────────────────────────────────────────

let activeConfigTab = 'cpu';

function bindConfigEvents() {
    $('#btn-config-tiers').addEventListener('click', openConfigModal);
    $('#config-close').addEventListener('click', closeConfigModal);
    $('#config-cancel').addEventListener('click', closeConfigModal);
    $('#config-save').addEventListener('click', saveConfig);
    $('#config-overlay').addEventListener('click', (e) => {
        if (e.target === $('#config-overlay')) closeConfigModal();
    });

    $$('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            $$('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeConfigTab = btn.dataset.tab;
            renderConfigList();
        });
    });

    $('#config-search').addEventListener('input', () => renderConfigList());
    $('#btn-reset-tiers').addEventListener('click', restoreDefaultTiers);
}

function closeConfigModal() {
    $('#config-overlay').classList.remove('open');
}

// We need a draft state for the config modal so we can cancel changes.
let draftTiers = null;

function openConfigModal() {
    // Deep copy current state.tiers
    draftTiers = JSON.parse(JSON.stringify(state.tiers));

    activeConfigTab = 'cpu';
    $$('.tab-btn').forEach(b => b.classList.remove('active'));
    $('.tab-btn[data-tab="cpu"]').classList.add('active');
    $('#config-search').value = '';
    renderConfigList();
    $('#config-overlay').classList.add('open');
}

function renderConfigList() {
    const container = $('#config-list');
    container.innerHTML = '';
    const filter = ($('#config-search').value || '').toLowerCase();

    let sourceData = {};
    if (activeConfigTab === 'cpu') sourceData = draftTiers.cpu;
    else if (activeConfigTab === 'gpu') sourceData = draftTiers.gpu;
    else if (activeConfigTab === 'panel') sourceData = draftTiers.panel;

    const entries = Object.entries(sourceData).sort((a, b) => {
        if (b[1] !== a[1]) return b[1] - a[1];
        return a[0].localeCompare(b[0]);
    });

    entries.forEach(([name, score]) => {
        if (filter && !name.toLowerCase().includes(filter)) return;

        const row = document.createElement('div');
        row.className = 'tier-item';
        row.innerHTML = `
            <span class="tier-name">${escHtml(name)}</span>
            <input type="number" class="tier-input" value="${score}" min="0" max="100" data-key="${escHtml(name)}">
        `;

        // Bind input event to update draftTiers
        const input = row.querySelector('input');
        input.addEventListener('input', (e) => {
            const val = parseInt(e.target.value) || 0;
            if (activeConfigTab === 'cpu') draftTiers.cpu[name] = val;
            else if (activeConfigTab === 'gpu') draftTiers.gpu[name] = val;
            else if (activeConfigTab === 'panel') draftTiers.panel[name] = val;
        });

        container.appendChild(row);
    });
}

function saveConfig() {
    state.tiers = JSON.parse(JSON.stringify(draftTiers));
    localStorage.setItem('exo_tiers', JSON.stringify(state.tiers));
    recalculate();
    closeConfigModal();
}

function restoreDefaultTiers() {
    if (!confirm('Are you sure you want to reset all scores to default?')) return;
    draftTiers = {
        cpu: { ...DEFAULT_CPU_TIERS },
        gpu: { ...DEFAULT_GPU_TIERS },
        panel: { ...DEFAULT_PANEL_SCORES }
    };
    renderConfigList();
}

// ─── Comparison Logic ───────────────────────────────────────

function toggleSelection(idx, checked) {
    if (checked) {
        if (state.selectedLaptops.size >= 3) {
            alert('You can compare max 3 laptops.');
            // Revert checkbox (UI update happens in render but event is fired)
            const cb = $(`tr[data-idx="${idx}"] .row-checkbox`);
            if (cb) cb.checked = false;
            return;
        }
        state.selectedLaptops.add(idx);
    } else {
        state.selectedLaptops.delete(idx);
    }

    // Highlight row
    const row = $(`tr[data-idx="${idx}"]`);
    if (row) {
        if (checked) row.classList.add('selected-row');
        else row.classList.remove('selected-row');
    }

    updateComparisonBar();
}

function clearSelection() {
    state.selectedLaptops.clear();
    // Uncheck all
    $$('.row-checkbox').forEach(cb => {
        cb.checked = false;
        cb.closest('tr').classList.remove('selected-row');
    });
    updateComparisonBar();
}

function updateComparisonBar() {
    const count = state.selectedLaptops.size;
    $('#compare-count').textContent = count;
    const bar = $('#compare-bar');
    if (count > 0) bar.classList.add('visible');
    else bar.classList.remove('visible');
}

function openComparisonModal() {
    if (state.selectedLaptops.size < 2) {
        alert('Please select at least 2 laptops to compare.');
        return;
    }

    const container = $('#compare-content');
    container.innerHTML = '';

    const laptops = Array.from(state.selectedLaptops).map(idx => state.processed[idx]);

    // Define rows to compare
    const rows = [
        { label: 'Overall Score', key: 'perf_score', highlight: true },
        { label: 'Price (M)', key: 'price_m', highlight: true },
        { label: 'Value (P/P)', key: 'ppr', highlight: true },
        { label: 'CPU Score', key: '_cpu' },
        { label: 'GPU Score', key: '_gpu' },

        { label: 'Core Specs', type: 'label' },
        { label: 'CPU Model', key: 'cpu_model' },
        { label: 'Cores', key: 'cpu_core_count' },
        { label: 'GPU Model', key: 'gpu_model' },
        { label: 'RAM', key: 'ram' },
        { label: 'Storage', key: 'ssd' },

        { label: 'Display & Build', type: 'label' },
        { label: 'Display Size', key: 'screen_size' },
        { label: 'Resolution', key: 'full_specs', sub: 'حداکثر وضوح تصویر' },
        { label: 'Refresh Rate', key: 'full_specs', sub: 'نرخ به روزرسانی تصویر' },
        { label: 'Weight', key: 'weight' },
    ];

    // Build grid
    const grid = document.createElement('div');
    grid.className = 'compare-grid';

    // Header Column (Labels)
    const labelCol = document.createElement('div');
    labelCol.className = 'compare-col';
    labelCol.style.minWidth = '140px';
    labelCol.style.flex = '0 0 140px';
    labelCol.style.background = 'var(--bg-2)';

    let labelHtml = `<div class="compare-header" style="display:flex;align-items:center;justify-content:center;font-weight:700;color:var(--text-2)">METRIC</div>`;
    rows.forEach(r => {
        if (r.type === 'label') {
            labelHtml += `<div class="compare-row label-row" style="justify-content:center">${escHtml(r.label)}</div>`;
        } else {
            labelHtml += `<div class="compare-row" style="color:var(--text-3);font-weight:600">${escHtml(r.label)}</div>`;
        }
    });
    labelCol.innerHTML = labelHtml;
    grid.appendChild(labelCol);

    // Laptop Columns
    laptops.forEach(lap => {
        const col = document.createElement('div');
        col.className = 'compare-col';

        // Header
        const imgHtml = lap.image_url ? `<img class="compare-thumb" src="${escHtml(lap.image_url)}">` : `<div class="compare-thumb" style="display:flex;align-items:center;justify-content:center;font-size:24px">💻</div>`;

        let colHtml = `
            <div class="compare-header">
                ${imgHtml}
                <div class="compare-title">${escHtml(lap.title || lap.model_code)}</div>
                <div style="margin-top:8px">
                    <a href="https://exo.ir/product/${escHtml(lap.slug)}" target="_blank" class="btn btn-sm btn-ghost" style="font-size:11px">View</a>
                </div>
            </div>
        `;

        rows.forEach(r => {
            if (r.type === 'label') {
                colHtml += `<div class="compare-row label-row">&nbsp;</div>`;
                return;
            }

            let val = '';
            if (r.sub && lap[r.key]) {
                val = lap[r.key][r.sub];
            } else {
                val = lap[r.key];
            }

            if (val === undefined || val === null) val = '—';

            const hlClass = r.highlight ? 'highlight' : '';
            colHtml += `
                <div class="compare-row" style="justify-content:center">
                    <span class="compare-val ${hlClass}" style="text-align:center">${escHtml(val)}</span>
                </div>
            `;
        });

        col.innerHTML = colHtml;
        grid.appendChild(col);
    });

    container.appendChild(grid);
    $('#compare-overlay').classList.add('open');
}

// ─── Boot ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', init);

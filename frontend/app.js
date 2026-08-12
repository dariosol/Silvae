const API_BASE = '';
//const API_BASE = 'https://height-parking-robots-enjoying.trycloudflare.com';
let state = {
    token: localStorage.getItem('token') || null,
    user:  JSON.parse(localStorage.getItem('user') || 'null'),
    allTrees: [], filteredTrees: [],
    currentPage: 1, pageSize: 25,
    activeTab: 'trees',
    sortField: null, sortDir: 'asc',
    nearbyMode: false, userLat: null, userLon: null, nearbyRadius: null,
    exportMode: false, exportSelected: new Set(),
    map: null, markers: [], markerLayer: null, mapTrees: [], userMarker: null, satelliteActive: false,
    areaSelectMode: false, areaVertices: [], areaDraft: null, areaMarkers: [], areaPoly: null, areaClosed: false, areaSelectedIds: [],
    gpkgColumns: null, gpkgExportIds: [],
    dropdowns: {}
};

function authHeader() {
    return state.token ? { 'Authorization': `Bearer ${state.token}` } : {};
}

function showTreeView(name) {
    document.querySelectorAll('#tab-trees .tab-view').forEach(v =>
        v.classList.toggle('active', v.id === 'view-' + name));
}

// ─── Dropdowns ───────────────────────────────────────────

async function fetchDropdowns() {
    const res = await fetch(`${API_BASE}/dropdowns`);
    if (!res.ok) return;
    state.dropdowns = await res.json();
    populateStaticDropdowns();
}

function populateSelect(id, items, valueFn, textFn) {
    const el = document.getElementById(id);
    if (!el) return;
    while (el.options.length > 1) el.remove(1); // keep first blank option
    items.forEach(item => {
        const o = document.createElement('option');
        o.value = valueFn(item);
        o.textContent = textFn(item);
        el.appendChild(o);
    });
}

function _isAltro(item) {
    return item === 'altro' || item === 'altro da specificare';
}

function populateMultiSelect(id, items) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = '';
    items.forEach(item => {
        const lbl = document.createElement('label');
        const cb  = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = item;
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(item));
        if (_isAltro(item)) {
            cb.dataset.altro = '1';
            const txt = document.createElement('input');
            txt.type = 'text';
            txt.placeholder = 'specificare…';
            txt.style.cssText = 'display:none;margin-left:6px;border:1px solid var(--border);border-radius:4px;padding:2px 6px;font-size:12px;flex:1;min-width:120px;';
            cb.addEventListener('change', () => {
                lbl.classList.toggle('chk-checked', cb.checked);
                txt.style.display = cb.checked ? 'inline-block' : 'none';
                if (cb.checked) txt.focus();
            });
            lbl.style.flexWrap = 'wrap';
            lbl.appendChild(txt);
        } else {
            cb.addEventListener('change', () => lbl.classList.toggle('chk-checked', cb.checked));
        }
        el.appendChild(lbl);
    });
}

function populateStaticDropdowns() {
    const d = state.dropdowns;
    if (!d || !Object.keys(d).length) return;

    // Species — datalist (consente anche valore libero)
    const dl = document.getElementById('species-datalist');
    if (dl) {
        dl.innerHTML = (d.species || [])
            .map(x => `<option value="${x.name}">${x.code} — ${x.name}</option>`)
            .join('');
    }

    // Dati generali
    ['dimora','stadio_sviluppo','posizione_sociale','localizzazione','vincoli'].forEach(k =>
        populateSelect(k, d[k] || [], x => x, x => x));

    // Pericolo selects (keys: 1-7, '0 x sospet', etc.)
    const pKeys = Object.keys(d.pericolo_ord || {});
    ['pericolo_rami','pericolo_tronco','pericolo_colletto','pericolo_zolla'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        while (el.options.length > 1) el.remove(1);
        pKeys.forEach(k => {
            const o = document.createElement('option');
            o.value = k;
            o.textContent = `${k} — ${(d.pericolo_ord[k] || '').substring(0, 60)}`;
            el.appendChild(o);
        });
    });

    // Bersaglio tipo dropdowns
    ['bersaglio_chioma_tipo', 'bersaglio_ramo_tipo'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        while (el.options.length > 1) el.remove(1);
        (d.bersaglio_tipi || []).forEach(t => {
            const o = document.createElement('option');
            o.value = t; o.textContent = t;
            el.appendChild(o);
        });
    });
    // Bersaglio class selects (1-7, used for pedoni/traffico types)
    ['bersaglio_chioma','bersaglio_ramo'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        while (el.options.length > 1) el.remove(1);
        for (let i = 1; i <= 7; i++) {
            const o = document.createElement('option');
            o.value = i; o.textContent = `${i}`;
            el.appendChild(o);
        }
    });

    // Condizione salute ecologica
    populateSelect('condizione_salute_ecologica', d.condizione_salute_ecologica || [], x => x, x => x);

    // Single-select lookups
    populateSelect('monitoraggio', d.monitoraggio || [], x => x, x => x);
    populateSelect('urgenza', d.urgenza || [], x => x, x => x);

    // Multi-select lookups
    populateMultiSelect('conflitti_list', d.conflitti || []);
    populateMultiSelect('agenti_carie', d.agenti_carie || []);
    populateMultiSelect('altri_patogeni', d.altri_patogeni || []);
    populateMultiSelect('prescrizioni_val', d.prescrizioni_val || []);
    populateMultiSelect('prescrizioni_mit', d.prescrizioni_mit || []);
    populateMultiSelect('prescrizioni_col', d.prescrizioni_col || []);
}

// ─── Diametro ↔ Circonferenza sync ───────────────────────

function syncDiamCirc(source) {
    const circ = document.getElementById('circonferenza_cm');
    const diam = document.getElementById('trunk_diameter_cm');
    if (source === 'circ') {
        const v = parseFloat(circ.value);
        diam.value = (v > 0) ? (v / Math.PI).toFixed(1) : '';
    } else {
        const v = parseFloat(diam.value);
        circ.value = (v > 0) ? (v * Math.PI).toFixed(1) : '';
    }
}

// ─── Valore ecologico live ────────────────────────────────

const _ECO_STADIO_ANNI = {
    'plantula': 10, 'giovane pianta': 20, 'albero giovane': 30,
    'albero adulto': 40, 'albero maturo': 60,
    'albero senescente': 80, 'albero veterano': 100,
};
const _ECO_CONDIZIONE_MAP = {
    'Condizioni vegetative e fitosanitarie ottimali. Albero integro': 0,
    'Condizioni vegetative e/o fitosanitarie ottimali. Albero lievemente alterato nella struttura': 5,
    'Condizioni vegetative e/o fitosanitarie buone o comunque non tali da condizionare la salute e la vigoria': 15,
    'Condizioni vegetative e/o fitosanitarie buone o comunque non tali da condizionare la salute e la vigoria. Albero strutturalmente alterato': 20,
    "Condizioni vegetative e/o fitosanitarie mediocri, che limitano l'efficienza funzionale. Salute e/o vigoria ridotte": 25,
    'Condizioni vegetative e/o fitosanitarie mediocri. Albero strutturalmente alterato': 30,
    "Condizioni vegetative e/o fitosanitarie scadenti, che ne condizionano la salute e l'aspettativa di vita": 40,
    'Condizioni vegetative e/o fitosanitarie scadenti. Albero molto alterato strutturalmente': 50,
    'Condizioni vegetative e/o fitosanitarie pessime': 60,
    'Condizioni vegetative e/o fitosanitarie pessime. Albero fortemente deperiente, strutturalmente molto alterato': 70,
    'Albero morto in piedi': 90,
};
const _ECO_POS_COL = {
    'oppressa': 2, 'dominata': 3, 'intermedia': 4, 'codominante': 5,
    'dominante margine': 6, 'dominante interna': 7, 'predominante': 8,
    'libera (p giovane)': 9, 'isolata': 10,
};
// deduction% → coefficients for pos_sociale col 2..10
const _ECO_COEFFS = {
     0: [0.80,0.85,0.90,0.92,0.96,0.94,0.98,1.00,1.00],
     5: [0.75,0.80,0.85,0.87,0.91,0.89,0.93,0.95,0.95],
    15: [0.65,0.70,0.75,0.77,0.81,0.79,0.83,0.85,0.85],
    20: [0.60,0.65,0.70,0.72,0.76,0.74,0.78,0.80,0.80],
    25: [0.55,0.60,0.65,0.67,0.71,0.69,0.73,0.75,0.75],
    30: [0.50,0.55,0.60,0.62,0.66,0.64,0.68,0.70,0.70],
    40: [0.40,0.45,0.50,0.52,0.56,0.54,0.58,0.60,0.60],
    50: [0.30,0.35,0.40,0.42,0.46,0.44,0.48,0.50,0.50],
    60: [0.20,0.25,0.30,0.32,0.36,0.34,0.38,0.40,0.40],
    70: [0.10,0.15,0.20,0.22,0.26,0.24,0.28,0.30,0.30],
    90: [0.00,0.00,0.00,0.02,0.06,0.04,0.08,0.10,0.10],
};

function calcEcoLive() {
    const diam_cm  = parseFloat(document.getElementById('trunk_diameter_cm')?.value);
    const h_m      = parseFloat(document.getElementById('tree_height_m')?.value);
    const stadio   = document.getElementById('stadio_sviluppo')?.value;
    const pos      = document.getElementById('posizione_sociale')?.value;
    const cond     = document.getElementById('condizione_salute_ecologica')?.value;

    const box = document.getElementById('eco_result');
    if (!box) return;

    const anni    = _ECO_STADIO_ANNI[stadio];
    const deduct  = _ECO_CONDIZIONE_MAP[cond];
    const pos_col = _ECO_POS_COL[pos];

    if (!diam_cm || diam_cm <= 0 || !h_m || h_m <= 0 ||
        anni == null || deduct == null || pos_col == null) {
        box.style.display = 'none';
        return;
    }

    const diam_m = diam_cm / 100;
    const bio    = Math.PI / 4 * diam_m * diam_m * h_m * 0.9 * 900;

    let co2, o2, ia;
    if (cond === 'Albero morto in piedi') {
        co2 = o2 = ia = 0;
    } else {
        const coeff = _ECO_COEFFS[deduct][pos_col - 2];
        co2 = (bio / anni) * coeff;
        o2  = co2 / 44.01 * 31.999 * 0.9;
        ia  = ((bio * 0.2) / anni) * coeff;
    }
    const val = bio * 0.55 + co2 * 1 + o2 * 5 + ia * 10;

    const r2 = x => Math.round(x * 100) / 100;
    document.getElementById('eco_bio').textContent = r2(bio) + ' kg';
    document.getElementById('eco_co2').textContent = r2(co2) + ' kg/a';
    document.getElementById('eco_o2').textContent  = r2(o2)  + ' kg/a';
    document.getElementById('eco_ia').textContent  = r2(ia)  + ' kg/a';
    document.getElementById('eco_val').textContent = '€ ' + r2(val);
    box.style.display = '';
}


// ─── Bersaglio tipo/value handling ───────────────────────

const BERSAGLIO_VALUE_TIPI = ['proprietà', 'occupazione'];

function onBersaglioTipoChange(side) {
    const d = state.dropdowns;
    const tipo = document.getElementById(`bersaglio_${side}_tipo`)?.value || '';
    const valueGrp = document.getElementById(`bersaglio_${side}_value_grp`);
    const classGrp = document.getElementById(`bersaglio_${side}_class_grp`);
    const flowGrp  = document.getElementById(`bersaglio_${side}_flow_grp`);
    const flowUnit = document.getElementById(`bersaglio_${side}_flow_unit`);
    const valueEl  = document.getElementById(`bersaglio_${side}_value`);
    if (!valueGrp || !classGrp || !flowGrp || !valueEl) return;

    while (valueEl.options.length > 1) valueEl.remove(1);

    const hide = (...els) => els.forEach(e => { if(e) e.style.display = 'none'; });
    const show = (...els) => els.forEach(e => { if(e) e.style.display = ''; });

    if (tipo === 'proprietà') {
        (d.bersaglio_proprieta_values || []).forEach(v => {
            const o = document.createElement('option');
            o.value = v; o.textContent = v;
            valueEl.appendChild(o);
        });
        show(valueGrp); hide(classGrp, flowGrp);
    } else if (tipo === 'occupazione') {
        (d.bersaglio_occupazione_values || []).forEach(v => {
            const o = document.createElement('option');
            o.value = v; o.textContent = v;
            valueEl.appendChild(o);
        });
        show(valueGrp); hide(classGrp, flowGrp);
    } else if (tipo === 'pedoni/ciclisti') {
        if (flowUnit) flowUnit.textContent = 'pedoni/ora';
        show(flowGrp); hide(valueGrp, classGrp);
    } else if (tipo.startsWith('traffico')) {
        if (flowUnit) flowUnit.textContent = 'auto/giorno';
        show(flowGrp); hide(valueGrp, classGrp);
    } else if (tipo) {
        show(classGrp); hide(valueGrp, flowGrp);
    } else {
        hide(valueGrp, classGrp, flowGrp);
    }
}

// ─── Diagnosi rows ────────────────────────────────────────

const DIAG_PARTS = ['zolla','colletto','fusto','castello','ramificazione','chioma'];

function addDiagRow(part, caratt = '', giudizio = '') {
    const d = state.dropdowns;
    const choices = d[`diag_${part}`] || [];
    const giuList = d.giudizio_severita || ['ps','s','ms'];

    const container = document.getElementById(`diag-rows-${part}`);
    if (!container) return;

    const row = document.createElement('div');
    row.className = 'diag-row';

    const selC = document.createElement('select');
    selC.className = 'fc';
    const blank = document.createElement('option');
    blank.value = ''; blank.textContent = '— carattere —';
    selC.appendChild(blank);
    choices.forEach(c => {
        const o = document.createElement('option');
        o.value = o.textContent = c;
        if (c === caratt) o.selected = true;
        selC.appendChild(o);
    });

    const selG = document.createElement('select');
    selG.className = 'fc sel-giu';
    const blankG = document.createElement('option');
    blankG.value = ''; blankG.textContent = '—';
    selG.appendChild(blankG);
    giuList.forEach(g => {
        const o = document.createElement('option');
        o.value = o.textContent = g;
        if (g === giudizio) o.selected = true;
        selG.appendChild(o);
    });

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-danger btn-sm btn-rm';
    btn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
    btn.onclick = () => row.remove();

    row.append(selC, selG, btn);
    container.appendChild(row);
}

function getDiagData(part) {
    const container = document.getElementById(`diag-rows-${part}`);
    if (!container) return [];
    return Array.from(container.querySelectorAll('.diag-row')).map(row => {
        const sels = row.querySelectorAll('select');
        return { caratt: sels[0].value, giudizio: sels[1].value };
    }).filter(x => x.caratt);
}

function clearDiagRows(part) {
    const container = document.getElementById(`diag-rows-${part}`);
    if (container) container.innerHTML = '';
}

function loadDiagRows(part, data) {
    clearDiagRows(part);
    (data || []).forEach(row => addDiagRow(part, row.caratt, row.giudizio));
}

// ─── Multi-select helpers ─────────────────────────────────

function getMultiSelect(id) {
    const el = document.getElementById(id);
    if (!el) return [];
    const result = [];
    el.querySelectorAll('input[type=checkbox]:checked').forEach(cb => {
        if (cb.dataset.altro) {
            const txt = cb.closest('label').querySelector('input[type=text]');
            const val = txt?.value.trim();
            if (val) result.push(val);
        } else {
            result.push(cb.value);
        }
    });
    return result;
}

function setMultiSelect(id, values) {
    const el = document.getElementById(id);
    if (!el) return;
    const vals = values || [];
    const standardVals = new Set(
        Array.from(el.querySelectorAll('input[type=checkbox]:not([data-altro])')).map(cb => cb.value)
    );
    const standardSet = new Set(vals.filter(v => standardVals.has(v)));
    const customVals  = vals.filter(v => v && !standardVals.has(v));
    let customIdx = 0;

    el.querySelectorAll('input[type=checkbox]').forEach(cb => {
        const lbl = cb.closest('label');
        if (cb.dataset.altro) {
            const txt = lbl.querySelector('input[type=text]');
            const val = customVals[customIdx] || '';
            cb.checked = !!val;
            lbl.classList.toggle('chk-checked', cb.checked);
            if (txt) {
                txt.value = val;
                txt.style.display = cb.checked ? 'inline-block' : 'none';
            }
            if (val) customIdx++;
        } else {
            cb.checked = standardSet.has(cb.value);
            lbl.classList.toggle('chk-checked', cb.checked);
        }
    });
}

// ─── Risk calculation ─────────────────────────────────────

async function calculateRisk() {
    const payload = buildRiskPayload();
    const res = await fetch(`${API_BASE}/calculate_risk`, {
        method: 'POST',
        headers: Object.assign({'Content-Type':'application/json'}, authHeader()),
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) { showStatus(data.message || 'Dati insufficienti per il calcolo', 'warning'); return; }
    renderRiskResults(data);
}

function buildRiskPayload() {
    const v = id => document.getElementById(id)?.value || null;
    return {
        tree_height_m: v('tree_height_m'), circonferenza_cm: v('circonferenza_cm'),
        crown_diameter_m: v('crown_diameter_m'),
        branch_diam_cm: v('branch_diam_cm'), branch_length_m: v('branch_length_m'),
        branch_height_m: v('branch_height_m'), target_height_m: v('target_height_m'),
        pericolo_rami: v('pericolo_rami'), pericolo_tronco: v('pericolo_tronco'),
        pericolo_colletto: v('pericolo_colletto'), pericolo_zolla: v('pericolo_zolla'),
        bersaglio_chioma_tipo:  v('bersaglio_chioma_tipo'),
        bersaglio_chioma_value: v('bersaglio_chioma_value'),
        bersaglio_chioma_flow:  v('bersaglio_chioma_flow') ? parseFloat(v('bersaglio_chioma_flow')) : null,
        bersaglio_chioma:       v('bersaglio_chioma'),
        bersaglio_ramo_tipo:    v('bersaglio_ramo_tipo'),
        bersaglio_ramo_value:   v('bersaglio_ramo_value'),
        bersaglio_ramo_flow:    v('bersaglio_ramo_flow') ? parseFloat(v('bersaglio_ramo_flow')) : null,
        bersaglio_ramo:         v('bersaglio_ramo'),
        moltiplicatore: v('moltiplicatore') ? parseInt(v('moltiplicatore')) : null,
        post_tree_height_m: v('post_tree_height_m'),
        post_circonferenza_cm: v('post_circonferenza_cm'),
        post_branch_diam_cm: v('post_branch_diam_cm'),
        post_branch_length_m: v('post_branch_length_m'),
        post_branch_height_m: v('post_branch_height_m'),
        post_target_height_m: v('post_target_height_m'),
    };
}

function renderRiskResults(data) {
    const box = document.getElementById('riskResults');
    if (!box) return;
    const labels = {rami:'Rami/Branche', tronco:'Tronco/Castello', colletto:'Colletto', zolla:'Zolla radicale'};

    // Colour map shared with rischioBadge
    const colour = desc => {
        if (!desc || desc === 'SOSPESO') return {fg:'#6b7280', bg:'#f3f4f6'};
        if (desc.includes('inaccettabile') || desc.includes('imposto a terzi'))
            return {fg:'#dc2626', bg:'#fef2f2'};
        if (desc.includes('per accordo') || desc.includes('ALARP'))
            return {fg:'#d97706', bg:'#fffbeb'};
        if (desc.includes('tollerabile'))
            return {fg:'#16a34a', bg:'#f0fdf4'};
        return {fg:'#2563eb', bg:'#eff6ff'};  // largamente accettabile
    };

    const html = ['attuale','residuo'].map(phase => {
        const d = data[phase];
        if (!d) return '';
        const title = phase === 'attuale' ? 'RISCHIO ATTUALE' : 'RISCHIO RESIDUO';

        // Summary: worst failure mode for this phase
        const entries = Object.entries(labels).map(([key,lbl]) => ({key, lbl, e: d[key]}));
        const worst = entries.slice().sort((a,b) =>
            rischioSeverity(b.e?.risk_description) - rischioSeverity(a.e?.risk_description))[0];
        const wc = colour(worst?.e?.risk_description);

        const rows = entries.map(({lbl, e}) => {
            if (!e) return '';
            const c = colour(e.risk_description);
            const ratio = e.risk_ratio === 'SOSPESO'
                ? `<span style="color:#6b7280;font-weight:600;">SOSPESO</span>`
                : `<span style="font-weight:700;font-size:15px;color:${c.fg};">${e.risk_ratio}</span>`;
            const bip = `<span style="font-size:10px;color:var(--text-muted);margin-left:4px;">B${e.bersaglio_class}·I${e.impulso_class}·P${e.pericolo_class}</span>`;
            const plusbers = (e.risk_ratio_plusbers && e.risk_ratio_plusbers !== e.risk_ratio_1bers)
                ? `<span style="font-size:10px;color:${c.fg};margin-left:4px;">(×n→${e.risk_ratio_plusbers})</span>` : '';
            return `<div class="risk-row" style="background:${c.bg};border-radius:4px;padding:5px 8px;margin-bottom:4px;border:none;">
                <span class="risk-label" style="font-size:12px;">${lbl}</span>
                <span style="display:flex;align-items:center;gap:2px;">${ratio}${plusbers}${bip}</span>
                <span style="font-size:11px;color:${c.fg};max-width:220px;text-align:right;">${e.risk_description}</span>
            </div>`;
        }).join('');

        return `<div class="risk-box" style="border-left:4px solid ${wc.fg};">
            <div style="font-weight:700;color:${wc.fg};margin-bottom:6px;font-size:13px;">${title}</div>
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px;">
              Impulso chioma: <strong>${d.crown_momentum_kgms}</strong> kg·m/s → cl.<strong>${d.crown_impulso_class}</strong>
              &nbsp;|&nbsp;
              Impulso ramo: <strong>${d.branch_momentum_kgms}</strong> kg·m/s → cl.<strong>${d.branch_impulso_class}</strong>
            </div>
            ${rows}
        </div>`;
    }).join('');
    box.innerHTML = html;
    box.style.display = 'block';
}

// ─── Auth UI ──────────────────────────────────────────────

async function init() {
    await Promise.all([populateCities(), fetchDropdowns()]);
    const resetToken = new URLSearchParams(window.location.search).get('token');
    if (resetToken) {
        document.getElementById('loginPage').style.display = 'flex';
        document.getElementById('appPage').style.display   = 'none';
        showLoginView('resetView');
        return;
    }
    setupAuthUI();
    if (state.token && state.user) fetchTrees();
    voiceInit();
}

function setupAuthUI() {
    const loginPage = document.getElementById('loginPage');
    const appPage   = document.getElementById('appPage');
    if (state.token && state.user) {
        loginPage.style.display = 'none';
        appPage.style.display   = 'flex';
        document.getElementById('loggedInUser').textContent =
            `${state.user.username}  (${state.user.role}${state.user.city ? ' · ' + state.user.city : ''})`;
        showRoleFeatures(state.user.role);
        populateUsers();
    } else {
        loginPage.style.display = 'flex';
        appPage.style.display   = 'none';
        showRoleFeatures(null);
    }
}

function showRoleFeatures(role) {
    const show = v => v ? 'block' : 'none';
    const isAdmin = role === 'superuser' || role === 'city';
    document.getElementById('userManagement').style.display = show(role === 'superuser');
    document.getElementById('agronomistManagement').style.display = show(role === 'city');
    document.getElementById('cityManagement').style.display = show(role === 'superuser');
    const tabManage = document.getElementById('tabManageBtn');
    if (tabManage) tabManage.style.display = show(isAdmin);
}

// ─── Login page view switching ────────────────────────────

function showLoginView(name) {
    ['loginView','registerView','forgotView','resetView'].forEach(id => {
        document.getElementById(id).style.display = id === name ? 'block' : 'none';
    });
}

// ─── Register ─────────────────────────────────────────────

async function register() {
    const username  = document.getElementById('regUsername').value.trim();
    const email     = document.getElementById('regEmail').value.trim();
    const password  = document.getElementById('regPassword').value;
    const password2 = document.getElementById('regPassword2').value;
    if (!username || !password) return showStatus('Nome utente e password obbligatori', 'warning');
    if (password !== password2)  return showStatus('Le password non coincidono', 'warning');
    const res  = await fetch(`${API_BASE}/register`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({username, email, password})
    });
    const data = await res.json();
    if (res.ok) {
        state.token = data.token; state.user = data.user;
        localStorage.setItem('token', state.token);
        localStorage.setItem('user', JSON.stringify(state.user));
        setupAuthUI(); fetchTrees();
        showStatus(`Benvenuto, ${data.user.username}! Account creato.`, 'success');
    } else {
        showStatus(data.message || 'Errore nella registrazione', 'danger');
    }
}

// ─── Forgot password ──────────────────────────────────────

async function forgotPassword() {
    const email = document.getElementById('forgotEmail').value.trim();
    if (!email) return showStatus('Inserisci la tua email', 'warning');
    const res  = await fetch(`${API_BASE}/forgot-password`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({email})
    });
    const data = await res.json();
    showStatus(data.message || 'Richiesta inviata', 'success');
}

// ─── Reset password (from email link) ─────────────────────

async function resetPassword() {
    const token = new URLSearchParams(window.location.search).get('token') || '';
    const pw1   = document.getElementById('resetPassword').value;
    const pw2   = document.getElementById('resetPassword2').value;
    if (!pw1) return showStatus('Inserisci la nuova password', 'warning');
    if (pw1 !== pw2) return showStatus('Le password non coincidono', 'warning');
    const res  = await fetch(`${API_BASE}/reset-password`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({token, password: pw1})
    });
    const data = await res.json();
    if (res.ok) {
        showStatus('Password aggiornata! Ora puoi accedere.', 'success');
        history.replaceState(null, '', window.location.pathname);
        showLoginView('loginView');
    } else {
        showStatus(data.message || 'Errore durante il reset', 'danger');
    }
}

// ─── Agronomer management (city role) ────────────────────

async function loadAgronomists() {
    const res = await fetch(`${API_BASE}/city/agronomers`, {headers: authHeader()});
    if (!res.ok) return;
    renderAgronomistList(await res.json());
}

function renderAgronomistList(agronomists) {
    const list = document.getElementById('agronomistList');
    if (!list) return;
    list.innerHTML = '';
    if (!agronomists.length) {
        list.innerHTML = '<p style="font-size:13px;color:var(--text-muted);padding:8px 0;">Nessun Agronomo collegato.</p>';
        return;
    }
    agronomists.forEach(a => {
        const div = document.createElement('div');
        div.className = 'user-item';
        div.innerHTML = `<i class="fa-regular fa-user"></i>
            <span>${a.username}</span>
            ${a.email ? `<span style="font-size:12px;color:var(--text-muted)">(${a.email})</span>` : ''}
            <button class="btn btn-danger btn-sm" style="margin-left:auto;"
                onclick="removeAgronomist(${a.membership_id})">
              <i class="fa-solid fa-xmark"></i>
            </button>`;
        list.appendChild(div);
    });
}

async function addAgronomist() {
    const username = document.getElementById('addAgronomistUsername').value.trim();
    if (!username) return showStatus('Inserisci il nome utente dell\'Agronomo', 'warning');
    const res  = await fetch(`${API_BASE}/city/agronomers`, {
        method: 'POST',
        headers: Object.assign({'Content-Type':'application/json'}, authHeader()),
        body: JSON.stringify({username})
    });
    const data = await res.json();
    if (res.ok) {
        showStatus(`${username} aggiunto al comune`, 'success');
        document.getElementById('addAgronomistUsername').value = '';
        await loadAgronomists();
        await fetchTrees();
    } else {
        showStatus(data.message || 'Errore', 'danger');
    }
}

async function removeAgronomist(membershipId) {
    if (!confirm('Rimuovere questo Agronomo dal comune?')) return;
    const res  = await fetch(`${API_BASE}/city/agronomers/${membershipId}`, {
        method: 'DELETE', headers: authHeader()
    });
    const data = await res.json();
    if (res.ok) { showStatus('Agronomo rimosso', 'success'); await loadAgronomists(); await fetchTrees(); }
    else showStatus(data.message || 'Errore', 'danger');
}

function switchTab(name) {
    state.activeTab = name;
    document.querySelectorAll('.tab-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('.tab-section').forEach(s =>
        s.classList.toggle('active', s.id === 'tab-' + name));
    if (name === 'manage' && state.user?.role === 'city') loadAgronomists();
    if (name === 'map') {
        if (!state.map) {
            state.map = L.map('map').setView([45.4642, 9.19], 12);
            const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19, attribution: '© OpenStreetMap'
            });
            const satelliteLayer = L.tileLayer(
                'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
                maxZoom: 19,
                attribution: 'Tiles © Esri — Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
            });
            osmLayer.addTo(state.map);
            L.control.layers(
                { 'Mappa stradale': osmLayer, 'Satellite': satelliteLayer },
                null,
                { position: 'topright', collapsed: false }
            ).addTo(state.map);
            state.map.on('baselayerchange', e => {
                state.satelliteActive = e.name === 'Satellite';
                _refreshMapMarkers();
            });
            const LocateControl = L.Control.extend({
                options: { position: 'topleft' },
                onAdd() {
                    const btn = L.DomUtil.create('button', 'leaflet-bar locate-ctrl-btn');
                    btn.innerHTML = '<i class="fa-solid fa-location-crosshairs"></i>';
                    btn.title = 'Mostra la mia posizione';
                    L.DomEvent.disableClickPropagation(btn);
                    L.DomEvent.on(btn, 'click', locateMe);
                    return btn;
                }
            });
            new LocateControl().addTo(state.map);

            // Selezione area rettangolare per l'export (stile Booking)
            setupAreaSelect();

            // Long-press on map → "Aggiungi albero qui?"
            let _lpTimer = null, _lpLatLng = null;
            const _LP_MS = 600;
            const _lpCancel = () => { if (_lpTimer) { clearTimeout(_lpTimer); _lpTimer = null; } };
            const _lpTrigger = latlng => {
                _lpCancel();
                L.popup({ closeOnClick: true, autoClose: true, className: 'lp-add-popup' })
                    .setLatLng(latlng)
                    .setContent(
                        `<div style="text-align:center;padding:2px 0">
                            <div style="font-size:13px;font-weight:600;margin-bottom:6px"><i class="fa-solid fa-seedling"></i> Aggiungi albero qui?</div>
                            <div style="font-size:11px;color:#777;margin-bottom:10px">${latlng.lat.toFixed(5)}, ${latlng.lng.toFixed(5)}</div>
                            <button id="_lp_yes" class="btn btn-primary btn-sm" style="margin-right:6px">Sì</button>
                            <button id="_lp_no" class="btn btn-sm" style="border:1px solid #ccc">No</button>
                        </div>`
                    )
                    .openOn(state.map);
                setTimeout(() => {
                    const yes = document.getElementById('_lp_yes');
                    const no  = document.getElementById('_lp_no');
                    if (yes) yes.onclick = () => {
                        state.map.closePopup();
                        resetForm();
                        switchTab('trees');
                        showTreeView('edit');
                        document.getElementById('latitude').value  = latlng.lat.toFixed(6);
                        document.getElementById('longitude').value = latlng.lng.toFixed(6);
                    };
                    if (no) no.onclick = () => state.map.closePopup();
                }, 30);
            };

            state.map.on('mousedown', e => {
                if (state.areaSelectMode) return;
                if (e.originalEvent.button !== 0) return;
                _lpLatLng = e.latlng;
                _lpTimer = setTimeout(() => _lpTrigger(_lpLatLng), _LP_MS);
            });
            state.map.on('mouseup mouseout drag zoomstart', _lpCancel);

            const _mapContainer = state.map.getContainer();
            _mapContainer.addEventListener('touchstart', e => {
                if (state.areaSelectMode) return;
                if (e.touches.length !== 1) return;
                const t = e.touches[0], rect = _mapContainer.getBoundingClientRect();
                _lpLatLng = state.map.containerPointToLatLng(
                    L.point(t.clientX - rect.left, t.clientY - rect.top)
                );
                _lpTimer = setTimeout(() => _lpTrigger(_lpLatLng), _LP_MS);
            }, { passive: true });
            _mapContainer.addEventListener('touchend',  _lpCancel, { passive: true });
            _mapContainer.addEventListener('touchmove', _lpCancel, { passive: true });

        } else { state.map.invalidateSize(); }
        showOnMap(state.allTrees);
    }
}

async function login() {
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    if (!username || !password) return showStatus('Inserisci nome utente e password', 'warning');
    const res  = await fetch(`${API_BASE}/login`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({username, password})
    });
    const data = await res.json();
    if (res.ok) {
        state.token = data.token; state.user = data.user;
        localStorage.setItem('token', state.token);
        localStorage.setItem('user', JSON.stringify(state.user));
        setupAuthUI(); fetchTrees();
        if (data.user.role === 'city') loadAgronomists();
        showStatus(`Benvenuto, ${data.user.username}`, 'success');
    } else {
        showStatus(data.message || 'Accesso fallito', 'danger');
        document.getElementById('loginPassword').value = '';
    }
}

function logout() {
    state.token = null; state.user = null;
    localStorage.removeItem('token'); localStorage.removeItem('user');
    state.allTrees = []; state.filteredTrees = [];
    document.getElementById('treeList').innerHTML = '';
    document.getElementById('treeCount').textContent = '0';
    setupAuthUI();
}

// ─── Comune autocomplete ──────────────────────────────────

function initComuneAutocomplete(inputId) {
    const input    = document.getElementById(inputId);
    const dropdown = document.getElementById(inputId + '-dropdown');
    if (!input || !dropdown) return;

    let timer;
    input.addEventListener('input', () => {
        clearTimeout(timer);
        const q = input.value.trim();
        if (q.length < 2) { dropdown.style.display = 'none'; return; }
        timer = setTimeout(async () => {
            const res = await fetch(`${API_BASE}/comuni/search?q=${encodeURIComponent(q)}`);
            if (!res.ok) return;
            renderComuneDropdown(input, dropdown, await res.json());
        }, 250);
    });

    document.addEventListener('click', e => {
        if (!input.contains(e.target) && !dropdown.contains(e.target))
            dropdown.style.display = 'none';
    });

    input.addEventListener('keydown', e => {
        const items = dropdown.querySelectorAll('li');
        const active = dropdown.querySelector('li.ac-active');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            const next = active ? active.nextElementSibling : items[0];
            if (active) active.classList.remove('ac-active');
            if (next) next.classList.add('ac-active');
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            const prev = active ? active.previousElementSibling : items[items.length - 1];
            if (active) active.classList.remove('ac-active');
            if (prev) prev.classList.add('ac-active');
        } else if (e.key === 'Enter' && active) {
            e.preventDefault();
            input.value = active.dataset.value;
            dropdown.style.display = 'none';
        } else if (e.key === 'Escape') {
            dropdown.style.display = 'none';
        }
    });
}

function renderComuneDropdown(input, dropdown, results) {
    dropdown.innerHTML = '';
    if (!results.length) { dropdown.style.display = 'none'; return; }
    results.forEach(c => {
        const li = document.createElement('li');
        li.dataset.value = c.nome;
        li.innerHTML = `${c.nome}<span class="cd-sigla">${c.sigla} — ${c.regione}</span>`;
        li.addEventListener('mousedown', e => {
            e.preventDefault();
            input.value = c.nome;
            dropdown.style.display = 'none';
        });
        dropdown.appendChild(li);
    });
    dropdown.style.display = 'block';
}

// ─── City ─────────────────────────────────────────────────

async function populateCities() {
    const sel = document.getElementById('citySelect');
    sel.innerHTML = '<option value="">Tutti i comuni</option>';
    const res = await fetch(`${API_BASE}/cities`);
    if (!res.ok) return;
    const cities = await res.json();
    cities.forEach(c => {
        const o = document.createElement('option');
        o.value = o.text = c; sel.appendChild(o);
    });
}

async function createCity() {
    const name = document.getElementById('cityName').value.trim();
    if (!name) return showStatus('Nome comune obbligatorio', 'warning');
    const res  = await fetch(`${API_BASE}/admin/cities`, {
        method: 'POST',
        headers: Object.assign({'Content-Type':'application/json'}, authHeader()),
        body: JSON.stringify({name})
    });
    const data = await res.json();
    if (res.ok) { showStatus('Comune creato: ' + name, 'success'); document.getElementById('cityName').value = ''; await populateCities(); }
    else showStatus(data.message || 'Errore', 'danger');
}

// ─── Users ────────────────────────────────────────────────

async function createUser() {
    const username = document.getElementById('newUsername').value.trim();
    const password = document.getElementById('newPassword').value;
    const role     = document.getElementById('newRole').value;
    const city     = document.getElementById('newCity').value.trim() || null;
    const res  = await fetch(`${API_BASE}/add_user`, {
        method: 'POST',
        headers: Object.assign({'Content-Type':'application/json'}, authHeader()),
        body: JSON.stringify({username, password, role, city})
    });
    const data = await res.json();
    if (res.ok) { showStatus('Utente creato: ' + username, 'success'); document.getElementById('newUsername').value = ''; document.getElementById('newPassword').value = ''; await populateUsers(); }
    else showStatus(data.message || 'Errore nella creazione utente', 'danger');
}

async function populateUsers() {
    const res = await fetch(`${API_BASE}/users`, {headers: authHeader()});
    if (!res.ok) return;
    const users = await res.json();
    const list  = document.getElementById('userList');
    if (!list) return;
    list.innerHTML = '';
    users.forEach(u => {
        const div = document.createElement('div');
        div.className = 'user-item';
        div.innerHTML = `<i class="fa-regular fa-user"></i><span>${u.username}</span>
            ${u.city ? `<span style="font-size:12px;color:var(--text-muted)">(${u.city})</span>` : ''}
            <span class="role-pill rp-${u.role}">${u.role}</span>`;
        list.appendChild(div);
    });
}

// ─── Trees: fetch ─────────────────────────────────────────

async function fetchTrees() {
    if (!state.token) return;
    const city   = document.getElementById('citySelect').value;
    const params = new URLSearchParams();
    if (city) params.append('city', city);
    document.getElementById('inventoryLabel').textContent = city ? `Alberi — ${city}` : 'Inventario Alberi';
    const res = await fetch(`${API_BASE}/trees?${params}`, {headers: authHeader()});
    if (!res.ok) { const d = await res.json().catch(()=>({})); showStatus(d.message||'Errore nel caricamento alberi','danger'); return; }
    state.allTrees    = await res.json();
    state.currentPage = 1;
    document.getElementById('idFilter').value = '';
    applyIdFilter();
    if (state.activeTab === 'map') { resetMapAddressFilter(); showOnMap(state.allTrees); }
}

// ─── Trees: sort ─────────────────────────────────────────

const COND_ORDER = {buono:0,eccellente:0,ottimo:0,discreto:1,mediocre:1,scarso:2,critico:2,morto:3,abbattuto:3};
function condSortVal(cond) {
    if (!cond) return 99;
    const c = cond.toLowerCase();
    for (const [key, val] of Object.entries(COND_ORDER)) { if (c.includes(key)) return val; }
    return 99;
}

function sortTrees(trees, field, dir) {
    return [...trees].sort((a, b) => {
        let va, vb;
        if (field === 'condition') { va = condSortVal(a.condition); vb = condSortVal(b.condition); }
        else if (field === 'latitude') { va = parseFloat(a.latitude)||0; vb = parseFloat(b.latitude)||0; }
        else if (field === 'next_check') { va = a.next_check||''; vb = b.next_check||''; }
        else { va = (a[field]||'').toLowerCase(); vb = (b[field]||'').toLowerCase(); }
        if (va < vb) return dir==='asc' ? -1 : 1;
        if (va > vb) return dir==='asc' ?  1 : -1;
        return 0;
    });
}

function applySort(field) {
    state.sortDir = state.sortField === field ? (state.sortDir==='asc'?'desc':'asc') : 'asc';
    state.sortField = field; state.currentPage = 1; renderPage();
}

function updateSortHeaders() {
    document.querySelectorAll('th.sortable').forEach(th => {
        const f = th.dataset.sort, ico = th.querySelector('.sort-ico');
        if (!ico) return;
        if (f === state.sortField) {
            ico.className = `sort-ico fa-solid fa-sort-${state.sortDir==='asc'?'up':'down'}`;
            th.classList.add('sort-active');
        } else { ico.className = 'sort-ico fa-solid fa-sort'; th.classList.remove('sort-active'); }
    });
}

// ─── Nearby sort ─────────────────────────────────────────

function haversine(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const φ1 = lat1 * Math.PI/180, φ2 = lat2 * Math.PI/180;
    const Δφ = (lat2-lat1) * Math.PI/180, Δλ = (lon2-lon1) * Math.PI/180;
    const a = Math.sin(Δφ/2)**2 + Math.cos(φ1)*Math.cos(φ2)*Math.sin(Δλ/2)**2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

function fmtDist(m) {
    return m < 1000 ? `${Math.round(m)} m` : `${(m/1000).toFixed(1)} km`;
}

function toggleNearby() {
    const btn = document.getElementById('nearbyBtn');
    if (state.nearbyMode) {
        state.nearbyMode = false; state.userLat = null; state.userLon = null; state.nearbyRadius = null;
        btn.classList.remove('btn-primary'); btn.classList.add('btn-outline');
        renderPage(); return;
    }
    if (!navigator.geolocation) { showStatus('Geolocalizzazione non supportata da questo browser', 'warning'); return; }
    navigator.geolocation.getCurrentPosition(pos => {
        state.userLat = pos.coords.latitude; state.userLon = pos.coords.longitude;
        state.nearbyMode = true; state.currentPage = 1;
        btn.classList.remove('btn-outline'); btn.classList.add('btn-primary');
        renderPage();
    }, () => showStatus('Impossibile ottenere la posizione attuale', 'danger'));
}

// ─── Filter + pagination ──────────────────────────────────

function applyIdFilter() {
    const q  = document.getElementById('idFilter').value.trim().toLowerCase();
    const qa = document.getElementById('listAddrInput')?.value.trim().toLowerCase() || '';
    let trees = state.allTrees;
    if (q)  trees = trees.filter(t => t.custom_id.toLowerCase().includes(q));
    if (qa) trees = trees.filter(t => (t.address || '').toLowerCase().includes(qa));
    state.filteredTrees = trees;
    state.currentPage = 1; renderPage();
}

function changePageSize() { state.pageSize = parseInt(document.getElementById('pageSizeSelect').value); state.currentPage = 1; renderPage(); }
function goToPage(page) { state.currentPage = page; renderPage(); }

function renderPage() {
    let trees = state.filteredTrees;
    if (state.nearbyMode && state.userLat !== null) {
        if (state.nearbyRadius !== null) {
            trees = trees.filter(t => t.latitude && t.longitude &&
                haversine(state.userLat, state.userLon, parseFloat(t.latitude), parseFloat(t.longitude)) <= state.nearbyRadius);
        }
        trees = [...trees].sort((a, b) => {
            const da = (a.latitude && a.longitude) ? haversine(state.userLat, state.userLon, parseFloat(a.latitude), parseFloat(a.longitude)) : Infinity;
            const db = (b.latitude && b.longitude) ? haversine(state.userLat, state.userLon, parseFloat(b.latitude), parseFloat(b.longitude)) : Infinity;
            return da - db;
        });
    } else if (state.sortField) {
        trees = sortTrees(trees, state.sortField, state.sortDir);
    }
    const {currentPage, pageSize} = state;
    const start = (currentPage - 1) * pageSize;
    const pageSlice = trees.slice(start, start + pageSize);
    renderTreeList(pageSlice);
    renderTreeCards(pageSlice);
    renderPagination(); updateSortHeaders();
    const total = state.allTrees.length, filtered = state.filteredTrees.length;
    document.getElementById('treeCount').textContent = filtered < total ? `${filtered} / ${total}` : total;
    if (state.exportMode) {
        const sel = state.exportSelected.size;
        document.getElementById('exportCount').textContent = `${sel} alber${sel !== 1 ? 'i' : 'o'} selezionat${sel !== 1 ? 'i' : 'o'}`;
        const allCb = document.getElementById('selectAllCb');
        if (allCb) {
            const tot = state.filteredTrees.length, selAll = state.filteredTrees.filter(t => state.exportSelected.has(t.id)).length;
            allCb.checked = tot > 0 && selAll === tot; allCb.indeterminate = selAll > 0 && selAll < tot;
        }
    }
}

function renderPagination() {
    const total = state.filteredTrees.length, totalPages = Math.ceil(total / state.pageSize);
    const cur = state.currentPage, start = (cur-1)*state.pageSize+1, end = Math.min(cur*state.pageSize, total);
    const bar = document.getElementById('paginationBar');
    bar.style.display = total > 0 ? 'flex' : 'none';
    document.getElementById('pagingInfo').textContent =
        total === 0 ? '' : `Visualizzando ${start}–${end} di ${total} alber${total!==1?'i':'o'}`;
    const pag = document.getElementById('pagination'); pag.innerHTML = '';
    if (totalPages <= 1) return;
    const mkBtn = (label, page, active=false, disabled=false) => {
        const b = document.createElement('button');
        b.className = `btn btn-sm ${active?'btn-primary':'btn-outline'}`;
        b.innerHTML = label; b.style.minWidth = '34px';
        if (disabled) { b.disabled = true; b.style.opacity = '.38'; }
        else b.addEventListener('click', () => goToPage(page));
        return b;
    };
    const mkDots = () => { const s = document.createElement('span'); s.textContent = '…'; s.style.cssText = 'padding:0 4px;color:var(--text-muted);font-size:13px;'; return s; };
    pag.appendChild(mkBtn('‹', cur-1, false, cur===1));
    let pages;
    if (totalPages<=7) { pages = Array.from({length:totalPages},(_,i)=>i+1); }
    else {
        pages=[1]; if(cur>3) pages.push('…');
        for(let p=Math.max(2,cur-1);p<=Math.min(totalPages-1,cur+1);p++) pages.push(p);
        if(cur<totalPages-2) pages.push('…'); pages.push(totalPages);
    }
    pages.forEach(p => pag.appendChild(p==='…' ? mkDots() : mkBtn(p, p, p===cur)));
    pag.appendChild(mkBtn('›', cur+1, false, cur===totalPages));
}

// ─── Tree list render ─────────────────────────────────────

// Categoria di colore della condizione. Le classi CPC/VTA (A/B/C/C/D/D) hanno
// priorità: quando c'è il CPC, la condizione è la lettera della classe.
//   A  / ottimo, eccellente                      → good   (verde)
//   B  / buono                                    → buono  (verdino)
//   C  / discreto, mediocre                       → fair   (arancione)
//   C/D, D / scarso, critico, morto, abbattuto    → poor   (rosso)
function condCategory(cond) {
    if (!cond) return 'other';
    const c = String(cond).trim().toLowerCase();
    // Classi CPC / VTA (la lettera vince)
    if (c === 'a') return 'good';
    if (c === 'b') return 'buono';
    if (c === 'c') return 'fair';
    if (c === 'd' || c === 'c/d') return 'poor';
    // Sinonimi testuali (IT/EN)
    if (c.includes('ottimo')||c.includes('eccellente')||c.includes('excel')||c.includes('good')) return 'good';
    if (c.includes('buono')) return 'buono';
    if (c.includes('discreto')||c.includes('mediocre')||c.includes('fair')||c.includes('moder')) return 'fair';
    if (c.includes('scarso')||c.includes('critico')||c.includes('morto')||c.includes('abbattuto')
        ||c.includes('poor')||c.includes('crit')||c.includes('dead')) return 'poor';
    return 'other';
}

const COND_BADGE_ICON = {
    good:'fa-circle-check', buono:'fa-circle-check', fair:'fa-circle-exclamation',
    poor:'fa-circle-xmark', other:'fa-circle',
};

function condClass(cond) { return 'tr-' + condCategory(cond); }

function condBadge(cond) {
    if (!cond) return `<span class="cond-badge cb-other">—</span>`;
    const cat = condCategory(cond);
    return `<span class="cond-badge cb-${cat}"><i class="fa-solid ${COND_BADGE_ICON[cat]}"></i> ${cond}</span>`;
}

function condDot(cond) {
    return `<span class="cond-dot dot-${condCategory(cond)}" title="${cond || '—'}"></span>`;
}

function renderTreeCards(trees) {
    const container = document.getElementById('treeCardList');
    container.innerHTML = '';
    if (trees.length === 0) {
        container.innerHTML = `<div class="empty-state"><i class="fa-solid fa-tree"></i><p>Nessun albero trovato.</p></div>`;
        return;
    }
    trees.forEach(t => {
        const addr = [t.address, t.city].filter(Boolean).join(' — ');
        const coords = (t.latitude && t.longitude)
            ? `${parseFloat(t.latitude).toFixed(4)}, ${parseFloat(t.longitude).toFixed(4)}`
            : '—';
        const distLine = (state.nearbyMode && state.userLat !== null && t.latitude && t.longitude)
            ? `<div><i class="fa-solid fa-location-dot"></i> ${fmtDist(haversine(state.userLat, state.userLon, parseFloat(t.latitude), parseFloat(t.longitude)))}</div>`
            : '';
        const div = document.createElement('div');
        div.className = `tree-card ${condClass(t.condition)}`;
        div.innerHTML = `
            <div class="tree-card-main" onclick="toggleCardDetail(this)">
                <div class="tree-card-actions">
                    <button class="btn btn-edit btn-sm" onclick="event.stopPropagation();openHistory(${t.id},'${t.custom_id}')" title="Storico"><i class="fa-solid fa-clock-rotate-left"></i></button>
                    <button class="btn btn-edit btn-sm" onclick="event.stopPropagation();openEditForm(${t.id})" title="Modifica"><i class="fa-solid fa-pen-to-square"></i></button>
                </div>
                <div class="tree-card-info">
                    ${condDot(t.condition)}
                    <span class="id-chip">${t.custom_id}</span>
                    <span class="species">${t.species}</span>
                </div>
                <i class="fa-solid fa-chevron-down tree-card-chevron"></i>
            </div>
            <div class="tree-card-detail" hidden>
                <div class="tree-card-detail-grid">
                    <div><i class="fa-solid fa-location-dot"></i> ${addr || '—'}</div>
                    <div><i class="fa-solid fa-map-pin"></i> ${coords}</div>
                    <div><i class="fa-solid fa-calendar-days"></i> ${t.next_check || '—'}</div>
                    ${distLine}
                </div>
                <button class="btn btn-danger btn-sm" onclick="deleteTreeById(${t.id})">
                    <i class="fa-solid fa-trash"></i> Elimina
                </button>
            </div>`;
        container.appendChild(div);
    });
}

function toggleCardDetail(mainEl) {
    const detail = mainEl.nextElementSibling;
    const chevron = mainEl.querySelector('.tree-card-chevron');
    if (detail.hasAttribute('hidden')) {
        detail.removeAttribute('hidden');
        chevron.style.transform = 'rotate(180deg)';
    } else {
        detail.setAttribute('hidden', '');
        chevron.style.transform = '';
    }
}

function mobileSort(field) {
    state.sortField = field; state.sortDir = 'asc'; state.currentPage = 1; renderPage();
}

function changeMobilePageSize(val) {
    state.pageSize = parseInt(val);
    const desktop = document.getElementById('pageSizeSelect');
    if (desktop) desktop.value = val;
    state.currentPage = 1; renderPage();
}

function toggleMobileSortDir() {
    state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    const btn = document.getElementById('mobileSortDirBtn');
    if (btn) btn.querySelector('i').className = state.sortDir === 'asc'
        ? 'fa-solid fa-arrow-up-short-wide' : 'fa-solid fa-arrow-down-wide-short';
    renderPage();
}

function renderTreeList(trees) {
    const tbody = document.getElementById('treeList'); tbody.innerHTML = '';
    if (trees.length === 0) {
        const q = document.getElementById('idFilter').value.trim();
        tbody.innerHTML = `<tr><td colspan="${state.exportMode ? 8 : 7}"><div class="empty-state"><i class="fa-solid fa-tree"></i>
            <p>${q ? `Nessun albero corrisponde all'ID "<strong>${q}</strong>".` : 'Nessun albero trovato. Seleziona un comune in alto, poi usa <strong>Aggiungi Albero</strong> per aggiungere il primo.'}</p>
        </div></td></tr>`;
        return;
    }
    trees.forEach(t => {
        const tr = document.createElement('tr');
        tr.className = `tree-row ${condClass(t.condition)}`;
        const addr = [t.address, t.city].filter(Boolean).join(' — ');
        const coords = (t.latitude && t.longitude)
            ? `<span class="coords-chip">${parseFloat(t.latitude).toFixed(4)},&thinsp;${parseFloat(t.longitude).toFixed(4)}</span>`
            : '<span style="color:var(--text-muted)">—</span>';
        const distBadge = (state.nearbyMode && state.userLat !== null && t.latitude && t.longitude)
            ? `<br><span style="font-size:11px;color:var(--g600);"><i class="fa-solid fa-location-dot"></i> ${fmtDist(haversine(state.userLat, state.userLon, parseFloat(t.latitude), parseFloat(t.longitude)))}</span>`
            : '';
        tr.innerHTML = `
            ${state.exportMode ? `<td style="text-align:center;"><input type="checkbox" ${state.exportSelected.has(t.id) ? 'checked' : ''} onchange="toggleTreeSelect(${t.id}, this.checked)"></td>` : ''}
            <td><span class="id-chip">${t.custom_id}</span></td>
            <td><span class="species">${t.species}</span></td>
            <td>${condBadge(t.condition)}</td>
            <td><span class="addr" title="${addr}">${addr||'—'}</span>${distBadge}</td>
            <td>${coords}</td>
            <td style="font-size:13px;color:var(--text-mid)">${t.next_check||'—'}</td>
            <td><div class="act-cell">
                <button class="btn btn-edit btn-sm" onclick="openHistory(${t.id},'${t.custom_id}')" title="Storico"><i class="fa-solid fa-clock-rotate-left"></i></button>
                <button class="btn btn-edit btn-sm" onclick="openEditForm(${t.id})" title="Modifica"><i class="fa-solid fa-pen-to-square"></i></button>
                <button class="btn btn-danger btn-sm" onclick="deleteTreeById(${t.id})" title="Elimina"><i class="fa-solid fa-trash"></i></button>
            </div></td>`;
        tbody.appendChild(tr);
    });
}

// ─── Tree CRUD ────────────────────────────────────────────

async function fetchTreeById(id) {
    const res  = await fetch(`${API_BASE}/tree/${id}`, {headers: authHeader()});
    const data = await res.json();
    if (!res.ok) { showStatus(data.message||'Albero non trovato','danger'); return null; }
    return data;
}

function fillForm(data) {
    document.getElementById('formTitle').innerHTML =
        `<i class="fa-solid fa-pen-to-square"></i> Modifica — ${data.custom_id}`;
    document.getElementById('editTreeId').value = data.id;

    // Simple fields
    const sv = (id, v) => { const el = document.getElementById(id); if (el) el.value = v || ''; };
    sv('custom_id', data.custom_id); sv('city', data.city); sv('cpc', data.cpc);
    sv('address', data.address); sv('latitude', data.latitude); sv('longitude', data.longitude);
    sv('species', data.species); sv('condition', data.condition);
    sv('comments', data.comments); sv('actions', data.actions);
    sv('height', data.height); sv('trunk_diameter_cm', data.trunk_diameter_cm);
    sv('crown_diameter_m', data.crown_diameter_m); sv('age', data.age);
    sv('location', data.location); sv('next_check', data.next_check);
    // ARETE dati generali
    sv('dimora', data.dimora); sv('stadio_sviluppo', data.stadio_sviluppo);
    sv('posizione_sociale', data.posizione_sociale); sv('localizzazione', data.localizzazione);
    sv('vincoli', data.vincoli);
    // Misure ORD
    sv('tree_height_m', data.tree_height_m); sv('circonferenza_cm', data.circonferenza_cm);
    sv('branch_diam_cm', data.branch_diam_cm); sv('branch_length_m', data.branch_length_m);
    sv('branch_height_m', data.branch_height_m); sv('target_height_m', data.target_height_m);
    // Post-intervention
    sv('post_tree_height_m', data.post_tree_height_m);
    sv('post_circonferenza_cm', data.post_circonferenza_cm);
    sv('post_branch_diam_cm', data.post_branch_diam_cm);
    sv('post_branch_length_m', data.post_branch_length_m);
    sv('post_branch_height_m', data.post_branch_height_m);
    sv('post_target_height_m', data.post_target_height_m);
    // Pericolo / Bersaglio
    sv('pericolo_rami', data.pericolo_rami); sv('pericolo_tronco', data.pericolo_tronco);
    sv('pericolo_colletto', data.pericolo_colletto); sv('pericolo_zolla', data.pericolo_zolla);
    // Bersaglio: set tipo first (triggers visibility), then value/flow/class
    sv('bersaglio_chioma_tipo', data.bersaglio_chioma_tipo);
    onBersaglioTipoChange('chioma');
    sv('bersaglio_chioma_value', data.bersaglio_chioma_value);
    sv('bersaglio_chioma_flow',  data.bersaglio_chioma_flow);
    sv('bersaglio_chioma', data.bersaglio_chioma);
    sv('bersaglio_ramo_tipo', data.bersaglio_ramo_tipo);
    onBersaglioTipoChange('ramo');
    sv('bersaglio_ramo_value', data.bersaglio_ramo_value);
    sv('bersaglio_ramo_flow',  data.bersaglio_ramo_flow);
    sv('bersaglio_ramo', data.bersaglio_ramo);
    sv('moltiplicatore', data.moltiplicatore);
    // Diagnosi rows
    DIAG_PARTS.forEach(p => loadDiagRows(p, data[`diag_${p}`]));
    // Multi-selects
    setMultiSelect('conflitti_list', data.conflitti_list);
    setMultiSelect('agenti_carie', data.agenti_carie);
    setMultiSelect('altri_patogeni', data.altri_patogeni);
    setMultiSelect('prescrizioni_val', data.prescrizioni_val);
    setMultiSelect('prescrizioni_mit', data.prescrizioni_mit);
    setMultiSelect('prescrizioni_col', data.prescrizioni_col);
    // Single selects
    sv('monitoraggio', data.monitoraggio); sv('urgenza', data.urgenza);
    // Valore ecologico
    sv('condizione_salute_ecologica', data.condizione_salute_ecologica);
    calcEcoLive();

    document.getElementById('riskResults').style.display = 'none';
    document.getElementById('formSubmitButton').innerHTML =
        '<i class="fa-solid fa-floppy-disk"></i> Salva modifiche';
    syncCpcToCondition();
}

function syncCpcToCondition() {
    const cpcEl  = document.getElementById('cpc');
    const condEl = document.getElementById('condition');
    if (!cpcEl || !condEl) return;
    if (cpcEl.value.trim()) {
        condEl.value    = cpcEl.value.trim();
        condEl.readOnly = true;
        condEl.style.background = 'var(--bg-alt, #f5f5f5)';
        condEl.style.color      = 'var(--text-muted, #888)';
    } else {
        condEl.readOnly = false;
        condEl.style.background = '';
        condEl.style.color      = '';
    }
}

async function openEditForm(id) {
    const tree = await fetchTreeById(id);
    if (!tree) return;
    fillForm(tree);
    switchTab('trees'); showTreeView('edit');
}

async function deleteTreeById(id) {
    if (!confirm('Eliminare questo albero dal database?')) return;
    const res  = await fetch(`${API_BASE}/tree/${id}`, {method:'DELETE', headers: authHeader()});
    const data = await res.json();
    if (res.ok) {
        state.allTrees      = state.allTrees.filter(t => t.id !== id);
        state.filteredTrees = state.filteredTrees.filter(t => t.id !== id);
        showStatus('Albero eliminato', 'success'); renderPage();
        if (state.activeTab === 'map') showOnMap(state.allTrees);
    } else showStatus(data.message||'Errore durante l\'eliminazione','danger');
}

async function submitTreeForm(e) {
    e.preventDefault();
    const editId  = document.getElementById('editTreeId').value;
    const v = id => document.getElementById(id)?.value || null;

    const payload = {
        custom_id: v('custom_id'), city: v('city'), address: v('address'),
        latitude: v('latitude'), longitude: v('longitude'),
        species: v('species'), condition: v('condition') || '—',
        comments: v('comments'), actions: v('actions'),
        height: v('height'), trunk_diameter_cm: v('trunk_diameter_cm') || null,
        crown_diameter_m: v('crown_diameter_m') || null,
        age: v('age'), location: v('location'), cpc: v('cpc'),
        next_check: v('next_check') || null,
        // ARETE
        dimora: v('dimora'), stadio_sviluppo: v('stadio_sviluppo'),
        posizione_sociale: v('posizione_sociale'), localizzazione: v('localizzazione'),
        vincoli: v('vincoli'),
        tree_height_m: v('tree_height_m') || null,
        circonferenza_cm: v('circonferenza_cm') || null,
        branch_diam_cm: v('branch_diam_cm') || null,
        branch_length_m: v('branch_length_m') || null,
        branch_height_m: v('branch_height_m') || null,
        target_height_m: v('target_height_m') || null,
        post_tree_height_m: v('post_tree_height_m') || null,
        post_circonferenza_cm: v('post_circonferenza_cm') || null,
        post_branch_diam_cm: v('post_branch_diam_cm') || null,
        post_branch_length_m: v('post_branch_length_m') || null,
        post_branch_height_m: v('post_branch_height_m') || null,
        post_target_height_m: v('post_target_height_m') || null,
        pericolo_rami: v('pericolo_rami'), pericolo_tronco: v('pericolo_tronco'),
        pericolo_colletto: v('pericolo_colletto'), pericolo_zolla: v('pericolo_zolla'),
        bersaglio_chioma_tipo:  v('bersaglio_chioma_tipo') || null,
        bersaglio_chioma_value: v('bersaglio_chioma_value') || null,
        bersaglio_chioma_flow:  v('bersaglio_chioma_flow') ? parseFloat(v('bersaglio_chioma_flow')) : null,
        bersaglio_chioma:       v('bersaglio_chioma') ? parseInt(v('bersaglio_chioma')) : null,
        bersaglio_ramo_tipo:    v('bersaglio_ramo_tipo') || null,
        bersaglio_ramo_value:   v('bersaglio_ramo_value') || null,
        bersaglio_ramo_flow:    v('bersaglio_ramo_flow') ? parseFloat(v('bersaglio_ramo_flow')) : null,
        bersaglio_ramo:         v('bersaglio_ramo') ? parseInt(v('bersaglio_ramo')) : null,
        moltiplicatore:         v('moltiplicatore') ? parseInt(v('moltiplicatore')) : null,
        // Diagnosi
        diag_zolla: getDiagData('zolla'),
        diag_colletto: getDiagData('colletto'),
        diag_fusto: getDiagData('fusto'),
        diag_castello: getDiagData('castello'),
        diag_ramificazione: getDiagData('ramificazione'),
        diag_chioma: getDiagData('chioma'),
        // Multi-selects
        conflitti_list: getMultiSelect('conflitti_list'),
        agenti_carie: getMultiSelect('agenti_carie'),
        altri_patogeni: getMultiSelect('altri_patogeni'),
        prescrizioni_val: getMultiSelect('prescrizioni_val'),
        prescrizioni_mit: getMultiSelect('prescrizioni_mit'),
        prescrizioni_col: getMultiSelect('prescrizioni_col'),
        monitoraggio: v('monitoraggio'), urgenza: v('urgenza'),
        condizione_salute_ecologica: v('condizione_salute_ecologica') || null,
    };

    const url    = editId ? `${API_BASE}/tree/${editId}` : `${API_BASE}/add_tree`;
    const method = editId ? 'PATCH' : 'POST';

    const res  = await fetch(url, {
        method,
        headers: Object.assign({'Content-Type':'application/json'}, authHeader()),
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
        showStatus(editId ? 'Albero aggiornato' : 'Albero aggiunto', 'success');
        await fetchTrees(); resetForm(); showTreeView('list');
    } else showStatus(data.message || JSON.stringify(data), 'danger');
}

function resetForm() {
    document.getElementById('addTreeForm').reset();
    document.getElementById('editTreeId').value = '';
    document.getElementById('formTitle').innerHTML = '<i class="fa-solid fa-seedling"></i> Nuovo Albero';
    document.getElementById('formSubmitButton').innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Salva albero';
    document.getElementById('gpsStatus').textContent = '';
    const rr = document.getElementById('riskResults');
    if (rr) { rr.innerHTML = ''; rr.style.display = 'none'; }
    const condEl = document.getElementById('condition');
    if (condEl) { condEl.readOnly = false; condEl.style.background = ''; condEl.style.color = ''; }
    DIAG_PARTS.forEach(p => clearDiagRows(p));
    // Reset multi-selects (deselect all)
    ['conflitti_list','agenti_carie','altri_patogeni','prescrizioni_val','prescrizioni_mit','prescrizioni_col'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.querySelectorAll('input[type=checkbox]').forEach(cb => {
            cb.checked = false;
            cb.closest('label').classList.remove('chk-checked');
            if (cb.dataset.altro) {
                const txt = cb.closest('label').querySelector('input[type=text]');
                if (txt) { txt.value = ''; txt.style.display = 'none'; }
            }
        });
    });
}

// ─── Coord check map ──────────────────────────────────────

let _ccMap = null, _ccPin = null, _ccTreeLayer = null;

function openCoordCheck() {
    const lat = parseFloat(document.getElementById('latitude').value);
    const lon = parseFloat(document.getElementById('longitude').value);
    if (isNaN(lat) || isNaN(lon)) { showStatus('Inserisci prima le coordinate', 'warning'); return; }

    document.getElementById('coordCheckModal').classList.add('open');

    if (!_ccMap) {
        _ccMap = L.map('coordCheckMap', { zoomControl: true }).setView([lat, lon], 19);
        L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            { maxZoom: 20, attribution: '© Esri' }
        ).addTo(_ccMap);
        _ccTreeLayer = L.layerGroup().addTo(_ccMap);
    } else {
        _ccMap.setView([lat, lon], 19);
    }

    // Nearby trees as small coloured circles, no interaction
    _ccTreeLayer.clearLayers();
    (state.allTrees || []).forEach(t => {
        if (!t.latitude || !t.longitude) return;
        const color = COND_COLOR[condClass(t.condition)] || COND_COLOR['tr-other'];
        L.circleMarker([parseFloat(t.latitude), parseFloat(t.longitude)], {
            radius: 5, fillColor: color, fillOpacity: 0.85,
            color: '#fff', weight: 1.5, interactive: false
        }).addTo(_ccTreeLayer);
    });

    // Draggable pin
    if (_ccPin) _ccMap.removeLayer(_ccPin);
    const pinIcon = L.divIcon({
        className: '',
        html: `<div style="width:24px;height:24px;border-radius:50%;background:rgba(255,255,255,.92);border:3px solid #e74c3c;box-shadow:0 2px 8px rgba(0,0,0,.45);cursor:grab;display:flex;align-items:center;justify-content:center;"><div style="width:7px;height:7px;border-radius:50%;background:#e74c3c;"></div></div>`,
        iconSize: [24, 24], iconAnchor: [12, 12]
    });
    _ccPin = L.marker([lat, lon], { icon: pinIcon, draggable: true, zIndexOffset: 1000 }).addTo(_ccMap);
    _ccPin.on('drag dragend', _ccUpdateInfo);
    _ccUpdateInfo();

    setTimeout(() => _ccMap.invalidateSize(), 60);
}

function _ccUpdateInfo() {
    if (!_ccPin) return;
    const p = _ccPin.getLatLng();
    document.getElementById('coordCheckInfo').textContent = `${p.lat.toFixed(6)},  ${p.lng.toFixed(6)}`;
}

function confirmCoordCheck() {
    if (!_ccPin) return;
    const p = _ccPin.getLatLng();
    document.getElementById('latitude').value  = p.lat.toFixed(6);
    document.getElementById('longitude').value = p.lng.toFixed(6);
    closeCoordCheck();
    showStatus('Coordinate aggiornate', 'success');
}

function closeCoordCheck() {
    document.getElementById('coordCheckModal').classList.remove('open');
}

// ─── GPS ──────────────────────────────────────────────────

function getLocation() {
    if (!navigator.geolocation) return showStatus('Geolocalizzazione non supportata', 'danger');
    document.getElementById('gpsStatus').textContent = 'Acquisizione segnale GPS…';
    navigator.geolocation.getCurrentPosition(async pos => {
        const lat = pos.coords.latitude, lon = pos.coords.longitude;
        document.getElementById('latitude').value  = lat;
        document.getElementById('longitude').value = lon;
        document.getElementById('gpsStatus').textContent = 'Ricerca indirizzo…';
        if (state.token) {
            const res = await fetch(`${API_BASE}/reverse_geocode`, {
                method: 'POST',
                headers: Object.assign({'Content-Type':'application/json'}, authHeader()),
                body: JSON.stringify({latitude: lat, longitude: lon})
            });
            if (res.ok) {
                const geo = await res.json();
                if (geo.address) document.getElementById('address').value = geo.address;
                if (geo.city && !document.getElementById('city').value)
                    document.getElementById('city').value = geo.city;
            }
        }
        document.getElementById('gpsStatus').textContent = `GPS: ${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    }, err => {
        document.getElementById('gpsStatus').textContent = '';
        showStatus('Errore GPS: ' + err.message, 'danger');
    });
}

// ─── Map ──────────────────────────────────────────────────

function locateMe() {
    if (!navigator.geolocation) { showStatus('Geolocalizzazione non supportata', 'danger'); return; }
    navigator.geolocation.getCurrentPosition(pos => {
        const { latitude: lat, longitude: lon } = pos.coords;
        if (state.userMarker) state.map.removeLayer(state.userMarker);
        const icon = L.divIcon({
            className: '',
            html: `<div class="user-dot"><div class="user-dot-pulse"></div></div>`,
            iconSize: [20, 20], iconAnchor: [10, 10]
        });
        state.userMarker = L.marker([lat, lon], {icon, zIndexOffset: 1000})
            .bindPopup('<strong>Sei qui</strong>')
            .addTo(state.map);
        state.map.setView([lat, lon], 16);
    }, () => showStatus('Impossibile ottenere la posizione', 'danger'));
}

function encodeHTML(s) { return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function _mapAddrPairs() {
    const seen = new Set();
    const pairs = [];
    for (const t of state.allTrees) {
        if (!t.address) continue;
        const key = `${t.address}||${t.city||''}`;
        if (!seen.has(key)) { seen.add(key); pairs.push({address: t.address, city: t.city||''}); }
    }
    return pairs.sort((a, b) => a.address.localeCompare(b.address));
}

function _mapAddrLabel(pair) {
    return pair.city ? `${pair.address} — ${pair.city}` : pair.address;
}

let _mapAddrKbd = -1;

function _mapAddrShowSuggestions(matches) {
    const ul = document.getElementById('mapAddrSuggestions');
    const q  = document.getElementById('mapAddressInput').value.trim().toLowerCase();
    _mapAddrKbd = -1;
    if (!matches.length) { ul.innerHTML = ''; ul.classList.remove('open'); return; }
    ul.innerHTML = matches.map(p => {
        const label = _mapAddrLabel(p);
        const i = label.toLowerCase().indexOf(q);
        const hi = i >= 0
            ? encodeHTML(label.slice(0,i)) + '<strong>' + encodeHTML(label.slice(i, i+q.length)) + '</strong>' + encodeHTML(label.slice(i+q.length))
            : encodeHTML(label);
        return `<li data-address="${encodeHTML(p.address)}" data-city="${encodeHTML(p.city)}">${hi}</li>`;
    }).join('');
    ul.classList.add('open');
}

function _mapAddrSelectFromInput() {
    const q = document.getElementById('mapAddressInput').value.trim().toLowerCase();
    if (!q) { resetMapAddressFilter(); return; }
    const exact = _mapAddrPairs().find(p => _mapAddrLabel(p).toLowerCase() === q);
    if (exact) { _mapAddrCommit(exact.address, exact.city); return; }
    const words = q.split(/\s+/).filter(Boolean);
    const trees = state.allTrees.filter(t => {
        const label = `${t.address || ''} ${t.city || ''}`.toLowerCase();
        return words.every(w => label.includes(w));
    });
    document.getElementById('mapAddrSuggestions').classList.remove('open');
    document.getElementById('mapAddrClearBtn').style.display = '';
    _mapAddrKbd = -1;
    showOnMap(trees.length ? trees : []);
}

function _mapAddrCommit(address, city) {
    const pair = {address, city};
    document.getElementById('mapAddressInput').value = _mapAddrLabel(pair);
    document.getElementById('mapAddrSuggestions').classList.remove('open');
    document.getElementById('mapAddrClearBtn').style.display = '';
    _mapAddrKbd = -1;
    const trees = state.allTrees.filter(t => t.address === address && (t.city||'') === city);
    showOnMap(trees);
}

function resetMapAddressFilter() {
    document.getElementById('mapAddressInput').value = '';
    document.getElementById('mapAddrSuggestions').classList.remove('open');
    document.getElementById('mapAddrClearBtn').style.display = 'none';
    _mapAddrKbd = -1;
    showOnMap(state.allTrees);
}

function initMapAddressAutocomplete() {
    const inp = document.getElementById('mapAddressInput');
    const ul  = document.getElementById('mapAddrSuggestions');

    inp.addEventListener('input', () => {
        const q = inp.value.trim().toLowerCase();
        document.getElementById('mapAddrClearBtn').style.display = inp.value ? '' : 'none';
        if (!q) { ul.innerHTML = ''; ul.classList.remove('open'); showOnMap(state.allTrees); return; }
        const matches = _mapAddrPairs().filter(p => _mapAddrLabel(p).toLowerCase().includes(q));
        _mapAddrShowSuggestions(matches);
    });

    inp.addEventListener('keydown', e => {
        const items = ul.querySelectorAll('li');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            items[_mapAddrKbd]?.classList.remove('kbd-active');
            _mapAddrKbd = Math.min(_mapAddrKbd + 1, items.length - 1);
            items[_mapAddrKbd]?.classList.add('kbd-active');
            items[_mapAddrKbd]?.scrollIntoView({block:'nearest'});
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            items[_mapAddrKbd]?.classList.remove('kbd-active');
            _mapAddrKbd = Math.max(_mapAddrKbd - 1, 0);
            items[_mapAddrKbd]?.classList.add('kbd-active');
            items[_mapAddrKbd]?.scrollIntoView({block:'nearest'});
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (_mapAddrKbd >= 0 && items[_mapAddrKbd]) {
                const li = items[_mapAddrKbd];
                _mapAddrCommit(li.dataset.address, li.dataset.city);
            } else { _mapAddrSelectFromInput(); }
        } else if (e.key === 'Escape') {
            ul.classList.remove('open');
        }
    });

    inp.addEventListener('blur', () => setTimeout(() => ul.classList.remove('open'), 150));

    ul.addEventListener('click', e => {
        const li = e.target.closest('li');
        if (li) _mapAddrCommit(li.dataset.address, li.dataset.city);
    });
}

const COND_COLOR = {
    'tr-good':  '#2d6a4f',
    'tr-buono': '#52b788',
    'tr-fair':  '#e67e22',
    'tr-poor':  '#c0392b',
    'tr-other': '#888888',
};

function treeMarkerIcon() {
    return L.divIcon({
        className: '',
        html: `<div style="background:var(--g800);color:#fff;border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,.3)"><i class="fa-solid fa-tree"></i></div>`,
        iconSize: [30, 30], iconAnchor: [15, 15]
    });
}

// Grid-based spatial decimation: one tree per cell, cell halves every zoom step.
// At zoom >= 18 show everything (viewport is small enough, trees are dense enough).
function _decimateTrees(trees, zoom) {
    if (zoom >= 18) return trees.filter(t => t.latitude && t.longitude);
    const cell = 0.0001 * Math.pow(2, 19 - zoom);
    const seen = new Map();
    const out  = [];
    for (const t of trees) {
        if (!t.latitude || !t.longitude) continue;
        const key = `${Math.floor(parseFloat(t.latitude) / cell)},${Math.floor(parseFloat(t.longitude) / cell)}`;
        if (!seen.has(key)) { seen.set(key, true); out.push(t); }
    }
    return out;
}

function _refreshMapMarkers() {
    if (!state.map || !state.markerLayer) return;
    state.markerLayer.clearLayers();
    state.markers = [];

    const zoom   = state.map.getZoom();
    const bounds = state.map.getBounds().pad(0.2);
    const inView = (state.mapTrees || []).filter(t =>
        t.latitude && t.longitude &&
        bounds.contains([parseFloat(t.latitude), parseFloat(t.longitude)])
    );

    _decimateTrees(inView, zoom).forEach(t => {
        const lat = parseFloat(t.latitude), lon = parseFloat(t.longitude);
        const popup = `<strong>${t.custom_id}</strong><br><em>${t.species}</em><br>${condBadge(t.condition)}<br><span style="font-size:12px;color:#555">${t.address||t.city||''}</span><br><br><button class="btn btn-sm btn-primary" onclick="openEditForm(${t.id})"><i class="fa-solid fa-pen-to-square"></i> Modifica</button>`;
        let m;
        if (state.satelliteActive) {
            const color = COND_COLOR[condClass(t.condition)] || COND_COLOR['tr-other'];
            m = L.circleMarker([lat, lon], { radius: 5, fillColor: color, fillOpacity: 0.85, color: '#fff', weight: 1.5 });
        } else {
            m = L.marker([lat, lon], { icon: treeMarkerIcon(t) });
        }
        m.bindPopup(popup);
        // Da zoom 19 in su mostra il custom ID accanto al pallino
        if (zoom >= 19 && t.custom_id) {
            m.bindTooltip(String(t.custom_id), {
                permanent: true,
                direction: 'right',
                offset: [8, 0],
                className: 'tree-id-label'
            });
        }
        m.treeId = t.id;
        state.markers.push(m);
        state.markerLayer.addLayer(m);
    });
}

function showOnMap(trees) {
    if (!state.map) return;
    state.mapTrees = trees;

    if (!state.markerLayer) {
        state.markerLayer = L.layerGroup().addTo(state.map);
        state.map.on('zoomend moveend', _refreshMapMarkers);
    }

    _refreshMapMarkers();

    const pts = trees.filter(t => t.latitude && t.longitude);
    if (pts.length > 0) {
        const lats = pts.map(t => parseFloat(t.latitude));
        const lons = pts.map(t => parseFloat(t.longitude));
        state.map.fitBounds(
            L.latLngBounds([Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]).pad(0.12)
        );
    }
}

// ─── Inspection history ───────────────────────────────────

function openHistory(treeId, customId) {
    document.getElementById('inspTreeId').value    = treeId;
    document.getElementById('inspDate').value      = new Date().toISOString().split('T')[0];
    document.getElementById('inspCondition').value = '';
    document.getElementById('inspComments').value  = '';
    document.getElementById('inspActions').value   = '';
    document.getElementById('historyTitle').innerHTML =
        `<i class="fa-solid fa-clock-rotate-left"></i> ${customId} — Storico`;
    document.getElementById('timelineContent').innerHTML =
        `<div class="tl-empty"><i class="fa-solid fa-spinner fa-spin"></i><p>Caricamento…</p></div>`;
    switchTab('trees'); showTreeView('history'); loadHistory(treeId);
}

async function loadHistory(treeId) {
    const res = await fetch(`${API_BASE}/tree/${treeId}/inspections`, {headers: authHeader()});
    if (!res.ok) {
        document.getElementById('timelineContent').innerHTML =
            `<div class="tl-empty"><i class="fa-solid fa-circle-exclamation"></i><p>Impossibile caricare lo storico.</p></div>`;
        return;
    }
    renderTimeline(await res.json());
}

function formatDate(str) {
    if (!str) return '—';
    return new Date(str + 'T12:00:00').toLocaleDateString('en-GB', {day:'numeric', month:'short', year:'numeric'});
}

function tlDotClass(cond) { return 'tl-dot-' + condCategory(cond); }

function rischioBadge(rischio) {
    if (!rischio) return '';
    const phases = ['attuale','residuo'];
    const parts = [];
    for (const phase of phases) {
        const d = rischio[phase];
        if (!d) continue;
        // pick the worst risk among rami/tronco/colletto/zolla
        const keys = ['rami','tronco','colletto','zolla'];
        const descs = keys.map(k => d[k]?.risk_description).filter(Boolean);
        if (!descs.length) continue;
        const worst = descs.sort((a,b) => rischioSeverity(b) - rischioSeverity(a))[0];
        const cls = rischioClass(worst);
        parts.push(`<span class="tl-risk-badge ${cls}" title="${phase === 'attuale' ? 'Rischio attuale' : 'Rischio residuo'}">`+
            `<i class="fa-solid fa-triangle-exclamation"></i> ${phase === 'attuale' ? 'att.' : 'res.'} ${worst}</span>`);
    }
    return parts.join('');
}

function rischioSeverity(desc) {
    if (!desc) return 0;
    if (desc.includes('inaccettabile')) return 5;
    if (desc.includes('imposto a terzi')) return 4;
    if (desc.includes('per accordo')) return 3;
    if (desc.includes('ALARP')) return 2;
    if (desc.includes('tollerabile')) return 1;
    return 0;
}

function rischioClass(desc) {
    if (!desc) return 'risk-unknown';
    if (desc.includes('inaccettabile')) return 'risk-high';
    if (desc.includes('imposto a terzi')) return 'risk-high';
    if (desc.includes('per accordo') || desc.includes('ALARP')) return 'risk-medium';
    if (desc.includes('tollerabile')) return 'risk-low';
    return 'risk-unknown';
}

function renderCardSummary(snap) {
    if (!snap) return '';
    const dim = [
        snap.tree_height_m      ? `H ${snap.tree_height_m} m`           : null,
        snap.circonferenza_cm   ? `Circ. ${snap.circonferenza_cm} cm`    : null,
        snap.crown_diameter_m   ? `Øchioma ${snap.crown_diameter_m} m`   : null,
        snap.branch_diam_cm     ? `Øramo ${snap.branch_diam_cm} cm`      : null,
        snap.branch_length_m    ? `Lramo ${snap.branch_length_m} m`      : null,
        snap.branch_height_m    ? `Hramo ${snap.branch_height_m} m`      : null,
        snap.target_height_m    ? `Hbers. ${snap.target_height_m} m`     : null,
    ].filter(Boolean);
    const per = [
        snap.pericolo_rami      != null ? `P.rami ${snap.pericolo_rami}`         : null,
        snap.pericolo_tronco    != null ? `P.tronco ${snap.pericolo_tronco}`     : null,
        snap.pericolo_colletto  != null ? `P.colletto ${snap.pericolo_colletto}` : null,
        snap.pericolo_zolla     != null ? `P.zolla ${snap.pericolo_zolla}`       : null,
    ].filter(Boolean);
    const idLine = snap.custom_id ? `<div class="tl-summary-id"><i class="fa-solid fa-tag"></i> ${snap.custom_id}</div>` : '';
    const dimLine = dim.length ? `<div class="tl-summary-row">${dim.map(d=>`<span class="tl-chip">${d}</span>`).join('')}</div>` : '';
    const perLine = per.length ? `<div class="tl-summary-row">${per.map(p=>`<span class="tl-chip tl-chip-p">${p}</span>`).join('')}</div>` : '';
    if (!idLine && !dimLine && !perLine) return '';
    return `<div class="tl-card-summary">${idLine}${dimLine}${perLine}</div>`;
}

function renderSnapshotDetails(snap) {
    if (!snap) return '<em style="color:var(--text-muted);font-size:12px;">Nessun dato disponibile</em>';
    const rows = [];
    const add = (label, val) => { if (val !== null && val !== undefined && val !== '') rows.push(`<div class="tl-snap-row"><span class="tl-snap-label">${label}</span><span class="tl-snap-val">${val}</span></div>`); };
    add('Specie', snap.species);
    add('Altezza', snap.height);
    add('Ø tronco', snap.trunk_diameter_cm ? snap.trunk_diameter_cm + ' cm' : null);
    add('Ø chioma', snap.crown_diameter_m ? snap.crown_diameter_m + ' m' : null);
    add('Dimora', snap.dimora);
    add('Stadio sviluppo', snap.stadio_sviluppo);
    add('Pos. sociale', snap.posizione_sociale);
    add('Localizzazione', snap.localizzazione);
    add('Vincoli', snap.vincoli);
    add('H albero', snap.tree_height_m ? snap.tree_height_m + ' m' : null);
    add('Circ.', snap.circonferenza_cm ? snap.circonferenza_cm + ' cm' : null);
    add('Ø ramo', snap.branch_diam_cm ? snap.branch_diam_cm + ' cm' : null);
    add('L ramo', snap.branch_length_m ? snap.branch_length_m + ' m' : null);
    add('H ramo', snap.branch_height_m ? snap.branch_height_m + ' m' : null);
    add('H bersaglio', snap.target_height_m ? snap.target_height_m + ' m' : null);
    add('H albero post-interv.', snap.post_tree_height_m ? snap.post_tree_height_m + ' m' : null);
    add('Circ. post-interv.', snap.post_circonferenza_cm ? snap.post_circonferenza_cm + ' cm' : null);
    add('Ø ramo post-interv.', snap.post_branch_diam_cm ? snap.post_branch_diam_cm + ' cm' : null);
    add('L ramo post-interv.', snap.post_branch_length_m ? snap.post_branch_length_m + ' m' : null);
    add('H ramo post-interv.', snap.post_branch_height_m ? snap.post_branch_height_m + ' m' : null);
    add('H bersaglio post-interv.', snap.post_target_height_m ? snap.post_target_height_m + ' m' : null);
    add('Pericolo rami', snap.pericolo_rami);
    add('Pericolo tronco', snap.pericolo_tronco);
    add('Pericolo colletto', snap.pericolo_colletto);
    add('Pericolo zolla', snap.pericolo_zolla);
    add('Bersaglio chioma tipo', snap.bersaglio_chioma_tipo);
    add('Bersaglio chioma desc.', snap.bersaglio_chioma_value);
    add('Bersaglio chioma flusso', snap.bersaglio_chioma_flow);
    add('Bersaglio chioma classe', snap.bersaglio_chioma);
    add('Bersaglio ramo tipo', snap.bersaglio_ramo_tipo);
    add('Bersaglio ramo desc.', snap.bersaglio_ramo_value);
    add('Bersaglio ramo flusso', snap.bersaglio_ramo_flow);
    add('Bersaglio ramo classe', snap.bersaglio_ramo);
    add('Moltiplicatore', snap.moltiplicatore);
    add('Monitoraggio', snap.monitoraggio);
    add('Urgenza', snap.urgenza);
    add('Condiz. salute ecologica', snap.condizione_salute_ecologica);
    add('Bio', snap.bio_kg != null ? snap.bio_kg + ' kg' : null);
    add('CO₂', snap.co2_kg_anno != null ? snap.co2_kg_anno + ' kg/anno' : null);
    add('O₂', snap.o2_kg_anno != null ? snap.o2_kg_anno + ' kg/anno' : null);
    add('Intercett. acqua', snap.ia_kg_anno != null ? snap.ia_kg_anno + ' kg/anno' : null);
    add('Valore ecologico', snap.valore_ecologico != null ? '€ ' + snap.valore_ecologico : null);
    const prescrMit = Array.isArray(snap.prescrizioni_mit) ? snap.prescrizioni_mit.join(', ') : snap.prescrizioni_mit;
    add('Prescrizioni mit.', prescrMit);
    const prescrVal = Array.isArray(snap.prescrizioni_val) ? snap.prescrizioni_val.join(', ') : snap.prescrizioni_val;
    add('Prescrizioni val.', prescrVal);
    const prescrCol = Array.isArray(snap.prescrizioni_col) ? snap.prescrizioni_col.join(', ') : snap.prescrizioni_col;
    add('Prescrizioni col.', prescrCol);
    if (!rows.length) return '<em style="color:var(--text-muted);font-size:12px;">Nessun dettaglio registrato</em>';
    return `<div class="tl-snap-grid">${rows.join('')}</div>`;
}

function renderTimeline(inspections) {
    const wrap = document.getElementById('timelineContent');
    if (!inspections.length) {
        wrap.innerHTML = `<div class="tl-empty"><i class="fa-regular fa-clock"></i><p>Nessuna ispezione registrata.</p></div>`;
        return;
    }
    wrap.innerHTML = '<div class="tl-divider">Più recenti prima</div>' +
        inspections.map((insp, idx) => {
            const snapHtml = renderSnapshotDetails(insp.snapshot);
            const uid = `snap-${insp.id || idx}`;
            const treatment = (() => {
                const mit = insp.snapshot?.prescrizioni_mit;
                const arr = Array.isArray(mit) ? mit : (mit ? [mit] : []);
                const txt = arr.filter(Boolean).join(', ') || insp.actions || '';
                return txt ? `<div class="tl-actions"><i class="fa-solid fa-scissors"></i>${txt}</div>` : '';
            })();
            return `
        <div class="tl-item">
            <div class="tl-dot ${tlDotClass(insp.condition)}"></div>
            <div class="tl-card">
                <div class="tl-header">
                    <span class="tl-date">${formatDate(insp.date)}</span>
                    ${condBadge(insp.condition)}
                    ${idx===0 && idx!==inspections.length-1?'<span class="tl-latest-tag">Ultima</span>':''}
                    ${idx===inspections.length-1?'<span class="tl-first-tag">Primo inserimento</span>':''}
                </div>
                ${rischioBadge(insp.rischio)}
                ${renderCardSummary(insp.snapshot)}
                ${treatment}
                ${insp.comments?`<div class="tl-body">${insp.comments}</div>`:''}
                <div class="tl-footer-row">
                    <div class="tl-inspector"><i class="fa-regular fa-user"></i>${insp.inspector_name||'Sconosciuto'}</div>
                    <button class="btn-tl-expand" onclick="toggleSnap('${uid}',this)">
                        <i class="fa-solid fa-chevron-down"></i> Dettagli
                    </button>
                </div>
                <div id="${uid}" class="tl-snap-panel" style="display:none;">${snapHtml}</div>
            </div>
        </div>`;
        }).join('');
}

function toggleSnap(id, btn) {
    const panel = document.getElementById(id);
    const open = panel.style.display !== 'none';
    panel.style.display = open ? 'none' : 'block';
    btn.innerHTML = open
        ? '<i class="fa-solid fa-chevron-down"></i> Dettagli'
        : '<i class="fa-solid fa-chevron-up"></i> Nascondi';
}

async function submitInspection() {
    const treeId = document.getElementById('inspTreeId').value;
    if (!treeId) return;
    const payload = {
        date: document.getElementById('inspDate').value,
        condition: document.getElementById('inspCondition').value.trim() || null,
        comments: document.getElementById('inspComments').value.trim(),
        actions: document.getElementById('inspActions').value.trim()
    };
    const res  = await fetch(`${API_BASE}/tree/${treeId}/inspections`, {
        method: 'POST',
        headers: Object.assign({'Content-Type':'application/json'}, authHeader()),
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
        showStatus('Ispezione registrata', 'success');
        document.getElementById('inspCondition').value = '';
        document.getElementById('inspComments').value  = '';
        document.getElementById('inspActions').value   = '';
        loadHistory(parseInt(treeId));
    } else showStatus(data.message||'Errore nel registrare l\'ispezione','danger');
}

// ─── Export selection ─────────────────────────────────────

function toggleExportMode() {
    state.exportMode = !state.exportMode;
    if (!state.exportMode) state.exportSelected = new Set();
    const btn  = document.getElementById('exportModeBtn');
    const bar  = document.getElementById('exportBar');
    const th   = document.getElementById('selectAllTh');
    btn.classList.toggle('btn-primary', state.exportMode);
    btn.classList.toggle('btn-outline', !state.exportMode);
    bar.style.display = state.exportMode ? 'flex' : 'none';
    th.style.display  = state.exportMode ? '' : 'none';
    renderPage();
}

function toggleSelectAll(cb) {
    if (cb.checked) state.filteredTrees.forEach(t => state.exportSelected.add(t.id));
    else state.exportSelected.clear();
    renderPage();
}

function toggleTreeSelect(id, checked) {
    if (checked) state.exportSelected.add(id); else state.exportSelected.delete(id);
    const allCb = document.getElementById('selectAllCb');
    if (allCb) {
        const total = state.filteredTrees.length;
        const sel   = state.filteredTrees.filter(t => state.exportSelected.has(t.id)).length;
        allCb.checked       = total > 0 && sel === total;
        allCb.indeterminate = sel > 0 && sel < total;
    }
    document.getElementById('exportCount').textContent = `${state.exportSelected.size} alber${state.exportSelected.size !== 1 ? 'i' : 'o'} selezionat${state.exportSelected.size !== 1 ? 'i' : 'o'}`;
}

async function deleteSelectedTrees() {
    const n = state.exportSelected.size;
    if (n === 0) { showStatus('Nessun albero selezionato', 'warning'); return; }
    if (!confirm(`Eliminare ${n} alber${n !== 1 ? 'i' : 'o'}? L'operazione è irreversibile.`)) return;
    const res = await fetch(`${API_BASE}/trees/bulk`, {
        method: 'DELETE',
        headers: { ...authHeader(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: [...state.exportSelected] })
    });
    const data = await res.json();
    if (!res.ok) { showStatus(data.message || 'Errore durante l\'eliminazione', 'danger'); return; }
    showStatus(`${data.deleted} alber${data.deleted !== 1 ? 'i eliminati' : 'o eliminato'}`, 'success');
    toggleExportMode();
    fetchTrees();
}

function exportSelectedExcel() {
    if (state.exportSelected.size === 0) { showStatus('Nessun albero selezionato', 'warning'); return; }
    return downloadExport('excel', [...state.exportSelected], 'alberi_selezione');
}

// ─── Import GPKG ─────────────────────────────────────────

const SILVAE_FIELDS = [
    { value: '',                  label: '— non importare —' },
    { value: 'custom_id',         label: 'ID Albero' },
    { value: 'species',           label: 'Specie (latino)' },
    { value: 'species_ita',       label: 'Specie (italiano)' },
    { value: 'condition',         label: 'Condizione' },
    { value: 'cpc',               label: 'Codice CPC' },
    { value: 'age',               label: 'Età / Stima età' },
    { value: 'address',           label: 'Indirizzo / Località' },
    { value: 'height',            label: 'Altezza (classe)' },
    { value: 'crown_diameter_m',  label: 'Diametro chioma (m)' },
    { value: 'circonferenza_cm',  label: 'Circonferenza (cm)' },
    { value: 'localizzazione',    label: 'Localizzazione' },
    { value: 'location',          label: 'Dettaglio posizione' },
    { value: 'next_check',        label: 'Prossima ispezione' },
    { value: 'longitude',         label: 'Longitudine' },
    { value: 'latitude',          label: 'Latitudine' },
    { value: 'dimora',            label: 'Dimora' },
    { value: 'stadio_sviluppo',   label: 'Stadio sviluppo' },
    { value: 'posizione_sociale', label: 'Posizione sociale' },
    { value: 'vincoli',           label: 'Vincoli' },
    { value: 'tree_height_m',     label: 'Altezza albero (m)' },
    { value: 'trunk_diameter_cm', label: 'Diametro tronco (cm)' },
    { value: 'branch_diam_cm',    label: 'Diam. ramo (cm)' },
    { value: 'branch_length_m',   label: 'Lunghezza ramo (m)' },
    { value: 'branch_height_m',   label: 'Altezza ramo (m)' },
    { value: 'target_height_m',   label: 'H target (m)' },
    { value: 'monitoraggio',      label: 'Monitoraggio' },
    { value: 'urgenza',           label: 'Urgenza' },
    { value: 'comments',          label: 'Note' },
    { value: 'actions',           label: 'Azioni' },
];

let _importMapping = {};  // {gpkg_col: silvae_field}

function initImportDropZone() {
    const zone  = document.getElementById('importDropZone');
    const input = document.getElementById('importFileInput');
    const label = document.getElementById('importFileName');
    if (!zone || !input) return;

    function setFile(file) {
        if (!file) return;
        input.files = (() => { const dt = new DataTransfer(); dt.items.add(file); return dt.files; })();
        label.textContent = file.name;
        zone.style.borderColor = 'var(--g600)';
        zone.style.background  = 'var(--g50)';
    }

    zone.addEventListener('click', e => { if (e.target.tagName !== 'LABEL') input.click(); });
    input.addEventListener('change', () => { if (input.files[0]) setFile(input.files[0]); });
    zone.addEventListener('dragover',  e => { e.preventDefault(); zone.style.borderColor = '#7c3aed'; });
    zone.addEventListener('dragleave', ()  => { zone.style.borderColor = 'var(--border)'; zone.style.background = ''; });
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.style.borderColor = 'var(--border)'; zone.style.background = '';
        const file = e.dataTransfer.files[0];
        if (file && file.name.endsWith('.gpkg')) setFile(file);
        else showStatus('Il file deve essere in formato .gpkg', 'warning');
    });
}

async function openImportMapping() {
    const input = document.getElementById('importFileInput');
    if (!input.files[0]) { showStatus('Seleziona prima un file .gpkg', 'warning'); return; }

    const btn = document.getElementById('importSubmitBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analisi file…';

    const fd = new FormData();
    fd.append('file', input.files[0]);

    try {
        const res  = await fetch(`${API_BASE}/import/gpkg/inspect`, { method: 'POST', headers: authHeader(), body: fd });
        const data = await res.json();
        if (!res.ok) { showStatus(data.message || 'Errore analisi file', 'danger'); return; }

        _importMapping = Object.assign({}, data.auto_mapping);
        _renderMappingTable(data.columns, data.sample, _importMapping);
        document.getElementById('importMappingModal').classList.add('open');
    } catch (e) {
        showStatus('Errore di connessione', 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-upload"></i> Avvia Importazione';
    }
}

function _renderMappingTable(columns, sample, mapping) {
    const rows = columns.map(col => {
        const ex  = (sample[col] || '').substring(0, 40);
        const sel = mapping[col] || '';
        const selectOpts = SILVAE_FIELDS.map(f =>
            `<option value="${f.value}"${f.value === sel ? ' selected' : ''}>${f.label}</option>`
        ).join('');
        return `<tr style="border-bottom:1px solid var(--border);">
          <td style="padding:6px 8px;font-weight:600;font-family:monospace;font-size:12px;">${col}</td>
          <td style="padding:6px 8px;color:var(--text-muted);font-size:12px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${ex}">${ex}</td>
          <td style="padding:4px 8px;">
            <select class="fc" style="font-size:12px;padding:4px 6px;" data-col="${col}" onchange="_importMapping[this.dataset.col]=this.value">
              ${selectOpts}
            </select>
          </td>
        </tr>`;
    }).join('');

    document.getElementById('importMappingBody').innerHTML = rows;
}

function closeImportMapping() {
    document.getElementById('importMappingModal').classList.remove('open');
}

function saveImportConfig() {
    const cfg = {};
    document.querySelectorAll('#importMappingBody select').forEach(sel => {
        if (sel.value) cfg[sel.dataset.col] = sel.value;
    });
    const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'import_config.json';
    a.click();
    URL.revokeObjectURL(a.href);
}

function loadImportConfig(input) {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => {
        try {
            const cfg = JSON.parse(e.target.result);
            document.querySelectorAll('#importMappingBody select').forEach(sel => {
                if (cfg[sel.dataset.col] !== undefined) {
                    sel.value = cfg[sel.dataset.col];
                    _importMapping[sel.dataset.col] = cfg[sel.dataset.col];
                }
            });
        } catch { showStatus('File di configurazione non valido', 'danger'); }
    };
    reader.readAsText(file);
    input.value = '';
}

async function confirmImportMapping() {
    const mapping = {};
    document.querySelectorAll('#importMappingBody select').forEach(sel => {
        if (sel.value) mapping[sel.dataset.col] = sel.value;
    });
    closeImportMapping();
    await _doImport(mapping);
}

async function _doImport(mapping) {
    const input    = document.getElementById('importFileInput');
    const city     = document.getElementById('importCity').value.trim();
    const conflict = document.getElementById('importConflict').value;
    const btn      = document.getElementById('importSubmitBtn');
    const result   = document.getElementById('importResult');

    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Importazione in corso…';
    result.style.display = 'none';

    const fd = new FormData();
    fd.append('file', input.files[0]);
    fd.append('city', city);
    fd.append('on_conflict', conflict);
    fd.append('mapping', JSON.stringify(mapping));

    try {
        const res  = await fetch(`${API_BASE}/import/gpkg`, { method: 'POST', headers: authHeader(), body: fd });
        const data = await res.json();
        if (!res.ok) {
            showStatus(data.message || 'Errore durante l\'importazione', 'danger');
        } else {
            const { inserted, skipped, errors, total, city: detectedCity, city_autodetected } = data;
            const cityLine = detectedCity
                ? `<div style="font-size:12px;color:var(--text-muted);margin-top:8px;text-align:center;">
                     <i class="fa-solid fa-location-dot" style="color:var(--g600);margin-right:4px;"></i>
                     Comune: <strong>${detectedCity}</strong>${city_autodetected ? ' <span style="font-size:11px;">(auto-rilevato)</span>' : ''}
                   </div>` : '';
            result.style.display = 'block';
            result.innerHTML = `
                <div style="font-weight:700;color:var(--g800);margin-bottom:8px;"><i class="fa-solid fa-circle-check" style="color:#16a34a;margin-right:6px;"></i>Importazione completata</div>
                <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center;">
                  <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:var(--r);padding:10px;">
                    <div style="font-size:22px;font-weight:700;color:#16a34a;">${inserted}</div>
                    <div style="font-size:11px;color:var(--text-muted);">Inseriti</div>
                  </div>
                  <div style="background:var(--g50);border:1px solid var(--border);border-radius:var(--r);padding:10px;">
                    <div style="font-size:22px;font-weight:700;color:var(--g600);">${skipped}</div>
                    <div style="font-size:11px;color:var(--text-muted);">Saltati</div>
                  </div>
                  <div style="background:${errors > 0 ? '#fef2f2' : 'var(--g50)'};border:1px solid ${errors > 0 ? '#fecaca' : 'var(--border)'};border-radius:var(--r);padding:10px;">
                    <div style="font-size:22px;font-weight:700;color:${errors > 0 ? '#dc2626' : 'var(--g600)'};">${errors}</div>
                    <div style="font-size:11px;color:var(--text-muted);">Errori</div>
                  </div>
                </div>
                ${cityLine}
                <div style="font-size:12px;color:var(--text-muted);margin-top:4px;text-align:center;">Totale righe nel file: ${total}</div>
                ${data.error_details?.length ? `<details style="margin-top:8px;font-size:11px;"><summary style="cursor:pointer;color:#dc2626;">Dettaglio errori (${data.error_details.length})</summary><pre style="margin:4px 0 0;white-space:pre-wrap;color:#dc2626;">${data.error_details.join('\n')}</pre></details>` : ''}`;
            showStatus(`Importazione completata: ${inserted} alberi inseriti`, 'success');
            if (detectedCity) {
                const sel = document.getElementById('citySelect');
                if (sel && ![...sel.options].some(o => o.value === detectedCity)) {
                    const o = document.createElement('option');
                    o.value = o.text = detectedCity;
                    sel.appendChild(o);
                }
                if (sel) sel.value = detectedCity;
            }
            fetchTrees();
        }
    } catch (e) {
        showStatus('Errore di connessione durante l\'importazione', 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-upload"></i> Avvia Importazione';
    }
}

// ─── Export ───────────────────────────────────────────────

// Punto d'ingresso per tutti gli export.
//   format: 'excel' | 'gpkg'
//   ids:    array di id (esporta solo quelli) oppure null/[] per l'export completo
//   defaultName: nome proposto, senza estensione
//   Excel → chiede solo il nome file; GPKG → apre la finestra di rinomina chiavi.
function downloadExport(format, ids, defaultName) {
    if (!state.token) { showStatus('Effettua prima il login', 'danger'); return; }
    if (format === 'gpkg') return openGpkgExportModal(ids || [], defaultName);
    return openExcelExportModal(ids || [], defaultName);
}

// Escape per testo/attributi inseriti in innerHTML.
function _htmlEsc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Normalizza un nome file: rimuove estensione/caratteri non validi, aggiunge quella giusta.
function _safeFilename(name, defaultName, ext) {
    name = (name || '').trim();
    if (!name) name = defaultName;
    if (name.toLowerCase().endsWith('.' + ext)) name = name.slice(0, -(ext.length + 1));
    name = name.replace(/[\\/:*?"<>|]/g, '_').trim() || defaultName;
    return `${name}.${ext}`;
}

// Esegue il download vero e proprio (con eventuale mappa di rinomina per il GPKG).
async function _performExport(format, ids, filename, renameObj, excludeArr) {
    const ext = format === 'excel' ? 'xlsx' : 'gpkg';
    showStatus(`Preparazione ${ext.toUpperCase()}…`, 'info');
    const params = new URLSearchParams();
    if (ids && ids.length) params.set('ids', ids.join(','));
    if (renameObj && Object.keys(renameObj).length) params.set('rename', JSON.stringify(renameObj));
    if (excludeArr && excludeArr.length) params.set('exclude', JSON.stringify(excludeArr));
    const qs = params.toString();
    const res = await fetch(`${API_BASE}/export/${format}${qs ? '?' + qs : ''}`, { headers: authHeader() });
    if (!res.ok) return showStatus('Esportazione fallita', 'danger');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob());
    a.download = filename; a.click();
    URL.revokeObjectURL(a.href);
    showStatus(`${ext.toUpperCase()} scaricato: ${filename}`, 'success');
}

// ─── Finestra export GPKG: rinomina delle chiavi ──────────

async function openGpkgExportModal(ids, defaultName) {
    if (!state.gpkgColumns) {
        try {
            const res = await fetch(`${API_BASE}/export/gpkg/columns`, { headers: authHeader() });
            if (!res.ok) throw new Error();
            state.gpkgColumns = await res.json();
        } catch { showStatus('Impossibile leggere le colonne del GPKG', 'danger'); return; }
    }
    state.gpkgExportIds = ids || [];
    state.gpkgExcluded  = state.gpkgExcluded || new Set();
    state.gpkgRenames   = state.gpkgRenames  || {};
    document.getElementById('gpkgExportFilename').value = defaultName || 'alberi';
    _renderGpkgExportTable();
    document.getElementById('gpkgExportModal').classList.add('open');
}

// Salva i nomi digitati prima di ridisegnare la tabella (per non perderli).
function _captureGpkgRenames() {
    document.querySelectorAll('#gpkgExportBody .gpkg-rename').forEach(i => {
        state.gpkgRenames[i.dataset.col] = i.value;
    });
}

function _renderGpkgExportTable() {
    const excl = state.gpkgExcluded;
    document.getElementById('gpkgExportBody').innerHTML = state.gpkgColumns.map(c => {
        const off = excl.has(c.name);
        const val = _htmlEsc(state.gpkgRenames[c.name] || '');
        return `<tr style="border-bottom:1px solid var(--border);${off ? 'opacity:.45;' : ''}">
          <td style="padding:6px 8px;font-family:monospace;font-size:12px;font-weight:600;${off ? 'text-decoration:line-through;' : ''}">${c.name}</td>
          <td style="padding:4px 8px;">
            <input class="inp gpkg-rename" data-col="${c.name}" type="text" placeholder="${c.name}" value="${val}" ${off ? 'disabled' : ''}
                   style="width:100%;font-size:12px;padding:4px 6px;">
          </td>
          <td style="padding:4px 8px;text-align:center;">
            <button type="button" class="btn btn-outline btn-sm" onclick="toggleGpkgField('${c.name}')" title="${off ? 'Reintegra campo' : 'Escludi campo'}" style="padding:2px 8px;">
              <i class="fa-solid ${off ? 'fa-rotate-left' : 'fa-xmark'}"></i>
            </button>
          </td>
        </tr>`;
    }).join('');
}

function toggleGpkgField(name) {
    _captureGpkgRenames();
    if (state.gpkgExcluded.has(name)) state.gpkgExcluded.delete(name);
    else state.gpkgExcluded.add(name);
    _renderGpkgExportTable();
}

function resetGpkgNames() {
    _captureGpkgRenames();
    state.gpkgRenames = {};
    state.gpkgExcluded.clear();
    _renderGpkgExportTable();
}

function closeGpkgExport() {
    document.getElementById('gpkgExportModal').classList.remove('open');
}

function confirmGpkgExport() {
    _captureGpkgRenames();
    const rename = {};
    state.gpkgColumns.forEach(c => {
        if (state.gpkgExcluded.has(c.name)) return;
        const v = (state.gpkgRenames[c.name] || '').trim();
        if (v && v !== c.name) rename[c.name] = v;
    });
    const exclude  = [...state.gpkgExcluded];
    const filename = _safeFilename(document.getElementById('gpkgExportFilename').value, 'alberi', 'gpkg');
    closeGpkgExport();
    _performExport('gpkg', state.gpkgExportIds, filename, rename, exclude);
}

// ─── Finestra export Excel: scelta dei campi ──────────────

async function openExcelExportModal(ids, defaultName) {
    if (!state.excelColumns) {
        try {
            const res = await fetch(`${API_BASE}/export/excel/columns`, { headers: authHeader() });
            if (!res.ok) throw new Error();
            state.excelColumns = await res.json();
        } catch { showStatus('Impossibile leggere le colonne Excel', 'danger'); return; }
    }
    state.excelExportIds = ids || [];
    state.excelExcluded  = state.excelExcluded || new Set();
    document.getElementById('excelExportFilename').value = defaultName || 'alberi';
    _renderExcelExportFields();
    document.getElementById('excelExportModal').classList.add('open');
}

function _renderExcelExportFields() {
    const excl = state.excelExcluded;
    document.getElementById('excelExportBody').innerHTML = state.excelColumns.map(g => `
      <div style="margin-bottom:10px;">
        <div style="font-size:12px;font-weight:700;color:var(--text-muted);margin:2px 0 6px;">${_htmlEsc(g.group)}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;">
          ${g.columns.map(c => {
            const off = excl.has(c);
            return `<button type="button" data-col="${_htmlEsc(c)}" onclick="toggleExcelField(this)"
                      style="font-size:12px;padding:3px 9px;border-radius:14px;border:1px solid var(--border);cursor:pointer;
                             ${off ? 'background:#f3f4f6;color:#9ca3af;text-decoration:line-through;'
                                   : 'background:#eef2ff;color:#3730a3;'}">
                      ${_htmlEsc(c)} <i class="fa-solid ${off ? 'fa-rotate-left' : 'fa-xmark'}" style="margin-left:3px;font-size:10px;"></i>
                    </button>`;
          }).join('')}
        </div>
      </div>`).join('');
}

function toggleExcelField(btn) {
    const col = btn.dataset.col;
    if (state.excelExcluded.has(col)) state.excelExcluded.delete(col);
    else state.excelExcluded.add(col);
    _renderExcelExportFields();
}

function resetExcelFields() {
    state.excelExcluded.clear();
    _renderExcelExportFields();
}

function closeExcelExport() {
    document.getElementById('excelExportModal').classList.remove('open');
}

function confirmExcelExport() {
    const filename = _safeFilename(document.getElementById('excelExportFilename').value, 'alberi', 'xlsx');
    const exclude  = [...state.excelExcluded];
    closeExcelExport();
    _performExport('excel', state.excelExportIds, filename, null, exclude);
}

function exportExcel() { return downloadExport('excel', null, 'alberi'); }
function exportGPKG()  { return downloadExport('gpkg',  null, 'alberi'); }

// ─── Schede albero (report) — PLACEHOLDER ─────────────────
// Carica l'elenco dei template nel <select> (una volta sola).
async function loadReportTemplates() {
    const sel = document.getElementById('reportTemplateSelect');
    if (!sel || sel.dataset.loaded) return;
    try {
        const res = await fetch(`${API_BASE}/report/templates`, { headers: authHeader() });
        if (!res.ok) throw new Error();
        const templates = await res.json();
        sel.innerHTML = templates.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
        sel.dataset.loaded = '1';
    } catch { sel.innerHTML = '<option value="">(nessun template)</option>'; }
}

// Genera e scarica il report schede per gli id dati (null/[] = tutti i visibili).
async function generateScheda(ids) {
    if (!state.token) { showStatus('Effettua prima il login', 'danger'); return; }
    const sel = document.getElementById('reportTemplateSelect');
    const template = sel ? sel.value : '';
    const params = new URLSearchParams();
    if (template) params.set('template', template);
    if (ids && ids.length) params.set('ids', ids.join(','));
    const qs = params.toString();
    showStatus('Preparazione schede…', 'info');
    const res = await fetch(`${API_BASE}/report/scheda${qs ? '?' + qs : ''}`, { headers: authHeader() });
    if (!res.ok) return showStatus('Generazione schede fallita', 'danger');
    const cd = res.headers.get('Content-Disposition') || '';
    const m = cd.match(/filename="?([^"]+)"?/);
    const filename = m ? m[1] : 'schede_albero.html';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob());
    a.download = filename; a.click();
    URL.revokeObjectURL(a.href);
    showStatus(`Schede generate: ${filename}`, 'success');
}

// Card "Esporta": schede degli alberi selezionati in tabella (o tutti se nessuna selezione).
function exportScheda() {
    return generateScheda(state.exportSelected.size ? [...state.exportSelected] : null);
}

// Barra selezione area sulla mappa: schede degli alberi nell'area selezionata.
function exportAreaScheda() {
    const ids = state.areaSelectedIds || [];
    if (ids.length === 0) { showStatus("Nessun albero nell'area selezionata", 'warning'); return; }
    return generateScheda(ids);
}

function exportSelectedGPKG() {
    if (state.exportSelected.size === 0) { showStatus('Nessun albero selezionato', 'warning'); return; }
    return downloadExport('gpkg', [...state.exportSelected], 'alberi_selezione');
}

// ─── Selezione area sulla mappa (rettangolo, stile Booking) ─

function setupAreaSelect() {
    const map = state.map;

    // Bottone toggle nella barra dei controlli (accanto a "posizione")
    const AreaControl = L.Control.extend({
        options: { position: 'topleft' },
        onAdd() {
            const btn = L.DomUtil.create('button', 'leaflet-bar locate-ctrl-btn');
            btn.id = 'areaSelectBtn';
            btn.innerHTML = '<i class="fa-solid fa-draw-polygon"></i>';
            btn.title = "Seleziona un'area (poligono) da esportare";
            L.DomEvent.disableClickPropagation(btn);
            L.DomEvent.on(btn, 'click', toggleAreaSelect);
            return btn;
        }
    });
    new AreaControl().addTo(map);

    // Click sulla mappa → aggiunge un vertice al poligono in costruzione.
    map.on('click', e => {
        if (!state.areaSelectMode) return;
        _addAreaVertex(e.latlng);
    });
    // Movimento del mouse → "elastico": anteprima del lato verso il cursore.
    map.on('mousemove', e => {
        if (!state.areaSelectMode || state.areaClosed || state.areaVertices.length === 0) return;
        _redrawAreaDraft(e.latlng);
    });
}

// Aggiunge un vertice; se il click è sul primo vertice (con ≥3 punti) chiude l'area.
function _addAreaVertex(latlng) {
    if (state.areaClosed) clearAreaSelect();
    if (state.areaVertices.length >= 3) {
        const p0 = state.map.latLngToContainerPoint(state.areaVertices[0]);
        const pc = state.map.latLngToContainerPoint(latlng);
        if (p0.distanceTo(pc) < 14) { closeAreaPolygon(); return; }
    }
    state.areaVertices.push(latlng);
    _redrawAreaDraft();
    updateAreaPanel();
}

// Ridisegna il poligono in costruzione (+ eventuale vertice "elastico" sotto al cursore)
// e i pallini dei vertici. Il primo vertice è cliccabile per chiudere l'area.
function _redrawAreaDraft(cursorLatLng) {
    const pts = state.areaVertices.slice();
    if (cursorLatLng) pts.push(cursorLatLng);

    if (state.areaDraft) { state.map.removeLayer(state.areaDraft); state.areaDraft = null; }
    if (pts.length >= 2) {
        state.areaDraft = L.polygon(pts, {
            color: '#1a5276', weight: 2, fillColor: '#1a5276', fillOpacity: 0.1,
            dashArray: '5,5', interactive: false
        }).addTo(state.map);
    }

    state.areaMarkers.forEach(m => state.map.removeLayer(m));
    state.areaMarkers = state.areaVertices.map((v, i) => {
        const first = i === 0;
        const m = L.circleMarker(v, {
            radius: first ? 6 : 4, color: '#1a5276', weight: 2,
            fillColor: first ? '#ffffff' : '#1a5276', fillOpacity: 1,
            interactive: first
        });
        if (first) {
            m.on('click', ev => {
                L.DomEvent.stop(ev);
                if (state.areaVertices.length >= 3) closeAreaPolygon();
            });
            m.bindTooltip("Clicca per chiudere l'area", { direction: 'top' });
        }
        return m.addTo(state.map);
    });
}

// Chiude il poligono e seleziona gli alberi interni.
function closeAreaPolygon() {
    if (state.areaVertices.length < 3) {
        showStatus("Servono almeno 3 punti per chiudere l'area", 'warning');
        return;
    }
    if (state.areaDraft) { state.map.removeLayer(state.areaDraft); state.areaDraft = null; }
    state.areaMarkers.forEach(m => state.map.removeLayer(m));
    state.areaMarkers = [];
    state.areaPoly = L.polygon(state.areaVertices, {
        color: '#1a5276', weight: 2, fillColor: '#1a5276', fillOpacity: 0.12, interactive: false
    }).addTo(state.map);
    state.areaClosed = true;
    finalizeAreaSelect(state.areaVertices);
}

// Test punto-in-poligono (ray casting). poly: array di [lat, lng].
function _pointInPolygon(lat, lng, poly) {
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const yi = poly[i][0], xi = poly[i][1];
        const yj = poly[j][0], xj = poly[j][1];
        const intersect = ((yi > lat) !== (yj > lat)) &&
            (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi);
        if (intersect) inside = !inside;
    }
    return inside;
}

function toggleAreaSelect() {
    if (!state.map) return;
    state.areaSelectMode = !state.areaSelectMode;
    const btn   = document.getElementById('areaSelectBtn');
    const panel = document.getElementById('areaSelectPanel');
    const mapEl = state.map.getContainer();
    if (state.areaSelectMode) {
        state.map.dragging.disable();
        state.map.doubleClickZoom.disable();
        mapEl.classList.add('area-select-cursor');
        if (btn)   btn.classList.add('active');
        if (panel) panel.style.display = 'flex';
        updateAreaPanel();
        showStatus("Clicca sulla mappa per disegnare l'area; clicca sul primo punto (o «Chiudi») per completarla", 'info');
    } else {
        state.map.dragging.enable();
        state.map.doubleClickZoom.enable();
        mapEl.classList.remove('area-select-cursor');
        if (btn)   btn.classList.remove('active');
        if (panel) panel.style.display = 'none';
        clearAreaSelect();
    }
}

function clearAreaSelect() {
    if (state.map) {
        if (state.areaDraft) state.map.removeLayer(state.areaDraft);
        if (state.areaPoly)  state.map.removeLayer(state.areaPoly);
        state.areaMarkers.forEach(m => state.map.removeLayer(m));
    }
    state.areaDraft = null;
    state.areaPoly = null;
    state.areaMarkers = [];
    state.areaVertices = [];
    state.areaClosed = false;
    state.areaSelectedIds = [];
    updateAreaPanel();
}

function finalizeAreaSelect(vertices) {
    const poly = vertices.map(v => [v.lat, v.lng]);
    const inside = (state.mapTrees || []).filter(t =>
        t.latitude && t.longitude &&
        _pointInPolygon(parseFloat(t.latitude), parseFloat(t.longitude), poly)
    );
    state.areaSelectedIds = inside.map(t => t.id);
    updateAreaPanel();
}

function updateAreaPanel() {
    const n = (state.areaSelectedIds || []).length;
    const countEl = document.getElementById('areaSelectCount');
    if (countEl) countEl.textContent = n;
    const xls = document.getElementById('areaExcelBtn');
    const gpk = document.getElementById('areaGpkgBtn');
    const sch = document.getElementById('areaSchedaBtn');
    if (xls) xls.disabled = n === 0;
    if (gpk) gpk.disabled = n === 0;
    if (sch) sch.disabled = n === 0;
}

function _areaExport(format) {
    const ids = state.areaSelectedIds || [];
    if (ids.length === 0) { showStatus("Nessun albero nell'area selezionata", 'warning'); return; }
    return downloadExport(format, ids, 'alberi_area');
}

function exportAreaExcel() { return _areaExport('excel'); }
function exportAreaGPKG()  { return _areaExport('gpkg');  }

// ─── Status toast ─────────────────────────────────────────

let _statusTimer = null;
function showStatus(msg, level='info') {
    const el = document.getElementById('status');
    const bg = {success:'#2d6a4f', danger:'#c0392b', warning:'#856404', info:'#1a5276'};
    el.textContent = msg; el.style.background = bg[level]||bg.info;
    el.style.color = '#fff'; el.classList.add('show');
    clearTimeout(_statusTimer);
    _statusTimer = setTimeout(() => el.classList.remove('show'), 5000);
}

// ─── Boot ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('loginBtn').addEventListener('click', login);
    document.getElementById('loginPassword').addEventListener('keydown', e => e.key==='Enter' && login());
    // Registrazione pubblica disabilitata: link "Crea account" nascosto (vedi index.html).
    // Riattivare questa riga quando si riapre la registrazione.
    // document.getElementById('showRegisterLink').addEventListener('click', e => { e.preventDefault(); showLoginView('registerView'); });
    document.getElementById('showForgotLink').addEventListener('click', e => { e.preventDefault(); showLoginView('forgotView'); });
    document.getElementById('showLoginFromRegLink').addEventListener('click', e => { e.preventDefault(); showLoginView('loginView'); });
    document.getElementById('showLoginFromForgotLink').addEventListener('click', e => { e.preventDefault(); showLoginView('loginView'); });
    document.getElementById('showLoginFromResetLink').addEventListener('click', e => { e.preventDefault(); history.replaceState(null, '', window.location.pathname); showLoginView('loginView'); });
    document.getElementById('resetBtn').addEventListener('click', resetPassword);
    document.getElementById('resetPassword2').addEventListener('keydown', e => e.key === 'Enter' && resetPassword());
    document.getElementById('registerBtn').addEventListener('click', register);
    document.getElementById('regPassword2').addEventListener('keydown', e => e.key==='Enter' && register());
    document.getElementById('forgotBtn').addEventListener('click', forgotPassword);
    document.getElementById('forgotEmail').addEventListener('keydown', e => e.key==='Enter' && forgotPassword());
    document.getElementById('addAgronomistBtn').addEventListener('click', addAgronomist);
    document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
    document.querySelectorAll('th.sortable').forEach(th => th.addEventListener('click', () => applySort(th.dataset.sort)));
    document.getElementById('logoutBtn').addEventListener('click', logout);
    document.getElementById('refreshCitiesBtn').addEventListener('click', populateCities);
    document.getElementById('createUserBtn').addEventListener('click', createUser);
    document.getElementById('createCityBtn').addEventListener('click', createCity);
    document.getElementById('idFilter').addEventListener('input', applyIdFilter);
    document.getElementById('pageSizeSelect').addEventListener('change', changePageSize);
    document.getElementById('addTreeForm').addEventListener('submit', submitTreeForm);
    document.getElementById('openFormBtn').addEventListener('click', () => { resetForm(); showTreeView('edit'); });
    initComuneAutocomplete('city');
    initComuneAutocomplete('newCity');
    initComuneAutocomplete('importCity');
    document.getElementById('cpc').addEventListener('input', syncCpcToCondition);
    initMapAddressAutocomplete();
    initImportDropZone();
    document.getElementById('exportExcelBtn').addEventListener('click', exportExcel);
    document.getElementById('exportGPKGBtn').addEventListener('click', exportGPKG);
    document.getElementById('exportSchedaBtn').addEventListener('click', exportScheda);
    loadReportTemplates();
    init();
});

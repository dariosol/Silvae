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
    map: null, markers: [], clusterGroup: null, userMarker: null,
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

function populateMultiSelect(id, items) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = '';
    items.forEach(item => {
        const o = document.createElement('option');
        o.value = o.textContent = item;
        el.appendChild(o);
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
    return Array.from(el.selectedOptions).map(o => o.value);
}

function setMultiSelect(id, values) {
    const el = document.getElementById(id);
    if (!el || !values) return;
    const set = new Set(values);
    Array.from(el.options).forEach(o => { o.selected = set.has(o.value); });
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
    ['loginView','registerView','forgotView'].forEach(id => {
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
    const city    = document.getElementById('citySelect').value;
    const address = document.getElementById('streetSearch').value.trim();
    const params  = new URLSearchParams();
    if (city)    params.append('city', city);
    if (address) params.append('address', address);
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
    const q = document.getElementById('idFilter').value.trim().toLowerCase();
    state.filteredTrees = q ? state.allTrees.filter(t => t.custom_id.toLowerCase().includes(q)) : state.allTrees;
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

function condClass(cond) {
    if (!cond) return 'tr-other'; const c = cond.toLowerCase();
    if (c.includes('buono')||c.includes('eccellente')||c.includes('ottimo')) return 'tr-good';
    if (c.includes('discreto')||c.includes('mediocre')) return 'tr-fair';
    if (c.includes('scarso')||c.includes('critico')||c.includes('morto')||c.includes('abbattuto')) return 'tr-poor';
    return 'tr-other';
}

function condBadge(cond) {
    if (!cond) return `<span class="cond-badge cb-other">—</span>`;
    const c = cond.toLowerCase(); let cls='cb-other', icon='fa-circle';
    if (c.includes('buono')||c.includes('eccellente')||c.includes('ottimo')) { cls='cb-good'; icon='fa-circle-check'; }
    else if (c.includes('discreto')||c.includes('mediocre')) { cls='cb-fair'; icon='fa-circle-exclamation'; }
    else if (c.includes('scarso')||c.includes('critico')||c.includes('morto')||c.includes('abbattuto')) { cls='cb-poor'; icon='fa-circle-xmark'; }
    return `<span class="cond-badge ${cls}"><i class="fa-solid ${icon}"></i> ${cond}</span>`;
}

function condDot(cond) {
    if (!cond) return `<span class="cond-dot dot-other" title="—"></span>`;
    const c = cond.toLowerCase();
    if (c.includes('buono')||c.includes('eccellente')||c.includes('ottimo')) return `<span class="cond-dot dot-good" title="${cond}"></span>`;
    if (c.includes('discreto')||c.includes('mediocre')) return `<span class="cond-dot dot-fair" title="${cond}"></span>`;
    if (c.includes('scarso')||c.includes('critico')||c.includes('morto')||c.includes('abbattuto')) return `<span class="cond-dot dot-poor" title="${cond}"></span>`;
    return `<span class="cond-dot dot-other" title="${cond}"></span>`;
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
    sv('species', data.species); sv('comments', data.comments); sv('actions', data.actions);
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

    document.getElementById('riskResults').style.display = 'none';
    document.getElementById('formSubmitButton').innerHTML =
        '<i class="fa-solid fa-floppy-disk"></i> Salva modifiche';
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
        resetForm(); showTreeView('list'); fetchTrees();
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
    DIAG_PARTS.forEach(p => clearDiagRows(p));
    // Reset multi-selects (deselect all)
    ['conflitti_list','agenti_carie','altri_patogeni','prescrizioni_val','prescrizioni_mit','prescrizioni_col'].forEach(id => {
        const el = document.getElementById(id);
        if (el) Array.from(el.options).forEach(o => o.selected = false);
    });
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

function showOnMap(trees) {
    if (state.clusterGroup) state.map.removeLayer(state.clusterGroup);
    state.markers = [];

    state.clusterGroup = L.markerClusterGroup({
        maxClusterRadius: 60,
        iconCreateFunction(cluster) {
            const n = cluster.getChildCount();
            return L.divIcon({
                className: '',
                html: `<div style="background:var(--g800);color:#fff;border-radius:50%;width:36px;height:36px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;box-shadow:0 2px 8px rgba(0,0,0,.35)">${n}</div>`,
                iconSize: [36, 36], iconAnchor: [18, 18]
            });
        }
    });

    trees.forEach(t => {
        if (!t.latitude || !t.longitude) return;
        const icon = L.divIcon({
            className: '',
            html: `<div style="background:var(--g800);color:#fff;border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,.3)"><i class="fa-solid fa-tree"></i></div>`,
            iconSize: [30, 30], iconAnchor: [15, 15]
        });
        const m = L.marker([t.latitude, t.longitude], {icon})
            .bindPopup(`<strong>${t.custom_id}</strong><br><em>${t.species}</em><br>${condBadge(t.condition)}<br><span style="font-size:12px;color:#555">${t.address||t.city||''}</span><br><br><button class="btn btn-sm btn-primary" onclick="openEditForm(${t.id})"><i class="fa-solid fa-pen-to-square"></i> Modifica</button>`);
        m.treeId = t.id;
        state.markers.push(m);
        state.clusterGroup.addLayer(m);
    });

    state.map.addLayer(state.clusterGroup);
    if (state.markers.length > 0)
        state.map.fitBounds(state.clusterGroup.getBounds().pad(0.12));
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

function tlDotClass(cond) {
    if (!cond) return 'tl-dot-other'; const c = cond.toLowerCase();
    if (c.includes('good')||c.includes('excel')) return 'tl-dot-good';
    if (c.includes('fair')||c.includes('moder')) return 'tl-dot-fair';
    if (c.includes('poor')||c.includes('crit')||c.includes('dead')) return 'tl-dot-poor';
    return 'tl-dot-other';
}

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
                    ${idx===0?'<span class="tl-latest-tag">Ultima</span>':''}
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

async function exportSelectedExcel() {
    if (state.exportSelected.size === 0) { showStatus('Nessun albero selezionato', 'warning'); return; }
    showStatus('Preparazione Excel…', 'info');
    const ids = [...state.exportSelected].join(',');
    const res = await fetch(`${API_BASE}/export/excel?ids=${ids}`, {headers: authHeader()});
    if (!res.ok) return showStatus('Esportazione fallita', 'danger');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob()); a.download = 'alberi.xlsx'; a.click();
    URL.revokeObjectURL(a.href); showStatus('File Excel scaricato', 'success');
}

// ─── Import GPKG ─────────────────────────────────────────

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

async function submitImportGPKG() {
    const input = document.getElementById('importFileInput');
    const city  = document.getElementById('importCity').value.trim();
    const conflict = document.getElementById('importConflict').value;
    const btn   = document.getElementById('importSubmitBtn');
    const result = document.getElementById('importResult');

    if (!input.files[0]) { showStatus('Seleziona un file .gpkg', 'warning'); return; }

    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Importazione in corso…';
    result.style.display = 'none';

    const fd = new FormData();
    fd.append('file', input.files[0]);
    fd.append('city', city);
    fd.append('on_conflict', conflict);

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
                <div style="font-size:12px;color:var(--text-muted);margin-top:4px;text-align:center;">Totale righe nel file: ${total}</div>`;
            showStatus(`Importazione completata: ${inserted} alberi inseriti`, 'success');
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

async function exportExcel() {
    if (!state.token) return showStatus('Effettua prima il login','danger');
    showStatus('Preparazione Excel…','info');
    const res = await fetch(`${API_BASE}/export/excel`, {headers: authHeader()});
    if (!res.ok) return showStatus('Esportazione fallita','danger');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob()); a.download = 'trees.xlsx'; a.click();
    URL.revokeObjectURL(a.href); showStatus('File Excel scaricato','success');
}

async function exportGPKG() {
    if (!state.token) return showStatus('Effettua prima il login','danger');
    showStatus('Preparazione GPKG…','info');
    const res = await fetch(`${API_BASE}/export/gpkg`, {headers: authHeader()});
    if (!res.ok) return showStatus('Esportazione fallita','danger');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob()); a.download = 'alberi.gpkg'; a.click();
    URL.revokeObjectURL(a.href); showStatus('GPKG scaricato','success');
}

async function exportSelectedGPKG() {
    if (state.exportSelected.size === 0) { showStatus('Nessun albero selezionato', 'warning'); return; }
    showStatus('Preparazione GPKG…', 'info');
    const ids = [...state.exportSelected].join(',');
    const res = await fetch(`${API_BASE}/export/gpkg?ids=${ids}`, {headers: authHeader()});
    if (!res.ok) return showStatus('Esportazione fallita', 'danger');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob()); a.download = 'alberi.gpkg'; a.click();
    URL.revokeObjectURL(a.href); showStatus('GPKG scaricato','success');
}

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
    document.getElementById('showRegisterLink').addEventListener('click', e => { e.preventDefault(); showLoginView('registerView'); });
    document.getElementById('showForgotLink').addEventListener('click', e => { e.preventDefault(); showLoginView('forgotView'); });
    document.getElementById('showLoginFromRegLink').addEventListener('click', e => { e.preventDefault(); showLoginView('loginView'); });
    document.getElementById('showLoginFromForgotLink').addEventListener('click', e => { e.preventDefault(); showLoginView('loginView'); });
    document.getElementById('registerBtn').addEventListener('click', register);
    document.getElementById('regPassword2').addEventListener('keydown', e => e.key==='Enter' && register());
    document.getElementById('forgotBtn').addEventListener('click', forgotPassword);
    document.getElementById('forgotEmail').addEventListener('keydown', e => e.key==='Enter' && forgotPassword());
    document.getElementById('addAgronomistBtn').addEventListener('click', addAgronomist);
    document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
    document.querySelectorAll('th.sortable').forEach(th => th.addEventListener('click', () => applySort(th.dataset.sort)));
    document.getElementById('logoutBtn').addEventListener('click', logout);
    document.getElementById('refreshCitiesBtn').addEventListener('click', populateCities);
    document.getElementById('streetSearch').addEventListener('keydown', e => e.key==='Enter' && fetchTrees());
    document.getElementById('createUserBtn').addEventListener('click', createUser);
    document.getElementById('createCityBtn').addEventListener('click', createCity);
    document.getElementById('idFilter').addEventListener('input', applyIdFilter);
    document.getElementById('pageSizeSelect').addEventListener('change', changePageSize);
    document.getElementById('addTreeForm').addEventListener('submit', submitTreeForm);
    document.getElementById('openFormBtn').addEventListener('click', () => { resetForm(); showTreeView('edit'); });
    initComuneAutocomplete('city');
    initComuneAutocomplete('newCity');
    initComuneAutocomplete('importCity');
    initMapAddressAutocomplete();
    initImportDropZone();
    document.getElementById('exportExcelBtn').addEventListener('click', exportExcel);
    document.getElementById('exportGPKGBtn').addEventListener('click', exportGPKG);
    init();
});

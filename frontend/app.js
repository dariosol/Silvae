const API_BASE = 'http://localhost:5000';

let state = {
    token: localStorage.getItem('token') || null,
    user:  JSON.parse(localStorage.getItem('user') || 'null'),
    // tree list state
    allTrees:      [],   // full server response for current city/filter
    filteredTrees: [],   // after client-side ID filter
    currentPage:   1,
    pageSize:      25,
    // tabs
    activeTab: 'trees',
    // sort
    sortField: null,
    sortDir:   'asc',
    // map
    map:     null,
    markers: []
};

function authHeader() {
    return state.token ? { 'Authorization': `Bearer ${state.token}` } : {};
}

// ─── Sub-view navigation (within Trees tab) ──────────────

function showTreeView(name) {
    document.querySelectorAll('#tab-trees .tab-view').forEach(v =>
        v.classList.toggle('active', v.id === 'view-' + name));
}

// ─── Auth UI ──────────────────────────────────────────────

async function init() {
    await populateCities();
    setupAuthUI();
    if (state.token && state.user) fetchTrees();
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
    document.getElementById('userManagement').style.display = show(isAdmin);
    document.getElementById('cityManagement').style.display = show(role === 'superuser');
    const tabManage = document.getElementById('tabManageBtn');
    if (tabManage) tabManage.style.display = show(isAdmin);
}

function switchTab(name) {
    state.activeTab = name;
    document.querySelectorAll('.tab-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('.tab-section').forEach(s =>
        s.classList.toggle('active', s.id === 'tab-' + name));
    if (name === 'map') {
        if (!state.map) {
            state.map = L.map('map').setView([45.4642, 9.19], 12);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19, attribution: '© OpenStreetMap'
            }).addTo(state.map);
        } else {
            state.map.invalidateSize();
        }
        showOnMap(state.allTrees);
    }
}

async function login() {
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    if (!username || !password) return showStatus('Enter username and password', 'warning');

    const res  = await fetch(`${API_BASE}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (res.ok) {
        state.token = data.token;
        state.user  = data.user;
        localStorage.setItem('token', state.token);
        localStorage.setItem('user', JSON.stringify(state.user));
        setupAuthUI();
        fetchTrees();
        showStatus(`Welcome, ${data.user.username}`, 'success');
    } else {
        showStatus(data.message || 'Login failed', 'danger');
        document.getElementById('loginPassword').value = '';
    }
}

function logout() {
    state.token = null;
    state.user  = null;
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    state.allTrees = [];
    state.filteredTrees = [];
    document.getElementById('treeList').innerHTML = '';
    document.getElementById('treeCount').textContent = '0';
    setupAuthUI();
}

// ─── City ─────────────────────────────────────────────────

async function populateCities() {
    const sel = document.getElementById('citySelect');
    sel.innerHTML = '<option value="">All cities</option>';
    const res = await fetch(`${API_BASE}/cities`);
    if (!res.ok) return;
    const cities = await res.json();
    cities.forEach(c => {
        const o = document.createElement('option');
        o.value = o.text = c;
        sel.appendChild(o);
    });
    const dl = document.getElementById('newCityDatalist');
    if (dl) {
        dl.innerHTML = '';
        cities.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c;
            dl.appendChild(opt);
        });
    }
}

async function createCity() {
    const name = document.getElementById('cityName').value.trim();
    if (!name) return showStatus('City name required', 'warning');
    const res  = await fetch(`${API_BASE}/admin/cities`, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader()),
        body: JSON.stringify({ name })
    });
    const data = await res.json();
    if (res.ok) {
        showStatus('City created: ' + name, 'success');
        document.getElementById('cityName').value = '';
        await populateCities();
    } else {
        showStatus(data.message || 'Error', 'danger');
    }
}

// ─── Users ────────────────────────────────────────────────

async function createUser() {
    const username = document.getElementById('newUsername').value.trim();
    const password = document.getElementById('newPassword').value;
    const role     = document.getElementById('newRole').value;
    const city     = document.getElementById('newCity').value.trim() || null;

    const res  = await fetch(`${API_BASE}/add_user`, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader()),
        body: JSON.stringify({ username, password, role, city })
    });
    const data = await res.json();
    if (res.ok) {
        showStatus('User created: ' + username, 'success');
        document.getElementById('newUsername').value = '';
        document.getElementById('newPassword').value = '';
        await populateUsers();
    } else {
        showStatus(data.message || 'Error creating user', 'danger');
    }
}

async function populateUsers() {
    const res = await fetch(`${API_BASE}/users`, { headers: authHeader() });
    if (!res.ok) return;
    const users = await res.json();
    const list  = document.getElementById('userList');
    if (!list) return;
    list.innerHTML = '';
    users.forEach(u => {
        const div = document.createElement('div');
        div.className = 'user-item';
        div.innerHTML = `
            <i class="fa-regular fa-user"></i>
            <span>${u.username}</span>
            ${u.city ? `<span style="font-size:12px;color:var(--text-muted)">(${u.city})</span>` : ''}
            <span class="role-pill rp-${u.role}">${u.role}</span>
        `;
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

    // Update inventory label to reflect current city context
    const label = document.getElementById('inventoryLabel');
    label.textContent = city ? `Trees — ${city}` : 'Tree Inventory';

    const res = await fetch(`${API_BASE}/trees?${params}`, { headers: authHeader() });
    if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        showStatus(d.message || 'Error fetching trees', 'danger');
        return;
    }

    state.allTrees    = await res.json();
    state.currentPage = 1;

    // Reset the ID filter when city changes
    document.getElementById('idFilter').value = '';
    applyIdFilter();

    if (state.activeTab === 'map') showOnMap(state.allTrees);
}

// ─── Trees: sort ─────────────────────────────────────────

const COND_ORDER = { good: 0, excellent: 0, fair: 1, moderate: 1, poor: 2, critical: 2, dead: 3 };

function condSortVal(cond) {
    if (!cond) return 99;
    const c = cond.toLowerCase();
    for (const [key, val] of Object.entries(COND_ORDER)) {
        if (c.includes(key)) return val;
    }
    return 99;
}

function sortTrees(trees, field, dir) {
    return [...trees].sort((a, b) => {
        let va, vb;
        if (field === 'condition') {
            va = condSortVal(a.condition);
            vb = condSortVal(b.condition);
        } else if (field === 'latitude') {
            va = parseFloat(a.latitude) || 0;
            vb = parseFloat(b.latitude) || 0;
        } else if (field === 'next_check') {
            va = a.next_check || '';
            vb = b.next_check || '';
        } else {
            va = (a[field] || '').toLowerCase();
            vb = (b[field] || '').toLowerCase();
        }
        if (va < vb) return dir === 'asc' ? -1 : 1;
        if (va > vb) return dir === 'asc' ?  1 : -1;
        return 0;
    });
}

function applySort(field) {
    if (state.sortField === field) {
        state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        state.sortField = field;
        state.sortDir   = 'asc';
    }
    state.currentPage = 1;
    renderPage();
}

function updateSortHeaders() {
    document.querySelectorAll('th.sortable').forEach(th => {
        const f   = th.dataset.sort;
        const ico = th.querySelector('.sort-ico');
        if (!ico) return;
        if (f === state.sortField) {
            ico.className = `sort-ico fa-solid fa-sort-${state.sortDir === 'asc' ? 'up' : 'down'}`;
            th.classList.add('sort-active');
        } else {
            ico.className = 'sort-ico fa-solid fa-sort';
            th.classList.remove('sort-active');
        }
    });
}

// ─── Trees: client-side filter + pagination ───────────────

function applyIdFilter() {
    const q = document.getElementById('idFilter').value.trim().toLowerCase();
    state.filteredTrees = q
        ? state.allTrees.filter(t => t.custom_id.toLowerCase().includes(q))
        : state.allTrees;
    state.currentPage = 1;
    renderPage();
}

function changePageSize() {
    state.pageSize    = parseInt(document.getElementById('pageSizeSelect').value);
    state.currentPage = 1;
    renderPage();
}

function goToPage(page) {
    state.currentPage = page;
    renderPage();
}

function renderPage() {
    let trees = state.filteredTrees;
    if (state.sortField) trees = sortTrees(trees, state.sortField, state.sortDir);
    const { currentPage, pageSize } = state;
    const start = (currentPage - 1) * pageSize;
    renderTreeList(trees.slice(start, start + pageSize));
    renderPagination();
    updateSortHeaders();

    const total    = state.allTrees.length;
    const filtered = state.filteredTrees.length;
    document.getElementById('treeCount').textContent =
        filtered < total ? `${filtered} / ${total}` : total;
}

function renderPagination() {
    const total      = state.filteredTrees.length;
    const totalPages = Math.ceil(total / state.pageSize);
    const cur        = state.currentPage;
    const start      = (cur - 1) * state.pageSize + 1;
    const end        = Math.min(cur * state.pageSize, total);

    const bar = document.getElementById('paginationBar');
    bar.style.display = total > 0 ? 'flex' : 'none';

    document.getElementById('pagingInfo').textContent =
        total === 0 ? '' : `Showing ${start}–${end} of ${total} tree${total !== 1 ? 's' : ''}`;

    const pag = document.getElementById('pagination');
    pag.innerHTML = '';
    if (totalPages <= 1) return;

    const mkBtn = (label, page, active = false, disabled = false) => {
        const b = document.createElement('button');
        b.className = `btn btn-sm ${active ? 'btn-primary' : 'btn-outline'}`;
        b.innerHTML = label;
        b.style.minWidth = '34px';
        if (disabled) { b.disabled = true; b.style.opacity = '.38'; }
        else b.addEventListener('click', () => goToPage(page));
        return b;
    };

    const mkDots = () => {
        const s = document.createElement('span');
        s.textContent = '…';
        s.style.cssText = 'padding:0 4px;color:var(--text-muted);font-size:13px;';
        return s;
    };

    pag.appendChild(mkBtn('‹', cur - 1, false, cur === 1));

    let pages;
    if (totalPages <= 7) {
        pages = Array.from({ length: totalPages }, (_, i) => i + 1);
    } else {
        pages = [1];
        if (cur > 3)              pages.push('…');
        for (let p = Math.max(2, cur - 1); p <= Math.min(totalPages - 1, cur + 1); p++) pages.push(p);
        if (cur < totalPages - 2) pages.push('…');
        pages.push(totalPages);
    }

    pages.forEach(p => {
        pag.appendChild(p === '…' ? mkDots() : mkBtn(p, p, p === cur));
    });

    pag.appendChild(mkBtn('›', cur + 1, false, cur === totalPages));
}

// ─── Trees: render rows ───────────────────────────────────

function condClass(cond) {
    if (!cond) return 'tr-other';
    const c = cond.toLowerCase();
    if (c.includes('good') || c.includes('excel')) return 'tr-good';
    if (c.includes('fair') || c.includes('moder')) return 'tr-fair';
    if (c.includes('poor') || c.includes('crit')  || c.includes('dead')) return 'tr-poor';
    return 'tr-other';
}

function condBadge(cond) {
    if (!cond) return `<span class="cond-badge cb-other">—</span>`;
    const c = cond.toLowerCase();
    let cls = 'cb-other', icon = 'fa-circle';
    if      (c.includes('good') || c.includes('excel')) { cls = 'cb-good'; icon = 'fa-circle-check'; }
    else if (c.includes('fair') || c.includes('moder')) { cls = 'cb-fair'; icon = 'fa-circle-exclamation'; }
    else if (c.includes('poor') || c.includes('crit') || c.includes('dead')) { cls = 'cb-poor'; icon = 'fa-circle-xmark'; }
    return `<span class="cond-badge ${cls}"><i class="fa-solid ${icon}"></i> ${cond}</span>`;
}

function renderTreeList(trees) {
    const tbody = document.getElementById('treeList');
    tbody.innerHTML = '';

    if (trees.length === 0) {
        const q = document.getElementById('idFilter').value.trim();
        tbody.innerHTML = `<tr><td colspan="7">
            <div class="empty-state">
                <i class="fa-solid fa-tree"></i>
                <p>${q ? `No trees match ID "<strong>${q}</strong>" — try a different filter.` : 'No trees found. Select a city above, then use <strong>Add Tree</strong> to add the first one.'}</p>
            </div>
        </td></tr>`;
        return;
    }

    trees.forEach(t => {
        const tr  = document.createElement('tr');
        tr.className = `tree-row ${condClass(t.condition)}`;
        const addr = [t.address, t.city].filter(Boolean).join(' — ');
        const coords = (t.latitude && t.longitude)
            ? `<span class="coords-chip">${parseFloat(t.latitude).toFixed(4)},&thinsp;${parseFloat(t.longitude).toFixed(4)}</span>`
            : '<span style="color:var(--text-muted)">—</span>';
        tr.innerHTML = `
            <td><span class="id-chip">${t.custom_id}</span></td>
            <td><span class="species">${t.species}</span></td>
            <td>${condBadge(t.condition)}</td>
            <td><span class="addr" title="${addr}">${addr || '—'}</span></td>
            <td>${coords}</td>
            <td style="font-size:13px;color:var(--text-mid)">${t.next_check || '—'}</td>
            <td>
                <div class="act-cell">
                    <button class="btn btn-edit btn-sm" onclick="openHistory(${t.id}, '${t.custom_id}')" title="Inspection history">
                        <i class="fa-solid fa-clock-rotate-left"></i>
                    </button>
                    <button class="btn btn-edit btn-sm" onclick="openEditForm(${t.id})" title="Edit">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    <button class="btn btn-danger btn-sm" onclick="deleteTreeById(${t.id})" title="Delete">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// ─── Tree CRUD ────────────────────────────────────────────

async function fetchTreeById(id) {
    const res  = await fetch(`${API_BASE}/tree/${id}`, { headers: authHeader() });
    const data = await res.json();
    if (!res.ok) { showStatus(data.message || 'Tree not found', 'danger'); return null; }
    return data;
}

function fillForm(data) {
    document.getElementById('formTitle').innerHTML =
        `<i class="fa-solid fa-pen-to-square"></i> Edit — ${data.custom_id}`;
    document.getElementById('editTreeId').value         = data.id;
    document.getElementById('custom_id').value          = data.custom_id;
    document.getElementById('city').value               = data.city;
    document.getElementById('address').value            = data.address || '';
    document.getElementById('latitude').value           = data.latitude  || '';
    document.getElementById('longitude').value          = data.longitude || '';
    document.getElementById('species').value            = data.species;
    document.getElementById('condition').value          = data.condition;
    document.getElementById('comments').value           = data.comments || '';
    document.getElementById('height').value             = data.height   || '';
    document.getElementById('trunk_diameter_cm').value  = data.trunk_diameter_cm || '';
    document.getElementById('crown_diameter_m').value   = data.crown_diameter_m  || '';
    document.getElementById('age').value                = data.age      || '';
    document.getElementById('actions').value            = data.actions  || '';
    document.getElementById('location').value           = data.location || '';
    document.getElementById('cpc').value                = data.cpc      || '';
    document.getElementById('next_check').value         = data.next_check || '';
    document.getElementById('formSubmitButton').innerHTML =
        '<i class="fa-solid fa-floppy-disk"></i> Save Changes';
}

async function openEditForm(id) {
    const tree = await fetchTreeById(id);
    if (!tree) return;
    fillForm(tree);
    switchTab('trees');
    showTreeView('edit');
}

async function deleteTreeById(id) {
    if (!confirm('Delete this tree from the database?')) return;
    const res  = await fetch(`${API_BASE}/tree/${id}`, {
        method: 'DELETE', headers: authHeader()
    });
    const data = await res.json();
    if (res.ok) {
        // remove from local state so we don't need a round-trip
        state.allTrees      = state.allTrees.filter(t => t.id !== id);
        state.filteredTrees = state.filteredTrees.filter(t => t.id !== id);
        showStatus('Tree deleted', 'success');
        renderPage();
        if (state.activeTab === 'map') showOnMap(state.allTrees);
    } else {
        showStatus(data.message || 'Error deleting', 'danger');
    }
}

async function submitTreeForm(e) {
    e.preventDefault();
    const editId  = document.getElementById('editTreeId').value;
    const payload = {
        custom_id:         document.getElementById('custom_id').value,
        city:              document.getElementById('city').value,
        address:           document.getElementById('address').value,
        latitude:          document.getElementById('latitude').value  || null,
        longitude:         document.getElementById('longitude').value || null,
        species:           document.getElementById('species').value,
        condition:         document.getElementById('condition').value,
        comments:          document.getElementById('comments').value,
        actions:           document.getElementById('actions').value,
        height:            document.getElementById('height').value,
        trunk_diameter_cm: document.getElementById('trunk_diameter_cm').value || null,
        crown_diameter_m:  document.getElementById('crown_diameter_m').value  || null,
        age:               document.getElementById('age').value,
        location:          document.getElementById('location').value,
        cpc:               document.getElementById('cpc').value,
        next_check:        document.getElementById('next_check').value || null
    };

    const url    = editId ? `${API_BASE}/tree/${editId}` : `${API_BASE}/add_tree`;
    const method = editId ? 'PATCH' : 'POST';

    const res  = await fetch(url, {
        method,
        headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader()),
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
        showStatus(editId ? 'Tree updated' : 'Tree added', 'success');
        resetForm();
        showTreeView('list');
        fetchTrees();
    } else {
        showStatus(data.message || JSON.stringify(data), 'danger');
    }
}

function resetForm() {
    document.getElementById('addTreeForm').reset();
    document.getElementById('editTreeId').value = '';
    document.getElementById('formTitle').innerHTML =
        '<i class="fa-solid fa-seedling"></i> Add New Tree';
    document.getElementById('formSubmitButton').innerHTML =
        '<i class="fa-solid fa-floppy-disk"></i> Save Tree';
    document.getElementById('gpsStatus').textContent = '';
}

// ─── GPS ──────────────────────────────────────────────────

function getLocation() {
    if (!navigator.geolocation) return showStatus('Geolocation not supported', 'danger');
    document.getElementById('gpsStatus').textContent = 'Acquiring GPS signal…';
    navigator.geolocation.getCurrentPosition(async pos => {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        document.getElementById('latitude').value  = lat;
        document.getElementById('longitude').value = lon;
        document.getElementById('gpsStatus').textContent = 'Resolving address…';
        if (state.token) {
            const res = await fetch(`${API_BASE}/reverse_geocode`, {
                method: 'POST',
                headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader()),
                body: JSON.stringify({ latitude: lat, longitude: lon })
            });
            if (res.ok) {
                const geo = await res.json();
                if (geo.address) document.getElementById('address').value = geo.address;
                if (geo.city && !document.getElementById('city').value)
                    document.getElementById('city').value = geo.city;
            }
        }
        document.getElementById('gpsStatus').textContent =
            `GPS: ${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    }, err => {
        document.getElementById('gpsStatus').textContent = '';
        showStatus('GPS error: ' + err.message, 'danger');
    });
}

// ─── Map ──────────────────────────────────────────────────


function showOnMap(trees) {
    state.markers.forEach(m => state.map.removeLayer(m));
    state.markers = [];
    trees.forEach(t => {
        if (!t.latitude || !t.longitude) return;
        const icon = L.divIcon({
            className: '',
            html: `<div style="background:var(--g800);color:#fff;border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,.3)"><i class="fa-solid fa-tree"></i></div>`,
            iconSize: [30, 30], iconAnchor: [15, 15]
        });
        const m = L.marker([t.latitude, t.longitude], { icon })
            .addTo(state.map)
            .bindPopup(`
                <strong>${t.custom_id}</strong><br>
                <em>${t.species}</em><br>
                ${condBadge(t.condition)}<br>
                <span style="font-size:12px;color:#555">${t.address || t.city || ''}</span>
            `);
        state.markers.push(m);
    });
    if (state.markers.length > 0)
        state.map.fitBounds(L.featureGroup(state.markers).getBounds().pad(0.12));
}

// ─── Inspection history ───────────────────────────────────

function openHistory(treeId, customId) {
    document.getElementById('inspTreeId').value    = treeId;
    document.getElementById('inspDate').value      = new Date().toISOString().split('T')[0];
    document.getElementById('inspCondition').value = '';
    document.getElementById('inspComments').value  = '';
    document.getElementById('inspActions').value   = '';

    document.getElementById('historyTitle').innerHTML =
        `<i class="fa-solid fa-clock-rotate-left"></i> ${customId} — History`;
    document.getElementById('timelineContent').innerHTML =
        `<div class="tl-empty"><i class="fa-solid fa-spinner fa-spin"></i><p>Loading…</p></div>`;

    switchTab('trees');
    showTreeView('history');
    loadHistory(treeId);
}

async function loadHistory(treeId) {
    const res = await fetch(`${API_BASE}/tree/${treeId}/inspections`, {
        headers: authHeader()
    });
    if (!res.ok) {
        document.getElementById('timelineContent').innerHTML =
            `<div class="tl-empty"><i class="fa-solid fa-circle-exclamation"></i><p>Could not load history.</p></div>`;
        return;
    }
    renderTimeline(await res.json());
}

function formatDate(str) {
    if (!str) return '—';
    const d = new Date(str + 'T12:00:00');
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function tlDotClass(cond) {
    if (!cond) return 'tl-dot-other';
    const c = cond.toLowerCase();
    if (c.includes('good') || c.includes('excel')) return 'tl-dot-good';
    if (c.includes('fair') || c.includes('moder')) return 'tl-dot-fair';
    if (c.includes('poor') || c.includes('crit') || c.includes('dead')) return 'tl-dot-poor';
    return 'tl-dot-other';
}

function renderTimeline(inspections) {
    const wrap = document.getElementById('timelineContent');
    if (!inspections.length) {
        wrap.innerHTML = `<div class="tl-empty">
            <i class="fa-regular fa-clock"></i>
            <p>No inspections recorded yet.</p>
        </div>`;
        return;
    }

    wrap.innerHTML = '<div class="tl-divider">Most recent first</div>' +
        inspections.map((insp, idx) => `
        <div class="tl-item">
            <div class="tl-dot ${tlDotClass(insp.condition)}"></div>
            <div class="tl-card">
                <div class="tl-header">
                    <span class="tl-date">${formatDate(insp.date)}</span>
                    ${condBadge(insp.condition)}
                    ${idx === 0 ? '<span class="tl-latest-tag">Latest</span>' : ''}
                </div>
                ${insp.comments
                    ? `<div class="tl-body">${insp.comments}</div>`
                    : ''}
                ${insp.actions
                    ? `<div class="tl-actions"><i class="fa-solid fa-scissors"></i>${insp.actions}</div>`
                    : ''}
                <div class="tl-inspector">
                    <i class="fa-regular fa-user"></i>${insp.inspector_name || 'Unknown'}
                </div>
            </div>
        </div>
    `).join('');
}

async function submitInspection() {
    const treeId = document.getElementById('inspTreeId').value;
    if (!treeId) return;

    const payload = {
        date:      document.getElementById('inspDate').value,
        condition: document.getElementById('inspCondition').value.trim() || null,
        comments:  document.getElementById('inspComments').value.trim(),
        actions:   document.getElementById('inspActions').value.trim()
    };

    const res  = await fetch(`${API_BASE}/tree/${treeId}/inspections`, {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader()),
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
        showStatus('Inspection logged', 'success');
        document.getElementById('inspCondition').value = '';
        document.getElementById('inspComments').value  = '';
        document.getElementById('inspActions').value   = '';
        loadHistory(parseInt(treeId));   // reload timeline
    } else {
        showStatus(data.message || 'Error logging inspection', 'danger');
    }
}

// ─── Export ───────────────────────────────────────────────

async function exportExcel() {
    if (!state.token) return showStatus('Please log in first', 'danger');
    showStatus('Preparing Excel…', 'info');
    const res = await fetch(`${API_BASE}/export/excel`, { headers: authHeader() });
    if (!res.ok) return showStatus('Export failed', 'danger');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob());
    a.download = 'trees.xlsx'; a.click();
    URL.revokeObjectURL(a.href);
    showStatus('Excel file downloaded', 'success');
}

async function exportGeoJSON() {
    if (!state.token) return showStatus('Please log in first', 'danger');
    showStatus('Preparing GeoJSON…', 'info');
    const res = await fetch(`${API_BASE}/export/geojson`, { headers: authHeader() });
    if (!res.ok) return showStatus('Export failed', 'danger');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob());
    a.download = 'trees.geojson'; a.click();
    URL.revokeObjectURL(a.href);
    showStatus('GeoJSON downloaded — drag into QGIS to import', 'success');
}

// ─── Status toast ─────────────────────────────────────────

let _statusTimer = null;
function showStatus(msg, level = 'info') {
    const el = document.getElementById('status');
    const bg = { success: '#2d6a4f', danger: '#c0392b', warning: '#856404', info: '#1a5276' };
    el.textContent = msg;
    el.style.background = bg[level] || bg.info;
    el.style.color = '#fff';
    el.classList.add('show');
    clearTimeout(_statusTimer);
    _statusTimer = setTimeout(() => el.classList.remove('show'), 5000);
}

// ─── Boot ─────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Login
    document.getElementById('loginBtn').addEventListener('click', login);
    document.getElementById('loginPassword').addEventListener('keydown',
        e => e.key === 'Enter' && login());

    // Tabs
    document.querySelectorAll('.tab-btn').forEach(btn =>
        btn.addEventListener('click', () => switchTab(btn.dataset.tab)));

    // Sort headers
    document.querySelectorAll('th.sortable').forEach(th =>
        th.addEventListener('click', () => applySort(th.dataset.sort)));

    // Nav
    document.getElementById('logoutBtn').addEventListener('click', logout);
    document.getElementById('refreshCitiesBtn').addEventListener('click', populateCities);
    document.getElementById('streetSearch').addEventListener('keydown',
        e => e.key === 'Enter' && fetchTrees());

    // Management
    document.getElementById('createUserBtn').addEventListener('click', createUser);
    document.getElementById('createCityBtn').addEventListener('click', createCity);

    // ID filter (live as-you-type)
    document.getElementById('idFilter').addEventListener('input', applyIdFilter);
    document.getElementById('pageSizeSelect').addEventListener('change', changePageSize);

    // Form
    document.getElementById('addTreeForm').addEventListener('submit', submitTreeForm);
    document.getElementById('openFormBtn').addEventListener('click', () => {
        resetForm();
        showTreeView('edit');
    });

    // Export
    document.getElementById('exportExcelBtn').addEventListener('click', exportExcel);
    document.getElementById('exportGeoJSONBtn').addEventListener('click', exportGeoJSON);

    init();
});

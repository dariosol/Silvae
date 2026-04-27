// app.js - Frontend logic for login, role-aware UI, and tree CRUD.
// Adjust the API_BASE if your server runs on a different host/port.
const API_BASE = 'http://localhost:5000'

let state = {
    token: localStorage.getItem('token') || null,
    user: JSON.parse(localStorage.getItem('user') || 'null'),
    mapVisible: false,
    map: null,
    markers: []
};

function authHeader() {
    if (!state.token) return {};
    return { 'Authorization': `Bearer ${state.token}` };
}

async function init() {
    await populateCities();
    setupAuthUI();
    fetchTrees();
}

function setupAuthUI() {
    const authDiv = document.getElementById('authSection');
    const loggedInDiv = document.getElementById('loggedInSection');
    const usernameSpan = document.getElementById('loggedInUser');

    if (state.token && state.user) {
        authDiv.style.display = 'none';
        loggedInDiv.style.display = 'block';
        usernameSpan.textContent = `${state.user.username} (${state.user.role}${state.user.city ? ' - ' + state.user.city : ''})`;
        showRoleFeatures(state.user.role);
    } else {
        authDiv.style.display = 'block';
        loggedInDiv.style.display = 'none';
        showRoleFeatures(null);
    }
}

function showRoleFeatures(role) {
    // Show/hide management UI elements based on role
    document.getElementById('userManagement').style.display = (role === 'superuser' || role === 'city') ? 'block' : 'none';
    document.getElementById('cityManagement').style.display = (role === 'superuser') ? 'block' : 'none';
}

async function login() {
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    const res = await fetch(`${API_BASE}/login`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username, password})
    });
    const data = await res.json();
    if (res.ok) {
        state.token = data.token;
        state.user = data.user;
        localStorage.setItem('token', state.token);
        localStorage.setItem('user', JSON.stringify(state.user));
        setupAuthUI();
        fetchTrees();
        showStatus('Logged in', 'success');
    } else {
        showStatus(data.message || 'Login failed', 'danger');
    }
}

function logout() {
    state.token = null;
    state.user = null;
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setupAuthUI();
    showStatus('Logged out', 'secondary');
}

async function createUser() {
    // Only visible to superuser or city
    const username = document.getElementById('newUsername').value;
    const password = document.getElementById('newPassword').value;
    const role = document.getElementById('newRole').value;
    let city = document.getElementById('newCity').value;
    if (!city) city = null;

    const res = await fetch(`${API_BASE}/add_user`, {
        method: 'POST',
        headers: Object.assign({'Content-Type': 'application/json'}, authHeader()),
        body: JSON.stringify({username, password, role, city})
    });
    const data = await res.json();
    if (res.ok) {
        showStatus('User created', 'success');
        document.getElementById('newUsername').value = '';
        document.getElementById('newPassword').value = '';
        await populateUsers();
        await populateCities(); // in case city user creation created a city association
    } else {
        showStatus(data.message || JSON.stringify(data), 'danger');
    }
}

async function createCity() {
    const name = document.getElementById('cityName').value;
    if (!name) return showStatus('City name required', 'danger');
    const res = await fetch(`${API_BASE}/admin/cities`, {
        method: 'POST',
        headers: Object.assign({'Content-Type': 'application/json'}, authHeader()),
        body: JSON.stringify({name})
    });
    const data = await res.json();
    if (res.ok) {
        showStatus('City created', 'success');
        document.getElementById('cityName').value = '';
        await populateCities();
    } else {
        showStatus(data.message || JSON.stringify(data), 'danger');
    }
}

async function populateCities() {
    const sel = document.getElementById('citySelect');
    sel.innerHTML = '<option value="">-- Choose a city --</option>';
    const res = await fetch(`${API_BASE}/cities`);
    if (!res.ok) return;
    const cities = await res.json();
    cities.forEach(c => {
        const o = document.createElement('option');
        o.value = c;
        o.text = c;
        sel.appendChild(o);
    });

    // also update newCity input options for creating users
    const newCityInput = document.getElementById('newCityDatalist');
    if (newCityInput) {
        newCityInput.innerHTML = '';
        cities.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c;
            newCityInput.appendChild(opt);
        });
    }
}

async function fetchTrees() {
    const city = document.getElementById('citySelect').value;
    const addressPart = document.getElementById('streetSearch').value;
    const params = new URLSearchParams();
    if (city) params.append('city', city);
    if (addressPart) params.append('address', addressPart);

    const res = await fetch(`${API_BASE}/trees?${params.toString()}`, {
        headers: authHeader()
    });
    if (!res.ok) {
        const d = await res.json().catch(()=>({message:'error'}));
        showStatus(d.message || 'Error fetching trees', 'danger');
        return;
    }
    const trees = await res.json();
    renderTreeList(trees);
    if (state.mapVisible) showOnMap(trees);
}

function renderTreeList(trees) {
    const tbody = document.getElementById('treeList');
    tbody.innerHTML = '';
    trees.forEach(t => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${t.id}</td>
            <td>${t.custom_id}</td>
            <td>${t.species}</td>
            <td>${t.condition}</td>
            <td>${t.address || ''} ${t.city ? '(' + t.city + ')' : ''}</td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="populateEditForm(${t.id})">Edit</button>
                <button class="btn btn-sm btn-danger" onclick="deleteTreeById(${t.id})">Delete</button>
                <button class="btn btn-sm btn-secondary" onclick="fetchTreeById(${t.id})">View</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

async function fetchTreeById(id) {
    const res = await fetch(`${API_BASE}/tree/${id}`, {
        headers: authHeader()
    });
    const data = await res.json();
    if (!res.ok) {
        showStatus(data.message || 'Error', 'danger');
        return;
    }
    // populate form for edit
    document.getElementById('formTitle').textContent = `🌿 Edit Tree #${id}`;
    document.getElementById('editTreeId').value = data.id;
    document.getElementById('custom_id').value = data.custom_id;
    document.getElementById('city').value = data.city;
    document.getElementById('address').value = data.address;
    document.getElementById('latitude').value = data.latitude || '';
    document.getElementById('longitude').value = data.longitude || '';
    document.getElementById('species').value = data.species;
    document.getElementById('condition').value = data.condition;
    document.getElementById('comments').value = data.comments || '';
    document.getElementById('height').value = data.height || '';
    document.getElementById('trunk_diameter_cm').value = data.trunk_diameter_cm || '';
    document.getElementById('crown_diameter_m').value = data.crown_diameter_m || '';
    document.getElementById('age').value = data.age || '';
    document.getElementById('actions').value = data.actions || '';
    document.getElementById('location').value = data.location || '';
    document.getElementById('cpc').value = data.cpc || '';
    document.getElementById('next_check').value = data.next_check || '';
    document.getElementById('formSubmitButton').textContent = 'Save Changes';
}

async function deleteTreeById(id) {
    if (!confirm('Delete tree?')) return;
    const res = await fetch(`${API_BASE}/tree/${id}`, {
        method: 'DELETE',
        headers: authHeader()
    });
    const data = await res.json();
    if (res.ok) {
        showStatus('Tree deleted', 'success');
        fetchTrees();
    } else {
        showStatus(data.message || 'Error deleting', 'danger');
    }
}

async function submitTreeForm(e) {
    e.preventDefault();
    const editId = document.getElementById('editTreeId').value;
    const payload = {
        custom_id: document.getElementById('custom_id').value,
        city: document.getElementById('city').value,
        address: document.getElementById('address').value,
        latitude: document.getElementById('latitude').value,
        longitude: document.getElementById('longitude').value,
        species: document.getElementById('species').value,
        condition: document.getElementById('condition').value,
        comments: document.getElementById('comments').value,
        actions: document.getElementById('actions').value,
        height: document.getElementById('height').value,
        trunk_diameter_cm: document.getElementById('trunk_diameter_cm').value || null,
        crown_diameter_m: document.getElementById('crown_diameter_m').value || null,
        age: document.getElementById('age').value,
        location: document.getElementById('location').value,
        cpc: document.getElementById('cpc').value,
        next_check: document.getElementById('next_check').value || null
    };

    if (editId) {
        // PATCH
        const res = await fetch(`${API_BASE}/tree/${editId}`, {
            method: 'PATCH',
            headers: Object.assign({'Content-Type': 'application/json'}, authHeader()),
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            showStatus('Tree updated', 'success');
            resetForm();
            fetchTrees();
        } else {
            showStatus(data.message || 'Error updating', 'danger');
        }
    } else {
        // POST add
        const res = await fetch(`${API_BASE}/add_tree`, {
            method: 'POST',
            headers: Object.assign({'Content-Type': 'application/json'}, authHeader()),
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            showStatus('Tree added', 'success');
            resetForm();
            fetchTrees();
        } else {
            showStatus(data.message || JSON.stringify(data), 'danger');
        }
    }
}

function resetForm() {
    document.getElementById('addTreeForm').reset();
    document.getElementById('editTreeId').value = '';
    document.getElementById('formTitle').textContent = '🌿 Add a New Tree';
    document.getElementById('formSubmitButton').textContent = '🌳 Add Tree';
}

function getLocation() {
    if (!navigator.geolocation) return showStatus('Geolocation not supported', 'danger');
    navigator.geolocation.getCurrentPosition((pos) => {
        document.getElementById('latitude').value = pos.coords.latitude;
        document.getElementById('longitude').value = pos.coords.longitude;
    }, err => showStatus('Could not get location: ' + err.message, 'danger'));
}

function showStatus(msg, level = 'info') {
    const el = document.getElementById('status');
    el.textContent = msg;
    el.className = `mt-2 alert alert-${level}`;
    setTimeout(()=> {
        el.textContent = '';
        el.className = '';
    }, 6000);
}

// Map functions
function toggleMap() {
    state.mapVisible = !state.mapVisible;
    const mdiv = document.getElementById('map');
    mdiv.style.display = state.mapVisible ? 'block' : 'none';
    if (state.mapVisible && !state.map) {
        state.map = L.map('map').setView([45.4642, 9.19], 12); // default coords (Milan)
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19
        }).addTo(state.map);
    }
    fetchTrees();
}

function showOnMap(trees) {
    // clear markers
    state.markers.forEach(m => state.map.removeLayer(m));
    state.markers = [];

    trees.forEach(t => {
        if (!t.latitude || !t.longitude) return;
        const m = L.marker([t.latitude, t.longitude]).addTo(state.map)
            .bindPopup(`<b>${t.custom_id}</b><br>${t.species}<br>${t.address || ''}`);
        state.markers.push(m);
    });
}

// populate edit with minimal check
function populateEditForm(id) {
    fetchTreeById(id);
    window.scrollTo({top: 0, behavior: 'smooth'});
}

// populate users (optional)
async function populateUsers() {
    const res = await fetch(`${API_BASE}/users`, {headers: authHeader()});
    if (!res.ok) return;
    const users = await res.json();
    const list = document.getElementById('userList');
    if (!list) return;
    list.innerHTML = '';
    users.forEach(u => {
        const li = document.createElement('li');
        li.className = 'list-group-item';
        li.textContent = `${u.username} — ${u.role}${u.city ? ' ('+u.city+')' : ''}`;
        list.appendChild(li);
    });
}

// Wire up forms and buttons
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('addTreeForm').addEventListener('submit', submitTreeForm);
    document.getElementById('loginBtn').addEventListener('click', login);
    document.getElementById('logoutBtn').addEventListener('click', logout);
    document.getElementById('createUserBtn').addEventListener('click', createUser);
    document.getElementById('createCityBtn').addEventListener('click', createCity);
    document.getElementById('refreshCitiesBtn').addEventListener('click', populateCities);

    init();
});

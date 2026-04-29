"""
Unit tests for the Tree Management API.

Run with:
    python -m pytest test_flask_api.py -v

The tests use Flask's built-in test client — no running server needed.
They share the real PostgreSQL database but clean up any data they create.
"""
import json
import pytest
from app import app as flask_app, db, User, Tree

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session', autouse=True)
def ensure_admin():
    """Make sure admin / password exists before any test runs."""
    with flask_app.app_context():
        admin = User.query.filter_by(username='admin').first()
        if admin:
            admin.set_password('password')
        else:
            admin = User(username='admin', role='superuser', city=None)
            admin.set_password('password')
            db.session.add(admin)
        db.session.commit()


@pytest.fixture(scope='session')
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture(scope='session')
def admin_token(client):
    res = client.post('/login', json={'username': 'admin', 'password': 'password'})
    assert res.status_code == 200, f"Admin login failed: {res.get_json()}"
    return res.get_json()['token']


@pytest.fixture
def auth_headers(admin_token):
    return {'Authorization': f'Bearer {admin_token}'}


# Base test tree (plain, no ARETE fields)
TEST_TREE = {
    'custom_id': 'PYTEST-001',
    'species': 'Quercus robur - farnia',
    'condition': 'Good',
    'city': 'TestCity',
    'latitude': 45.4642,
    'longitude': 9.1900,
    'address': 'Via Test 1, TestCity',
}

# Test tree with full ARETE ORD fields
ARETE_TREE = {
    'custom_id': 'PYTEST-ARETE-001',
    'species': 'Platanus x acerifolia - platano ibrido',
    'condition': 'monitoraggio',
    'city': 'TestCity',
    'latitude': 45.4642,
    'longitude': 9.1900,
    'address': 'Via ARETE 1, TestCity',
    # Dati generali
    'dimora': 'alberata stradale',
    'stadio_sviluppo': 'albero adulto',
    'posizione_sociale': 'dominante interna',
    'localizzazione': 'centro città',
    'vincoli': 'paesaggistico',
    # Misure ORD
    'tree_height_m': 16.5,
    'circonferenza_cm': 130.0,
    'crown_diameter_m': 8.0,
    'branch_diam_cm': 10.0,
    'branch_length_m': 3.5,
    'branch_height_m': 9.0,
    'target_height_m': 1.8,
    # Pericolo / Bersaglio
    'pericolo_rami': '4',
    'pericolo_tronco': '5',
    'pericolo_colletto': '6',
    'pericolo_zolla': '5',
    'bersaglio_chioma': 3,
    'bersaglio_ramo': 3,
    # Diagnosi
    'diag_zolla': [
        {'caratt': 'compattazione', 'giudizio': 's'},
        {'caratt': 'radici affioranti', 'giudizio': 'ps'},
    ],
    'diag_fusto': [
        {'caratt': 'carie', 'giudizio': 'ms'},
    ],
    'diag_chioma': [],
    # Multi-selects
    'conflitti_list': ['asfalto', 'marciapiedi'],
    'agenti_carie': ['Ganoderma applanatum'],
    'prescrizioni_val': ['valutaz ordinaria'],
    'prescrizioni_col': ['7) rimonda del seccume (in conformità con EAS)'],
    'monitoraggio': '1 anno',
    'urgenza': '< 6 mesi',
}

# Minimal payload for risk calculation tests
RISK_PAYLOAD = {
    'tree_height_m': 16.5,
    'circonferenza_cm': 130.0,
    'crown_diameter_m': 8.0,
    'branch_diam_cm': 10.0,
    'branch_length_m': 3.5,
    'branch_height_m': 9.0,
    'target_height_m': 1.8,
    'pericolo_rami': 4,
    'pericolo_tronco': 5,
    'pericolo_colletto': 6,
    'pericolo_zolla': 5,
    'bersaglio_chioma': 3,
    'bersaglio_ramo': 3,
}


@pytest.fixture
def added_tree_id(client, auth_headers):
    """Add a plain test tree, yield its id, delete on teardown."""
    with flask_app.app_context():
        leftover = Tree.query.filter_by(custom_id=TEST_TREE['custom_id']).first()
        if leftover:
            db.session.delete(leftover); db.session.commit()

    res = client.post('/add_tree', json=TEST_TREE, headers=auth_headers)
    assert res.status_code == 201, f"Setup failed: {res.get_json()}"
    tree_id = res.get_json()['tree_id']
    yield tree_id

    with flask_app.app_context():
        t = db.session.get(Tree, tree_id)
        if t: db.session.delete(t); db.session.commit()


@pytest.fixture
def added_arete_tree_id(client, auth_headers):
    """Add a full-ARETE test tree, yield its id, delete on teardown."""
    with flask_app.app_context():
        leftover = Tree.query.filter_by(custom_id=ARETE_TREE['custom_id']).first()
        if leftover:
            db.session.delete(leftover); db.session.commit()

    res = client.post('/add_tree', json=ARETE_TREE, headers=auth_headers)
    assert res.status_code == 201, f"ARETE tree setup failed: {res.get_json()}"
    tree_id = res.get_json()['tree_id']
    yield tree_id

    with flask_app.app_context():
        t = db.session.get(Tree, tree_id)
        if t: db.session.delete(t); db.session.commit()


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------

class TestAuthentication:
    def test_login_success(self, client):
        res = client.post('/login', json={'username': 'admin', 'password': 'password'})
        assert res.status_code == 200
        data = res.get_json()
        assert 'token' in data
        assert data['user']['username'] == 'admin'
        assert data['user']['role'] == 'superuser'

    def test_login_wrong_password(self, client):
        res = client.post('/login', json={'username': 'admin', 'password': 'wrongpassword'})
        assert res.status_code == 401

    def test_login_unknown_user(self, client):
        res = client.post('/login', json={'username': 'nobody', 'password': 'x'})
        assert res.status_code == 401

    def test_login_missing_fields(self, client):
        res = client.post('/login', json={'username': 'admin'})
        assert res.status_code == 400

    def test_protected_route_without_token(self, client):
        assert client.get('/trees').status_code == 401

    def test_protected_route_with_bad_token(self, client):
        res = client.get('/trees', headers={'Authorization': 'Bearer notavalidtoken'})
        assert res.status_code == 401

    def test_me_endpoint(self, client, auth_headers):
        res = client.get('/me', headers=auth_headers)
        assert res.status_code == 200
        assert res.get_json()['username'] == 'admin'


# ---------------------------------------------------------------------------
# Dropdowns endpoint
# ---------------------------------------------------------------------------

class TestDropdowns:
    def test_dropdowns_accessible_without_auth(self, client):
        """Dropdowns are public so the form can load without login."""
        res = client.get('/dropdowns')
        assert res.status_code == 200

    def test_dropdowns_structure(self, client):
        data = client.get('/dropdowns').get_json()
        expected_keys = [
            'species', 'dimora', 'stadio_sviluppo', 'posizione_sociale',
            'localizzazione', 'vincoli', 'giudizio_severita', 'pericolo_ord',
            'bersaglio_range',
            'diag_zolla', 'diag_colletto', 'diag_fusto',
            'diag_castello', 'diag_ramificazione', 'diag_chioma',
            'monitoraggio', 'urgenza', 'conflitti',
            'agenti_carie', 'altri_patogeni',
            'prescrizioni_val', 'prescrizioni_mit', 'prescrizioni_col',
        ]
        for k in expected_keys:
            assert k in data, f"Missing key: {k}"

    def test_dropdowns_species_format(self, client):
        data = client.get('/dropdowns').get_json()
        species = data['species']
        assert isinstance(species, list)
        assert len(species) > 100
        assert all('code' in s and 'name' in s for s in species)

    def test_dropdowns_pericolo_ord_keys(self, client):
        data = client.get('/dropdowns').get_json()
        pericolo = data['pericolo_ord']
        assert isinstance(pericolo, dict)
        # Must contain integer keys 1-7
        for k in range(1, 8):
            assert str(k) in pericolo

    def test_dropdowns_bersaglio_range(self, client):
        data = client.get('/dropdowns').get_json()
        assert data['bersaglio_range'] == list(range(1, 8))

    def test_dropdowns_diag_lists_nonempty(self, client):
        data = client.get('/dropdowns').get_json()
        for part in ['diag_zolla', 'diag_colletto', 'diag_fusto',
                     'diag_castello', 'diag_ramificazione', 'diag_chioma']:
            assert len(data[part]) > 0, f"{part} is empty"

    def test_dropdowns_giudizio_severita(self, client):
        data = client.get('/dropdowns').get_json()
        assert set(data['giudizio_severita']) == {'ps', 's', 'ms'}


# ---------------------------------------------------------------------------
# Tree CRUD (basic)
# ---------------------------------------------------------------------------

class TestTreeCRUD:
    def test_add_tree(self, added_tree_id):
        assert isinstance(added_tree_id, int)

    def test_add_tree_missing_required_fields(self, client, auth_headers):
        res = client.post('/add_tree', json={'custom_id': 'INCOMPLETE'}, headers=auth_headers)
        assert res.status_code == 400

    def test_add_tree_duplicate_custom_id(self, client, auth_headers, added_tree_id):
        assert isinstance(added_tree_id, int)  # tree exists; same custom_id must conflict
        res = client.post('/add_tree', json=TEST_TREE, headers=auth_headers)
        assert res.status_code == 409

    def test_get_trees(self, client, auth_headers, added_tree_id):
        res = client.get('/trees', headers=auth_headers)
        assert res.status_code == 200
        trees = res.get_json()
        assert isinstance(trees, list)
        assert added_tree_id in [t['id'] for t in trees]

    def test_get_tree_by_id(self, client, auth_headers, added_tree_id):
        res = client.get(f'/tree/{added_tree_id}', headers=auth_headers)
        assert res.status_code == 200
        data = res.get_json()
        assert data['id'] == added_tree_id
        assert data['species'] == TEST_TREE['species']
        assert data['city'] == TEST_TREE['city']

    def test_get_tree_by_custom_id(self, client, auth_headers, added_tree_id):
        res = client.get(f'/tree/custom/{TEST_TREE["custom_id"]}', headers=auth_headers)
        assert res.status_code == 200
        assert res.get_json()['id'] == added_tree_id

    def test_get_nonexistent_tree(self, client, auth_headers):
        res = client.get('/tree/999999', headers=auth_headers)
        assert res.status_code == 404

    def test_update_tree(self, client, auth_headers, added_tree_id):
        res = client.patch(f'/tree/{added_tree_id}',
                           json={'condition': 'Poor', 'comments': 'Needs pruning'},
                           headers=auth_headers)
        assert res.status_code == 200
        data = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert data['condition'] == 'Poor'
        assert data['comments'] == 'Needs pruning'

    def test_update_tree_species(self, client, auth_headers, added_tree_id):
        res = client.patch(f'/tree/{added_tree_id}',
                           json={'species': 'Fagus sylvatica L. - faggio'},
                           headers=auth_headers)
        assert res.status_code == 200
        data = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert data['species'] == 'Fagus sylvatica L. - faggio'

    def test_filter_trees_by_city(self, client, auth_headers, added_tree_id):
        res = client.get('/trees?city=TestCity', headers=auth_headers)
        assert res.status_code == 200
        trees = res.get_json()
        assert all(t['city'] == 'TestCity' for t in trees)
        assert any(t['id'] == added_tree_id for t in trees)

    def test_delete_tree(self, client, auth_headers):
        res = client.post('/add_tree',
                          json={**TEST_TREE, 'custom_id': 'PYTEST-DEL'},
                          headers=auth_headers)
        assert res.status_code == 201
        tid = res.get_json()['tree_id']
        assert client.delete(f'/tree/{tid}', headers=auth_headers).status_code == 200
        assert client.get(f'/tree/{tid}', headers=auth_headers).status_code == 404

    def test_tree_response_includes_arete_keys(self, client, auth_headers, added_tree_id):
        """Every tree GET must include the new ARETE JSON fields."""
        data = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        for key in ['dimora', 'stadio_sviluppo', 'posizione_sociale', 'localizzazione',
                    'vincoli', 'tree_height_m', 'circonferenza_cm', 'pericolo_rami',
                    'bersaglio_chioma', 'diag_zolla', 'diag_colletto', 'diag_fusto',
                    'diag_castello', 'diag_ramificazione', 'diag_chioma',
                    'conflitti_list', 'agenti_carie', 'prescrizioni_val',
                    'monitoraggio', 'urgenza']:
            assert key in data, f"Missing key in tree response: {key}"


# ---------------------------------------------------------------------------
# ARETE fields: create, persist, update
# ---------------------------------------------------------------------------

class TestARETeFields:
    def test_add_arete_tree(self, client, auth_headers, added_arete_tree_id):
        assert isinstance(added_arete_tree_id, int)

    def test_arete_dati_generali_persisted(self, client, auth_headers, added_arete_tree_id):
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert data['dimora'] == ARETE_TREE['dimora']
        assert data['stadio_sviluppo'] == ARETE_TREE['stadio_sviluppo']
        assert data['posizione_sociale'] == ARETE_TREE['posizione_sociale']
        assert data['localizzazione'] == ARETE_TREE['localizzazione']
        assert data['vincoli'] == ARETE_TREE['vincoli']

    def test_arete_dimensions_persisted(self, client, auth_headers, added_arete_tree_id):
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert data['tree_height_m'] == ARETE_TREE['tree_height_m']
        assert data['circonferenza_cm'] == ARETE_TREE['circonferenza_cm']
        assert data['branch_diam_cm'] == ARETE_TREE['branch_diam_cm']
        assert data['branch_length_m'] == ARETE_TREE['branch_length_m']
        assert data['target_height_m'] == ARETE_TREE['target_height_m']

    def test_arete_pericolo_persisted(self, client, auth_headers, added_arete_tree_id):
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert data['pericolo_rami'] == ARETE_TREE['pericolo_rami']
        assert data['pericolo_tronco'] == ARETE_TREE['pericolo_tronco']
        assert data['pericolo_colletto'] == ARETE_TREE['pericolo_colletto']
        assert data['pericolo_zolla'] == ARETE_TREE['pericolo_zolla']

    def test_arete_bersaglio_persisted(self, client, auth_headers, added_arete_tree_id):
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert data['bersaglio_chioma'] == ARETE_TREE['bersaglio_chioma']
        assert data['bersaglio_ramo'] == ARETE_TREE['bersaglio_ramo']

    def test_update_arete_pericolo(self, client, auth_headers, added_arete_tree_id):
        res = client.patch(f'/tree/{added_arete_tree_id}',
                           json={'pericolo_rami': '2', 'pericolo_zolla': '3'},
                           headers=auth_headers)
        assert res.status_code == 200
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert data['pericolo_rami'] == '2'
        assert data['pericolo_zolla'] == '3'

    def test_update_arete_dimensions(self, client, auth_headers, added_arete_tree_id):
        res = client.patch(f'/tree/{added_arete_tree_id}',
                           json={'tree_height_m': 18.0, 'circonferenza_cm': 145.0},
                           headers=auth_headers)
        assert res.status_code == 200
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert data['tree_height_m'] == 18.0
        assert data['circonferenza_cm'] == 145.0

    def test_monitoraggio_urgenza_persisted(self, client, auth_headers, added_arete_tree_id):
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert data['monitoraggio'] == ARETE_TREE['monitoraggio']
        assert data['urgenza'] == ARETE_TREE['urgenza']


# ---------------------------------------------------------------------------
# Diagnosi JSON fields
# ---------------------------------------------------------------------------

class TestDiagnosiFields:
    def test_diag_zolla_persisted(self, client, auth_headers, added_arete_tree_id):
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        diag = data['diag_zolla']
        assert isinstance(diag, list)
        assert len(diag) == len(ARETE_TREE['diag_zolla'])
        assert diag[0]['caratt'] == 'compattazione'
        assert diag[0]['giudizio'] == 's'

    def test_diag_fusto_persisted(self, client, auth_headers, added_arete_tree_id):
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        diag = data['diag_fusto']
        assert isinstance(diag, list)
        assert len(diag) == 1
        assert diag[0]['caratt'] == 'carie'
        assert diag[0]['giudizio'] == 'ms'

    def test_diag_chioma_empty_list(self, client, auth_headers, added_arete_tree_id):
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert data['diag_chioma'] == []

    def test_diag_unset_returns_empty_list(self, client, auth_headers, added_tree_id):
        """A plain tree (no diagnosi set) must return empty lists, not null."""
        data = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        for part in ['diag_zolla','diag_colletto','diag_fusto',
                     'diag_castello','diag_ramificazione','diag_chioma']:
            assert data[part] == [], f"{part} should be [] not {data[part]!r}"

    def test_update_diag_zolla(self, client, auth_headers, added_arete_tree_id):
        new_diag = [
            {'caratt': 'pavimentazione', 'giudizio': 'ms'},
            {'caratt': 'radici strozzanti', 'giudizio': 's'},
        ]
        res = client.patch(f'/tree/{added_arete_tree_id}',
                           json={'diag_zolla': new_diag},
                           headers=auth_headers)
        assert res.status_code == 200
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert len(data['diag_zolla']) == 2
        assert data['diag_zolla'][1]['caratt'] == 'radici strozzanti'

    def test_diag_giudizio_values(self, client, auth_headers, added_arete_tree_id):
        """All severity values must be one of ps / s / ms."""
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        valid = {'ps', 's', 'ms'}
        for part in ['diag_zolla','diag_fusto']:
            for entry in data[part]:
                assert entry['giudizio'] in valid


# ---------------------------------------------------------------------------
# Multi-select JSON fields
# ---------------------------------------------------------------------------

class TestMultiSelectFields:
    def test_conflitti_persisted(self, client, auth_headers, added_arete_tree_id):
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert isinstance(data['conflitti_list'], list)
        assert set(data['conflitti_list']) == set(ARETE_TREE['conflitti_list'])

    def test_agenti_carie_persisted(self, client, auth_headers, added_arete_tree_id):
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert 'Ganoderma applanatum' in data['agenti_carie']

    def test_prescrizioni_val_persisted(self, client, auth_headers, added_arete_tree_id):
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert ARETE_TREE['prescrizioni_val'][0] in data['prescrizioni_val']

    def test_multiselect_unset_returns_empty_list(self, client, auth_headers, added_tree_id):
        data = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        for field in ['conflitti_list','agenti_carie','altri_patogeni',
                      'prescrizioni_val','prescrizioni_mit','prescrizioni_col']:
            assert data[field] == [], f"{field} should be []"

    def test_update_conflitti(self, client, auth_headers, added_arete_tree_id):
        new_conf = ['cavi aerei', 'fabbricati', 'lampioni']
        res = client.patch(f'/tree/{added_arete_tree_id}',
                           json={'conflitti_list': new_conf},
                           headers=auth_headers)
        assert res.status_code == 200
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert set(data['conflitti_list']) == set(new_conf)

    def test_clear_multiselect_with_empty_list(self, client, auth_headers, added_arete_tree_id):
        res = client.patch(f'/tree/{added_arete_tree_id}',
                           json={'agenti_carie': []},
                           headers=auth_headers)
        assert res.status_code == 200
        data = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert data['agenti_carie'] == []


# ---------------------------------------------------------------------------
# Risk calculation endpoint
# ---------------------------------------------------------------------------

class TestRiskCalculation:
    def test_calculate_risk_success(self, client, auth_headers):
        res = client.post('/calculate_risk', json=RISK_PAYLOAD, headers=auth_headers)
        assert res.status_code == 200
        data = res.get_json()
        assert 'attuale' in data
        assert 'residuo' in data

    def test_risk_result_structure(self, client, auth_headers):
        data = client.post('/calculate_risk', json=RISK_PAYLOAD, headers=auth_headers).get_json()
        for phase in ('attuale', 'residuo'):
            d = data[phase]
            assert 'crown_momentum_kgms' in d
            assert 'branch_momentum_kgms' in d
            assert 'crown_impulso_class' in d
            for mode in ('rami', 'tronco', 'colletto', 'zolla'):
                assert mode in d
                e = d[mode]
                for k in ('pericolo_class', 'bersaglio_class', 'impulso_class',
                          'risk_key', 'risk_ratio', 'risk_description'):
                    assert k in e, f"Missing {k} in {phase}.{mode}"

    def test_risk_ratio_is_valid_string(self, client, auth_headers):
        data = client.post('/calculate_risk', json=RISK_PAYLOAD, headers=auth_headers).get_json()
        valid_prefixes = ('1:', '<1:')
        for phase in ('attuale', 'residuo'):
            for mode in ('rami', 'tronco', 'colletto', 'zolla'):
                ratio = data[phase][mode]['risk_ratio']
                assert any(ratio.startswith(p) for p in valid_prefixes), \
                    f"Unexpected ratio: {ratio}"

    def test_risk_with_post_intervention(self, client, auth_headers):
        payload = {**RISK_PAYLOAD,
                   'post_branch_length_m': 1.5,
                   'post_branch_height_m': 9.0}
        data = client.post('/calculate_risk', json=payload, headers=auth_headers).get_json()
        # After shortening the branch the rami impulso class must be ≥ attuale (less momentum)
        att_imp = data['attuale']['rami']['impulso_class']
        res_imp = data['residuo']['rami']['impulso_class']
        assert res_imp >= att_imp

    def test_risk_requires_auth(self, client):
        res = client.post('/calculate_risk', json=RISK_PAYLOAD)
        assert res.status_code == 401

    def test_risk_missing_fields(self, client, auth_headers):
        incomplete = {k: v for k, v in RISK_PAYLOAD.items() if k != 'bersaglio_ramo'}
        res = client.post('/calculate_risk', json=incomplete, headers=auth_headers)
        assert res.status_code == 400

    def test_risk_classes_in_range_1_7(self, client, auth_headers):
        data = client.post('/calculate_risk', json=RISK_PAYLOAD, headers=auth_headers).get_json()
        for phase in ('attuale', 'residuo'):
            for mode in ('rami', 'tronco', 'colletto', 'zolla'):
                e = data[phase][mode]
                assert 1 <= e['pericolo_class'] <= 7
                assert 1 <= e['bersaglio_class'] <= 7
                assert 1 <= e['impulso_class'] <= 7

    def test_risk_key_format(self, client, auth_headers):
        data = client.post('/calculate_risk', json=RISK_PAYLOAD, headers=auth_headers).get_json()
        for phase in ('attuale', 'residuo'):
            for mode in ('rami', 'tronco', 'colletto', 'zolla'):
                key = data[phase][mode]['risk_key']
                assert len(key) == 3 and key.isdigit(), f"Bad risk key: {key}"


# ---------------------------------------------------------------------------
# Torino dataset (Dario's 50 trees)
# ---------------------------------------------------------------------------

class TestTorinoDataset:
    """Smoke tests against the pre-seeded Torino trees owned by Dario."""

    @pytest.fixture(scope='class')
    def torino_trees(self, client, admin_token):
        # admin_token is session-scoped; build header here to avoid scope mismatch
        headers = {'Authorization': f'Bearer {admin_token}'}
        res = client.get('/trees?city=Torino', headers=headers)
        assert res.status_code == 200
        trees = res.get_json()
        return [t for t in trees if t['city'] == 'Torino']

    def test_50_trees_in_torino(self, torino_trees):
        assert len(torino_trees) >= 50

    def test_all_have_custom_id_to_prefix(self, torino_trees):
        to_trees = [t for t in torino_trees if t['custom_id'].startswith('TO-')]
        assert len(to_trees) == 50

    def test_all_have_coordinates(self, torino_trees):
        for t in torino_trees:
            if not t['custom_id'].startswith('TO-'):
                continue
            assert t['latitude'] is not None
            assert t['longitude'] is not None
            # Rough bounding box for Torino province
            assert 44.9 <= t['latitude'] <= 45.2
            assert 7.5 <= t['longitude'] <= 7.9

    def test_all_have_species(self, torino_trees):
        for t in torino_trees:
            if t['custom_id'].startswith('TO-'):
                assert t['species'] and len(t['species']) > 3

    def test_arete_fields_populated(self, torino_trees):
        to_trees = [t for t in torino_trees if t['custom_id'].startswith('TO-')]
        populated_dimora    = sum(1 for t in to_trees if t.get('dimora'))
        populated_stadio    = sum(1 for t in to_trees if t.get('stadio_sviluppo'))
        populated_pericolo  = sum(1 for t in to_trees if t.get('pericolo_rami'))
        populated_circ      = sum(1 for t in to_trees if t.get('circonferenza_cm'))
        assert populated_dimora   == 50
        assert populated_stadio   == 50
        assert populated_pericolo == 50
        assert populated_circ     == 50

    def test_diagnosi_are_lists(self, torino_trees):
        for t in torino_trees:
            if not t['custom_id'].startswith('TO-'):
                continue
            for part in ['diag_zolla','diag_colletto','diag_fusto','diag_chioma']:
                assert isinstance(t[part], list), f"{t['custom_id']}.{part} is not a list"

    def test_pericolo_values_valid(self, torino_trees):
        valid = set(str(i) for i in range(1, 8)) | {'0 x sospet','0 x difetto','0 x costituz','N.S.'}
        for t in torino_trees:
            if not t['custom_id'].startswith('TO-'):
                continue
            for field in ['pericolo_rami','pericolo_tronco','pericolo_colletto','pericolo_zolla']:
                val = t.get(field)
                if val:
                    assert val in valid, f"{t['custom_id']}.{field}={val!r} not in valid set"

    def test_bersaglio_values_in_range(self, torino_trees):
        for t in torino_trees:
            if not t['custom_id'].startswith('TO-'):
                continue
            for field in ['bersaglio_chioma','bersaglio_ramo']:
                val = t.get(field)
                if val is not None:
                    assert 1 <= val <= 7, f"{t['custom_id']}.{field}={val}"

    def test_one_torino_tree_risk_calculation(self, client, admin_token, torino_trees):
        """Pick the first TO-tree with full dims and compute ORD risk."""
        headers = {'Authorization': f'Bearer {admin_token}'}
        sample = next((t for t in torino_trees
                       if t['custom_id'].startswith('TO-') and t.get('tree_height_m')
                       and t.get('pericolo_rami')), None)
        assert sample is not None, "No TO- tree with ORD dimensions found"
        payload = {
            'tree_height_m': sample['tree_height_m'],
            'circonferenza_cm': sample['circonferenza_cm'],
            'crown_diameter_m': sample.get('crown_diameter_m') or 5.0,
            'branch_diam_cm': sample['branch_diam_cm'],
            'branch_length_m': sample['branch_length_m'],
            'branch_height_m': sample['branch_height_m'],
            'target_height_m': sample['target_height_m'],
            'pericolo_rami': int(sample['pericolo_rami']),
            'pericolo_tronco': int(sample['pericolo_tronco']),
            'pericolo_colletto': int(sample['pericolo_colletto']),
            'pericolo_zolla': int(sample['pericolo_zolla']),
            'bersaglio_chioma': sample['bersaglio_chioma'],
            'bersaglio_ramo': sample['bersaglio_ramo'],
        }
        res = client.post('/calculate_risk', json=payload, headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        assert 'attuale' in data and 'residuo' in data


# ---------------------------------------------------------------------------
# Role-based access
# ---------------------------------------------------------------------------

class TestRoleAccess:
    @pytest.fixture(autouse=True)
    def city_user(self, client, auth_headers):
        res = client.post('/add_user',
                          json={'username': 'pytest_cityuser', 'password': 'testpass',
                                'role': 'city', 'city': 'TestCity'},
                          headers=auth_headers)
        assert res.status_code == 201, f"Could not create city user: {res.get_json()}"
        yield
        with flask_app.app_context():
            u = User.query.filter_by(username='pytest_cityuser').first()
            if u: db.session.delete(u); db.session.commit()

    def _login(self, client, username, password):
        res = client.post('/login', json={'username': username, 'password': password})
        assert res.status_code == 200
        return {'Authorization': 'Bearer ' + res.get_json()['token']}

    def test_city_user_sees_own_city_only(self, client, auth_headers, added_tree_id):
        city_headers = self._login(client, 'pytest_cityuser', 'testpass')
        res = client.post('/add_tree',
                          json={**TEST_TREE, 'custom_id': 'PYTEST-OTHER', 'city': 'OtherCity'},
                          headers=auth_headers)
        assert res.status_code == 201
        other_id = res.get_json()['tree_id']
        try:
            trees = client.get('/trees', headers=city_headers).get_json()
            tree_ids = {t['id'] for t in trees}
            assert added_tree_id in tree_ids           # own-city tree is visible
            assert 'OtherCity' not in {t['city'] for t in trees}
        finally:
            with flask_app.app_context():
                t = db.session.get(Tree, other_id)
                if t: db.session.delete(t); db.session.commit()

    def test_superuser_can_create_city_user(self, client, auth_headers):
        res = client.get('/users', headers=auth_headers)
        assert res.status_code == 200
        assert 'pytest_cityuser' in [u['username'] for u in res.get_json()]

    def test_city_user_cannot_create_superuser(self, client):
        city_headers = self._login(client, 'pytest_cityuser', 'testpass')
        res = client.post('/add_user',
                          json={'username': 'evil', 'password': 'x', 'role': 'superuser'},
                          headers=city_headers)
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_excel(self, client, auth_headers, added_tree_id):
        assert isinstance(added_tree_id, int)  # ensure at least one tree exists
        res = client.get('/export/excel', headers=auth_headers)
        assert res.status_code == 200
        assert 'spreadsheetml' in res.content_type
        assert len(res.data) > 0

    def test_export_geojson(self, client, auth_headers, added_tree_id):
        res = client.get('/export/geojson', headers=auth_headers)
        assert res.status_code == 200
        geo = res.get_json()
        assert geo['type'] == 'FeatureCollection'
        assert added_tree_id in [f['properties']['id'] for f in geo['features']]

    def test_export_requires_auth(self, client):
        assert client.get('/export/excel').status_code == 401
        assert client.get('/export/geojson').status_code == 401


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))

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

    def test_cities_selector_scoped_to_own_trees(self, client, auth_headers):
        """Il selettore dei comuni non elenca i comuni degli altri agronomi:
        selezionarli mostrerebbe una lista vuota."""
        agro = {'username': 'pytest_agro_scope', 'password': 'testpass', 'role': 'user'}
        assert client.post('/add_user', json=agro, headers=auth_headers).status_code == 201
        tree_id = None
        try:
            res = client.post('/add_tree',
                              json={**TEST_TREE, 'custom_id': 'PYTEST-SCOPE',
                                    'city': 'ComuneAltrui'},
                              headers=auth_headers)        # albero dell'admin
            assert res.status_code == 201
            tree_id = res.get_json()['tree_id']
            agro_headers = self._login(client, agro['username'], agro['password'])
            comuni = client.get('/cities', headers=agro_headers).get_json()
            assert comuni == [], f'agronomo senza alberi vede {comuni}'
            # il superuser invece continua a vedere tutto
            assert 'ComuneAltrui' in client.get('/cities', headers=auth_headers).get_json()
        finally:
            if tree_id:
                client.delete(f'/tree/{tree_id}', headers=auth_headers)
            with flask_app.app_context():
                u = User.query.filter_by(username=agro['username']).first()
                if u: db.session.delete(u); db.session.commit()

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


# ---------------------------------------------------------------------------
# Fase 0 QGIS (qgis.md): token API, uuid/updated_*, _upsert_tree
# ---------------------------------------------------------------------------

import io, sqlite3, tempfile, os
from app import ApiToken, _upsert_tree, _role_tree_query


def _edit_gpkg(data, sql):
    """Applica una UPDATE al layer `alberi` di un GPKG in memoria."""
    path = tempfile.mktemp(suffix='.gpkg'); open(path, 'wb').write(data)
    con = sqlite3.connect(path); con.execute(sql); con.commit(); con.close()
    out = open(path, 'rb').read(); os.remove(path)
    return out


class TestApiToken:
    def test_token_lifecycle(self, client, auth_headers):
        res = client.post('/me/tokens', json={'name': 'pytest'}, headers=auth_headers)
        assert res.status_code == 201
        body = res.get_json()
        assert body['token'].startswith('slv_') and body['prefix'] == body['token'][:12]
        tok_headers = {'Authorization': f"Bearer {body['token']}"}
        try:
            me = client.get('/me', headers=tok_headers)
            assert me.status_code == 200 and me.get_json()['username'] == 'admin'
            # un token API non crea altri token
            assert client.post('/me/tokens', json={}, headers=tok_headers).status_code == 403
            assert any(t['id'] == body['id'] for t in client.get('/me/tokens', headers=auth_headers).get_json())
        finally:
            assert client.delete(f"/me/tokens/{body['id']}", headers=auth_headers).status_code == 200
        assert client.get('/me', headers=tok_headers).status_code == 401
        with flask_app.app_context():
            t = db.session.get(ApiToken, body['id'])
            if t: db.session.delete(t); db.session.commit()

    def test_demo_cannot_create_token(self, client):
        res = client.post('/login', json={'username': 'demo_user', 'password': 'demo_password'})
        if res.status_code != 200:
            pytest.skip('account demo non disponibile')
        h = {'Authorization': f"Bearer {res.get_json()['token']}"}
        assert client.post('/me/tokens', json={}, headers=h).status_code == 403


class TestTreeTracking:
    def test_uuid_and_updated_fields(self, client, auth_headers, added_tree_id):
        d = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert d['uuid'] and len(d['uuid']) == 36
        assert d['updated_at'] and d['updated_by'] == 'admin'
        before = d['updated_at']
        assert client.patch(f'/tree/{added_tree_id}', json={'comments': 'x'}, headers=auth_headers).status_code == 200
        after = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert after['updated_at'] > before and after['uuid'] == d['uuid']


class TestUpsertImport:
    def _import(self, client, headers, data, on_conflict='update'):
        res = client.post('/import/gpkg',
                          data={'file': (io.BytesIO(data), 'x.gpkg'), 'city': TEST_TREE['city'],
                                'on_conflict': on_conflict},
                          headers=headers, content_type='multipart/form-data')
        assert res.status_code == 200, res.get_json()
        return res.get_json()

    def test_reimport_is_idempotent(self, client, auth_headers, added_tree_id):
        g = client.get(f'/export/gpkg?ids={added_tree_id}', headers=auth_headers).data
        r = self._import(client, auth_headers, g)
        assert (r['created'], r['updated'], r['unchanged'], r['errors']) == (0, 0, 1, 0)
        assert r['inserted'] == 1  # compatibilità con il frontend

    def test_moved_point_updates_by_uuid(self, client, auth_headers, added_tree_id):
        g = client.get(f'/export/gpkg?ids={added_tree_id}', headers=auth_headers).data
        g = _edit_gpkg(g, "UPDATE alberi SET latitude = latitude + 0.001")
        r = self._import(client, auth_headers, g)
        assert (r['created'], r['updated']) == (0, 1)
        d = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert abs(d['latitude'] - (TEST_TREE['latitude'] + 0.001)) < 1e-6

    def test_empty_values_and_derived_fields_are_ignored(self, client, auth_headers, added_tree_id):
        g = client.get(f'/export/gpkg?ids={added_tree_id}', headers=auth_headers).data
        g = _edit_gpkg(g, "UPDATE alberi SET species = NULL, bersaglio_chioma = 7")
        r = self._import(client, auth_headers, g)
        assert r['unchanged'] == 1
        d = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert d['species'] == TEST_TREE['species'] and d['bersaglio_chioma'] is None

    def test_strict_uuid_rejects_unknown(self, client, auth_headers, added_tree_id):
        with flask_app.app_context():
            admin = User.query.filter_by(username='admin').first()
            scope = _role_tree_query('superuser', admin.id, None)
            with pytest.raises(ValueError):
                _upsert_tree({'uuid': '00000000-0000-0000-0000-000000000000', 'custom_id': 'X',
                              'latitude': 1.0, 'longitude': 1.0},
                             city=TEST_TREE['city'], on_conflict='update',
                             user_id=admin.id, scope=scope, strict_uuid=True)
            db.session.rollback()


class TestExportCity:
    """`?city=` sugli export: tutti gli alberi di un comune senza elencare gli
    id nella URL (oltre ~660 id Gunicorn rifiuta la riga di richiesta)."""

    def _names(self, res):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(res.get_data())
        ns = root.tag.split('}')[0].strip('{')
        return sorted(w.find(f'{{{ns}}}name').text for w in root.findall(f'{{{ns}}}wpt'))

    def test_city_filters_export(self, client, auth_headers, added_tree_id):
        altrove = client.post('/add_tree',
                              json={**TEST_TREE, 'custom_id': 'PYTEST-ALTROVE',
                                    'city': 'AltroComune'},
                              headers=auth_headers)
        assert altrove.status_code == 201
        other_id = altrove.get_json()['tree_id']
        try:
            res = client.get(f"/export/gpx?city={TEST_TREE['city']}", headers=auth_headers)
            assert res.status_code == 200
            nomi = self._names(res)
            assert TEST_TREE['custom_id'] in nomi
            assert 'PYTEST-ALTROVE' not in nomi          # comune diverso, escluso

            res = client.get('/export/gpx?city=AltroComune', headers=auth_headers)
            assert self._names(res) == ['PYTEST-ALTROVE']

            # confronto esatto: un nome parziale non deve pescare nulla
            parziale = TEST_TREE['city'][:-1]
            assert self._names(client.get(f'/export/gpx?city={parziale}',
                                          headers=auth_headers)) == []

            # ids e city si combinano: l'intersezione, non l'unione
            assert self._names(client.get(
                f"/export/gpx?city=AltroComune&ids={added_tree_id}",
                headers=auth_headers)) == []
        finally:
            client.delete(f'/tree/{other_id}', headers=auth_headers)

    def test_list_and_export_agree_on_city(self, client, auth_headers, added_tree_id):
        """/trees e gli export devono selezionare lo stesso insieme: il filtro
        comune e' un confronto esatto in entrambi, non una sottostringa."""
        citta = TEST_TREE['city']
        simile = citta + 'zzo'          # es. TestCity -> TestCityzzo
        res = client.post('/add_tree',
                          json={**TEST_TREE, 'custom_id': 'PYTEST-SIMILE', 'city': simile},
                          headers=auth_headers)
        assert res.status_code == 201
        simile_id = res.get_json()['tree_id']
        try:
            lista = client.get(f'/trees?city={citta}', headers=auth_headers).get_json()
            assert {t['city'] for t in lista} == {citta}, 'la lista pesca un comune simile'
            nomi_lista = {t['custom_id'] for t in lista}
            nomi_export = set(self._names(
                client.get(f'/export/gpx?city={citta}', headers=auth_headers)))
            assert nomi_lista == nomi_export, 'lista ed export non coincidono'
            # il comune simile resta raggiungibile col suo nome
            altri = client.get(f'/trees?city={simile}', headers=auth_headers).get_json()
            assert {t['custom_id'] for t in altri} == {'PYTEST-SIMILE'}
        finally:
            client.delete(f'/tree/{simile_id}', headers=auth_headers)

    def test_city_on_excel_and_gpkg(self, client, auth_headers, added_tree_id):
        for fmt in ('excel', 'gpkg'):
            res = client.get(f"/export/{fmt}?city={TEST_TREE['city']}", headers=auth_headers)
            assert res.status_code == 200, f'{fmt}: {res.status_code}'
            assert len(res.get_data()) > 0


class TestQgisFeatures:
    def test_requires_city_or_ids(self, client, auth_headers):
        assert client.get('/qgis/features', headers=auth_headers).status_code == 400
        assert client.get('/qgis/features?city=X').status_code == 401

    def test_geojson_shape_and_flat_properties(self, client, auth_headers, added_arete_tree_id):
        res = client.get(f'/qgis/features?ids={added_arete_tree_id}', headers=auth_headers)
        assert res.status_code == 200 and res.headers['X-Silvae-Schema'] == '1'
        body = res.get_json()
        assert body['type'] == 'FeatureCollection' and body['silvae']['count'] == 1
        f = body['features'][0]
        assert f['id'] == added_arete_tree_id and f['geometry']['type'] == 'Point'
        lon, lat = f['geometry']['coordinates']
        assert abs(lat - ARETE_TREE['latitude']) < 1e-9 and abs(lon - ARETE_TREE['longitude']) < 1e-9
        p = f['properties']
        assert p['uuid'] and p['owner'] == 'admin' and p['updated_at']
        assert 'rischio' not in p and 'owner_id' not in p
        for k in ('stat_bucket', 'stat_label', 'rischio_classe', 'rischio_rami', 'rischio_residuo_classe', 'rischio_json'):
            assert k in p
        # liste e diagnosi appiattite a stringa, mai list/dict
        assert all(not isinstance(v, (list, dict)) for v in p.values())
        if p['rischio_classe']:
            assert p['stat_bucket'] == f"risk:{p['rischio_classe']}"

    def test_city_filter_and_since(self, client, auth_headers, added_tree_id):
        res = client.get(f"/qgis/features?city={TEST_TREE['city']}", headers=auth_headers)
        ids = [f['id'] for f in res.get_json()['features']]
        assert added_tree_id in ids
        assert client.get('/qgis/features?city=__nessuno__', headers=auth_headers).get_json()['silvae']['count'] == 0
        upd = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()['updated_at']
        # since = updated_at dell'albero → escluso; since molto vecchio → incluso
        res = client.get(f"/qgis/features?city={TEST_TREE['city']}&since={upd}", headers=auth_headers)
        assert added_tree_id not in [f['id'] for f in res.get_json()['features']]
        res = client.get(f"/qgis/features?city={TEST_TREE['city']}&since=2000-01-01T00:00:00Z", headers=auth_headers)
        assert added_tree_id in [f['id'] for f in res.get_json()['features']]
        assert client.get('/qgis/features?city=X&since=ieri', headers=auth_headers).status_code == 400

    def test_since_accepts_offset_with_mangled_plus(self):
        # In una query string un `+` non codificato arriva come spazio: l'ora
        # che restituiamo noi («…+00:00») deve essere rileggibile comunque.
        from app import _parse_iso_dt
        atteso = _parse_iso_dt('2026-10-24T09:12:33+00:00')
        assert atteso is not None
        assert _parse_iso_dt('2026-10-24T09:12:33 00:00') == atteso
        assert _parse_iso_dt('2026-10-24T09:12:33Z') == atteso
        assert _parse_iso_dt('2026-10-24 09:12:33') == atteso        # separatore a spazio
        assert _parse_iso_dt('2026-10-24T09:12:33 02:00').utcoffset().total_seconds() == 7200
        assert _parse_iso_dt('2026-10-24T09:12:33-02:00').utcoffset().total_seconds() == -7200
        assert _parse_iso_dt('ieri') is None and _parse_iso_dt('') is None

    def test_bbox(self, client, auth_headers, added_tree_id):
        lat, lon = TEST_TREE['latitude'], TEST_TREE['longitude']
        inside = f'{lon-0.01},{lat-0.01},{lon+0.01},{lat+0.01}'
        outside = f'{lon+1},{lat+1},{lon+2},{lat+2}'
        c = TEST_TREE['city']
        assert added_tree_id in [f['id'] for f in client.get(f'/qgis/features?city={c}&bbox={inside}', headers=auth_headers).get_json()['features']]
        assert added_tree_id not in [f['id'] for f in client.get(f'/qgis/features?city={c}&bbox={outside}', headers=auth_headers).get_json()['features']]
        assert client.get(f'/qgis/features?city={c}&bbox=1,2', headers=auth_headers).status_code == 400


class TestQgisStyle:
    def test_style_endpoint(self, client):
        from tools import qgis_style
        for by in qgis_style.STYLES:
            res = client.get(f'/qgis/style.qml?by={by}')
            assert res.status_code == 200 and 'xml' in res.content_type
            assert f'attr="{qgis_style.STYLES[by]["field"]}"' in res.get_data(as_text=True)
        assert client.get('/qgis/style.qml?by=x').status_code == 400
        txt = client.get('/qgis/style.qml?field=categoria&labels=0').get_data(as_text=True)
        assert 'attr="categoria"' in txt and '<labeling' not in txt

    def test_categories_follow_palette(self):
        from tools import qgis_style, palette
        cats = dict((v, c) for v, _l, c in qgis_style.categories('stat'))
        for e in palette.RISK:
            if e['key'] != 'na': assert cats[f"risk:{e['key']}"] == e['main']
        for e in palette.CONDITION:
            assert cats[f"cond:{e['key']}"] == e['main']
        assert cats['na'] == palette.by_key('risk', 'na')['main']

    def test_gpkg_has_category_columns_and_default_style(self, client, auth_headers, added_tree_id):
        res = client.get(f'/export/gpkg?ids={added_tree_id}', headers=auth_headers)
        assert res.status_code == 200
        path = tempfile.mktemp(suffix='.gpkg'); open(path, 'wb').write(res.data)
        con = sqlite3.connect(path)
        cols = [r[1] for r in con.execute('pragma table_info(alberi)')]
        assert {'stat_bucket', 'rischio_classe', 'cond_classe'} <= set(cols)
        row = con.execute("SELECT f_table_name, useAsDefault, styleQML FROM layer_styles").fetchone()
        assert row[0] == 'alberi' and row[1] == 1 and 'attr="stat_bucket"' in row[2]
        val = con.execute('SELECT stat_bucket FROM alberi').fetchone()[0]
        assert val.startswith(('risk:', 'cond:')) or val == 'na'
        con.close(); os.remove(path)
        # colonna esclusa → nessuno stile
        res = client.get(f'/export/gpkg?ids={added_tree_id}&exclude=' + json.dumps(['stat_bucket']), headers=auth_headers)
        path = tempfile.mktemp(suffix='.gpkg'); open(path, 'wb').write(res.data)
        con = sqlite3.connect(path)
        assert not con.execute("SELECT name FROM sqlite_master WHERE name='layer_styles'").fetchone()
        con.close(); os.remove(path)


class TestQgisDeliveries:
    def _create(self, client, headers, **body):
        return client.post('/qgis/deliveries', json=body, headers=headers)

    def _cleanup(self, ids):
        from app import QgisDelivery
        with flask_app.app_context():
            for i in ids:
                d = db.session.get(QgisDelivery, i)
                if d: db.session.delete(d)
            db.session.commit()

    def test_create_list_fetch_delete(self, client, auth_headers, added_tree_id):
        res = self._create(client, auth_headers, city=TEST_TREE['city'], ids=[added_tree_id],
                           polygon=[[45.0, 9.0], [45.1, 9.0], [45.1, 9.1]])
        assert res.status_code == 201
        d = res.get_json()
        assert d['count'] == 1 and d['city'] == TEST_TREE['city'] and d['fetched_at'] is None
        assert d['title'] and d['polygon'] and d['expires_at']
        try:
            lst = client.get('/qgis/deliveries', headers=auth_headers).get_json()
            assert d['id'] in [x['id'] for x in lst]
            # ritiro: alberi correnti dell'invio + marcatura
            fc = client.get(f"/qgis/features?delivery={d['id']}", headers=auth_headers).get_json()
            assert [f['id'] for f in fc['features']] == [added_tree_id]
            assert fc['silvae']['delivery']['id'] == d['id'] and fc['silvae']['delivery']['fetched_at']
            assert fc['silvae']['city'] == TEST_TREE['city']
            # ritirato → fuori dalla lista in attesa, dentro con ?all=1
            assert d['id'] not in [x['id'] for x in client.get('/qgis/deliveries', headers=auth_headers).get_json()]
            assert d['id'] in [x['id'] for x in client.get('/qgis/deliveries?all=1', headers=auth_headers).get_json()]
        finally:
            assert client.delete(f"/qgis/deliveries/{d['id']}", headers=auth_headers).status_code == 200
        assert client.delete(f"/qgis/deliveries/{d['id']}", headers=auth_headers).status_code == 404

    def test_rejects_invalid(self, client, auth_headers):
        assert self._create(client, auth_headers, ids=[]).status_code == 400
        assert self._create(client, auth_headers, ids=['x']).status_code == 400
        assert self._create(client, auth_headers, ids=[999999999]).status_code == 404
        assert client.post('/qgis/deliveries', json={'ids': [1]}).status_code == 401

    def test_only_visible_trees_and_owner(self, client, auth_headers, added_tree_id):
        """Gli id non visibili sono scartati; l'invio è personale."""
        res = self._create(client, auth_headers, ids=[added_tree_id, 999999999])
        d = res.get_json()
        assert res.status_code == 201 and d['count'] == 1 and d['requested'] == 2
        try:
            other = client.post('/login', json={'username': 'demo_user', 'password': 'demo_password'})
            if other.status_code == 200:
                h2 = {'Authorization': f"Bearer {other.get_json()['token']}"}
                assert d['id'] not in [x['id'] for x in client.get('/qgis/deliveries', headers=h2).get_json()]
                assert client.get(f"/qgis/features?delivery={d['id']}", headers=h2).status_code == 404
                assert client.delete(f"/qgis/deliveries/{d['id']}", headers=h2).status_code == 404
        finally:
            self._cleanup([d['id']])

    def test_api_token_cannot_create(self, client, auth_headers, added_tree_id):
        from app import ApiToken
        tok = client.post('/me/tokens', json={'name': 'pytest-deliv'}, headers=auth_headers).get_json()
        h = {'Authorization': f"Bearer {tok['token']}"}
        try:
            assert self._create(client, h, ids=[added_tree_id]).status_code == 403
            assert client.get('/qgis/deliveries', headers=h).status_code == 200   # leggere sì
        finally:
            client.delete(f"/me/tokens/{tok['id']}", headers=auth_headers)

    def test_expired_are_purged(self, client, auth_headers, added_tree_id):
        from app import QgisDelivery
        from datetime import datetime, timezone, timedelta
        d = self._create(client, auth_headers, ids=[added_tree_id]).get_json()
        with flask_app.app_context():
            row = db.session.get(QgisDelivery, d['id'])
            row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
            db.session.commit()
        assert d['id'] not in [x['id'] for x in client.get('/qgis/deliveries?all=1', headers=auth_headers).get_json()]
        with flask_app.app_context():
            assert db.session.get(QgisDelivery, d['id']) is None


class TestQgisPush:
    """POST /qgis/features: scrittura da QGIS (qgis.md §6.2)."""

    def _pull(self, client, headers, tree_id):
        fc = client.get(f'/qgis/features?ids={tree_id}', headers=headers).get_json()
        return fc['features'][0]

    def _push(self, client, headers, features, **kw):
        body = {'type': 'FeatureCollection', 'features': features,
                'city': kw.pop('city', TEST_TREE['city']), **kw}
        return client.post('/qgis/features', json=body, headers=headers)

    def test_roundtrip_unchanged(self, client, auth_headers, added_tree_id):
        f = self._pull(client, auth_headers, added_tree_id)
        res = self._push(client, auth_headers, [f])
        assert res.status_code == 200
        out = res.get_json()
        assert out['counts'] == {'created': 0, 'updated': 0, 'unchanged': 1,
                                 'skipped': 0, 'conflicts': 0, 'errors': 0}
        assert out['unchanged'][0]['id'] == added_tree_id

    def test_moved_point_and_attribute(self, client, auth_headers, added_tree_id):
        f = self._pull(client, auth_headers, added_tree_id)
        lon, lat = f['geometry']['coordinates']
        f['geometry']['coordinates'] = [lon + 0.001, lat + 0.001]
        f['properties']['comments'] = 'nota da QGIS'
        out = self._push(client, auth_headers, [f]).get_json()
        assert out['counts']['updated'] == 1
        changed = set(out['updated'][0]['changed'])
        assert {'latitude', 'longitude', 'comments'} <= changed
        d = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert abs(d['latitude'] - (lat + 0.001)) < 1e-9 and d['comments'] == 'nota da QGIS'
        assert d['updated_by'] == 'admin'

    def test_geometry_wins_over_stale_lat_lon(self, client, auth_headers, added_tree_id):
        """Spostando il punto in QGIS le colonne latitude/longitude restano
        quelle del pull: deve valere la geometria."""
        f = self._pull(client, auth_headers, added_tree_id)
        lon, lat = f['geometry']['coordinates']
        f['geometry']['coordinates'] = [lon + 0.002, lat + 0.002]
        out = self._push(client, auth_headers, [f]).get_json()
        assert out['counts']['updated'] == 1
        d = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert abs(d['latitude'] - (lat + 0.002)) < 1e-9

    def test_derived_fields_ignored(self, client, auth_headers, added_arete_tree_id):
        f = self._pull(client, auth_headers, added_arete_tree_id)
        before = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        f['properties']['bersaglio_chioma'] = 7
        f['properties']['valore_ecologico'] = 999999
        f['properties']['city'] = 'ComuneInventato'
        out = self._push(client, auth_headers, [f]).get_json()
        assert 'bersaglio_chioma' in out['ignored_fields']
        after = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert after['bersaglio_chioma'] == before['bersaglio_chioma']
        assert after['valore_ecologico'] == before['valore_ecologico']
        assert after['city'] == before['city']

    def test_risk_recomputed_from_inputs(self, client, auth_headers, added_arete_tree_id):
        f = self._pull(client, auth_headers, added_arete_tree_id)
        before = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert before['rischio'], 'il fixture ARETE deve avere il rischio calcolato'
        f['properties']['pericolo_rami'] = '1'
        out = self._push(client, auth_headers, [f]).get_json()
        assert out['counts']['updated'] == 1 and 'rischio' in out['updated'][0]['changed']
        after = client.get(f'/tree/{added_arete_tree_id}', headers=auth_headers).get_json()
        assert after['rischio'] != before['rischio']

    def test_new_tree_created(self, client, auth_headers):
        feat = {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [9.2, 45.5]},
                'properties': {'custom_id': 'QGIS-NEW-1', 'species': 'Acer campestre'}}
        out = self._push(client, auth_headers, [feat]).get_json()
        assert out['counts']['created'] == 1
        new = out['created'][0]
        assert new['id'] and new['uuid'] and new['custom_id'] == 'QGIS-NEW-1'
        try:
            d = client.get(f"/tree/{new['id']}", headers=auth_headers).get_json()
            assert d['species'] == 'Acer campestre' and d['city'] == TEST_TREE['city']
            insp = client.get(f"/tree/{new['id']}/inspections", headers=auth_headers).get_json()
            assert len(insp) == 1 and insp[0]['snapshot']['species'] == 'Acer campestre'
        finally:
            client.delete(f"/tree/{new['id']}", headers=auth_headers)

    def test_snapshot_inspection_keeps_previous_state(self, client, auth_headers, added_tree_id):
        before = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        n0 = len(client.get(f'/tree/{added_tree_id}/inspections', headers=auth_headers).get_json())
        f = self._pull(client, auth_headers, added_tree_id)
        f['properties']['species'] = 'Specie cambiata da QGIS'
        assert self._push(client, auth_headers, [f]).get_json()['counts']['updated'] == 1
        insp = client.get(f'/tree/{added_tree_id}/inspections', headers=auth_headers).get_json()
        assert len(insp) == n0 + 1
        last = insp[0]
        assert 'QGIS' in (last['comments'] or '') and 'species' in (last['comments'] or '')
        snap = last['snapshot']
        if isinstance(snap, str): snap = json.loads(snap)
        assert snap['species'] == before['species']   # lo snapshot è PRIMA della modifica

    def test_no_inspection_when_nothing_changes(self, client, auth_headers, added_tree_id):
        n0 = len(client.get(f'/tree/{added_tree_id}/inspections', headers=auth_headers).get_json())
        f = self._pull(client, auth_headers, added_tree_id)
        assert self._push(client, auth_headers, [f]).get_json()['counts']['unchanged'] == 1
        assert len(client.get(f'/tree/{added_tree_id}/inspections', headers=auth_headers).get_json()) == n0

    def test_dry_run_writes_nothing(self, client, auth_headers, added_tree_id):
        before = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        f = self._pull(client, auth_headers, added_tree_id)
        f['properties']['comments'] = 'anteprima'
        new = {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [9.3, 45.6]},
               'properties': {'custom_id': 'QGIS-DRY-1', 'species': 'Tilia'}}
        out = self._push(client, auth_headers, [f, new], dry_run=True).get_json()
        assert out['dry_run'] and out['counts']['updated'] == 1 and out['counts']['created'] == 1
        assert 'comments' in out['updated'][0]['changed']
        after = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert after['comments'] == before['comments'] and after['updated_at'] == before['updated_at']
        assert client.get('/tree/custom/QGIS-DRY-1', headers=auth_headers).status_code == 404

    def test_conflict_detected_and_forced(self, client, auth_headers, added_tree_id):
        f = self._pull(client, auth_headers, added_tree_id)          # updated_at "visto"
        client.patch(f'/tree/{added_tree_id}', json={'actions': 'modifica dalla webapp'},
                     headers=auth_headers)                          # qualcuno scrive dopo
        f['properties']['comments'] = 'modifica da QGIS'
        out = self._push(client, auth_headers, [f]).get_json()
        assert out['counts']['conflicts'] == 1 and out['counts']['updated'] == 0
        c = out['conflicts'][0]
        assert c['id'] == added_tree_id and c['server_updated_at'] > c['seen_updated_at']
        assert client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()['comments'] != 'modifica da QGIS'
        # force: la modifica di QGIS vince
        out = self._push(client, auth_headers, [f], force=True).get_json()
        assert out['counts']['updated'] == 1
        assert client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()['comments'] == 'modifica da QGIS'

    def test_unknown_uuid_is_an_error_not_a_new_tree(self, client, auth_headers, added_tree_id):
        f = self._pull(client, auth_headers, added_tree_id)
        f['properties']['uuid'] = '00000000-0000-0000-0000-000000000000'
        out = self._push(client, auth_headers, [f]).get_json()
        assert out['counts']['errors'] == 1 and out['counts']['created'] == 0
        assert 'uuid' in out['errors'][0]['message']

    def test_on_conflict_skip(self, client, auth_headers, added_tree_id):
        f = self._pull(client, auth_headers, added_tree_id)
        f['properties']['comments'] = 'non deve entrare'
        out = self._push(client, auth_headers, [f], on_conflict='skip').get_json()
        assert out['counts']['skipped'] == 1
        assert client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()['comments'] != 'non deve entrare'

    def test_custom_column_mapping(self, client, auth_headers, added_tree_id):
        f = self._pull(client, auth_headers, added_tree_id)
        feat = {'type': 'Feature', 'geometry': f['geometry'],
                'properties': {'silvae_uuid': f['properties']['uuid'],
                               'Specie': 'Quercus da mappatura', 'NOTE': 'commento mappato'}}
        out = self._push(client, auth_headers, [feat],
                         mapping={'silvae_uuid': 'uuid', 'Specie': 'species', 'NOTE': 'comments'}).get_json()
        assert out['counts']['updated'] == 1
        d = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert d['species'] == 'Quercus da mappatura' and d['comments'] == 'commento mappato'

    def test_validation(self, client, auth_headers, added_tree_id):
        f = self._pull(client, auth_headers, added_tree_id)
        assert self._push(client, auth_headers, []).status_code == 400
        assert self._push(client, auth_headers, [f], city='').status_code == 400
        assert client.post('/qgis/features', json={'features': [f], 'city': 'X'}).status_code == 401
        big = [f] * 2001
        assert self._push(client, auth_headers, big).status_code == 413

    def test_mapping_endpoint(self, client, auth_headers):
        res = client.post('/qgis/mapping', json={'columns': ['_NUMERO', '_TASSONOMI', 'pippo', 'uuid']},
                          headers=auth_headers)
        assert res.status_code == 200
        body = res.get_json()
        assert body['mapping']['_NUMERO'] == 'custom_id' and body['mapping']['_TASSONOMI'] == 'species'
        assert 'pippo' not in body['mapping']
        assert 'species' in body['fields'] and 'rischio' in body['derived']

    def test_city_readonly_cannot_push(self, client, added_tree_id):
        res = client.post('/login', json={'username': 'demo_city', 'password': 'demo_city_password'})
        if res.status_code != 200:
            pytest.skip('account demo non disponibile')
        h = {'Authorization': f"Bearer {res.get_json()['token']}"}
        feat = {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [9, 45]},
                'properties': {'custom_id': 'X'}}
        assert self._push(client, h, [feat]).status_code == 403


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))

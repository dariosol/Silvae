"""
Unit tests for the Tree Management API.

Run with:
    python -m pytest test_flask_api.py -v

The tests use Flask's built-in test client — no running server needed.
They share the real PostgreSQL database but clean up any data they create.
"""
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
    """Log in as admin and return the JWT token."""
    res = client.post('/login', json={'username': 'admin', 'password': 'password'})
    assert res.status_code == 200, f"Admin login failed: {res.get_json()}"
    return res.get_json()['token']


@pytest.fixture
def auth_headers(admin_token):
    return {'Authorization': f'Bearer {admin_token}'}


# Test tree data; custom_id is made unique enough to avoid collisions
TEST_TREE = {
    'custom_id': 'PYTEST-001',
    'species': 'Quercus robur',
    'condition': 'Good',
    'city': 'TestCity',
    'latitude': 45.4642,
    'longitude': 9.1900,
    'address': 'Via Test 1, TestCity',
}


@pytest.fixture
def added_tree_id(client, auth_headers):
    """Add a test tree and return its id; delete it on teardown."""
    # Clean up any leftover from a previous failed run
    with flask_app.app_context():
        leftover = Tree.query.filter_by(custom_id=TEST_TREE['custom_id']).first()
        if leftover:
            db.session.delete(leftover)
            db.session.commit()

    res = client.post('/add_tree', json=TEST_TREE, headers=auth_headers)
    assert res.status_code == 201, f"Setup tree creation failed: {res.get_json()}"
    tree_id = res.get_json()['tree_id']

    yield tree_id

    with flask_app.app_context():
        tree = db.session.get(Tree, tree_id)
        if tree:
            db.session.delete(tree)
            db.session.commit()


# ---------------------------------------------------------------------------
# Auth tests
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
        res = client.get('/trees')
        assert res.status_code == 401

    def test_protected_route_with_bad_token(self, client):
        res = client.get('/trees', headers={'Authorization': 'Bearer notavalidtoken'})
        assert res.status_code == 401

    def test_me_endpoint(self, client, auth_headers):
        res = client.get('/me', headers=auth_headers)
        assert res.status_code == 200
        assert res.get_json()['username'] == 'admin'


# ---------------------------------------------------------------------------
# Tree CRUD tests
# ---------------------------------------------------------------------------

class TestTreeCRUD:
    def test_add_tree(self, client, auth_headers, added_tree_id):
        assert isinstance(added_tree_id, int)

    def test_add_tree_missing_required_fields(self, client, auth_headers):
        res = client.post('/add_tree', json={'custom_id': 'INCOMPLETE'}, headers=auth_headers)
        assert res.status_code == 400

    def test_add_tree_duplicate_custom_id(self, client, auth_headers, added_tree_id):
        res = client.post('/add_tree', json=TEST_TREE, headers=auth_headers)
        assert res.status_code == 409

    def test_get_trees(self, client, auth_headers, added_tree_id):
        res = client.get('/trees', headers=auth_headers)
        assert res.status_code == 200
        trees = res.get_json()
        assert isinstance(trees, list)
        ids = [t['id'] for t in trees]
        assert added_tree_id in ids

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
        # Verify the change persisted
        data = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert data['condition'] == 'Poor'
        assert data['comments'] == 'Needs pruning'

    def test_update_tree_species(self, client, auth_headers, added_tree_id):
        res = client.patch(f'/tree/{added_tree_id}',
                           json={'species': 'Fagus sylvatica'},
                           headers=auth_headers)
        assert res.status_code == 200
        data = client.get(f'/tree/{added_tree_id}', headers=auth_headers).get_json()
        assert data['species'] == 'Fagus sylvatica'

    def test_filter_trees_by_city(self, client, auth_headers, added_tree_id):
        res = client.get('/trees?city=TestCity', headers=auth_headers)
        assert res.status_code == 200
        trees = res.get_json()
        assert all(t['city'] == 'TestCity' for t in trees)

    def test_delete_tree(self, client, auth_headers):
        # Add a dedicated tree for this test so we don't touch added_tree_id
        res = client.post('/add_tree',
                          json={**TEST_TREE, 'custom_id': 'PYTEST-DEL'},
                          headers=auth_headers)
        assert res.status_code == 201
        tid = res.get_json()['tree_id']

        res = client.delete(f'/tree/{tid}', headers=auth_headers)
        assert res.status_code == 200

        res = client.get(f'/tree/{tid}', headers=auth_headers)
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Role-based access tests
# ---------------------------------------------------------------------------

class TestRoleAccess:
    @pytest.fixture(autouse=True)
    def city_user(self, client, auth_headers):
        """Create a city-role user for TestCity and remove it afterwards."""
        res = client.post('/add_user',
                          json={'username': 'pytest_cityuser',
                                'password': 'testpass',
                                'role': 'city',
                                'city': 'TestCity'},
                          headers=auth_headers)
        assert res.status_code == 201, f"Could not create city user: {res.get_json()}"
        yield
        with flask_app.app_context():
            u = User.query.filter_by(username='pytest_cityuser').first()
            if u:
                db.session.delete(u)
                db.session.commit()

    def _login(self, client, username, password):
        res = client.post('/login', json={'username': username, 'password': password})
        assert res.status_code == 200
        return {'Authorization': 'Bearer ' + res.get_json()['token']}

    def test_city_user_sees_own_city_only(self, client, auth_headers, added_tree_id):
        city_headers = self._login(client, 'pytest_cityuser', 'testpass')
        # Add a tree in a different city as admin
        res = client.post('/add_tree',
                          json={**TEST_TREE,
                                'custom_id': 'PYTEST-OTHER',
                                'city': 'OtherCity'},
                          headers=auth_headers)
        assert res.status_code == 201
        other_id = res.get_json()['tree_id']

        try:
            trees = client.get('/trees', headers=city_headers).get_json()
            cities = {t['city'] for t in trees}
            assert 'OtherCity' not in cities
        finally:
            with flask_app.app_context():
                t = db.session.get(Tree, other_id)
                if t:
                    db.session.delete(t)
                    db.session.commit()

    def test_superuser_can_create_city_user(self, client, auth_headers):
        # The city_user fixture already verified this — just assert the user exists
        res = client.get('/users', headers=auth_headers)
        assert res.status_code == 200
        usernames = [u['username'] for u in res.get_json()]
        assert 'pytest_cityuser' in usernames

    def test_city_user_cannot_create_superuser(self, client):
        city_headers = self._login(client, 'pytest_cityuser', 'testpass')
        res = client.post('/add_user',
                          json={'username': 'evil', 'password': 'x', 'role': 'superuser'},
                          headers=city_headers)
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_excel(self, client, auth_headers, added_tree_id):
        res = client.get('/export/excel', headers=auth_headers)
        assert res.status_code == 200
        assert 'spreadsheetml' in res.content_type
        assert len(res.data) > 0

    def test_export_geojson(self, client, auth_headers, added_tree_id):
        res = client.get('/export/geojson', headers=auth_headers)
        assert res.status_code == 200
        assert 'json' in res.content_type
        geo = res.get_json()
        assert geo['type'] == 'FeatureCollection'
        assert isinstance(geo['features'], list)
        ids = [f['properties']['id'] for f in geo['features']]
        assert added_tree_id in ids

    def test_export_requires_auth(self, client):
        assert client.get('/export/excel').status_code == 401
        assert client.get('/export/geojson').status_code == 401


if __name__ == '__main__':
    import sys
    import pytest
    sys.exit(pytest.main([__file__, '-v']))

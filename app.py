#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from geoalchemy2 import Geometry
from geopy.geocoders import Nominatim
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from functools import wraps
import os
import io
import json
import openpyxl

# -----------------------
# Configuration
# -----------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Use environment variable if available, otherwise fallback (change for production)
DB_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:c0st4m4gn4@localhost/trees_db')
app.config['SQLALCHEMY_DATABASE_URI'] = DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
SECRET_KEY = os.environ.get('SECRET_KEY', 'super-secret-change-me')
app.config['SECRET_KEY'] = SECRET_KEY

db = SQLAlchemy(app)
geolocator = Nominatim(user_agent="tree_locator")

# -----------------------
# Models
# -----------------------
class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # superuser, city, user
    city = db.Column(db.String(100), nullable=True)  # city name for city-users and normal users

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class City(db.Model):
    __tablename__ = 'city'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

class Tree(db.Model):
    __tablename__ = 'tree'
    __table_args__ = (
        db.UniqueConstraint('custom_id', 'city', name='uq_tree_custom_id_city'),
    )
    id = db.Column(db.Integer, primary_key=True)
    custom_id = db.Column(db.String(50), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    address = db.Column(db.String(255))
    city = db.Column(db.String(100), nullable=False)
    species = db.Column(db.String(100), nullable=False)
    condition = db.Column(db.String(50), nullable=False)
    comments = db.Column(db.Text)
    actions = db.Column(db.Text)
    height = db.Column(db.String(50))
    trunk_diameter_cm = db.Column(db.Float)
    crown_diameter_m = db.Column(db.Float)
    age = db.Column(db.String(50))
    location = db.Column(db.String(255))
    cpc = db.Column(db.String(50))
    next_check = db.Column(db.Date)
    geom = db.Column(Geometry('POINT', srid=4326))
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class Inspection(db.Model):
    __tablename__ = 'inspection'
    id            = db.Column(db.Integer, primary_key=True)
    tree_id       = db.Column(db.Integer, db.ForeignKey('tree.id', ondelete='CASCADE'), nullable=False)
    date          = db.Column(db.Date, nullable=False)
    condition     = db.Column(db.String(50))
    comments      = db.Column(db.Text)
    actions       = db.Column(db.Text)
    inspector_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    inspector_name= db.Column(db.String(80))
    created_at    = db.Column(db.DateTime(timezone=True),
                              default=lambda: datetime.now(timezone.utc))

# -----------------------
# Create tables (dev)
# -----------------------
with app.app_context():
    db.create_all()

# -----------------------
# Helpers: auth decorators
# -----------------------
def generate_token(user, expires_minutes=60*24):
    payload = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "city": user.city,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    # pyjwt returns str for v2+, keep consistent
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return token

def auth_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', None)
        if not auth:
            return jsonify({'message': 'Missing Authorization header'}), 401
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
        else:
            token = auth

        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expired'}), 401
        except Exception as e:
            return jsonify({'message': 'Invalid token', 'error': str(e)}), 401

        # attach user info to request context
        request.user = data
        return f(*args, **kwargs)
    return wrapper

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not hasattr(request, 'user'):
                return jsonify({'message': 'Unauthorized'}), 401
            role = request.user.get('role')
            if role not in allowed_roles:
                return jsonify({'message': 'Forbidden - insufficient role'}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator

# -----------------------
# Auth endpoints
# -----------------------
@app.route('/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'message': 'username and password required'}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'message': 'Invalid credentials'}), 401

    token = generate_token(user)
    return jsonify({
        'token': token,
        'user': {'id': user.id, 'username': user.username, 'role': user.role, 'city': user.city}
    })

@app.route('/me', methods=['GET'])
@auth_required
def me():
    return jsonify({
        'user_id': request.user.get('user_id'),
        'username': request.user.get('username'),
        'role': request.user.get('role'),
        'city': request.user.get('city')
    })

# -----------------------
# User management
# -----------------------
@app.route('/add_user', methods=['POST'])
@auth_required
def add_user():
    creator = request.user
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    city = data.get('city')

    if not username or not password or not role:
        return jsonify({'message': 'username, password and role are required'}), 400

    # Users cannot create users
    if creator['role'] == 'user':
        return jsonify({'message': 'Users cannot create new users'}), 403

    # City-roles can only create normal 'user' accounts assigned to their own city
    if creator['role'] == 'city':
        if role != 'user':
            return jsonify({'message': 'City users can only create users with role "user"'}), 403
        if city and city != creator.get('city'):
            return jsonify({'message': 'City users can only create users in their own city'}), 403
        # force city to creator city
        city = creator.get('city')

    # Superuser can create anything; if city is provided that's fine.

    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Username already exists'}), 400

    new_user = User(username=username, role=role, city=city)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': 'User created', 'user': {'id': new_user.id, 'username': username, 'role': role, 'city': city}}), 201

@app.route('/users', methods=['GET'])
@auth_required
def list_users():
    # superuser -> all. city -> its city. user -> only itself
    role = request.user.get('role')
    user_city = request.user.get('city')
    user_id = request.user.get('user_id')

    if role == 'superuser':
        users = User.query.all()
    elif role == 'city':
        users = User.query.filter_by(city=user_city).all()
    else:  # role == user
        users = User.query.filter_by(id=user_id).all()

    return jsonify([{'id': u.id, 'username': u.username, 'role': u.role, 'city': u.city} for u in users])

# -----------------------
# City management
# -----------------------
@app.route('/admin/cities', methods=['POST'])
@auth_required
@role_required('superuser')
def add_city():
    data = request.json or {}
    name = data.get('name')
    if not name:
        return jsonify({'message': 'City name required'}), 400
    if City.query.filter_by(name=name).first():
        return jsonify({'message': 'City already exists'}), 400
    c = City(name=name)
    db.session.add(c)
    db.session.commit()
    return jsonify({'message': 'City created', 'city': {'id': c.id, 'name': c.name}}), 201

@app.route('/cities', methods=['GET'])
def get_cities():
    """Union of canonical City table and any city values already on trees."""
    from_table = {c.name for c in City.query.all()}
    from_trees = {row[0] for row in db.session.query(Tree.city).distinct() if row[0]}
    return jsonify(sorted(from_table | from_trees))

# -----------------------
# Tree endpoints (updated with owner & role checks)
# -----------------------
@app.route('/trees', methods=['GET'])
@auth_required
def get_trees():
    role = request.user.get('role')
    user_city = request.user.get('city')
    user_id = request.user.get('user_id')

    city_q = request.args.get('city')
    address_part = request.args.get('address')

    query = Tree.query

    # Role-based visibility
    if role == 'user':
        query = query.filter(Tree.owner_id == user_id)
    elif role == 'city':
        # city users see all trees in their city
        query = query.filter(Tree.city == user_city)
    # superuser sees all

    # optional query filters
    if city_q:
        query = query.filter(Tree.city.ilike(f"%{city_q}%"))
    if address_part:
        query = query.filter(Tree.address.ilike(f"%{address_part}%"))

    trees = query.all()
    return jsonify([
        {
            'id': t.id,
            'custom_id': t.custom_id,
            'latitude': t.latitude,
            'longitude': t.longitude,
            'address': t.address,
            'city': t.city,
            'species': t.species,
            'condition': t.condition,
            'comments': t.comments,
            'actions': t.actions,
            'height': t.height,
            'trunk_diameter_cm': t.trunk_diameter_cm,
            'crown_diameter_m': t.crown_diameter_m,
            'age': t.age,
            'location': t.location,
            'cpc': t.cpc,
            'next_check': t.next_check.strftime("%Y-%m-%d") if t.next_check else None,
            'owner_id': t.owner_id
        } for t in trees
    ])

@app.route('/tree/<int:tree_id>', methods=['GET'])
@auth_required
def get_tree_by_id(tree_id):
    tree = db.session.get(Tree, tree_id)
    if not tree:
        return jsonify({'message': 'Tree not found'}), 404

    # permission check
    role = request.user.get('role')
    user_city = request.user.get('city')
    user_id = request.user.get('user_id')

    if role == 'user' and tree.owner_id != user_id:
        return jsonify({'message': 'Forbidden'}), 403
    if role == 'city' and tree.city != user_city:
        return jsonify({'message': 'Forbidden'}), 403

    return jsonify({
        'id': tree.id,
        'custom_id': tree.custom_id,
        'latitude': tree.latitude,
        'longitude': tree.longitude,
        'address': tree.address,
        'city': tree.city,
        'species': tree.species,
        'condition': tree.condition,
        'comments': tree.comments,
        'actions': tree.actions,
        'height': tree.height,
        'trunk_diameter_cm': tree.trunk_diameter_cm,
        'crown_diameter_m': tree.crown_diameter_m,
        'age': tree.age,
        'location': tree.location,
        'cpc': tree.cpc,
        'next_check': tree.next_check.strftime("%Y-%m-%d") if tree.next_check else None,
        'owner_id': tree.owner_id
    })

@app.route('/tree/<int:tree_id>', methods=['PATCH'])
@auth_required
def update_tree(tree_id):
    tree = db.session.get(Tree, tree_id)
    if not tree:
        return jsonify({'message': 'Tree not found'}), 404

    role = request.user.get('role')
    user_city = request.user.get('city')
    user_id = request.user.get('user_id')

    # permission check: user can only update own trees; city only in their city; superuser can do all
    if role == 'user' and tree.owner_id != user_id:
        return jsonify({'message': 'Forbidden'}), 403
    if role == 'city' and tree.city != user_city:
        return jsonify({'message': 'Forbidden'}), 403

    data = request.json or {}
    for field in ['species', 'condition', 'comments', 'actions', 'height',
                  'trunk_diameter_cm', 'crown_diameter_m', 'age', 'location', 'cpc', 'address']:
        if field in data:
            setattr(tree, field, data[field])

    if 'next_check' in data and data['next_check']:
        try:
            tree.next_check = datetime.strptime(data['next_check'], "%Y-%m-%d")
        except ValueError:
            return jsonify({'message': 'Invalid date format for next_check. Use YYYY-MM-DD'}), 400

    if data.get('latitude') and data.get('longitude'):
        try:
            tree.latitude = float(data['latitude'])
            tree.longitude = float(data['longitude'])
            tree.geom = f'SRID=4326;POINT({float(data["longitude"])} {float(data["latitude"])})'
        except (ValueError, TypeError):
            return jsonify({'message': 'Invalid latitude/longitude values'}), 400

    db.session.commit()

    # Auto-log inspection whenever any inspection-relevant field was touched
    inspection_fields = {'condition', 'comments', 'actions'}
    if inspection_fields & set(data.keys()):
        db.session.add(Inspection(
            tree_id=tree_id,
            date=datetime.now(timezone.utc).date(),
            condition=tree.condition,
            comments=tree.comments or '',
            actions=tree.actions or '',
            inspector_id=request.user.get('user_id'),
            inspector_name=request.user.get('username')
        ))
        db.session.commit()

    return jsonify({'message': f'Tree {tree_id} updated successfully!'}), 200

@app.route('/tree/<int:tree_id>', methods=['DELETE'])
@auth_required
def delete_tree(tree_id):
    tree = db.session.get(Tree, tree_id)
    if not tree:
        return jsonify({'message': 'Tree not found'}), 404

    role = request.user.get('role')
    user_city = request.user.get('city')
    user_id = request.user.get('user_id')

    if role == 'user' and tree.owner_id != user_id:
        return jsonify({'message': 'Forbidden'}), 403
    if role == 'city' and tree.city != user_city:
        return jsonify({'message': 'Forbidden'}), 403

    db.session.delete(tree)
    db.session.commit()
    return jsonify({'message': f'Tree {tree_id} deleted successfully!'}), 200

@app.route('/add_tree', methods=['POST'])
@auth_required
def add_tree():
    data = request.json or {}
    # owner is set from token
    user_id = request.user.get('user_id')
    role = request.user.get('role')
    user_city = request.user.get('city')

    # basic required fields (custom_id, species, condition, city or use user's city)
    if not data.get('custom_id') or not data.get('species') or not data.get('condition'):
        return jsonify({'message': 'custom_id, species and condition are required'}), 400

    # if role is 'user' or 'city' and no city provided, use user's city
    if not data.get('city'):
        if role in ('user', 'city') and user_city:
            data['city'] = user_city
        else:
            return jsonify({'message': 'city is required'}), 400

    # geo fallback
    if not data.get('latitude') or not data.get('longitude'):
        full_address = (data.get('address') or '') + " " + data.get('city', '')
        location = geolocator.geocode(full_address)
        if location:
            data['latitude'] = location.latitude
            data['longitude'] = location.longitude
        else:
            return jsonify({'error': 'Invalid address, coordinates not found'}), 400

    # create
    try:
        next_check_date = datetime.strptime(data.get('next_check'), "%Y-%m-%d") if data.get('next_check') else None
    except ValueError:
        return jsonify({'message': 'Invalid date format for next_check. Use YYYY-MM-DD'}), 400

    new_tree = Tree(
        custom_id=data['custom_id'],
        latitude=float(data['latitude']),
        longitude=float(data['longitude']),
        address=data.get('address', ''),
        city=data['city'],
        species=data['species'],
        condition=data['condition'],
        comments=data.get('comments', ''),
        actions=data.get('actions', ''),
        height=data.get('height', ''),
        trunk_diameter_cm=data.get('trunk_diameter_cm'),
        crown_diameter_m=data.get('crown_diameter_m'),
        age=data.get('age', ''),
        location=data.get('location', ''),
        cpc=data.get('cpc', ''),
        next_check=next_check_date,
        geom=f'SRID=4326;POINT({float(data["longitude"])} {float(data["latitude"])})',
        owner_id=user_id
    )

    db.session.add(new_tree)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'message': f"Custom ID '{data['custom_id']}' already exists in {data['city']}"}), 409

    # Record initial inspection
    db.session.add(Inspection(
        tree_id=new_tree.id,
        date=datetime.now(timezone.utc).date(),
        condition=new_tree.condition,
        comments=new_tree.comments or '',
        actions=new_tree.actions or '',
        inspector_id=user_id,
        inspector_name=request.user.get('username')
    ))
    db.session.commit()
    return jsonify({'message': 'Tree added successfully!', 'tree_id': new_tree.id}), 201

@app.route('/tree/custom/<string:custom_id>', methods=['GET'])
@auth_required
def get_tree_by_custom_id(custom_id):
    role = request.user.get('role')
    user_city = request.user.get('city')
    user_id = request.user.get('user_id')

    query = Tree.query.filter_by(custom_id=custom_id)

    # Scope automatically by role so the same custom_id in different cities is unambiguous
    if role == 'user':
        query = query.filter(Tree.owner_id == user_id)
    elif role == 'city':
        query = query.filter(Tree.city == user_city)
    else:
        # superuser: optional ?city= filter to disambiguate across cities
        city_param = request.args.get('city')
        if city_param:
            query = query.filter(Tree.city == city_param)

    tree = query.first()
    if not tree:
        return jsonify({'message': 'Tree not found'}), 404

    return jsonify({
        'id': tree.id,
        'custom_id': tree.custom_id,
        'latitude': tree.latitude,
        'longitude': tree.longitude,
        'address': tree.address,
        'city': tree.city,
        'species': tree.species,
        'condition': tree.condition,
        'comments': tree.comments,
        'actions': tree.actions,
        'height': tree.height,
        'trunk_diameter_cm': tree.trunk_diameter_cm,
        'crown_diameter_m': tree.crown_diameter_m,
        'age': tree.age,
        'location': tree.location,
        'cpc': tree.cpc,
        'next_check': tree.next_check.strftime("%Y-%m-%d") if tree.next_check else None,
        'owner_id': tree.owner_id
    })

@app.route('/tree/<int:tree_id>/inspections', methods=['GET'])
@auth_required
def get_inspections(tree_id):
    tree = db.session.get(Tree, tree_id)
    if not tree:
        return jsonify({'message': 'Tree not found'}), 404

    role = request.user.get('role')
    user_city = request.user.get('city')
    user_id = request.user.get('user_id')
    if role == 'user' and tree.owner_id != user_id:
        return jsonify({'message': 'Forbidden'}), 403
    if role == 'city' and tree.city != user_city:
        return jsonify({'message': 'Forbidden'}), 403

    rows = (Inspection.query
            .filter_by(tree_id=tree_id)
            .order_by(Inspection.date.desc(), Inspection.created_at.desc())
            .all())
    return jsonify([{
        'id': i.id,
        'date': i.date.strftime('%Y-%m-%d'),
        'condition': i.condition,
        'comments': i.comments,
        'actions': i.actions,
        'inspector_name': i.inspector_name,
        'created_at': i.created_at.strftime('%Y-%m-%d %H:%M') if i.created_at else None
    } for i in rows])

@app.route('/tree/<int:tree_id>/inspections', methods=['POST'])
@auth_required
def add_inspection(tree_id):
    tree = db.session.get(Tree, tree_id)
    if not tree:
        return jsonify({'message': 'Tree not found'}), 404

    role = request.user.get('role')
    user_city = request.user.get('city')
    user_id = request.user.get('user_id')
    if role == 'user' and tree.owner_id != user_id:
        return jsonify({'message': 'Forbidden'}), 403
    if role == 'city' and tree.city != user_city:
        return jsonify({'message': 'Forbidden'}), 403

    data = request.json or {}
    date_str = data.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    try:
        insp_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'message': 'Invalid date format, use YYYY-MM-DD'}), 400

    insp = Inspection(
        tree_id=tree_id,
        date=insp_date,
        condition=data.get('condition') or tree.condition,
        comments=data.get('comments', ''),
        actions=data.get('actions', ''),
        inspector_id=user_id,
        inspector_name=request.user.get('username')
    )
    db.session.add(insp)
    db.session.commit()
    return jsonify({'message': 'Inspection logged', 'id': insp.id}), 201

@app.route('/test_geocode', methods=['POST'])
def test_geocode():
    address = request.json.get('address')
    location = geolocator.geocode(address)
    if location:
        return jsonify({'latitude': location.latitude, 'longitude': location.longitude})
    return jsonify({'error': 'Address not found'}), 404

@app.route('/reverse_geocode', methods=['POST'])
@auth_required
def reverse_geocode():
    data = request.json or {}
    lat = data.get('latitude')
    lon = data.get('longitude')
    if lat is None or lon is None:
        return jsonify({'message': 'latitude and longitude required'}), 400
    try:
        location = geolocator.reverse(f"{lat}, {lon}", language='en')
        if location:
            addr = location.raw.get('address', {})
            city = (addr.get('city') or addr.get('town') or
                    addr.get('village') or addr.get('municipality') or '')
            return jsonify({'address': location.address, 'city': city})
    except Exception:
        pass
    return jsonify({'address': '', 'city': ''})

@app.route('/export/excel', methods=['GET'])
@auth_required
def export_excel():
    role = request.user.get('role')
    user_city = request.user.get('city')
    user_id = request.user.get('user_id')

    query = Tree.query
    if role == 'user':
        query = query.filter(Tree.owner_id == user_id)
    elif role == 'city':
        query = query.filter(Tree.city == user_city)
    trees = query.all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Trees'
    ws.append(['ID', 'Custom ID', 'City', 'Address', 'Latitude', 'Longitude',
               'Species', 'Condition', 'Height (m)', 'Trunk Diameter (cm)',
               'Crown Diameter (m)', 'Age', 'Location', 'CPC Code',
               'Comments', 'Actions', 'Next Check', 'Owner ID'])
    for t in trees:
        ws.append([
            t.id, t.custom_id, t.city, t.address, t.latitude, t.longitude,
            t.species, t.condition, t.height, t.trunk_diameter_cm,
            t.crown_diameter_m, t.age, t.location, t.cpc,
            t.comments, t.actions,
            t.next_check.strftime("%Y-%m-%d") if t.next_check else None,
            t.owner_id
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, download_name='trees.xlsx', as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/export/geojson', methods=['GET'])
@auth_required
def export_geojson():
    role = request.user.get('role')
    user_city = request.user.get('city')
    user_id = request.user.get('user_id')

    query = Tree.query
    if role == 'user':
        query = query.filter(Tree.owner_id == user_id)
    elif role == 'city':
        query = query.filter(Tree.city == user_city)
    trees = query.all()

    features = []
    for t in trees:
        if t.latitude is None or t.longitude is None:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [t.longitude, t.latitude]},
            "properties": {
                "id": t.id, "custom_id": t.custom_id, "city": t.city,
                "address": t.address, "species": t.species, "condition": t.condition,
                "height": t.height, "trunk_diameter_cm": t.trunk_diameter_cm,
                "crown_diameter_m": t.crown_diameter_m, "age": t.age,
                "location": t.location, "cpc": t.cpc, "comments": t.comments,
                "actions": t.actions,
                "next_check": t.next_check.strftime("%Y-%m-%d") if t.next_check else None,
                "owner_id": t.owner_id
            }
        })

    geojson = {"type": "FeatureCollection", "features": features}
    buf = io.BytesIO(json.dumps(geojson, ensure_ascii=False).encode('utf-8'))
    buf.seek(0)
    return send_file(buf, download_name='trees.geojson', as_attachment=True,
                     mimetype='application/geo+json')

# -----------------------
# Bootstrap: create initial superuser if none exists (dev convenience)
# -----------------------
with app.app_context():
    if not User.query.filter_by(role='superuser').first():
        su = User(username='admin', role='superuser', city=None)
        su.set_password('admin')  # CHANGE IMMEDIATELY in production
        db.session.add(su)
        db.session.commit()
        print("Created default superuser: admin / admin (change password!)")

# -----------------------
# Run (for dev)
# -----------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

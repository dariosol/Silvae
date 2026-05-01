#!/usr/bin/env python3
import sys, os, io, json, secrets
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from geoalchemy2 import Geometry
from geopy.geocoders import Nominatim
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy import inspect, text, case
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from functools import wraps
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

from Schede_Rilevamento_ARETE import dropdowns_ord as dd
from Schede_Rilevamento_ARETE.lookup_tables import (
    species_lookup, monitoraggio as lt_monitoraggio, urgenza as lt_urgenza,
    conflitti as lt_conflitti, agenti_di_carie as lt_agenti_carie,
    altri_patogeni as lt_altri_patogeni,
    prescrizioni_valutative as lt_prescrizioni_val,
    prescrizioni_mitigazione as lt_prescrizioni_mit,
    prescrizioni_colturali as lt_prescrizioni_col,
)
from Schede_Rilevamento_ARETE.ord_calculator import assess_tree

# -----------------------
# Configuration
# -----------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

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
    id                     = db.Column(db.Integer, primary_key=True)
    username               = db.Column(db.String(80), unique=True, nullable=False)
    email                  = db.Column(db.String(120), unique=True, nullable=True)
    password_hash          = db.Column(db.String(255), nullable=False)
    role                   = db.Column(db.String(20), nullable=False)
    city                   = db.Column(db.String(100), nullable=True)
    password_reset_token   = db.Column(db.String(100), nullable=True)
    password_reset_expires = db.Column(db.DateTime(timezone=True), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class CityMembership(db.Model):
    __tablename__ = 'city_membership'
    __table_args__ = (
        db.UniqueConstraint('city_user_id', 'agronomer_id', name='uq_city_agronomer'),
    )
    id           = db.Column(db.Integer, primary_key=True)
    city_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    agronomer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class City(db.Model):
    __tablename__ = 'city'
    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

class Comune(db.Model):
    __tablename__ = 'comune'
    id        = db.Column(db.Integer, primary_key=True)
    nome      = db.Column(db.String(120), nullable=False, index=True)
    provincia = db.Column(db.String(100))
    sigla     = db.Column(db.String(2))
    regione   = db.Column(db.String(100))
    codice    = db.Column(db.String(10), unique=True)

class Tree(db.Model):
    __tablename__ = 'tree'
    __table_args__ = (
        db.UniqueConstraint('custom_id', 'city', name='uq_tree_custom_id_city'),
    )
    # --- existing fields ---
    id               = db.Column(db.Integer, primary_key=True)
    custom_id        = db.Column(db.String(50), nullable=False)
    latitude         = db.Column(db.Float)
    longitude        = db.Column(db.Float)
    address          = db.Column(db.String(255))
    city             = db.Column(db.String(100), nullable=False)
    species          = db.Column(db.String(200), nullable=False)
    condition        = db.Column(db.String(50), nullable=False)
    comments         = db.Column(db.Text)
    actions          = db.Column(db.Text)
    height           = db.Column(db.String(50))
    trunk_diameter_cm= db.Column(db.Float)
    crown_diameter_m = db.Column(db.Float)
    age              = db.Column(db.String(50))
    location         = db.Column(db.String(255))
    cpc              = db.Column(db.String(50))
    next_check       = db.Column(db.Date)
    geom             = db.Column(Geometry('POINT', srid=4326))
    owner_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # --- ARETE dati generali ---
    dimora            = db.Column(db.String(100))
    stadio_sviluppo   = db.Column(db.String(50))
    posizione_sociale = db.Column(db.String(50))
    localizzazione    = db.Column(db.String(50))
    vincoli           = db.Column(db.String(100))

    # --- ORD dimensions (current) ---
    tree_height_m    = db.Column(db.Float)
    circonferenza_cm = db.Column(db.Float)
    branch_diam_cm   = db.Column(db.Float)
    branch_length_m  = db.Column(db.Float)
    branch_height_m  = db.Column(db.Float)
    target_height_m  = db.Column(db.Float)

    # --- ORD dimensions (post-intervention) ---
    post_tree_height_m    = db.Column(db.Float)
    post_circonferenza_cm = db.Column(db.Float)
    post_branch_diam_cm   = db.Column(db.Float)
    post_branch_length_m  = db.Column(db.Float)
    post_branch_height_m  = db.Column(db.Float)
    post_target_height_m  = db.Column(db.Float)

    # --- Pericolo (stored as string to allow '0 x sospet' etc.) ---
    pericolo_rami     = db.Column(db.String(20))
    pericolo_tronco   = db.Column(db.String(20))
    pericolo_colletto = db.Column(db.String(20))
    pericolo_zolla    = db.Column(db.String(20))

    # --- Bersaglio ---
    bersaglio_chioma = db.Column(db.Integer)
    bersaglio_ramo   = db.Column(db.Integer)

    # --- Diagnosi (JSON: [{caratt, giudizio}, ...]) ---
    diag_zolla        = db.Column(db.Text)
    diag_colletto     = db.Column(db.Text)
    diag_fusto        = db.Column(db.Text)
    diag_castello     = db.Column(db.Text)
    diag_ramificazione= db.Column(db.Text)
    diag_chioma       = db.Column(db.Text)

    # --- Other multi-select (JSON arrays) ---
    conflitti_list   = db.Column(db.Text)
    agenti_carie     = db.Column(db.Text)
    altri_patogeni   = db.Column(db.Text)
    prescrizioni_val = db.Column(db.Text)
    prescrizioni_mit = db.Column(db.Text)
    prescrizioni_col = db.Column(db.Text)
    monitoraggio     = db.Column(db.String(50))
    urgenza          = db.Column(db.String(50))
    rischio          = db.Column(db.Text)   # JSON: latest assess_tree result

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
    snapshot      = db.Column(db.Text)   # JSON snapshot of all tree fields at this moment
    rischio       = db.Column(db.Text)   # JSON: assess_tree result at inspection time
    created_at    = db.Column(db.DateTime(timezone=True),
                              default=lambda: datetime.now(timezone.utc))

# -----------------------
# DB init + migrate new columns
# -----------------------
with app.app_context():
    db.create_all()
    # Add any new columns that don't exist yet (safe for existing DBs)
    insp = inspect(db.engine)
    existing_cols = {c['name'] for c in insp.get_columns('tree')}
    new_cols = [
        ('dimora','VARCHAR(100)'), ('stadio_sviluppo','VARCHAR(50)'),
        ('posizione_sociale','VARCHAR(50)'), ('localizzazione','VARCHAR(50)'),
        ('vincoli','VARCHAR(100)'),
        ('tree_height_m','FLOAT'), ('circonferenza_cm','FLOAT'),
        ('branch_diam_cm','FLOAT'), ('branch_length_m','FLOAT'),
        ('branch_height_m','FLOAT'), ('target_height_m','FLOAT'),
        ('post_tree_height_m','FLOAT'), ('post_circonferenza_cm','FLOAT'),
        ('post_branch_diam_cm','FLOAT'), ('post_branch_length_m','FLOAT'),
        ('post_branch_height_m','FLOAT'), ('post_target_height_m','FLOAT'),
        ('pericolo_rami','VARCHAR(20)'), ('pericolo_tronco','VARCHAR(20)'),
        ('pericolo_colletto','VARCHAR(20)'), ('pericolo_zolla','VARCHAR(20)'),
        ('bersaglio_chioma','INTEGER'), ('bersaglio_ramo','INTEGER'),
        ('diag_zolla','TEXT'), ('diag_colletto','TEXT'), ('diag_fusto','TEXT'),
        ('diag_castello','TEXT'), ('diag_ramificazione','TEXT'), ('diag_chioma','TEXT'),
        ('conflitti_list','TEXT'), ('agenti_carie','TEXT'), ('altri_patogeni','TEXT'),
        ('prescrizioni_val','TEXT'), ('prescrizioni_mit','TEXT'), ('prescrizioni_col','TEXT'),
        ('monitoraggio','VARCHAR(50)'), ('urgenza','VARCHAR(50)'),
        ('rischio','TEXT'),
    ]
    with db.engine.connect() as conn:
        for col_name, col_type in new_cols:
            if col_name not in existing_cols:
                conn.execute(text(f'ALTER TABLE tree ADD COLUMN {col_name} {col_type}'))
        conn.commit()
    existing_insp_cols = {c['name'] for c in insp.get_columns('inspection')}
    insp_new_cols = [('snapshot', 'TEXT'), ('rischio', 'TEXT')]
    with db.engine.connect() as conn:
        for col_name, col_type in insp_new_cols:
            if col_name not in existing_insp_cols:
                conn.execute(text(f'ALTER TABLE inspection ADD COLUMN {col_name} {col_type}'))
        conn.commit()
    existing_user_cols = {c['name'] for c in insp.get_columns('user')}
    user_new_cols = [
        ('email', 'VARCHAR(120)'),
        ('password_reset_token', 'VARCHAR(100)'),
        ('password_reset_expires', 'TIMESTAMPTZ'),
    ]
    with db.engine.connect() as conn:
        for col_name, col_type in user_new_cols:
            if col_name not in existing_user_cols:
                conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {col_name} {col_type}'))
        conn.commit()

# -----------------------
# Helpers
# -----------------------
def parse_json_field(v):
    if not v: return []
    try: return json.loads(v)
    except: return []

def tree_to_dict(t):
    return {
        'id': t.id, 'custom_id': t.custom_id,
        'latitude': t.latitude, 'longitude': t.longitude,
        'address': t.address, 'city': t.city,
        'species': t.species, 'condition': t.condition,
        'comments': t.comments, 'actions': t.actions,
        'height': t.height, 'trunk_diameter_cm': t.trunk_diameter_cm,
        'crown_diameter_m': t.crown_diameter_m, 'age': t.age,
        'location': t.location, 'cpc': t.cpc,
        'next_check': t.next_check.strftime("%Y-%m-%d") if t.next_check else None,
        'owner_id': t.owner_id,
        # ARETE
        'dimora': t.dimora, 'stadio_sviluppo': t.stadio_sviluppo,
        'posizione_sociale': t.posizione_sociale, 'localizzazione': t.localizzazione,
        'vincoli': t.vincoli,
        'tree_height_m': t.tree_height_m, 'circonferenza_cm': t.circonferenza_cm,
        'branch_diam_cm': t.branch_diam_cm, 'branch_length_m': t.branch_length_m,
        'branch_height_m': t.branch_height_m, 'target_height_m': t.target_height_m,
        'post_tree_height_m': t.post_tree_height_m,
        'post_circonferenza_cm': t.post_circonferenza_cm,
        'post_branch_diam_cm': t.post_branch_diam_cm,
        'post_branch_length_m': t.post_branch_length_m,
        'post_branch_height_m': t.post_branch_height_m,
        'post_target_height_m': t.post_target_height_m,
        'pericolo_rami': t.pericolo_rami, 'pericolo_tronco': t.pericolo_tronco,
        'pericolo_colletto': t.pericolo_colletto, 'pericolo_zolla': t.pericolo_zolla,
        'bersaglio_chioma': t.bersaglio_chioma, 'bersaglio_ramo': t.bersaglio_ramo,
        'diag_zolla': parse_json_field(t.diag_zolla),
        'diag_colletto': parse_json_field(t.diag_colletto),
        'diag_fusto': parse_json_field(t.diag_fusto),
        'diag_castello': parse_json_field(t.diag_castello),
        'diag_ramificazione': parse_json_field(t.diag_ramificazione),
        'diag_chioma': parse_json_field(t.diag_chioma),
        'conflitti_list': parse_json_field(t.conflitti_list),
        'agenti_carie': parse_json_field(t.agenti_carie),
        'altri_patogeni': parse_json_field(t.altri_patogeni),
        'prescrizioni_val': parse_json_field(t.prescrizioni_val),
        'prescrizioni_mit': parse_json_field(t.prescrizioni_mit),
        'prescrizioni_col': parse_json_field(t.prescrizioni_col),
        'monitoraggio': t.monitoraggio, 'urgenza': t.urgenza,
        'rischio': json.loads(t.rischio) if t.rischio else None,
    }

def apply_tree_fields(tree_obj, data):
    """Set simple + JSON fields on a Tree instance from request data dict."""
    simple = [
        'species','condition','comments','actions','height','trunk_diameter_cm',
        'crown_diameter_m','age','location','cpc','address',
        'dimora','stadio_sviluppo','posizione_sociale','localizzazione','vincoli',
        'tree_height_m','circonferenza_cm','branch_diam_cm','branch_length_m',
        'branch_height_m','target_height_m',
        'post_tree_height_m','post_circonferenza_cm','post_branch_diam_cm',
        'post_branch_length_m','post_branch_height_m','post_target_height_m',
        'pericolo_rami','pericolo_tronco','pericolo_colletto','pericolo_zolla',
        'bersaglio_chioma','bersaglio_ramo',
        'monitoraggio','urgenza',
    ]
    json_fields = [
        'diag_zolla','diag_colletto','diag_fusto','diag_castello',
        'diag_ramificazione','diag_chioma',
        'conflitti_list','agenti_carie','altri_patogeni',
        'prescrizioni_val','prescrizioni_mit','prescrizioni_col',
    ]
    for f in simple:
        if f in data:
            setattr(tree_obj, f, data[f])
    for f in json_fields:
        if f in data:
            v = data[f]
            setattr(tree_obj, f, json.dumps(v) if isinstance(v, (list, dict)) else v)

def _calc_rischio(tree_obj):
    """Return assess_tree dict for tree_obj, or None if ORD fields are incomplete."""
    def _f(v):
        try: return float(v) if v not in (None, '') else None
        except: return None
    def _i(v):
        try: return int(v) if v not in (None, '') else None
        except: return None
    rq = {
        'tree_height_m':   _f(tree_obj.tree_height_m),
        'circumference_cm':_f(tree_obj.circonferenza_cm),
        'branch_diam_cm':  _f(tree_obj.branch_diam_cm),
        'branch_length_m': _f(tree_obj.branch_length_m),
        'branch_height_m': _f(tree_obj.branch_height_m),
        'target_height_m': _f(tree_obj.target_height_m),
        'pericolo_rami':   _i(tree_obj.pericolo_rami),
        'pericolo_tronco': _i(tree_obj.pericolo_tronco),
        'pericolo_colletto':_i(tree_obj.pericolo_colletto),
        'pericolo_zolla':  _i(tree_obj.pericolo_zolla),
        'bersaglio_chioma':_i(tree_obj.bersaglio_chioma),
        'bersaglio_ramo':  _i(tree_obj.bersaglio_ramo),
    }
    if any(v is None for v in rq.values()):
        return None
    try:
        return assess_tree(
            crown_diam_m=_f(tree_obj.crown_diameter_m) or 0,
            post_tree_height_m=_f(tree_obj.post_tree_height_m),
            post_circumference_cm=_f(tree_obj.post_circonferenza_cm),
            post_branch_diam_cm=_f(tree_obj.post_branch_diam_cm),
            post_branch_length_m=_f(tree_obj.post_branch_length_m),
            post_branch_height_m=_f(tree_obj.post_branch_height_m),
            post_target_height_m=_f(tree_obj.post_target_height_m),
            **rq
        )
    except Exception:
        return None

def _make_inspection(tree_obj, user_id, username):
    """Build an Inspection with snapshot + rischio for the current tree state."""
    rischio_val = _calc_rischio(tree_obj)
    snap = tree_to_dict(tree_obj)
    return Inspection(
        tree_id=tree_obj.id,
        date=datetime.now(timezone.utc).date(),
        condition=tree_obj.condition,
        comments=tree_obj.comments or '',
        actions=tree_obj.actions or '',
        inspector_id=user_id,
        inspector_name=username,
        snapshot=json.dumps(snap),
        rischio=json.dumps(rischio_val) if rischio_val else None,
    )

def generate_token(user, expires_minutes=60*24):
    payload = {
        "user_id": user.id, "username": user.username,
        "role": user.role, "city": user.city,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return token.decode('utf-8') if isinstance(token, bytes) else token

def auth_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', None)
        if not auth:
            return jsonify({'message': 'Missing Authorization header'}), 401
        token = auth.split(" ", 1)[1] if auth.startswith("Bearer ") else auth
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expired'}), 401
        except Exception as e:
            return jsonify({'message': 'Invalid token', 'error': str(e)}), 401
        request.user = data
        return f(*args, **kwargs)
    return wrapper

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not hasattr(request, 'user'):
                return jsonify({'message': 'Unauthorized'}), 401
            if request.user.get('role') not in allowed_roles:
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
    username, password = data.get('username'), data.get('password')
    if not username or not password:
        return jsonify({'message': 'username and password required'}), 400
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'message': 'Invalid credentials'}), 401
    token = generate_token(user)
    return jsonify({'token': token,
                    'user': {'id': user.id, 'username': user.username,
                             'role': user.role, 'city': user.city}})

@app.route('/me', methods=['GET'])
@auth_required
def me():
    return jsonify({'user_id': request.user.get('user_id'),
                    'username': request.user.get('username'),
                    'role': request.user.get('role'),
                    'city': request.user.get('city')})

@app.route('/register', methods=['POST'])
def register():
    data = request.json or {}
    username = data.get('username', '').strip()
    email    = data.get('email', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'message': 'Username e password obbligatori'}), 400
    if len(password) < 6:
        return jsonify({'message': 'Password troppo corta (minimo 6 caratteri)'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Username già in uso'}), 400
    if email and User.query.filter_by(email=email).first():
        return jsonify({'message': 'Email già registrata'}), 400
    user = User(username=username, email=email or None, role='user', city=None)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    token = generate_token(user)
    return jsonify({'token': token,
                    'user': {'id': user.id, 'username': user.username,
                             'role': user.role, 'city': user.city}}), 201

@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data  = request.json or {}
    email = data.get('email', '').strip()
    user  = User.query.filter_by(email=email).first() if email else None
    if user:
        token = secrets.token_urlsafe(32)
        user.password_reset_token   = token
        user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=2)
        db.session.commit()
        # TODO: send email — replace this block with your SMTP/SendGrid call
        print(f"[PASSWORD RESET] Token for {user.email}: {token}")
    # Always return the same message to avoid user enumeration
    return jsonify({'message': 'Se l\'email è registrata riceverai un link per il reset.'}), 200

@app.route('/reset-password', methods=['POST'])
def reset_password():
    data         = request.json or {}
    token        = data.get('token', '').strip()
    new_password = data.get('password', '')
    if not token or not new_password:
        return jsonify({'message': 'Token e nuova password obbligatori'}), 400
    if len(new_password) < 6:
        return jsonify({'message': 'Password troppo corta (minimo 6 caratteri)'}), 400
    user = User.query.filter_by(password_reset_token=token).first()
    if not user or not user.password_reset_expires:
        return jsonify({'message': 'Token non valido'}), 400
    if user.password_reset_expires < datetime.now(timezone.utc):
        return jsonify({'message': 'Token scaduto'}), 400
    user.set_password(new_password)
    user.password_reset_token   = None
    user.password_reset_expires = None
    db.session.commit()
    return jsonify({'message': 'Password aggiornata con successo'}), 200

# -----------------------
# User management
# -----------------------
@app.route('/add_user', methods=['POST'])
@auth_required
def add_user():
    creator = request.user
    data = request.json or {}
    username, password, role, city = (data.get(k) for k in ('username','password','role','city'))
    if not username or not password or not role:
        return jsonify({'message': 'username, password and role are required'}), 400
    if creator['role'] == 'user':
        return jsonify({'message': 'Users cannot create new users'}), 403
    if creator['role'] == 'city':
        if role != 'user':
            return jsonify({'message': 'City users can only create role "user"'}), 403
        city = creator.get('city')
    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Username already exists'}), 400
    new_user = User(username=username, role=role, city=city)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User created',
                    'user': {'id': new_user.id, 'username': username, 'role': role, 'city': city}}), 201

@app.route('/users', methods=['GET'])
@auth_required
def list_users():
    role, user_city, user_id = (request.user.get(k) for k in ('role','city','user_id'))
    if role == 'superuser':   users = User.query.all()
    elif role == 'city':      users = User.query.filter_by(city=user_city).all()
    else:                     users = User.query.filter_by(id=user_id).all()
    return jsonify([{'id': u.id, 'username': u.username, 'role': u.role, 'city': u.city} for u in users])

# -----------------------
# City ↔ Agronomer membership
# -----------------------
@app.route('/city/agronomers', methods=['GET'])
@auth_required
@role_required('city', 'superuser')
def list_city_agronomers():
    user_id = request.user.get('user_id')
    role    = request.user.get('role')
    city_user_id = int(request.args.get('city_user_id', user_id)) if role == 'superuser' else user_id
    rows = CityMembership.query.filter_by(city_user_id=city_user_id).all()
    result = []
    for m in rows:
        a = db.session.get(User, m.agronomer_id)
        if a:
            result.append({'membership_id': m.id, 'agronomer_id': a.id,
                           'username': a.username, 'email': a.email or ''})
    return jsonify(result)

@app.route('/city/agronomers', methods=['POST'])
@auth_required
@role_required('city', 'superuser')
def add_city_agronomer():
    user_id = request.user.get('user_id')
    role    = request.user.get('role')
    data    = request.json or {}
    username = data.get('username', '').strip()
    if not username:
        return jsonify({'message': 'username obbligatorio'}), 400
    agronomer = User.query.filter_by(username=username, role='user').first()
    if not agronomer:
        return jsonify({'message': f'Agronomo "{username}" non trovato'}), 404
    city_user_id = user_id if role == 'city' else int(data.get('city_user_id', user_id))
    if CityMembership.query.filter_by(city_user_id=city_user_id, agronomer_id=agronomer.id).first():
        return jsonify({'message': 'Agronomo già collegato a questo comune'}), 409
    m = CityMembership(city_user_id=city_user_id, agronomer_id=agronomer.id)
    db.session.add(m)
    db.session.commit()
    return jsonify({'membership_id': m.id, 'agronomer_id': agronomer.id,
                    'username': agronomer.username, 'email': agronomer.email or ''}), 201

@app.route('/city/agronomers/<int:membership_id>', methods=['DELETE'])
@auth_required
@role_required('city', 'superuser')
def remove_city_agronomer(membership_id):
    user_id = request.user.get('user_id')
    role    = request.user.get('role')
    m = db.session.get(CityMembership, membership_id)
    if not m:
        return jsonify({'message': 'Collegamento non trovato'}), 404
    if role == 'city' and m.city_user_id != user_id:
        return jsonify({'message': 'Forbidden'}), 403
    db.session.delete(m)
    db.session.commit()
    return jsonify({'message': 'Agronomo rimosso dal comune'}), 200

# -----------------------
# City management
# -----------------------
@app.route('/admin/cities', methods=['POST'])
@auth_required
@role_required('superuser')
def add_city():
    name = (request.json or {}).get('name')
    if not name: return jsonify({'message': 'City name required'}), 400
    if City.query.filter_by(name=name).first():
        return jsonify({'message': 'City already exists'}), 400
    c = City(name=name)
    db.session.add(c); db.session.commit()
    return jsonify({'message': 'City created', 'city': {'id': c.id, 'name': c.name}}), 201

@app.route('/cities', methods=['GET'])
def get_cities():
    from_table = {c.name for c in City.query.all()}
    from_trees = {row[0] for row in db.session.query(Tree.city).distinct() if row[0]}
    return jsonify(sorted(from_table | from_trees))

@app.route('/comuni/search', methods=['GET'])
def search_comuni():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    results = (
        Comune.query
        .filter(Comune.nome.ilike(f'%{q}%'))
        .order_by(
            case((Comune.nome.ilike(f'{q}%'), 0), else_=1),
            Comune.nome
        )
        .limit(20)
        .all()
    )
    return jsonify([{
        'nome': c.nome,
        'provincia': c.provincia,
        'sigla': c.sigla,
        'regione': c.regione,
    } for c in results])

# -----------------------
# Dropdowns endpoint
# -----------------------
@app.route('/dropdowns', methods=['GET'])
def get_dropdowns():
    return jsonify({
        'species': [{'code': k, 'name': v} for k, v in species_lookup.items()],
        'dimora': dd.dimora,
        'stadio_sviluppo': dd.stadio_sviluppo,
        'posizione_sociale': dd.posizione_sociale,
        'localizzazione': dd.localizzazione,
        'vincoli': dd.vincoli,
        'giudizio_severita': dd.giudizio_severita,
        'pericolo_ord': {str(k): v for k, v in dd.pericolo_ord.items()},
        'bersaglio_range': list(range(1, 8)),
        'diag_zolla': dd.zolla_radicale,
        'diag_colletto': dd.caratteri_colletto,
        'diag_fusto': dd.caratteri_fusto,
        'diag_castello': dd.caratteri_castello,
        'diag_ramificazione': dd.caratteri_ramificazione,
        'diag_chioma': dd.caratteri_chioma,
        'monitoraggio': lt_monitoraggio,
        'urgenza': lt_urgenza,
        'conflitti': lt_conflitti,
        'agenti_carie': lt_agenti_carie,
        'altri_patogeni': lt_altri_patogeni,
        'prescrizioni_val': lt_prescrizioni_val,
        'prescrizioni_mit': lt_prescrizioni_mit,
        'prescrizioni_col': lt_prescrizioni_col,
    })

# -----------------------
# Risk calculation
# -----------------------
@app.route('/calculate_risk', methods=['POST'])
@auth_required
def calculate_risk():
    data = request.json or {}
    def f(k):
        v = data.get(k)
        try: return float(v) if v not in (None,'') else None
        except: return None
    def i(k):
        v = data.get(k)
        try: return int(v) if v not in (None,'') else None
        except: return None

    required = {
        'tree_height_m': f('tree_height_m'), 'circonferenza_cm': f('circonferenza_cm'),
        'branch_diam_cm': f('branch_diam_cm'), 'branch_length_m': f('branch_length_m'),
        'branch_height_m': f('branch_height_m'), 'target_height_m': f('target_height_m'),
        'pericolo_rami': i('pericolo_rami'), 'pericolo_tronco': i('pericolo_tronco'),
        'pericolo_colletto': i('pericolo_colletto'), 'pericolo_zolla': i('pericolo_zolla'),
        'bersaglio_chioma': i('bersaglio_chioma'), 'bersaglio_ramo': i('bersaglio_ramo'),
    }
    missing = [k for k, v in required.items() if v is None]
    if missing:
        return jsonify({'message': f'Missing: {", ".join(missing)}'}), 400

    result = assess_tree(
        tree_height_m=required['tree_height_m'],
        circumference_cm=required['circonferenza_cm'],
        crown_diam_m=f('crown_diameter_m') or 0,
        branch_diam_cm=required['branch_diam_cm'],
        branch_length_m=required['branch_length_m'],
        branch_height_m=required['branch_height_m'],
        target_height_m=required['target_height_m'],
        pericolo_rami=required['pericolo_rami'],
        pericolo_tronco=required['pericolo_tronco'],
        pericolo_colletto=required['pericolo_colletto'],
        pericolo_zolla=required['pericolo_zolla'],
        bersaglio_chioma=required['bersaglio_chioma'],
        bersaglio_ramo=required['bersaglio_ramo'],
        post_tree_height_m=f('post_tree_height_m'),
        post_circumference_cm=f('post_circonferenza_cm'),
        post_branch_diam_cm=f('post_branch_diam_cm'),
        post_branch_length_m=f('post_branch_length_m'),
        post_branch_height_m=f('post_branch_height_m'),
        post_target_height_m=f('post_target_height_m'),
    )
    return jsonify(result)

# -----------------------
# City visibility helpers
# -----------------------
def city_tree_filter(query, city_user_id, user_city):
    linked = db.session.query(CityMembership.agronomer_id).filter_by(city_user_id=city_user_id)
    return query.filter(Tree.owner_id.in_(linked), Tree.city == user_city)

def city_can_access_tree(tree, city_user_id, user_city):
    if tree.owner_id is None or tree.city != user_city:
        return False
    return CityMembership.query.filter_by(
        city_user_id=city_user_id, agronomer_id=tree.owner_id).first() is not None

# -----------------------
# Tree endpoints
# -----------------------
@app.route('/trees', methods=['GET'])
@auth_required
def get_trees():
    role, user_id, user_city = (request.user.get(k) for k in ('role','user_id','city'))
    query = Tree.query
    if role == 'user':   query = query.filter(Tree.owner_id == user_id)
    elif role == 'city': query = city_tree_filter(query, user_id, user_city)
    city_q = request.args.get('city')
    addr_q = request.args.get('address')
    if city_q:  query = query.filter(Tree.city.ilike(f"%{city_q}%"))
    if addr_q:  query = query.filter(Tree.address.ilike(f"%{addr_q}%"))
    return jsonify([tree_to_dict(t) for t in query.all()])

@app.route('/tree/<int:tree_id>', methods=['GET'])
@auth_required
def get_tree_by_id(tree_id):
    tree = db.session.get(Tree, tree_id)
    if not tree: return jsonify({'message': 'Tree not found'}), 404
    role, user_id, user_city = (request.user.get(k) for k in ('role','user_id','city'))
    if role == 'user' and tree.owner_id != user_id:          return jsonify({'message': 'Forbidden'}), 403
    if role == 'city' and not city_can_access_tree(tree, user_id, user_city): return jsonify({'message': 'Forbidden'}), 403
    return jsonify(tree_to_dict(tree))

@app.route('/tree/<int:tree_id>', methods=['PATCH'])
@auth_required
def update_tree(tree_id):
    tree = db.session.get(Tree, tree_id)
    if not tree: return jsonify({'message': 'Tree not found'}), 404
    role, user_id, user_city = (request.user.get(k) for k in ('role','user_id','city'))
    if role == 'user' and tree.owner_id != user_id:          return jsonify({'message': 'Forbidden'}), 403
    if role == 'city' and not city_can_access_tree(tree, user_id, user_city): return jsonify({'message': 'Forbidden'}), 403

    data = request.json or {}
    apply_tree_fields(tree, data)

    if 'next_check' in data and data['next_check']:
        try: tree.next_check = datetime.strptime(data['next_check'], "%Y-%m-%d")
        except ValueError: return jsonify({'message': 'Invalid date for next_check'}), 400

    if data.get('latitude') and data.get('longitude'):
        try:
            tree.latitude  = float(data['latitude'])
            tree.longitude = float(data['longitude'])
            tree.geom = f'SRID=4326;POINT({float(data["longitude"])} {float(data["latitude"])})'
        except (ValueError, TypeError):
            return jsonify({'message': 'Invalid lat/lon'}), 400

    tree.rischio = json.dumps(r) if (r := _calc_rischio(tree)) else None
    db.session.commit()

    if {'condition','comments','actions'} & set(data.keys()):
        db.session.add(_make_inspection(tree, request.user.get('user_id'), request.user.get('username')))
        db.session.commit()
    return jsonify({'message': f'Tree {tree_id} updated successfully!'}), 200

@app.route('/tree/<int:tree_id>', methods=['DELETE'])
@auth_required
def delete_tree(tree_id):
    tree = db.session.get(Tree, tree_id)
    if not tree: return jsonify({'message': 'Tree not found'}), 404
    role, user_id, user_city = (request.user.get(k) for k in ('role','user_id','city'))
    if role == 'user' and tree.owner_id != user_id:          return jsonify({'message': 'Forbidden'}), 403
    if role == 'city' and not city_can_access_tree(tree, user_id, user_city): return jsonify({'message': 'Forbidden'}), 403
    db.session.delete(tree); db.session.commit()
    return jsonify({'message': f'Tree {tree_id} deleted successfully!'}), 200

@app.route('/add_tree', methods=['POST'])
@auth_required
def add_tree():
    data = request.json or {}
    user_id = request.user.get('user_id')
    role    = request.user.get('role')
    user_city = request.user.get('city')

    if not data.get('custom_id') or not data.get('species'):
        return jsonify({'message': 'custom_id and species are required'}), 400

    if not data.get('city'):
        if role in ('user','city') and user_city: data['city'] = user_city
        else: return jsonify({'message': 'city is required'}), 400

    if not data.get('latitude') or not data.get('longitude'):
        full_address = (data.get('address') or '') + ' ' + data.get('city','')
        loc = geolocator.geocode(full_address)
        if loc: data['latitude'], data['longitude'] = loc.latitude, loc.longitude
        else: return jsonify({'error': 'Invalid address, coordinates not found'}), 400

    try:
        next_check_date = datetime.strptime(data['next_check'], "%Y-%m-%d") if data.get('next_check') else None
    except ValueError:
        return jsonify({'message': 'Invalid date for next_check'}), 400

    new_tree = Tree(
        custom_id=data['custom_id'],
        latitude=float(data['latitude']), longitude=float(data['longitude']),
        address=data.get('address',''), city=data['city'],
        species=data['species'], condition=data.get('condition','—'),
        comments=data.get('comments',''), actions=data.get('actions',''),
        height=data.get('height',''), trunk_diameter_cm=data.get('trunk_diameter_cm'),
        crown_diameter_m=data.get('crown_diameter_m'), age=data.get('age',''),
        location=data.get('location',''), cpc=data.get('cpc',''),
        next_check=next_check_date,
        geom=f'SRID=4326;POINT({float(data["longitude"])} {float(data["latitude"])})',
        owner_id=user_id
    )
    apply_tree_fields(new_tree, data)
    new_tree.rischio = json.dumps(r) if (r := _calc_rischio(new_tree)) else None
    db.session.add(new_tree)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'message': f"Custom ID '{data['custom_id']}' already exists in {data['city']}"}), 409

    db.session.add(_make_inspection(new_tree, user_id, request.user.get('username')))
    db.session.commit()
    return jsonify({'message': 'Tree added successfully!', 'tree_id': new_tree.id}), 201

@app.route('/tree/custom/<string:custom_id>', methods=['GET'])
@auth_required
def get_tree_by_custom_id(custom_id):
    role, user_id, user_city = (request.user.get(k) for k in ('role','user_id','city'))
    query = Tree.query.filter_by(custom_id=custom_id)
    if role == 'user':   query = query.filter(Tree.owner_id == user_id)
    elif role == 'city': query = city_tree_filter(query, user_id, user_city)
    else:
        city_param = request.args.get('city')
        if city_param: query = query.filter(Tree.city == city_param)
    tree = query.first()
    if not tree: return jsonify({'message': 'Tree not found'}), 404
    return jsonify(tree_to_dict(tree))

@app.route('/tree/<int:tree_id>/inspections', methods=['GET'])
@auth_required
def get_inspections(tree_id):
    tree = db.session.get(Tree, tree_id)
    if not tree: return jsonify({'message': 'Tree not found'}), 404
    role, user_id, user_city = (request.user.get(k) for k in ('role','user_id','city'))
    if role == 'user' and tree.owner_id != user_id:          return jsonify({'message': 'Forbidden'}), 403
    if role == 'city' and not city_can_access_tree(tree, user_id, user_city): return jsonify({'message': 'Forbidden'}), 403
    rows = (Inspection.query.filter_by(tree_id=tree_id)
            .order_by(Inspection.date.desc(), Inspection.created_at.desc()).all())
    return jsonify([{
        'id': i.id, 'date': i.date.strftime('%Y-%m-%d'),
        'condition': i.condition, 'comments': i.comments, 'actions': i.actions,
        'inspector_name': i.inspector_name,
        'created_at': i.created_at.strftime('%Y-%m-%d %H:%M') if i.created_at else None,
        'rischio': json.loads(i.rischio) if i.rischio else None,
        'snapshot': json.loads(i.snapshot) if i.snapshot else None,
    } for i in rows])

@app.route('/tree/<int:tree_id>/inspections', methods=['POST'])
@auth_required
def add_inspection(tree_id):
    tree = db.session.get(Tree, tree_id)
    if not tree: return jsonify({'message': 'Tree not found'}), 404
    role, user_id, user_city = (request.user.get(k) for k in ('role','user_id','city'))
    if role == 'user' and tree.owner_id != user_id:          return jsonify({'message': 'Forbidden'}), 403
    if role == 'city' and not city_can_access_tree(tree, user_id, user_city): return jsonify({'message': 'Forbidden'}), 403
    data = request.json or {}
    date_str = data.get('date') or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    try: insp_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError: return jsonify({'message': 'Invalid date format'}), 400
    condition = data.get('condition') or tree.condition
    rischio_val = _calc_rischio(tree)
    snap = tree_to_dict(tree)
    snap['condition'] = condition

    insp = Inspection(
        tree_id=tree_id, date=insp_date,
        condition=condition,
        comments=data.get('comments',''), actions=data.get('actions',''),
        inspector_id=user_id, inspector_name=request.user.get('username'),
        snapshot=json.dumps(snap),
        rischio=json.dumps(rischio_val) if rischio_val else None,
    )
    db.session.add(insp); db.session.commit()
    return jsonify({'message': 'Inspection logged', 'id': insp.id}), 201

@app.route('/test_geocode', methods=['POST'])
def test_geocode():
    address = request.json.get('address')
    loc = geolocator.geocode(address)
    if loc: return jsonify({'latitude': loc.latitude, 'longitude': loc.longitude})
    return jsonify({'error': 'Address not found'}), 404

@app.route('/reverse_geocode', methods=['POST'])
@auth_required
def reverse_geocode():
    data = request.json or {}
    lat, lon = data.get('latitude'), data.get('longitude')
    if lat is None or lon is None:
        return jsonify({'message': 'latitude and longitude required'}), 400
    try:
        loc = geolocator.reverse(f"{lat}, {lon}", language='en')
        if loc:
            addr = loc.raw.get('address', {})
            city = (addr.get('city') or addr.get('town') or
                    addr.get('village') or addr.get('municipality') or '')
            return jsonify({'address': loc.address, 'city': city})
    except Exception:
        pass
    return jsonify({'address': '', 'city': ''})

@app.route('/export/excel', methods=['GET'])
@auth_required
def export_excel():
    role, user_id, user_city = (request.user.get(k) for k in ('role','user_id','city'))
    query = Tree.query
    if role == 'user':   query = query.filter(Tree.owner_id == user_id)
    elif role == 'city': query = city_tree_filter(query, user_id, user_city)
    ids_param = request.args.get('ids')
    if ids_param:
        id_list = [int(x) for x in ids_param.split(',') if x.strip().isdigit()]
        query = query.filter(Tree.id.in_(id_list))
    trees = query.all()

    def _jlist(val):
        if not val: return ''
        try:
            lst = json.loads(val) if isinstance(val, str) else val
            return ', '.join(str(x) for x in lst) if isinstance(lst, list) else str(lst)
        except: return ''

    def _diag(val):
        if not val: return ''
        try:
            lst = json.loads(val) if isinstance(val, str) else val
            return '; '.join(
                f"{r.get('caratt','')}: {r.get('giudizio','')}"
                for r in lst if isinstance(r, dict) and r.get('caratt')
            )
        except: return ''

    def _rtop(t, phase, field):
        if not t.rischio: return ''
        try: return json.loads(t.rischio).get(phase, {}).get(field, '')
        except: return ''

    def _rpart(t, phase, part, field):
        if not t.rischio: return ''
        try: return json.loads(t.rischio).get(phase, {}).get(part, {}).get(field, '')
        except: return ''

    # (group_label, color_hex, [(col_header, getter), ...])
    GROUPS = [
        ('Identificazione', 'BDD7EE', [
            ('ID',                  lambda t: t.id),
            ('ID Albero',           lambda t: t.custom_id),
            ('Comune',              lambda t: t.city),
            ('Indirizzo',           lambda t: t.address or ''),
            ('Latitudine',          lambda t: t.latitude),
            ('Longitudine',         lambda t: t.longitude),
            ('Specie',              lambda t: t.species),
            ('Condizione',          lambda t: t.condition),
            ('Età',                 lambda t: t.age or ''),
            ('CPC',                 lambda t: t.cpc or ''),
            ('Posizione',           lambda t: t.location or ''),
            ('Dimora',              lambda t: t.dimora or ''),
            ('Stadio sviluppo',     lambda t: t.stadio_sviluppo or ''),
            ('Posizione sociale',   lambda t: t.posizione_sociale or ''),
            ('Localizzazione',      lambda t: t.localizzazione or ''),
            ('Vincoli',             lambda t: t.vincoli or ''),
            ('Prossima ispezione',  lambda t: t.next_check.strftime('%Y-%m-%d') if t.next_check else ''),
            ('Urgenza',             lambda t: t.urgenza or ''),
            ('Monitoraggio',        lambda t: t.monitoraggio or ''),
            ('Note',                lambda t: t.comments or ''),
            ('Azioni',              lambda t: t.actions or ''),
        ]),
        ('Misure', 'C6EFCE', [
            ('Altezza (m)',         lambda t: t.tree_height_m),
            ('Altezza generica',    lambda t: t.height or ''),
            ('Circonferenza (cm)',  lambda t: t.circonferenza_cm),
            ('Ø Tronco (cm)',       lambda t: t.trunk_diameter_cm),
            ('Ø Chioma (m)',        lambda t: t.crown_diameter_m),
            ('Ø Ramo (cm)',         lambda t: t.branch_diam_cm),
            ('Lung. ramo (m)',      lambda t: t.branch_length_m),
            ('Alt. ramo (m)',       lambda t: t.branch_height_m),
            ('Alt. target (m)',     lambda t: t.target_height_m),
        ]),
        ('Post-intervento', 'FFF2CC', [
            ('Altezza post (m)',        lambda t: t.post_tree_height_m),
            ('Circonferenza post (cm)', lambda t: t.post_circonferenza_cm),
            ('Ø Ramo post (cm)',        lambda t: t.post_branch_diam_cm),
            ('Lung. ramo post (m)',     lambda t: t.post_branch_length_m),
            ('Alt. ramo post (m)',      lambda t: t.post_branch_height_m),
            ('Alt. target post (m)',    lambda t: t.post_target_height_m),
        ]),
        ('Valutazione rischio', 'FCE4D6', [
            ('Pericolo rami',               lambda t: t.pericolo_rami or ''),
            ('Pericolo tronco',             lambda t: t.pericolo_tronco or ''),
            ('Pericolo colletto',           lambda t: t.pericolo_colletto or ''),
            ('Pericolo zolla',              lambda t: t.pericolo_zolla or ''),
            ('Bersaglio chioma',            lambda t: t.bersaglio_chioma),
            ('Bersaglio ramo',              lambda t: t.bersaglio_ramo),
            ('Imp. chioma att. (kgm/s)',    lambda t: _rtop(t, 'attuale', 'crown_momentum_kgms')),
            ('Classe imp. chioma att.',     lambda t: _rtop(t, 'attuale', 'crown_impulso_class')),
            ('Imp. ramo att. (kgm/s)',      lambda t: _rtop(t, 'attuale', 'branch_momentum_kgms')),
            ('Classe imp. ramo att.',       lambda t: _rtop(t, 'attuale', 'branch_impulso_class')),
            ('Rischio rami (att.)',         lambda t: _rpart(t, 'attuale', 'rami',     'risk_description')),
            ('Rischio tronco (att.)',       lambda t: _rpart(t, 'attuale', 'tronco',   'risk_description')),
            ('Rischio colletto (att.)',     lambda t: _rpart(t, 'attuale', 'colletto', 'risk_description')),
            ('Rischio zolla (att.)',        lambda t: _rpart(t, 'attuale', 'zolla',    'risk_description')),
            ('Imp. chioma res. (kgm/s)',    lambda t: _rtop(t, 'residuo', 'crown_momentum_kgms')),
            ('Classe imp. chioma res.',     lambda t: _rtop(t, 'residuo', 'crown_impulso_class')),
            ('Imp. ramo res. (kgm/s)',      lambda t: _rtop(t, 'residuo', 'branch_momentum_kgms')),
            ('Classe imp. ramo res.',       lambda t: _rtop(t, 'residuo', 'branch_impulso_class')),
            ('Rischio rami (res.)',         lambda t: _rpart(t, 'residuo', 'rami',     'risk_description')),
            ('Rischio tronco (res.)',       lambda t: _rpart(t, 'residuo', 'tronco',   'risk_description')),
            ('Rischio colletto (res.)',     lambda t: _rpart(t, 'residuo', 'colletto', 'risk_description')),
            ('Rischio zolla (res.)',        lambda t: _rpart(t, 'residuo', 'zolla',    'risk_description')),
        ]),
        ('Diagnosi', 'E2EFDA', [
            ('Diagnosi zolla',          lambda t: _diag(t.diag_zolla)),
            ('Diagnosi colletto',       lambda t: _diag(t.diag_colletto)),
            ('Diagnosi fusto',          lambda t: _diag(t.diag_fusto)),
            ('Diagnosi castello',       lambda t: _diag(t.diag_castello)),
            ('Diagnosi ramificazione',  lambda t: _diag(t.diag_ramificazione)),
            ('Diagnosi chioma',         lambda t: _diag(t.diag_chioma)),
        ]),
        ('Prescrizioni e patologie', 'E8DAEF', [
            ('Conflitti',                   lambda t: _jlist(t.conflitti_list)),
            ('Agenti carie',                lambda t: _jlist(t.agenti_carie)),
            ('Altri patogeni',              lambda t: _jlist(t.altri_patogeni)),
            ('Prescrizioni valutazione',    lambda t: _jlist(t.prescrizioni_val)),
            ('Prescrizioni mitigazione',    lambda t: _jlist(t.prescrizioni_mit)),
            ('Prescrizioni collaterale',    lambda t: _jlist(t.prescrizioni_col)),
        ]),
    ]

    # Flatten columns and track group spans for merged header row
    all_cols   = []  # [(header, getter, color)]
    group_info = []  # [(label, start_col, end_col, color)]
    col_idx = 1
    for label, color, cols in GROUPS:
        group_info.append((label, col_idx, col_idx + len(cols) - 1, color))
        for header, getter in cols:
            all_cols.append((header, getter, color))
        col_idx += len(cols)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Alberi'

    hdr_font   = Font(bold=True)
    center     = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # Row 1: group labels (merged)
    for label, start, end, color in group_info:
        if start < end:
            ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=end)
        cell = ws.cell(row=1, column=start, value=label)
        cell.fill      = PatternFill(fill_type='solid', fgColor=color)
        cell.font      = Font(bold=True, size=11)
        cell.alignment = center

    # Row 2: column headers
    for col_num, (header, _, color) in enumerate(all_cols, 1):
        cell = ws.cell(row=2, column=col_num, value=header)
        cell.fill      = PatternFill(fill_type='solid', fgColor=color)
        cell.font      = hdr_font
        cell.alignment = center

    # Data rows
    for row_num, t in enumerate(trees, 3):
        for col_num, (_, getter, _color) in enumerate(all_cols, 1):
            val = getter(t)
            ws.cell(row=row_num, column=col_num, value=val if val != '' else None)

    # Column widths (approx by header length, capped)
    for col_num, (header, _, _) in enumerate(all_cols, 1):
        ws.column_dimensions[get_column_letter(col_num)].width = max(10, min(35, len(header) + 3))

    ws.row_dimensions[1].height = 20
    ws.row_dimensions[2].height = 30
    ws.freeze_panes = 'C3'  # freeze first 2 cols + 2 header rows

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, download_name='alberi.xlsx', as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/export/geojson', methods=['GET'])
@auth_required
def export_geojson():
    role, user_id, user_city = (request.user.get(k) for k in ('role','user_id','city'))
    query = Tree.query
    if role == 'user':   query = query.filter(Tree.owner_id == user_id)
    elif role == 'city': query = city_tree_filter(query, user_id, user_city)
    ids_param = request.args.get('ids')
    if ids_param:
        id_list = [int(x) for x in ids_param.split(',') if x.strip().isdigit()]
        query = query.filter(Tree.id.in_(id_list))
    features = []
    for t in query.all():
        if t.latitude is None or t.longitude is None: continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [t.longitude, t.latitude]},
            "properties": tree_to_dict(t)
        })
    buf = io.BytesIO(json.dumps({"type":"FeatureCollection","features":features},
                                ensure_ascii=False).encode('utf-8'))
    buf.seek(0)
    return send_file(buf, download_name='trees.geojson', as_attachment=True,
                     mimetype='application/geo+json')

# -----------------------
# Bootstrap
# -----------------------
with app.app_context():
    if not User.query.filter_by(role='superuser').first():
        su = User(username='admin', role='superuser', city=None)
        su.set_password('admin')
        db.session.add(su); db.session.commit()
        print("Created default superuser: admin / admin")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

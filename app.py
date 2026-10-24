#!/usr/bin/env python3
import sys, os, io, json, re, secrets, struct, tempfile, sqlite3, time, urllib.request
import uuid as uuid_lib, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()  # loads .env when running locally; no-op on Railway

from flask import Flask, request, jsonify, send_file, send_from_directory, has_request_context
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from geopy.geocoders import Nominatim
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy import inspect, text, case, event
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import wraps
from contextlib import contextmanager
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter
from groq import Groq as GroqClient

from tools import dropdowns_ord as dd
from tools.lookup_tables import (
    species_lookup, monitoraggio as lt_monitoraggio, urgenza as lt_urgenza,
    conflitti as lt_conflitti, agenti_di_carie as lt_agenti_carie,
    altri_patogeni as lt_altri_patogeni,
    prescrizioni_valutative as lt_prescrizioni_val,
    prescrizioni_mitigazione as lt_prescrizioni_mit,
    prescrizioni_colturali as lt_prescrizioni_col,
)
from tools.ord_calculator import (
    assess_tree, bersaglio_value_to_class, bersaglio_flow_to_class,
    calc_ecological_value,
)
from tools import report_templates as report_tpl
from tools import palette
from tools import map_render
from tools import qgis_style

# -----------------------
# Configuration
# -----------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def _no_cache_api(resp):
    """Le risposte JSON dipendono dal token: nessuna cache intermedia (la cache
    di rete di QGIS riusava /me di un altro token, stesso URL)."""
    if resp.mimetype in ('application/json', 'application/geo+json'):
        resp.headers.setdefault('Cache-Control', 'no-store')
    return resp

DB_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:c0st4m4gn4@localhost/trees_db')
# Railway provides postgres:// — SQLAlchemy requires postgresql://
if DB_URL.startswith('postgres://'):
    DB_URL = DB_URL.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
SECRET_KEY = os.environ.get('SECRET_KEY', 'super-secret-change-me')
app.config['SECRET_KEY'] = SECRET_KEY

SMTP_USER    = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5000')

# Demo accounts: shared read/write sandbox wiped and re-seeded to a fixed state
# on every demo login, so every visitor always sees the same demo of Torino.
# - demo_user (role "user"): the agronomer that owns the demo trees.
# - demo_city (role "city"): the municipality, linked to demo_user only, to
#   showcase the city role on the same trees.
DEMO_USERNAME       = os.environ.get('DEMO_USERNAME', 'demo_user')
DEMO_PASSWORD       = os.environ.get('DEMO_PASSWORD', 'demo_password')
DEMO_CITY_USERNAME  = os.environ.get('DEMO_CITY_USERNAME', 'demo_city')
DEMO_CITY_PASSWORD  = os.environ.get('DEMO_CITY_PASSWORD', 'demo_city_password')
DEMO_CITY_NAME      = 'Torino'

# Public self-registration. Disabled for now (not in production yet); re-enable by
# setting REGISTRATION_ENABLED=true (and un-hiding the "Crea account" link in the frontend).
REGISTRATION_ENABLED = os.environ.get('REGISTRATION_ENABLED', 'false').lower() == 'true'

db = SQLAlchemy(app)
geolocator = Nominatim(user_agent="tree_locator")

# -----------------------
# Models
# -----------------------
# Alfabeto senza caratteri ambigui (0/O, 1/I/L) per un codice facile da dettare.
_CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'

def _new_agronomer_code():
    """Genera un codice agronomo univoco nel formato ``AGR-XXXX-XXXX``."""
    while True:
        raw  = ''.join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        code = f'AGR-{raw[:4]}-{raw[4:]}'
        if not User.query.filter_by(agronomer_code=code).first():
            return code

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
    # Codice identificativo dell'agronomo (ruolo `user`): generato una volta
    # sola e mai più cambiato. L'agronomo lo comunica al comune, che lo usa per
    # collegarlo (vedi /city/agronomers).
    agronomer_code         = db.Column(db.String(20), unique=True, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def ensure_agronomer_code(self):
        """Assegna il codice agronomo se manca (solo ruolo `user`). Ritorna il codice."""
        if self.role != 'user':
            return None
        if not self.agronomer_code:
            self.agronomer_code = _new_agronomer_code()
        return self.agronomer_code

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
    latitude  = db.Column(db.Float)
    longitude = db.Column(db.Float)

class Tree(db.Model):
    __tablename__ = 'tree'
    __table_args__ = ()
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
    bersaglio_chioma_tipo  = db.Column(db.String(50))   # C32: proprietà/occupazione/pedoni/traffico…
    bersaglio_chioma_value = db.Column(db.String(100))  # description (proprietà/occupazione types)
    bersaglio_chioma_flow  = db.Column(db.Float)        # flow rate (pedoni/ora or auto/giorno)
    bersaglio_chioma       = db.Column(db.Integer)      # resolved class 1-7 (G32)
    bersaglio_ramo_tipo    = db.Column(db.String(50))   # N32
    bersaglio_ramo_value   = db.Column(db.String(100))
    bersaglio_ramo_flow    = db.Column(db.Float)        # flow rate for ramo
    bersaglio_ramo         = db.Column(db.Integer)      # resolved class 1-7 (R32)
    moltiplicatore         = db.Column(db.Integer)      # n simultaneous targets (H32); NULL = 1

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

    # --- Valore ecologico (ORD row 10) ---
    condizione_salute_ecologica = db.Column(db.Text)   # dropdown input
    bio_kg                      = db.Column(db.Float)  # biomassa (kg)
    co2_kg_anno                 = db.Column(db.Float)  # CO2 sequestrata (kg/anno)
    o2_kg_anno                  = db.Column(db.Float)  # O2 prodotta (kg/anno)
    ia_kg_anno                  = db.Column(db.Float)  # intercett. acqua (kg/anno)
    valore_ecologico            = db.Column(db.Float)  # valore monetario (€)

    # --- Collegamento esterno e tracciabilità (QGIS, vedi qgis.md §4) ---
    # `uuid` è la chiave stabile con cui un layer esterno resta collegato
    # all'albero (custom_id è rinominabile e unico solo per comune).
    uuid       = db.Column(db.String(36), unique=True, default=lambda: str(uuid_lib.uuid4()))
    # Lo storico segue l'albero anche dove il vincolo ON DELETE CASCADE non è
    # applicato (SQLite non lo fa senza PRAGMA): senza questa cascata un
    # albero nuovo che riusa l'id di uno cancellato ne eredita le ispezioni.
    inspections = db.relationship('Inspection', backref='tree', lazy='dynamic',
                                  cascade='all, delete-orphan')
    updated_at = db.Column(db.DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    updated_by = db.Column(db.String(80))   # username dell'ultima modifica

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

class ApiToken(db.Model):
    """Token d'accesso longevo e revocabile per client esterni (plugin QGIS,
    vedi qgis.md §5). Il JWT di /login scade e congela ruolo e comune: qui in
    DB sta solo l'hash, e ruolo/comune vengono riletti dall'utente a ogni
    richiesta. Il token in chiaro (`slv_…`) si vede una volta sola, alla
    creazione."""
    __tablename__ = 'api_token'
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    name         = db.Column(db.String(80), nullable=False)
    token_hash   = db.Column(db.String(64), unique=True, nullable=False)   # sha256 esadecimale
    prefix       = db.Column(db.String(12), nullable=False)                # per riconoscerlo in lista
    created_at   = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at = db.Column(db.DateTime(timezone=True))
    revoked_at   = db.Column(db.DateTime(timezone=True))

    def to_dict(self):
        fmt = lambda d: d.strftime('%Y-%m-%d %H:%M') if d else None
        return {'id': self.id, 'name': self.name, 'prefix': self.prefix,
                'created_at': fmt(self.created_at), 'last_used_at': fmt(self.last_used_at),
                'revoked': self.revoked_at is not None}

class QgisDelivery(db.Model):
    """Cassetta postale webapp → QGIS (qgis.md §6.3). Un browser non può
    parlare con QGIS sul PC dell'utente: «Invia a QGIS» deposita qui *gli id*
    degli alberi (non i dati, così il ritiro è sempre aggiornato) e il plugin
    li trova al primo controllo. L'invio è personale: lo ritira chi l'ha
    creato."""
    __tablename__ = 'qgis_delivery'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    city       = db.Column(db.String(100))
    title      = db.Column(db.String(160), nullable=False)
    tree_ids   = db.Column(db.Text, nullable=False)     # JSON array di id
    polygon    = db.Column(db.Text)                     # JSON [[lat, lon], …] dell'area, se c'è
    count      = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    fetched_at = db.Column(db.DateTime(timezone=True))
    expires_at = db.Column(db.DateTime(timezone=True))

    def to_dict(self):
        fmt = lambda d: d.isoformat() if d else None
        return {'id': self.id, 'city': self.city, 'title': self.title, 'count': self.count,
                'created_at': fmt(self.created_at), 'fetched_at': fmt(self.fetched_at),
                'expires_at': fmt(self.expires_at),
                'polygon': json.loads(self.polygon) if self.polygon else None}

DELIVERY_TTL_DAYS = 7
DELIVERY_MAX_TREES = 20000

API_TOKEN_PREFIX = 'slv_'

def _hash_api_token(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def _new_api_token(user, name):
    """Crea un ApiToken per `user`; ritorna (token_in_chiaro, oggetto). Non committa."""
    raw = API_TOKEN_PREFIX + secrets.token_urlsafe(30)
    tok = ApiToken(user_id=user.id, name=(name or 'QGIS').strip()[:80],
                   token_hash=_hash_api_token(raw), prefix=raw[:12])
    db.session.add(tok)
    return raw, tok

def _resolve_api_token(raw):
    """(ApiToken, User) per un token in chiaro valido e non revocato, altrimenti None."""
    tok = ApiToken.query.filter_by(token_hash=_hash_api_token(raw), revoked_at=None).first()
    if not tok:
        return None
    user = db.session.get(User, tok.user_id)
    if not user:
        return None
    return tok, user

@event.listens_for(db.session, 'before_flush')
def _stamp_updated_by(session, flush_context, instances):
    """Scrive `Tree.updated_by` con l'utente della richiesta corrente su ogni
    albero creato o modificato (`updated_at` lo gestisce la colonna stessa)."""
    if not (has_request_context() and hasattr(request, 'user')):
        return
    username = request.user.get('username')
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, Tree) and (obj in session.new or session.is_modified(obj)):
            obj.updated_by = username

# -----------------------
# DB init + migrate new columns
# -----------------------
# Chiave dell'advisory lock che serializza la migrazione: un bigint qualsiasi,
# purché identico in tutti i processi.
_MIGRATION_LOCK_KEY = 8114201
_MIGRATION_LOCK_WAIT_S = 90

@contextmanager
def _migration_lock():
    """Fa in modo che un solo processo per volta esegua la migrazione.

    Senza questo, due processi che partono insieme (due istanze, o un
    container che riparte mentre il precedente e' ancora nel backfill) si
    incastrano: il backfill tiene aperta una transazione su `tree`, l'ALTER
    TABLE dell'altro processo si accoda chiedendo l'accesso esclusivo e da
    quel momento anche le semplici letture si accodano dietro di lui. Per
    PostgreSQL non e' un deadlock — la prima sessione aspetta il suo client,
    non un lock — quindi non si sblocca da se'.

    Il lock sta su una connessione dedicata tenuta aperta per tutta la durata
    (gli advisory lock sono di sessione e sopravvivono ai commit); il resto
    della migrazione continua a usare le proprie connessioni. Chi non lo
    ottiene entro _MIGRATION_LOCK_WAIT_S avvia senza migrare: la migrazione e'
    idempotente e condizionata ai dati, quindi la sta completando l'altro
    processo e al prossimo riavvio si ripara comunque. Su SQLite
    (test_locale.py --sqlite) gli advisory lock non esistono e non servono.
    """
    if db.engine.dialect.name != 'postgresql':
        yield True
        return
    conn = db.engine.connect()
    preso = False
    try:
        scadenza = time.monotonic() + _MIGRATION_LOCK_WAIT_S
        while True:
            preso = bool(conn.execute(text('SELECT pg_try_advisory_lock(:k)'),
                                      {'k': _MIGRATION_LOCK_KEY}).scalar())
            conn.commit()        # niente «idle in transaction» su questa connessione
            if preso or time.monotonic() >= scadenza:
                break
            time.sleep(1)
        if not preso:
            print(f'Migrazione: lock occupato da oltre {_MIGRATION_LOCK_WAIT_S}s, '
                  'la sta eseguendo un altro processo: avvio senza migrare')
        yield preso
    finally:
        if preso:
            conn.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': _MIGRATION_LOCK_KEY})
            conn.commit()
        conn.close()

def _migrate_schema():
    """Crea le tabelle mancanti e aggiunge le colonne nuove sui DB esistenti.
    Da chiamare solo dentro _migration_lock(). Idempotente."""

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
        ('bersaglio_chioma_tipo','VARCHAR(50)'), ('bersaglio_chioma_value','VARCHAR(100)'),
        ('bersaglio_chioma_flow','FLOAT'), ('bersaglio_chioma','INTEGER'),
        ('bersaglio_ramo_tipo','VARCHAR(50)'), ('bersaglio_ramo_value','VARCHAR(100)'),
        ('bersaglio_ramo_flow','FLOAT'), ('bersaglio_ramo','INTEGER'),
        ('moltiplicatore','INTEGER'),
        ('diag_zolla','TEXT'), ('diag_colletto','TEXT'), ('diag_fusto','TEXT'),
        ('diag_castello','TEXT'), ('diag_ramificazione','TEXT'), ('diag_chioma','TEXT'),
        ('conflitti_list','TEXT'), ('agenti_carie','TEXT'), ('altri_patogeni','TEXT'),
        ('prescrizioni_val','TEXT'), ('prescrizioni_mit','TEXT'), ('prescrizioni_col','TEXT'),
        ('monitoraggio','VARCHAR(50)'), ('urgenza','VARCHAR(50)'),
        ('rischio','TEXT'),
        ('condizione_salute_ecologica','TEXT'),
        ('bio_kg','FLOAT'), ('co2_kg_anno','FLOAT'),
        ('o2_kg_anno','FLOAT'), ('ia_kg_anno','FLOAT'),
        ('valore_ecologico','FLOAT'),
        ('uuid','VARCHAR(36)'), ('updated_at','TIMESTAMPTZ'), ('updated_by','VARCHAR(80)'),
    ]
    with db.engine.connect() as conn:
        for col_name, col_type in new_cols:
            if col_name not in existing_cols:
                conn.execute(text(f'ALTER TABLE tree ADD COLUMN {col_name} {col_type}'))
        conn.commit()
    # Backfill degli alberi creati prima delle colonne: uuid per riga,
    # updated_at = adesso. Non è condizionato allo schema ma allo stato dei
    # dati, così un avvio interrotto a metà (colonne aggiunte, righe non
    # riempite) si ripara da sé al riavvio successivo; a regime è una query
    # su colonna indicizzata che non trova nulla. L'indice univoco su uuid va
    # creato DOPO il backfill.
    senza_uuid = Tree.query.filter(Tree.uuid.is_(None)).all()
    if senza_uuid:
        for t in senza_uuid:
            t.uuid = str(uuid_lib.uuid4())
        db.session.commit()
        print(f'Backfill uuid: {len(senza_uuid)} alberi aggiornati')
    with db.engine.connect() as conn:
        res = conn.execute(Tree.__table__.update()
                           .where(Tree.updated_at.is_(None))
                           .values(updated_at=datetime.now(timezone.utc)))
        conn.commit()
        if res.rowcount:
            print(f'Backfill updated_at: {res.rowcount} alberi aggiornati')
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_tree_uuid ON tree (uuid)'))
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
        ('agronomer_code', 'VARCHAR(20)'),
    ]
    with db.engine.connect() as conn:
        for col_name, col_type in user_new_cols:
            if col_name not in existing_user_cols:
                conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {col_name} {col_type}'))
        # Indice univoco separato: SQLite non accetta UNIQUE in ADD COLUMN.
        conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_user_agronomer_code ON "user" (agronomer_code)'))
        conn.commit()
    # Backfill: gli agronomi esistenti ricevono il codice (una volta sola).
    for u in User.query.filter_by(role='user', agronomer_code=None).all():
        u.ensure_agronomer_code()
    db.session.commit()
    with db.engine.connect() as conn:
        try:
            conn.execute(text('ALTER TABLE tree DROP CONSTRAINT uq_tree_custom_id_city'))
            conn.commit()
        except Exception:
            conn.rollback()
    existing_comune_cols = {c['name'] for c in insp.get_columns('comune')}
    comune_new_cols = [('latitude', 'DOUBLE PRECISION'), ('longitude', 'DOUBLE PRECISION')]
    with db.engine.connect() as conn:
        for col_name, col_type in comune_new_cols:
            if col_name not in existing_comune_cols:
                conn.execute(text(f'ALTER TABLE comune ADD COLUMN {col_name} {col_type}'))
        conn.commit()

with app.app_context():
    with _migration_lock() as consentito:
        if consentito:
            _migrate_schema()

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
        'uuid': t.uuid,
        'updated_at': t.updated_at.isoformat() if t.updated_at else None,
        'updated_by': t.updated_by,
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
        'bersaglio_chioma_tipo':  t.bersaglio_chioma_tipo,
        'bersaglio_chioma_value': t.bersaglio_chioma_value,
        'bersaglio_chioma_flow':  t.bersaglio_chioma_flow,
        'bersaglio_chioma':       t.bersaglio_chioma,
        'bersaglio_ramo_tipo':    t.bersaglio_ramo_tipo,
        'bersaglio_ramo_value':   t.bersaglio_ramo_value,
        'bersaglio_ramo_flow':    t.bersaglio_ramo_flow,
        'bersaglio_ramo':         t.bersaglio_ramo,
        'moltiplicatore': t.moltiplicatore,
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
        'condizione_salute_ecologica': t.condizione_salute_ecologica,
        'bio_kg': t.bio_kg, 'co2_kg_anno': t.co2_kg_anno,
        'o2_kg_anno': t.o2_kg_anno, 'ia_kg_anno': t.ia_kg_anno,
        'valore_ecologico': t.valore_ecologico,
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
        'bersaglio_chioma_tipo','bersaglio_chioma_value','bersaglio_chioma_flow','bersaglio_chioma',
        'bersaglio_ramo_tipo','bersaglio_ramo_value','bersaglio_ramo_flow','bersaglio_ramo',
        'moltiplicatore',
        'monitoraggio','urgenza',
        'condizione_salute_ecologica',
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
    # Auto-compute bersaglio class from tipo + value (proprietà/occupazione)
    # or tipo + flow rate (pedoni/ciclisti, traffico *).
    def _f(v):
        try: return float(v) if v not in (None, '') else None
        except: return None
    crown_diam = _f(data.get('crown_diameter_m')) or _f(getattr(tree_obj, 'crown_diameter_m', None)) or 0.0
    tree_h     = _f(data.get('tree_height_m'))    or _f(getattr(tree_obj, 'tree_height_m',    None)) or 0.0
    branch_l   = _f(data.get('branch_length_m'))  or _f(getattr(tree_obj, 'branch_length_m',  None)) or 0.0
    zone_chioma = (crown_diam + tree_h) / 2.0 if (crown_diam + tree_h) > 0 else 0.0
    zone_ramo   = branch_l * 1.25 if branch_l > 0 else 0.0

    for tipo_key, value_key, flow_key, class_key, zone_w in [
        ('bersaglio_chioma_tipo', 'bersaglio_chioma_value', 'bersaglio_chioma_flow',
         'bersaglio_chioma', zone_chioma),
        ('bersaglio_ramo_tipo',   'bersaglio_ramo_value',   'bersaglio_ramo_flow',
         'bersaglio_ramo',   zone_ramo),
    ]:
        tipo  = data.get(tipo_key)  or getattr(tree_obj, tipo_key,  None)
        value = data.get(value_key) or getattr(tree_obj, value_key, None)
        flow  = _f(data.get(flow_key)) or _f(getattr(tree_obj, flow_key, None))
        if tipo and value:
            computed = bersaglio_value_to_class(tipo, value)
            if computed is not None:
                setattr(tree_obj, class_key, computed)
        elif tipo and flow is not None and zone_w > 0:
            computed = bersaglio_flow_to_class(tipo, flow, zone_w)
            if computed is not None:
                setattr(tree_obj, class_key, computed)

    # Auto-compute valore ecologico when all required inputs are available
    eco = calc_ecological_value(
        trunk_diameter_cm          = _f(data.get('trunk_diameter_cm'))          or _f(getattr(tree_obj, 'trunk_diameter_cm', None)),
        tree_height_m              = _f(data.get('tree_height_m'))              or _f(getattr(tree_obj, 'tree_height_m', None)),
        stadio_sviluppo            = data.get('stadio_sviluppo')                or getattr(tree_obj, 'stadio_sviluppo', None),
        posizione_sociale          = data.get('posizione_sociale')              or getattr(tree_obj, 'posizione_sociale', None),
        condizione_salute_ecologica= data.get('condizione_salute_ecologica')    or getattr(tree_obj, 'condizione_salute_ecologica', None),
    )
    if eco is not None:
        tree_obj.bio_kg           = eco['bio_kg']
        tree_obj.co2_kg_anno      = eco['co2_kg_anno']
        tree_obj.o2_kg_anno       = eco['o2_kg_anno']
        tree_obj.ia_kg_anno       = eco['ia_kg_anno']
        tree_obj.valore_ecologico = eco['valore_ecologico']

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
    mult = _i(tree_obj.moltiplicatore) or 1
    try:
        return assess_tree(
            crown_diam_m=_f(tree_obj.crown_diameter_m) or 0,
            moltiplicatore=mult,
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

# --- Scrittura da fonti esterne (import file, plugin QGIS) --------------------
# Campi che il server calcola da altri o che governano identità e permessi:
# chi scrive dall'esterno non li può impostare (qgis.md §7).
_DERIVED_TREE_FIELDS = frozenset({
    'id', 'uuid', 'owner_id', 'city', 'updated_at', 'updated_by',
    'rischio', 'bersaglio_chioma', 'bersaglio_ramo',
    'bio_kg', 'co2_kg_anno', 'o2_kg_anno', 'ia_kg_anno', 'valore_ecologico',
})
_TREE_COMPARE_FIELDS = [c.key for c in Tree.__table__.columns
                        if c.key not in ('id', 'updated_at', 'updated_by')]
_COORD_MATCH_TOL = 1e-6   # gradi (~10 cm): due punti più vicini sono lo stesso albero

def _tree_values(tree):
    return {k: getattr(tree, k) for k in _TREE_COMPARE_FIELDS}

def _match_tree(record, city, scope, strict_uuid=True):
    """Albero esistente corrispondente a `record` dentro `scope` (query già
    filtrata per ruolo), o None. Ordine: uuid → coordinate entro
    _COORD_MATCH_TOL → custom_id, quest'ultimo solo se la riga non ha
    coordinate: nei censimenti la numerazione riparte per località (nel file
    di Bra «7» compare due volte, in due punti diversi), quindi con le
    coordinate decidono quelle e un albero spostato senza uuid è un albero
    nuovo. Un uuid di un altro comune è sempre un errore; un uuid sconosciuto
    lo è solo con `strict_uuid` (push da QGIS: non si resuscita un albero
    cancellato), altrimenti si prosegue con gli altri criteri (import da
    file, che può venire da un altro account)."""
    u = record.get('uuid')
    if u:
        t = scope.filter(Tree.uuid == u).first()
        if t:
            if t.city != city:
                raise ValueError(f'uuid {u} appartiene al comune {t.city}, non a {city}')
            return t
        if strict_uuid:
            raise ValueError(f'uuid {u} sconosciuto o non visibile')
    q = scope.filter(Tree.city == city)
    lat, lon = record.get('latitude'), record.get('longitude')
    if lat is not None and lon is not None:
        return q.filter(Tree.latitude.between(lat - _COORD_MATCH_TOL, lat + _COORD_MATCH_TOL),
                        Tree.longitude.between(lon - _COORD_MATCH_TOL, lon + _COORD_MATCH_TOL)).first()
    cid = record.get('custom_id')
    if cid:
        return q.filter(Tree.custom_id == cid).first()
    return None

_UNSET = object()

def _upsert_tree(record, *, city, on_conflict, user_id, scope, strict_uuid=True, existing=_UNSET):
    """Crea o aggiorna un albero da `record`: dict con i nomi dei campi di
    `Tree` e valori già convertiti (float per i numeri, stringhe JSON per le
    liste, `date` per next_check). Regole (qgis.md §13):
      - un valore None non tocca il campo; i derivati vengono ignorati;
      - si abbina solo tra gli alberi di `scope` e non si cambia mai l'owner;
      - il server ricalcola bersaglio, valore ecologico e rischio.
    `existing` evita di ripetere l'abbinamento a chi l'ha già fatto (il push
    da QGIS, che prima controlla i conflitti e salva lo snapshot).
    Ritorna (esito, albero, campi_cambiati) con esito in
    'created' | 'updated' | 'unchanged' | 'skipped'. Non committa."""
    record = {k: v for k, v in record.items() if v is not None}
    if existing is _UNSET:
        existing = _match_tree(record, city, scope, strict_uuid)   # uuid/custom_id/coordinate
    if existing is not None and on_conflict != 'update':
        return 'skipped', existing, []
    file_uuid = record.get('uuid')
    record = {k: v for k, v in record.items() if k not in _DERIVED_TREE_FIELDS}
    if existing is None:
        custom_id = str(record.get('custom_id') or '').strip()
        if not custom_id:
            raise ValueError('custom_id mancante')
        tree = Tree(custom_id=custom_id, city=city, owner_id=user_id,
                    species='Sconosciuta', condition='—')
        # Un uuid del file che non appartiene a nessun albero (es. cancellato)
        # viene riusato, così il layer di origine resta collegato.
        if file_uuid and not Tree.query.filter(Tree.uuid == file_uuid).first():
            tree.uuid = file_uuid
        db.session.add(tree)
    else:
        tree = existing
    before = _tree_values(tree)

    if record.get('custom_id'):
        tree.custom_id = str(record['custom_id']).strip() or tree.custom_id
    lat, lon = record.get('latitude'), record.get('longitude')
    if lat is not None and lon is not None:
        tree.latitude, tree.longitude = float(lat), float(lon)
    if record.get('next_check') is not None:
        tree.next_check = record['next_check']
    apply_tree_fields(tree, record)
    if tree.cpc:
        tree.condition = tree.cpc
    tree.rischio = json.dumps(r) if (r := _calc_rischio(tree)) else None

    after = _tree_values(tree)
    changed = [k for k in after if after[k] != before[k]]
    if existing is not None and not changed:
        return 'unchanged', tree, []
    return ('created' if existing is None else 'updated'), tree, changed


# -----------------------
# Demo account seeding
# -----------------------
# Fixed set of demo trees in Torino. Owned by the demo user, wiped and re-created
# on every demo login so the demo always looks identical. A few carry full ORD
# measures so the risk (B·I·P) is computed; others are left partial on purpose.
DEMO_TREES = [
    dict(custom_id='DEMO-001', species='Platanus × acerifolia', condition='Buono',
         address='Corso Vittorio Emanuele II', latitude=45.0625, longitude=7.6819,
         height='18', trunk_diameter_cm=62, crown_diameter_m=12, age='45',
         location='Filare stradale',
         tree_height_m=18, circonferenza_cm=195, branch_diam_cm=22, branch_length_m=8,
         branch_height_m=9, target_height_m=1.7,
         pericolo_rami='1', pericolo_tronco='0', pericolo_colletto='0', pericolo_zolla='0',
         bersaglio_chioma=6, bersaglio_ramo=5, moltiplicatore=1,
         comments='Esemplare in filare lungo corso trafficato.'),
    dict(custom_id='DEMO-002', species='Tilia cordata', condition='Discreto',
         address='Giardini Reali', latitude=45.0728, longitude=7.6874,
         height='14', trunk_diameter_cm=48, crown_diameter_m=9, age='35',
         location='Parco storico',
         tree_height_m=14, circonferenza_cm=151, branch_diam_cm=16, branch_length_m=6,
         branch_height_m=7, target_height_m=1.7,
         pericolo_rami='1', pericolo_tronco='1', pericolo_colletto='0', pericolo_zolla='0',
         bersaglio_chioma=4, bersaglio_ramo=3, moltiplicatore=1,
         comments='Lieve carie al colletto da monitorare.'),
    dict(custom_id='DEMO-003', species='Aesculus hippocastanum', condition='Scarso',
         address='Parco del Valentino', latitude=45.0556, longitude=7.6862,
         height='16', trunk_diameter_cm=55, crown_diameter_m=11, age='60',
         location='Parco urbano',
         tree_height_m=16, circonferenza_cm=173, branch_diam_cm=20, branch_length_m=7,
         branch_height_m=8, target_height_m=1.7,
         pericolo_rami='2', pericolo_tronco='2', pericolo_colletto='1', pericolo_zolla='1',
         bersaglio_chioma=5, bersaglio_ramo=4, moltiplicatore=1,
         comments='Corpi fruttiferi e defogliazione da cameraria.'),
    dict(custom_id='DEMO-004', species='Celtis australis', condition='Ottimo',
         address='Piazza Vittorio Veneto', latitude=45.0647, longitude=7.6942,
         height='12', trunk_diameter_cm=38, crown_diameter_m=8, age='25',
         location='Piazza', comments='Giovane esemplare in buona vigoria.'),
    dict(custom_id='DEMO-005', species='Quercus robur', condition='Buono',
         address='Parco della Pellerina', latitude=45.0889, longitude=7.6467,
         height='20', trunk_diameter_cm=78, crown_diameter_m=15, age='90',
         location='Grande parco', comments='Esemplare monumentale.'),
    dict(custom_id='DEMO-006', species='Cedrus deodara', condition='Discreto',
         address='Parco del Valentino', latitude=45.0533, longitude=7.6875,
         height='22', trunk_diameter_cm=70, crown_diameter_m=13, age='70',
         location='Parco urbano', comments='Conifera ornamentale, sofferenza estiva.'),
]

def _ensure_demo_account(username, password, role):
    """Create the demo account if missing; keep password/role/city in sync with config."""
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username, email=None, role=role, city=DEMO_CITY_NAME)
        db.session.add(u)
    u.set_password(password)
    u.role = role
    u.city = DEMO_CITY_NAME
    u.ensure_agronomer_code()
    db.session.commit()
    return u

def _seed_demo_trees(demo_user):
    """Delete all demo-owned trees (and their inspections) and re-create the fixed set."""
    tree_ids = [tid for (tid,) in
                db.session.query(Tree.id).filter(Tree.owner_id == demo_user.id).all()]
    if tree_ids:
        Inspection.query.filter(Inspection.tree_id.in_(tree_ids)).delete(synchronize_session=False)
        Tree.query.filter(Tree.owner_id == demo_user.id).delete(synchronize_session=False)
        db.session.commit()
    for d in DEMO_TREES:
        t = Tree(owner_id=demo_user.id, city=DEMO_CITY_NAME, **d)
        t.rischio = json.dumps(r) if (r := _calc_rischio(t)) else None
        db.session.add(t)
    db.session.commit()
    # Ispezione di "primo inserimento" per ogni albero demo: è il punto di
    # partenza che deve comparire nello storico.
    for t in Tree.query.filter(Tree.owner_id == demo_user.id).all():
        db.session.add(_make_inspection(t, demo_user.id, DEMO_USERNAME))
    db.session.commit()

def reset_demo():
    """Reset the whole demo to its fixed state: both accounts, their link, and the trees."""
    demo_user = _ensure_demo_account(DEMO_USERNAME, DEMO_PASSWORD, 'user')
    demo_city = _ensure_demo_account(DEMO_CITY_USERNAME, DEMO_CITY_PASSWORD, 'city')
    # demo_city manages only demo_user: clear any other links, then link demo_user.
    CityMembership.query.filter_by(city_user_id=demo_city.id).delete(synchronize_session=False)
    db.session.commit()
    db.session.add(CityMembership(city_user_id=demo_city.id, agronomer_id=demo_user.id))
    db.session.commit()
    _seed_demo_trees(demo_user)

def _demo_user_id():
    u = User.query.filter_by(username=DEMO_USERNAME).first()
    return u.id if u else None

def _is_demo_account(username):
    """Demo accounts are read-only for admin actions (creating users, linking agronomers)."""
    return username in (DEMO_USERNAME, DEMO_CITY_USERNAME)

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
        if token.startswith(API_TOKEN_PREFIX):
            # Token API (plugin QGIS): ruolo e comune letti ora dal DB, non
            # congelati nel token come nel JWT.
            found = _resolve_api_token(token)
            if not found:
                return jsonify({'message': 'Invalid token'}), 401
            tok, user = found
            request.user = {'user_id': user.id, 'username': user.username,
                            'role': user.role, 'city': user.city,
                            'auth': 'api_token', 'token_id': tok.id}
            now = datetime.now(timezone.utc)
            last = tok.last_used_at
            if last and last.tzinfo is None:   # SQLite perde il fuso
                last = last.replace(tzinfo=timezone.utc)
            if not last or (now - last).total_seconds() > 60:
                tok.last_used_at = now
                db.session.commit()
            return f(*args, **kwargs)
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

CITY_READONLY_MSG = ("Solo gli utenti agronomi possono modificare i campi degli alberi: "
                     "l'utente comune ha accesso in sola lettura.")

def _city_readonly():
    """L'utente `city` vede ed esporta gli alberi del proprio comune ma non li
    modifica: ritorna la risposta 403 da restituire, oppure None se il chiamante
    può scrivere (`user` sui propri alberi, `superuser` ovunque)."""
    if request.user.get('role') == 'city':
        return jsonify({'message': CITY_READONLY_MSG}), 403
    return None

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
    # Demo accounts: reset the shared sandbox to the fixed demo state on every login.
    if user.username in (DEMO_USERNAME, DEMO_CITY_USERNAME):
        reset_demo()
    if user.role == 'user' and not user.agronomer_code:
        user.ensure_agronomer_code(); db.session.commit()
    token = generate_token(user)
    return jsonify({'token': token,
                    'user': {'id': user.id, 'username': user.username,
                             'role': user.role, 'city': user.city,
                             'agronomer_code': user.agronomer_code}})

@app.route('/me', methods=['GET'])
@auth_required
def me():
    user = db.session.get(User, request.user.get('user_id'))
    code = None
    if user and user.role == 'user':
        code = user.ensure_agronomer_code()
        db.session.commit()
    return jsonify({'user_id': request.user.get('user_id'),
                    'username': request.user.get('username'),
                    'role': request.user.get('role'),
                    'city': request.user.get('city'),
                    'email': (user.email if user else None) or '',
                    'agronomer_code': code})

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

@app.route('/me', methods=['PATCH'])
@auth_required
def update_me():
    """Aggiorna i dati del proprio account. Per ora solo l'email, che serve
    al recupero password (/forgot-password) — utile ai comuni creati dal
    superuser senza email. Stringa vuota = rimuove l'email."""
    if _is_demo_account(request.user.get('username')):
        return jsonify({'message': 'Azione non disponibile nell\'account demo'}), 403
    user = db.session.get(User, request.user.get('user_id'))
    if not user:
        return jsonify({'message': 'Utente non trovato'}), 404
    data = request.json or {}
    if 'email' not in data:
        return jsonify({'message': 'Nessun campo da aggiornare'}), 400
    email = (data.get('email') or '').strip().lower()
    if email:
        if not _EMAIL_RE.match(email):
            return jsonify({'message': 'Indirizzo email non valido'}), 400
        other = User.query.filter(User.email == email, User.id != user.id).first()
        if other:
            return jsonify({'message': 'Email già associata a un altro account'}), 409
    user.email = email or None
    db.session.commit()
    return jsonify({'message': 'Email aggiornata' if email else 'Email rimossa',
                    'email': user.email or ''}), 200


# --- Token API (plugin QGIS, qgis.md §5) ---
@app.route('/me/tokens', methods=['GET'])
@auth_required
def list_api_tokens():
    toks = (ApiToken.query.filter_by(user_id=request.user['user_id'], revoked_at=None)
            .order_by(ApiToken.created_at.desc()).all())
    return jsonify([t.to_dict() for t in toks])

@app.route('/me/tokens', methods=['POST'])
@auth_required
def create_api_token():
    """Crea un token API per l'utente loggato (solo con JWT, non con un altro
    token API). Il token in chiaro è nella risposta e non è più recuperabile."""
    if request.user.get('auth') == 'api_token':
        return jsonify({'message': 'Un token API non può crearne altri: accedi dalla webapp.'}), 403
    user = db.session.get(User, request.user['user_id'])
    if not user or _is_demo_account(user.username):
        return jsonify({'message': 'Gli account demo non possono creare token API.'}), 403
    name = (request.json or {}).get('name') or 'QGIS'
    raw, tok = _new_api_token(user, name)
    db.session.commit()
    return jsonify({'token': raw, **tok.to_dict()}), 201

@app.route('/me/tokens/<int:token_id>', methods=['DELETE'])
@auth_required
def revoke_api_token(token_id):
    tok = db.session.get(ApiToken, token_id)
    if not tok or tok.user_id != request.user['user_id'] or tok.revoked_at:
        return jsonify({'message': 'Token non trovato'}), 404
    tok.revoked_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'message': 'Token revocato'})

@app.route('/register', methods=['POST'])
def register():
    if not REGISTRATION_ENABLED:
        return jsonify({'message': 'Registrazione non disponibile'}), 403
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
    user.ensure_agronomer_code()
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
        reset_url = f"{APP_BASE_URL}/?token={token}"
        if SMTP_USER and SMTP_PASSWORD:
            try:
                html_body = f"""
<div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;background:#f9f9f7;border-radius:12px;">
  <h2 style="color:#2d6a4f;margin-top:0;">Reimposta la tua password</h2>
  <p style="color:#444;">Hai richiesto il reset della password per il tuo account <strong>Silvae Pro</strong>.</p>
  <p style="color:#444;">Clicca il pulsante qui sotto per scegliere una nuova password. Il link è valido per <strong>2 ore</strong>.</p>
  <a href="{reset_url}"
     style="display:inline-block;margin:20px 0;padding:12px 28px;background:#2d6a4f;color:#fff;text-decoration:none;border-radius:8px;font-weight:bold;">
    Reimposta password
  </a>
  <p style="font-size:12px;color:#888;">Se non hai richiesto il reset, ignora questa email. La tua password rimarrà invariata.</p>
  <hr style="border:none;border-top:1px solid #ddd;margin:24px 0;">
  <p style="font-size:11px;color:#aaa;">Silvae Pro &nbsp;·&nbsp; Sistema di Gestione Alberi</p>
</div>
"""
                msg = MIMEMultipart('alternative')
                msg['Subject'] = 'Silvae Pro – Reimposta la tua password'
                msg['From']    = SMTP_USER
                msg['To']      = user.email
                msg.attach(MIMEText(f"Reimposta la password: {reset_url}", 'plain'))
                msg.attach(MIMEText(html_body, 'html'))
                with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                    smtp.sendmail(SMTP_USER, user.email, msg.as_string())
            except Exception as e:
                print(f"[PASSWORD RESET] Errore invio email: {e}")
        else:
            print(f"[PASSWORD RESET] SMTP non configurato. Link: {reset_url}")
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

@app.route('/change-password', methods=['POST'])
@auth_required
def change_password():
    """Cambio password dell'utente loggato (tutti i ruoli): serve la password
    attuale. Pensato per il primo accesso del comune con password temporanea."""
    if _is_demo_account(request.user.get('username')):
        return jsonify({'message': 'Azione non disponibile nell\'account demo'}), 403
    data         = request.json or {}
    current      = data.get('current_password', '')
    new_password = data.get('new_password', '')
    if not current or not new_password:
        return jsonify({'message': 'Password attuale e nuova password obbligatorie'}), 400
    if len(new_password) < 6:
        return jsonify({'message': 'Password troppo corta (minimo 6 caratteri)'}), 400
    if new_password == current:
        return jsonify({'message': 'La nuova password deve essere diversa da quella attuale'}), 400
    user = db.session.get(User, request.user.get('user_id'))
    if not user or not user.check_password(current):
        return jsonify({'message': 'Password attuale non corretta'}), 401
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
    if _is_demo_account(creator.get('username')):
        return jsonify({'message': 'Azione non disponibile nell\'account demo'}), 403
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
    email = (data.get('email') or '').strip().lower() or None
    if email:
        if not _EMAIL_RE.match(email):
            return jsonify({'message': 'Indirizzo email non valido'}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'Email già associata a un altro account'}), 409
    new_user = User(username=username, email=email, role=role, city=city)
    new_user.set_password(password)
    new_user.ensure_agronomer_code()
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User created',
                    'user': {'id': new_user.id, 'username': username, 'role': role, 'city': city,
                             'email': new_user.email or '',
                             'agronomer_code': new_user.agronomer_code}}), 201

@app.route('/admin/users/<int:target_id>', methods=['PATCH'])
@auth_required
@role_required('superuser')
def admin_update_user(target_id):
    """Il superuser aggiorna email e/o password di un utente (assistenza:
    utente senza email o che non riesce più ad accedere). Campi opzionali:
    ``email`` (stringa vuota = rimuove) e ``password`` (nuova password)."""
    target = db.session.get(User, target_id)
    if not target:
        return jsonify({'message': 'Utente non trovato'}), 404
    if _is_demo_account(target.username):
        return jsonify({'message': 'Gli account demo non sono modificabili'}), 403
    data = request.json or {}
    if 'email' not in data and not data.get('password'):
        return jsonify({'message': 'Nessun campo da aggiornare'}), 400
    changed = []
    if 'email' in data:
        email = (data.get('email') or '').strip().lower()
        if email:
            if not _EMAIL_RE.match(email):
                return jsonify({'message': 'Indirizzo email non valido'}), 400
            if User.query.filter(User.email == email, User.id != target.id).first():
                return jsonify({'message': 'Email già associata a un altro account'}), 409
        target.email = email or None
        changed.append('email')
    if data.get('password'):
        if len(data['password']) < 6:
            return jsonify({'message': 'Password troppo corta (minimo 6 caratteri)'}), 400
        target.set_password(data['password'])
        target.password_reset_token   = None
        target.password_reset_expires = None
        changed.append('password')
    db.session.commit()
    return jsonify({'message': f'Aggiornato: {", ".join(changed)}',
                    'user': {'id': target.id, 'username': target.username, 'role': target.role,
                             'city': target.city, 'email': target.email or ''}}), 200

@app.route('/users', methods=['GET'])
@auth_required
def list_users():
    role, user_city, user_id = (request.user.get(k) for k in ('role','city','user_id'))
    if role == 'superuser':   users = User.query.all()
    elif role == 'city':      users = User.query.filter_by(city=user_city).all()
    else:                     users = User.query.filter_by(id=user_id).all()
    return jsonify([{'id': u.id, 'username': u.username, 'role': u.role, 'city': u.city,
                     'email': u.email or '',
                     'agronomer_code': u.agronomer_code if role == 'superuser' else None}
                    for u in users])

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
                           'username': a.username, 'email': a.email or '',
                           'agronomer_code': a.agronomer_code})
    return jsonify(result)

@app.route('/city/agronomers', methods=['POST'])
@auth_required
@role_required('city', 'superuser')
def add_city_agronomer():
    if _is_demo_account(request.user.get('username')):
        return jsonify({'message': 'Azione non disponibile nell\'account demo'}), 403
    user_id = request.user.get('user_id')
    role    = request.user.get('role')
    data    = request.json or {}
    # Il comune collega l'agronomo tramite il suo codice (AGR-XXXX-XXXX);
    # il superuser può usare anche lo username, per l'associazione manuale.
    code     = (data.get('code') or '').strip().upper()
    username = (data.get('username') or '').strip()
    if code:
        agronomer = User.query.filter_by(agronomer_code=code, role='user').first()
        if not agronomer:
            return jsonify({'message': f'Nessun agronomo con codice "{code}"'}), 404
    elif username and role == 'superuser':
        agronomer = User.query.filter_by(username=username, role='user').first()
        if not agronomer:
            return jsonify({'message': f'Agronomo "{username}" non trovato'}), 404
    elif username:
        return jsonify({'message': 'Inserisci il codice agronomo (AGR-XXXX-XXXX) comunicato dall\'agronomo'}), 400
    else:
        return jsonify({'message': 'Codice agronomo obbligatorio'}), 400
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
    if _is_demo_account(request.user.get('username')):
        return jsonify({'message': 'Azione non disponibile nell\'account demo'}), 403
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
@auth_required
def get_cities():
    """Comuni per il selettore in alto, limitati a quelli dove il chiamante
    vede qualcosa: selezionare un comune altrui mostrerebbe una lista vuota.

      - `city`    : solo il proprio.
      - `user`    : i comuni dei **propri** alberi, piu' quelli dei comuni a
                    cui e' collegato, dove magari non ha ancora censito nulla
                    ed e' proprio dove deve iniziare.
      - `superuser`: i comuni creati in Gestione piu' quelli degli alberi che
                    vede (la demo e' esclusa da _role_tree_query).

    I nomi sui comuni visibili escono dalla stessa query di visibilita' degli
    alberi, cosi' il selettore non puo' divergere da cio' che poi la lista
    mostra.
    """
    role, uid, own = (request.user.get(k) for k in ('role', 'user_id', 'city'))
    if role == 'city':
        return jsonify([own] if own else [])
    nomi = {c for (c,) in (_role_tree_query(role, uid, own)
                           .with_entities(Tree.city).distinct()) if c}
    if role == 'user':
        nomi |= {c for (c,) in (db.session.query(User.city)
                                .join(CityMembership,
                                      CityMembership.city_user_id == User.id)
                                .filter(CityMembership.agronomer_id == uid)
                                .distinct()) if c}
    else:
        nomi |= {c.name for c in City.query.all()}
    return jsonify(sorted(nomi))

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
        'bersaglio_tipi': dd.BERSAGLIO_TIPI,
        'bersaglio_proprieta_values': dd.BERSAGLIO_PROPRIETA_VALUES,
        'bersaglio_occupazione_values': dd.BERSAGLIO_OCCUPAZIONE_VALUES,
        'condizione_salute_ecologica': [desc for desc, _ in dd.CONDIZIONE_SALUTE_ECOLOGICA],
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
    # Resolve bersaglio class from tipo+value (proprietà/occupazione)
    # or from tipo+flow (pedoni/traffico).
    crown_diam_m = f('crown_diameter_m') or 0
    tree_h_m     = required['tree_height_m'] or 0
    branch_l_m   = required['branch_length_m'] or 0
    zone_chioma  = (crown_diam_m + tree_h_m) / 2.0
    zone_ramo    = branch_l_m * 1.25
    for tipo_key, value_key, flow_key, class_key, zone_w in [
        ('bersaglio_chioma_tipo', 'bersaglio_chioma_value', 'bersaglio_chioma_flow',
         'bersaglio_chioma', zone_chioma),
        ('bersaglio_ramo_tipo',   'bersaglio_ramo_value',   'bersaglio_ramo_flow',
         'bersaglio_ramo',   zone_ramo),
    ]:
        tipo  = data.get(tipo_key)
        value = data.get(value_key)
        flow  = f(flow_key)
        if tipo and value:
            computed = bersaglio_value_to_class(tipo, value)
            if computed is not None:
                required[class_key] = computed
        elif tipo and flow is not None and zone_w > 0:
            computed = bersaglio_flow_to_class(tipo, flow, zone_w)
            if computed is not None:
                required[class_key] = computed
    # I gradi di pericolo si valutano per-componente, come nella scheda: un
    # pericolo mancante diventa 0 = "non determinato" (SOSPESO), non blocca il
    # calcolo. Si rifiuta solo se mancano TUTTI e quattro.
    PERICOLI = ('pericolo_rami', 'pericolo_tronco', 'pericolo_colletto', 'pericolo_zolla')
    if all(required[k] is None for k in PERICOLI):
        return jsonify({'message': 'Per calcolare il rischio inserisci almeno un '
                                   'grado di pericolo (rami, tronco, colletto o zolla).'}), 400
    for k in PERICOLI:
        if required[k] is None:
            required[k] = 0

    # Gli altri campi (dimensioni e bersagli) restano obbligatori.
    missing = [k for k, v in required.items() if v is None]
    if missing:
        return jsonify({'message': f'Missing: {", ".join(missing)}'}), 400

    result = assess_tree(
        tree_height_m=required['tree_height_m'],
        circumference_cm=required['circonferenza_cm'],
        crown_diam_m=crown_diam_m,
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
        moltiplicatore=i('moltiplicatore') or 1,
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
    elif role == 'superuser':
        did = _demo_user_id()
        if did and did != user_id: query = query.filter(Tree.owner_id != did)
    city_q = request.args.get('city')
    addr_q = request.args.get('address')
    # Comune: confronto esatto, come in ogni altro punto (export, /qgis/features,
    # filtro del ruolo city). Il nome arriva dal selettore, cioe' dai valori che
    # sono nel database: con ilike('%Bra%') si caricava anche «Brandizzo», e la
    # lista mostrava alberi che l'export dello stesso comune poi non conteneva.
    # L'indirizzo resta una ricerca libera, quindi per sottostringa.
    if city_q:  query = query.filter(Tree.city == city_q)
    if addr_q:  query = query.filter(Tree.address.ilike(f"%{addr_q}%"))
    return jsonify([tree_to_dict(t) for t in query.order_by(Tree.id).all()])

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
    if (denied := _city_readonly()): return denied
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
        except (ValueError, TypeError):
            return jsonify({'message': 'Invalid lat/lon'}), 400

    if tree.cpc:
        tree.condition = tree.cpc

    tree.rischio = json.dumps(r) if (r := _calc_rischio(tree)) else None
    db.session.commit()

    if {'condition','comments','actions'} & set(data.keys()):
        db.session.add(_make_inspection(tree, request.user.get('user_id'), request.user.get('username')))
        db.session.commit()
    return jsonify({'message': f'Tree {tree_id} updated successfully!'}), 200

@app.route('/tree/<int:tree_id>', methods=['DELETE'])
@auth_required
def delete_tree(tree_id):
    if (denied := _city_readonly()): return denied
    tree = db.session.get(Tree, tree_id)
    if not tree: return jsonify({'message': 'Tree not found'}), 404
    role, user_id, user_city = (request.user.get(k) for k in ('role','user_id','city'))
    if role == 'user' and tree.owner_id != user_id:          return jsonify({'message': 'Forbidden'}), 403
    if role == 'city' and not city_can_access_tree(tree, user_id, user_city): return jsonify({'message': 'Forbidden'}), 403
    db.session.delete(tree); db.session.commit()
    return jsonify({'message': f'Tree {tree_id} deleted successfully!'}), 200

@app.route('/trees/bulk', methods=['DELETE'])
@auth_required
def delete_trees_bulk():
    if (denied := _city_readonly()): return denied
    user_id   = request.user.get('user_id')
    role      = request.user.get('role')
    user_city = request.user.get('city')
    ids = (request.json or {}).get('ids', [])
    if not ids:
        return jsonify({'message': 'Nessun ID fornito'}), 400
    deleted = 0
    for tree_id in ids:
        tree = db.session.get(Tree, int(tree_id))
        if not tree: continue
        if role == 'user' and tree.owner_id != user_id: continue
        if role == 'city' and not city_can_access_tree(tree, user_id, user_city): continue
        db.session.delete(tree)
        deleted += 1
    db.session.commit()
    return jsonify({'deleted': deleted})

@app.route('/add_tree', methods=['POST'])
@auth_required
def add_tree():
    if (denied := _city_readonly()): return denied
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
        owner_id=user_id
    )
    apply_tree_fields(new_tree, data)
    if new_tree.cpc:
        new_tree.condition = new_tree.cpc
    new_tree.rischio = json.dumps(r) if (r := _calc_rischio(new_tree)) else None
    db.session.add(new_tree)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'message': 'Errore durante il salvataggio. Riprova.'}), 409

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
    if (denied := _city_readonly()): return denied
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

# --- Excel export: helper e definizione delle colonne (raggruppate) -----------
# Definiti a livello di modulo così da poter essere condivisi tra l'endpoint di
# export e quello che elenca le colonne (per la scelta dei campi da esportare).
def _xl_jlist(val):
    if not val: return ''
    try:
        lst = json.loads(val) if isinstance(val, str) else val
        return ', '.join(str(x) for x in lst) if isinstance(lst, list) else str(lst)
    except: return ''

def _xl_diag(val):
    if not val: return ''
    try:
        lst = json.loads(val) if isinstance(val, str) else val
        return '; '.join(
            f"{r.get('caratt','')}: {r.get('giudizio','')}"
            for r in lst if isinstance(r, dict) and r.get('caratt')
        )
    except: return ''

def _xl_rtop(t, phase, field):
    if not t.rischio: return ''
    try: return json.loads(t.rischio).get(phase, {}).get(field, '')
    except: return ''

def _xl_rpart(t, phase, part, field):
    if not t.rischio: return ''
    try: return json.loads(t.rischio).get(phase, {}).get(part, {}).get(field, '')
    except: return ''


def _excel_groups():
    """Colonne dell'export Excel: (group_label, color_hex, [(col_header, getter), ...]).
    L'intestazione di colonna funge anche da chiave stabile per l'esclusione dei campi."""
    _jlist, _diag, _rtop, _rpart = _xl_jlist, _xl_diag, _xl_rtop, _xl_rpart
    return [
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
            ('Tipo bersaglio chioma',        lambda t: t.bersaglio_chioma_tipo or ''),
            ('Descrizione bersaglio chioma',lambda t: t.bersaglio_chioma_value or ''),
            ('Flusso bersaglio chioma',     lambda t: t.bersaglio_chioma_flow),
            ('Classe bersaglio chioma',     lambda t: t.bersaglio_chioma),
            ('Tipo bersaglio ramo',         lambda t: t.bersaglio_ramo_tipo or ''),
            ('Descrizione bersaglio ramo',  lambda t: t.bersaglio_ramo_value or ''),
            ('Flusso bersaglio ramo',       lambda t: t.bersaglio_ramo_flow),
            ('Classe bersaglio ramo',       lambda t: t.bersaglio_ramo),
            ('Moltiplicatore (n bersagli)', lambda t: t.moltiplicatore or 1),
            ('Imp. chioma att. (kgm/s)',    lambda t: _rtop(t, 'attuale', 'crown_momentum_kgms')),
            ('Classe imp. chioma att.',     lambda t: _rtop(t, 'attuale', 'crown_impulso_class')),
            ('Imp. ramo att. (kgm/s)',      lambda t: _rtop(t, 'attuale', 'branch_momentum_kgms')),
            ('Classe imp. ramo att.',       lambda t: _rtop(t, 'attuale', 'branch_impulso_class')),
            ('Rischio rami 1bers (att.)',   lambda t: _rpart(t, 'attuale', 'rami',     'risk_ratio_1bers')),
            ('Rischio rami (att.)',         lambda t: _rpart(t, 'attuale', 'rami',     'risk_description')),
            ('Rischio tronco 1bers (att.)',lambda t: _rpart(t, 'attuale', 'tronco',   'risk_ratio_1bers')),
            ('Rischio tronco (att.)',       lambda t: _rpart(t, 'attuale', 'tronco',   'risk_description')),
            ('Rischio colletto 1bers (att.)',lambda t: _rpart(t, 'attuale', 'colletto','risk_ratio_1bers')),
            ('Rischio colletto (att.)',     lambda t: _rpart(t, 'attuale', 'colletto', 'risk_description')),
            ('Rischio zolla 1bers (att.)', lambda t: _rpart(t, 'attuale', 'zolla',    'risk_ratio_1bers')),
            ('Rischio zolla (att.)',        lambda t: _rpart(t, 'attuale', 'zolla',    'risk_description')),
            ('Imp. chioma res. (kgm/s)',    lambda t: _rtop(t, 'residuo', 'crown_momentum_kgms')),
            ('Classe imp. chioma res.',     lambda t: _rtop(t, 'residuo', 'crown_impulso_class')),
            ('Imp. ramo res. (kgm/s)',      lambda t: _rtop(t, 'residuo', 'branch_momentum_kgms')),
            ('Classe imp. ramo res.',       lambda t: _rtop(t, 'residuo', 'branch_impulso_class')),
            ('Rischio rami 1bers (res.)',   lambda t: _rpart(t, 'residuo', 'rami',     'risk_ratio_1bers')),
            ('Rischio rami (res.)',         lambda t: _rpart(t, 'residuo', 'rami',     'risk_description')),
            ('Rischio tronco 1bers (res.)',lambda t: _rpart(t, 'residuo', 'tronco',   'risk_ratio_1bers')),
            ('Rischio tronco (res.)',       lambda t: _rpart(t, 'residuo', 'tronco',   'risk_description')),
            ('Rischio colletto 1bers (res.)',lambda t: _rpart(t, 'residuo', 'colletto','risk_ratio_1bers')),
            ('Rischio colletto (res.)',     lambda t: _rpart(t, 'residuo', 'colletto', 'risk_description')),
            ('Rischio zolla 1bers (res.)', lambda t: _rpart(t, 'residuo', 'zolla',    'risk_ratio_1bers')),
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


def _export_exclude_set():
    """Insieme dei campi da NON esportare, dal parametro `exclude` (array JSON di chiavi).
    La chiave è l'intestazione colonna (Excel) o il nome colonna di default (GPKG)."""
    raw = request.args.get('exclude')
    if not raw:
        return set()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {str(x) for x in data}
    except Exception:
        pass
    return set()


@app.route('/export/excel/columns', methods=['GET'])
@auth_required
def export_excel_columns():
    """Gruppi e intestazioni delle colonne dell'export Excel, per la scelta dei campi."""
    return jsonify([
        {'group': label, 'color': color, 'columns': [h for h, _ in cols]}
        for label, color, cols in _excel_groups()
    ])


@app.route('/export/excel', methods=['GET'])
@auth_required
def export_excel():
    trees   = _export_tree_query().all()
    exclude = _export_exclude_set()

    # Flatten columns and track group spans for merged header row,
    # skipping excluded columns and dropping any group left empty.
    all_cols   = []  # [(header, getter, color)]
    group_info = []  # [(label, start_col, end_col, color)]
    col_idx = 1
    for label, color, cols in _excel_groups():
        kept = [(h, g) for (h, g) in cols if h not in exclude]
        if not kept:
            continue
        group_info.append((label, col_idx, col_idx + len(kept) - 1, color))
        for header, getter in kept:
            all_cols.append((header, getter, color))
        col_idx += len(kept)
    if not all_cols:
        return jsonify({'error': "Nessun campo selezionato per l'export"}), 400

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

# Canonical column list shared by export and import.
# Format: (gpkg_column_name, sql_type, export_getter, tree_attr_or_None)
# tree_attr is the Tree model attribute name for import; None = skip on import.
# Multi-value fields (conflitti etc.) use a special prefix 'CSV:' handled below.
_GPKG_COLS = [
    ('id',                    'INTEGER', lambda t: t.id,                          None),
    ('uuid',                  'TEXT',    lambda t: t.uuid,                        'uuid'),  # chiave stabile per il round-trip
    ('custom_id',             'TEXT',    lambda t: t.custom_id,                   'custom_id'),
    ('city',                  'TEXT',    lambda t: t.city,                        None),  # city comes from the form
    ('address',               'TEXT',    lambda t: t.address or '',               'address'),
    ('latitude',              'REAL',    lambda t: t.latitude,                    'latitude'),
    ('longitude',             'REAL',    lambda t: t.longitude,                   'longitude'),
    ('species',               'TEXT',    lambda t: t.species,                     'species'),
    ('condition',             'TEXT',    lambda t: t.condition or '',             'condition'),
    ('age',                   'TEXT',    lambda t: t.age or '',                   'age'),
    ('cpc',                   'TEXT',    lambda t: t.cpc or '',                   'cpc'),
    ('location',              'TEXT',    lambda t: t.location or '',              'location'),
    ('height',                'TEXT',    lambda t: t.height or '',               'height'),
    ('dimora',                'TEXT',    lambda t: t.dimora or '',               'dimora'),
    ('stadio_sviluppo',       'TEXT',    lambda t: t.stadio_sviluppo or '',      'stadio_sviluppo'),
    ('posizione_sociale',     'TEXT',    lambda t: t.posizione_sociale or '',    'posizione_sociale'),
    ('localizzazione',        'TEXT',    lambda t: t.localizzazione or '',       'localizzazione'),
    ('vincoli',               'TEXT',    lambda t: t.vincoli or '',              'vincoli'),
    ('tree_height_m',         'REAL',    lambda t: t.tree_height_m,              'tree_height_m'),
    ('circonferenza_cm',      'REAL',    lambda t: t.circonferenza_cm,           'circonferenza_cm'),
    ('trunk_diameter_cm',     'REAL',    lambda t: t.trunk_diameter_cm,          'trunk_diameter_cm'),
    ('crown_diameter_m',      'REAL',    lambda t: t.crown_diameter_m,           'crown_diameter_m'),
    ('branch_diam_cm',        'REAL',    lambda t: t.branch_diam_cm,             'branch_diam_cm'),
    ('branch_length_m',       'REAL',    lambda t: t.branch_length_m,            'branch_length_m'),
    ('branch_height_m',       'REAL',    lambda t: t.branch_height_m,            'branch_height_m'),
    ('target_height_m',       'REAL',    lambda t: t.target_height_m,            'target_height_m'),
    ('post_tree_height_m',    'REAL',    lambda t: t.post_tree_height_m,         'post_tree_height_m'),
    ('post_circonferenza_cm', 'REAL',    lambda t: t.post_circonferenza_cm,      'post_circonferenza_cm'),
    ('post_branch_diam_cm',   'REAL',    lambda t: t.post_branch_diam_cm,        'post_branch_diam_cm'),
    ('post_branch_length_m',  'REAL',    lambda t: t.post_branch_length_m,       'post_branch_length_m'),
    ('post_branch_height_m',  'REAL',    lambda t: t.post_branch_height_m,       'post_branch_height_m'),
    ('post_target_height_m',  'REAL',    lambda t: t.post_target_height_m,       'post_target_height_m'),
    ('pericolo_rami',         'TEXT',    lambda t: t.pericolo_rami or '',        'pericolo_rami'),
    ('pericolo_tronco',       'TEXT',    lambda t: t.pericolo_tronco or '',      'pericolo_tronco'),
    ('pericolo_colletto',     'TEXT',    lambda t: t.pericolo_colletto or '',    'pericolo_colletto'),
    ('pericolo_zolla',        'TEXT',    lambda t: t.pericolo_zolla or '',       'pericolo_zolla'),
    ('bersaglio_chioma_tipo', 'TEXT',    lambda t: t.bersaglio_chioma_tipo or '', 'bersaglio_chioma_tipo'),
    ('bersaglio_chioma_value','TEXT',    lambda t: t.bersaglio_chioma_value or '','bersaglio_chioma_value'),
    ('bersaglio_chioma_flow', 'REAL',    lambda t: t.bersaglio_chioma_flow,      'bersaglio_chioma_flow'),
    ('bersaglio_chioma',      'INTEGER', lambda t: t.bersaglio_chioma,           'bersaglio_chioma'),
    ('bersaglio_ramo_tipo',   'TEXT',    lambda t: t.bersaglio_ramo_tipo or '',  'bersaglio_ramo_tipo'),
    ('bersaglio_ramo_value',  'TEXT',    lambda t: t.bersaglio_ramo_value or '', 'bersaglio_ramo_value'),
    ('bersaglio_ramo_flow',   'REAL',    lambda t: t.bersaglio_ramo_flow,        'bersaglio_ramo_flow'),
    ('bersaglio_ramo',        'INTEGER', lambda t: t.bersaglio_ramo,             'bersaglio_ramo'),
    ('moltiplicatore',        'INTEGER', lambda t: t.moltiplicatore,             'moltiplicatore'),
    ('monitoraggio',          'TEXT',    lambda t: t.monitoraggio or '',         'monitoraggio'),
    ('urgenza',               'TEXT',    lambda t: t.urgenza or '',              'urgenza'),
    ('next_check',            'TEXT',    lambda t: t.next_check.strftime('%Y-%m-%d') if t.next_check else '', 'next_check'),
    ('comments',              'TEXT',    lambda t: t.comments or '',             'comments'),
    ('actions',               'TEXT',    lambda t: t.actions or '',              'actions'),
    ('conflitti',             'TEXT',    None,                                    'CSV:conflitti_list'),
    ('agenti_carie',          'TEXT',    None,                                    'CSV:agenti_carie'),
    ('altri_patogeni',        'TEXT',    None,                                    'CSV:altri_patogeni'),
    ('prescrizioni_val',      'TEXT',    None,                                    'CSV:prescrizioni_val'),
    ('prescrizioni_mit',      'TEXT',    None,                                    'CSV:prescrizioni_mit'),
    ('prescrizioni_col',      'TEXT',    None,                                    'CSV:prescrizioni_col'),
    # Categorie calcolate (le stesse della barra statistiche): servono allo
    # stile QGIS; in import vengono ignorate.
    ('stat_bucket',           'TEXT',    lambda t: _stat_bucket_value(t),         None),
    ('rischio_classe',        'TEXT',    lambda t: _worst_risk(t),                None),
    ('cond_classe',           'TEXT',    lambda t: _cond_key(t),                  None),
]

_GPX_WPT_TAGS = ('name', 'cmt', 'desc', 'ele', 'sym', 'type', 'time', 'src', 'link')

def _xml_local(tag):
    """'{ns}tag' → 'tag'."""
    return tag.rsplit('}', 1)[-1]

def _gpx_read_waypoints(f_or_path):
    """Read the <wpt> of a GPX file (1.0 or 1.1, any namespace) and return
    (cols, rows, 'waypoints') in the same shape as _gpkg_read_table(), so the
    GPX import goes through the same column mapping and insert logic.
    Columns: lat, lon, the standard child tags, plus the children of
    <extensions> (e.g. the attributes QGIS or Silvae itself write there)."""
    import xml.etree.ElementTree as ET
    src = f_or_path.stream if hasattr(f_or_path, 'stream') else f_or_path
    root = ET.parse(src).getroot()
    if _xml_local(root.tag) != 'gpx':
        raise ValueError('Il file non è un GPX (elemento radice diverso da <gpx>)')
    # Nei file scritti da Silvae, <cmt> e <desc> sono derivati dai campi in
    # <extensions>: ignorarli evita che il riassunto finisca nelle note.
    derived = {'cmt', 'desc'} if (root.get('creator') or '').startswith('Silvae') else set()
    cols, rows = ['lat', 'lon'], []
    seen = set(cols)
    for wpt in root.iter():
        if _xml_local(wpt.tag) != 'wpt':
            continue
        row = {'lat': wpt.get('lat'), 'lon': wpt.get('lon')}
        for child in wpt:
            tag = _xml_local(child.tag)
            if tag == 'extensions':
                for ext in child.iter():
                    if ext is child or len(ext):   # solo le foglie
                        continue
                    row[_xml_local(ext.tag)] = (ext.text or '').strip()
            elif tag == 'link':
                row['link'] = child.get('href') or ''
            elif tag in derived:
                continue
            else:
                row[tag] = (child.text or '').strip()
        for k in row:
            if k not in seen:
                seen.add(k); cols.append(k)
        rows.append(row)
    if not rows:
        raise ValueError('Nessun waypoint <wpt> trovato nel file GPX')
    return cols, rows, 'waypoints'

def _read_import_file(f):
    """Dispatch on file extension: GPX → waypoints, everything else → GPKG."""
    name = (f.filename or '').lower()
    if name.endswith('.gpx'):
        return _gpx_read_waypoints(f)
    return _gpkg_read_table(f)

def _gpkg_jlist(val):
    """DB JSON array → comma-separated string for GPKG storage."""
    if not val: return ''
    try:
        lst = json.loads(val) if isinstance(val, str) else val
        return ', '.join(str(x) for x in lst) if isinstance(lst, list) else str(lst)
    except: return ''

def _gpkg_csv_to_json(val):
    """Comma-separated GPKG string → DB JSON array string."""
    if not val or not str(val).strip(): return None
    items = [x.strip() for x in str(val).split(',') if x.strip()]
    return json.dumps(items, ensure_ascii=False) if items else None

@app.route('/export/gpkg/columns', methods=['GET'])
@auth_required
def export_gpkg_columns():
    """Nomi (chiavi) di default delle colonne del GPKG, per la finestra di rinomina in export."""
    return jsonify([{'name': n, 'type': typ} for n, typ, _, _ in _GPKG_COLS])


def _san_gpkg_ident(name):
    """Ripulisce un nome colonna in un identificatore SQL valido (o None se vuoto)."""
    s = re.sub(r'[^0-9A-Za-z_]', '_', str(name).strip())
    if not s:
        return None
    if s[0].isdigit():
        s = '_' + s
    return s


def _resolve_gpkg_names(overrides):
    """Restituisce la lista dei nomi colonna di output applicando le rinomine richieste.
    Garantisce nomi validi, non duplicati e diversi dalle colonne riservate (fid, geom)."""
    reserved = {'fid', 'geom'}
    out_names = []
    seen = {r.lower() for r in reserved}
    for (n, _typ, _g, _attr) in _GPKG_COLS:
        target = n
        if n in overrides:
            cand = _san_gpkg_ident(overrides[n])
            if cand and cand.lower() not in seen:
                target = cand
        base, k = target, 2
        while target.lower() in seen:
            target = f'{base}_{k}'
            k += 1
        seen.add(target.lower())
        out_names.append(target)
    return out_names


@app.route('/export/gpkg', methods=['GET'])
@auth_required
def export_gpkg():
    trees = [t for t in _export_tree_query().all()
             if t.latitude is not None and t.longitude is not None]

    def make_point(lon, lat):
        return b'GP\x00\x01' + struct.pack('<i', 4326) + struct.pack('<BIdd', 1, 1, lon, lat)

    # CSV multi-value getters (not in _GPKG_COLS lambdas to avoid closure issues)
    _csv_getters = {
        'conflitti':       lambda t: _gpkg_jlist(t.conflitti_list),
        'agenti_carie':    lambda t: _gpkg_jlist(t.agenti_carie),
        'altri_patogeni':  lambda t: _gpkg_jlist(t.altri_patogeni),
        'prescrizioni_val':lambda t: _gpkg_jlist(t.prescrizioni_val),
        'prescrizioni_mit':lambda t: _gpkg_jlist(t.prescrizioni_mit),
        'prescrizioni_col':lambda t: _gpkg_jlist(t.prescrizioni_col),
    }

    def get_val(col_name, getter, t):
        if getter is not None:
            return getter(t)
        return _csv_getters[col_name](t)

    # Rinomina delle chiavi (colonne) richiesta dall'utente: {nome_default: nome_nuovo}
    overrides = {}
    rename_param = request.args.get('rename')
    if rename_param:
        try:
            raw = json.loads(rename_param)
            if isinstance(raw, dict):
                overrides = {str(k): v for k, v in raw.items()}
        except Exception:
            overrides = {}
    out_names = _resolve_gpkg_names(overrides)

    # (nome_default, nome_output, tipo, getter) — il valore si estrae col nome default
    cols = [(n, out, typ, g) for (n, typ, g, _), out in zip(_GPKG_COLS, out_names)]

    # Esclusione dei campi non desiderati (per nome colonna di default)
    exclude = _export_exclude_set()
    if exclude:
        cols = [c for c in cols if c[0] not in exclude]
    if not cols:
        return jsonify({'error': "Nessun campo selezionato per l'export"}), 400

    col_defs = ', '.join(f'{out} {typ}' for _, out, typ, _ in cols)
    col_names = ', '.join(out for _, out, _, _ in cols)
    placeholders = ', '.join(['?'] * len(cols))

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.gpkg', delete=False) as tmp:
            tmp_path = tmp.name

        conn = sqlite3.connect(tmp_path)
        cur  = conn.cursor()

        cur.execute('PRAGMA application_id = 1196444487')
        cur.execute('PRAGMA user_version   = 10200')
        conn.commit()

        cur.executescript(f"""
            CREATE TABLE gpkg_spatial_ref_sys (
                srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY,
                organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
                definition TEXT NOT NULL, description TEXT
            );
            INSERT INTO gpkg_spatial_ref_sys VALUES
                ('Undefined cartesian SRS', -1, 'NONE', -1, 'undefined', NULL),
                ('Undefined geographic SRS', 0, 'NONE', 0, 'undefined', NULL),
                ('WGS 84 geodetic', 4326, 'EPSG', 4326,
                 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]',
                 'WGS 84');
            CREATE TABLE gpkg_contents (
                table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL,
                identifier TEXT, description TEXT DEFAULT '',
                last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                min_x REAL, min_y REAL, max_x REAL, max_y REAL, srs_id INTEGER
            );
            CREATE TABLE gpkg_geometry_columns (
                table_name TEXT NOT NULL, column_name TEXT NOT NULL,
                geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL,
                z TINYINT NOT NULL, m TINYINT NOT NULL,
                CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name)
            );
            CREATE TABLE alberi (
                fid INTEGER PRIMARY KEY AUTOINCREMENT,
                geom BLOB,
                {col_defs}
            );
        """)

        lons = [t.longitude for t in trees]
        lats = [t.latitude  for t in trees]
        cur.execute(
            "INSERT INTO gpkg_contents (table_name,data_type,identifier,srs_id,min_x,min_y,max_x,max_y) "
            "VALUES ('alberi','features','alberi',4326,?,?,?,?)",
            (min(lons) if lons else None, min(lats) if lats else None,
             max(lons) if lons else None, max(lats) if lats else None)
        )
        cur.execute("INSERT INTO gpkg_geometry_columns VALUES ('alberi','geom','POINT',4326,0,0)")

        INSERT = f"INSERT INTO alberi (geom, {col_names}) VALUES (?, {placeholders})"
        for t in trees:
            cur.execute(INSERT,
                [make_point(t.longitude, t.latitude)] +
                [get_val(n, g, t) for n, _out, _typ, g in cols])

        # Stile QGIS predefinito dentro il file (tabella layer_styles): QGIS lo
        # applica da solo quando aggiunge il layer. Solo se la colonna di
        # categoria non è stata esclusa; il nome è quello scelto dall'utente.
        stat_col = next((out for n, out, _t, _g in cols if n == 'stat_bucket'), None)
        if stat_col:
            cur.executescript("""
                CREATE TABLE layer_styles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    f_table_catalog TEXT(256), f_table_schema TEXT(256),
                    f_table_name TEXT(256), f_geometry_column TEXT(256),
                    styleName TEXT(30), styleQML TEXT, styleSLD TEXT,
                    useAsDefault BOOLEAN, description TEXT, owner TEXT(30),
                    ui TEXT(30), update_time DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute(
                "INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name, f_geometry_column, "
                "styleName, styleQML, styleSLD, useAsDefault, description, owner, update_time) "
                "VALUES ('', '', 'alberi', 'geom', ?, ?, '', 1, ?, 'Silvae Pro', ?)",
                ('Silvae — rischio/condizione', qgis_style.qml('stat', field=stat_col),
                 'Colori per classe di rischio ARETE e condizione VTA, come nella webapp',
                 datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')))

        conn.commit()
        conn.close()

        buf = io.BytesIO()
        with open(tmp_path, 'rb') as f:
            buf.write(f.read())
        buf.seek(0)
        return send_file(buf, download_name='alberi.gpkg', as_attachment=True,
                         mimetype='application/geopackage+sqlite3')
    finally:
        if tmp_path:
            try: os.unlink(tmp_path)
            except Exception: pass

# -----------------------
# Export GPX (waypoint per GPS / QGIS)
# -----------------------
# Ordine di gravità delle categorie: le chiavi sono quelle di tools/palette.py.
_RISK_SEVERITY = {e['key']: i for i, e in enumerate(palette.RISK) if e['key'] != 'na'}

def _risk_category(desc):
    """Descrizione ARETE → chiave di palette.RISK; stessa logica di riskStatCategory() nel frontend."""
    d = (desc or '').lower()
    if not d or 'non determinato' in d: return None
    if 'per accordo' in d:               return 'accordo'
    if 'inaccettabile' in d:             return 'inaccettabile'
    if 'alarp' in d:                     return 'alarp'
    if 'largamente accettabile' in d:    return 'accettabile'
    if 'tollerabile' in d:               return 'alarp'
    return None

_RISK_PARTS = ('rami', 'tronco', 'colletto', 'zolla')

def _worst_risk_of(section):
    """Chiave della categoria peggiore tra rami/tronco/colletto/zolla di una
    sezione del JSON di rischio (`attuale` o `residuo`), o '' se non calcolata."""
    worst = None
    for part in _RISK_PARTS:
        cat = _risk_category(((section or {}).get(part) or {}).get('risk_description'))
        if cat and (worst is None or _RISK_SEVERITY[cat] > _RISK_SEVERITY[worst]):
            worst = cat
    return worst or ''

def _worst_risk(t):
    """Chiave della categoria di rischio peggiore della fase attuale
    (rami/tronco/colletto/zolla), o '' se non calcolato."""
    if not t.rischio: return ''
    try: att = json.loads(t.rischio).get('attuale') or {}
    except Exception: return ''
    return _worst_risk_of(att)

def _risk_label(key):
    """Etichetta leggibile di una chiave di palette.RISK ('' se vuota)."""
    e = palette.by_key('risk', key) if key else None
    return e['label'] if e else ''

def _cond_category(cond):
    """Condizione / classe CPC → chiave di palette.CONDITION; stessa logica di condCategory() nel frontend."""
    c = (cond or '').strip().lower()
    if not c: return 'other'
    if c == 'a': return 'good'
    if c == 'b': return 'buono'
    if c == 'c': return 'fair'
    if c in ('d', 'c/d'): return 'poor'
    if any(k in c for k in ('ottimo', 'eccellente', 'excel', 'good')): return 'good'
    if 'buono' in c: return 'buono'
    if any(k in c for k in ('discreto', 'mediocre', 'fair', 'moder')): return 'fair'
    if any(k in c for k in ('scarso', 'critico', 'morto', 'abbattuto', 'poor', 'crit', 'dead')): return 'poor'
    return 'other'

def _tree_bucket(t):
    """Casella statistica dell'albero, come treeStatBucket() nel frontend:
    ('risk', chiave) se il rischio è calcolato, altrimenti ('cond', chiave) da
    CPC o condizione, altrimenti ('na', 'na')."""
    r = _worst_risk(t)
    if r: return 'risk', r
    src = (t.cpc or '').strip() or (t.condition or '').strip()
    if src: return 'cond', _cond_category(src)
    return 'na', 'na'

def _cond_key(t):
    """Chiave di palette.CONDITION da CPC o condizione, '' se nessuna delle due."""
    src = (t.cpc or '').strip() or (t.condition or '').strip()
    return _cond_category(src) if src else ''

def _stat_bucket_value(t):
    """Valore della colonna `stat_bucket` ('risk:<k>' | 'cond:<k>' | 'na'),
    su cui è categorizzato lo stile QGIS predefinito."""
    group, key = _tree_bucket(t)
    return 'na' if group == 'na' else f'{group}:{key}'

# Attributi scritti in <extensions> di ogni waypoint (nome tag, getter).
# QGIS li legge come campi del layer; l'import li riconosce per nome.
_GPX_EXT_FIELDS = [
    ('custom_id',   lambda t: t.custom_id),
    ('uuid',        lambda t: t.uuid),
    ('city',        lambda t: t.city),
    ('species',     lambda t: t.species if t.species != 'Sconosciuta' else ''),
    ('condition',   lambda t: t.condition if t.condition != '—' else ''),
    ('cpc',         lambda t: t.cpc),
    ('address',     lambda t: t.address),
    ('rischio',     lambda t: _risk_label(_worst_risk(t))),
    ('next_check',  lambda t: t.next_check.strftime('%d/%m/%Y') if t.next_check else ''),
    ('comments',    lambda t: t.comments),
]

@app.route('/export/gpx', methods=['GET'])
@auth_required
def export_gpx():
    """Waypoint GPX 1.1 (WGS84): <name> = ID albero, <cmt> = specie, <desc> =
    riassunto leggibile, più i campi Silvae in <extensions>. Stesso filtro per
    ruolo e stessa selezione `ids` degli altri export."""
    import xml.etree.ElementTree as ET
    trees = [t for t in _export_tree_query().order_by(Tree.custom_id).all()
             if t.latitude is not None and t.longitude is not None]

    NS = 'http://www.topografix.com/GPX/1/1'
    SNS = 'https://silvae.pro/gpx/1'
    ET.register_namespace('', NS)
    ET.register_namespace('silvae', SNS)
    root = ET.Element(f'{{{NS}}}gpx', {
        'version': '1.1', 'creator': 'Silvae Pro',
        'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsi:schemaLocation': f'{NS} http://www.topografix.com/GPX/1/1/gpx.xsd',
    })
    meta = ET.SubElement(root, f'{{{NS}}}metadata')
    ET.SubElement(meta, f'{{{NS}}}name').text = 'Silvae Pro — alberi'
    ET.SubElement(meta, f'{{{NS}}}time').text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    for t in trees:
        wpt = ET.SubElement(root, f'{{{NS}}}wpt', {'lat': f'{t.latitude:.9f}', 'lon': f'{t.longitude:.9f}'})
        ET.SubElement(wpt, f'{{{NS}}}name').text = t.custom_id or ''
        if t.species and t.species != 'Sconosciuta':
            ET.SubElement(wpt, f'{{{NS}}}cmt').text = t.species
        worst = _risk_label(_worst_risk(t))
        desc = ' | '.join(x for x in (
            (t.species if t.species != 'Sconosciuta' else ''),
            (f'Condizione: {t.condition}' if t.condition and t.condition != '—' else ''),
            (f'CPC: {t.cpc}' if t.cpc else ''),
            (f'Rischio: {worst}' if worst else ''),
            t.address or '', t.city or '',
        ) if x)
        if desc:
            ET.SubElement(wpt, f'{{{NS}}}desc').text = desc
        ET.SubElement(wpt, f'{{{NS}}}sym').text = 'Flag, Blue'
        ET.SubElement(wpt, f'{{{NS}}}type').text = 'Albero'
        ext = ET.SubElement(wpt, f'{{{NS}}}extensions')
        for tag, getter in _GPX_EXT_FIELDS:
            v = getter(t)
            if v is not None and str(v).strip():
                ET.SubElement(ext, f'{{{SNS}}}{tag}').text = str(v)

    ET.indent(root)
    buf = io.BytesIO()
    ET.ElementTree(root).write(buf, encoding='utf-8', xml_declaration=True)
    buf.seek(0)
    return send_file(buf, download_name='alberi.gpx', as_attachment=True,
                     mimetype='application/gpx+xml')

# -----------------------
# Report — Schede albero (PLACEHOLDER)
# -----------------------

def _role_tree_query(role, user_id, user_city):
    """Query degli alberi visibili a un utente: i propri per `user`, quelli del
    comune per `city`, tutti tranne la demo per `superuser`."""
    query = Tree.query
    if role == 'user':   query = query.filter(Tree.owner_id == user_id)
    elif role == 'city': query = city_tree_filter(query, user_id, user_city)
    elif role == 'superuser':
        did = _demo_user_id()
        if did and did != user_id: query = query.filter(Tree.owner_id != did)
    return query

def _scoped_tree_query():
    """Query alberi filtrata per ruolo del chiamante e per il parametro `ids`.
    Stessa logica di visibilità/selezione usata dagli export (excel/gpkg)."""
    query = _role_tree_query(*(request.user.get(k) for k in ('role', 'user_id', 'city')))
    ids_param = request.args.get('ids')
    if ids_param:
        id_list = [int(x) for x in ids_param.split(',') if x.strip().isdigit()]
        query = query.filter(Tree.id.in_(id_list))
    return query

def _export_tree_query():
    """Query di export e report: visibilità per ruolo, selezione per `ids` e,
    in più, `city` per prendere **tutti** gli alberi di un comune.

    Serve perché elencare gli id nella URL ha un tetto: la riga di richiesta
    che Gunicorn accetta e' 4094 byte (`--limit-request-line`), cioè circa 660
    id, oltre i quali la richiesta viene rifiutata con 400 prima di arrivare a
    Flask. Con `?city=Bra` la URL resta corta qualunque sia la dimensione del
    comune. Confronto esatto sul nome, come in `/qgis/features`.
    """
    query = _scoped_tree_query()
    city = (request.args.get('city') or '').strip()
    if city:
        query = query.filter(Tree.city == city)
    return query


@app.route('/report/templates', methods=['GET'])
@auth_required
def report_templates_list():
    """Elenco dei template di scheda albero disponibili (per il frontend)."""
    return jsonify(report_tpl.list_templates())


@app.route('/report/scheda', methods=['GET'])
@auth_required
def report_scheda():
    """Genera il report "schede albero" per gli alberi visibili/selezionati.

    Parametri:
      - ids:      selezione opzionale (`1,2,3`); assente = tutti i visibili
      - template: id del template (assente = template di default)

    Il template di default ("scheda_arete") produce l'.xlsx identico al template
    ufficiale ARETE (foglio ORD), compilato coi dati del database — un file per
    albero, oppure uno .zip se gli alberi selezionati sono più d'uno.
    """
    template_id = request.args.get('template')
    template = report_tpl.get_template(template_id)
    if template is None:
        return jsonify({'error': f'Template non trovato: {template_id}'}), 404

    trees = _export_tree_query().all()
    if not trees:
        return jsonify({'error': 'Nessun albero da includere nelle schede'}), 404

    filename, content, mimetype = report_tpl.render_schede(trees, template)

    buf = io.BytesIO(content)
    buf.seek(0)
    return send_file(buf, download_name=filename, as_attachment=True,
                     mimetype=mimetype)


@app.route('/report/map', methods=['GET'])
@auth_required
def report_map():
    """Tavola cartografica (PNG o PDF, A4) degli alberi visibili/selezionati:
    basemap OSM o ortofoto, marker colorati per categoria (rischio ORD, oppure
    condizione VTA, oppure NA — la stessa logica della barra statistiche),
    ID albero come etichetta, perimetro dell'area, legenda, scala e nord.

    Parametri:
      - ids:     selezione opzionale (`1,2,3`); assente = tutti i visibili
      - basemap: `osm` (default) | `satellite`
      - format:  `pdf` (default) | `png`
      - polygon: vertici dell'area selezionata `lat,lon;lat,lon;…` (opzionale)
    """
    basemap = request.args.get('basemap', 'osm')
    fmt = request.args.get('format', 'pdf')
    if basemap not in map_render.BASEMAPS:
        return jsonify({'error': f'Basemap non valida: {basemap}'}), 400
    if fmt not in map_render.FORMATS:
        return jsonify({'error': f'Formato non valido: {fmt}'}), 400

    polygon = []
    for pair in (request.args.get('polygon') or '').split(';'):
        parts = pair.split(',')
        if len(parts) == 2:
            try: polygon.append((float(parts[0]), float(parts[1])))
            except ValueError: pass

    trees = [t for t in _export_tree_query().order_by(Tree.custom_id).all()
             if t.latitude is not None and t.longitude is not None]
    if not trees:
        return jsonify({'error': 'Nessun albero con coordinate da mappare'}), 404

    counts = {}
    points = []
    for t in trees:
        group, key = _tree_bucket(t)
        counts[(group, key)] = counts.get((group, key), 0) + 1
        entry = palette.by_key('risk' if group != 'cond' else 'cond', key)
        points.append({'lat': t.latitude, 'lon': t.longitude,
                       'label': t.custom_id, 'color': entry['main']})

    # Legenda: un gruppo compare solo se ha almeno un albero; dentro un gruppo
    # si stampano tutte le classi, così la scala resta leggibile per intero.
    legend = []
    if any(g == 'risk' for g, _ in counts):
        legend += [{'group': 'Rischio ORD', 'label': e['label'], 'color': e['main'],
                    'count': counts.get(('risk', e['key']), 0)}
                   for e in palette.RISK if e['key'] != 'na']
    if any(g == 'cond' for g, _ in counts):
        legend += [{'group': 'Condizione VTA', 'label': e['label'], 'color': e['main'],
                    'count': counts.get(('cond', e['key']), 0)}
                   for e in palette.CONDITION]
    if counts.get(('na', 'na')):
        e = palette.by_key('risk', 'na')
        legend.append({'group': '', 'label': e['label'], 'color': e['main'],
                       'count': counts[('na', 'na')]})

    cities = sorted({t.city for t in trees if t.city})
    place = cities[0] if len(cities) == 1 else f'{len(cities)} comuni'
    now = datetime.now()
    title = f'Mappa alberi — {place}'
    subtitle = (f'{len(trees)} alberi · {"area selezionata" if polygon else "intera vista"} · '
                f'{map_render.BASEMAPS[basemap]["label"]} · {now.strftime("%d/%m/%Y")}')
    footer = f'Silvae Pro · generato il {now.strftime("%d/%m/%Y %H:%M")} da {request.user.get("username", "")}'

    try:
        content, mimetype = map_render.render(points, polygon or None, basemap, fmt,
                                              title=title, subtitle=subtitle,
                                              legend=legend, footer=footer)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    safe_place = re.sub(r'[^\w-]+', '_', place).strip('_') or 'alberi'
    filename = f'mappa_{safe_place}_{now.strftime("%Y%m%d")}.{fmt}'
    return send_file(io.BytesIO(content), download_name=filename,
                     as_attachment=True, mimetype=mimetype)

# -----------------------
# Import GPKG
# -----------------------

def _gpkg_parse_float(val):
    if val is None:
        return None
    try:
        return float(str(val).replace(',', '.').strip())
    except (ValueError, TypeError):
        return None

def _gpkg_parse_date(val):
    if not val:
        return None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m/%y'):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None

def _gpkg_point(blob):
    """Decode a GeoPackage binary geometry blob and return (lon, lat)."""
    if not blob or len(blob) < 8:
        return None, None
    try:
        if bytes(blob[:2]) != b'GP':
            return None, None
        flags = blob[3]
        env_code = (flags >> 1) & 0x07
        env_size = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(env_code, 0)
        wkb = bytes(blob[8 + env_size:])
        if len(wkb) < 21:
            return None, None
        endian = '<' if wkb[0] == 1 else '>'
        x, y = struct.unpack(f'{endian}dd', wkb[5:21])
        return x, y
    except Exception:
        return None, None

def _reverse_geocode_comune(lat, lon):
    """Return Italian comune name from coordinates via Nominatim (1 call per import)."""
    url = (f'https://nominatim.openstreetmap.org/reverse'
           f'?lat={lat}&lon={lon}&format=json&zoom=10&addressdetails=1&accept-language=it')
    req = urllib.request.Request(url, headers={'User-Agent': 'SilvaePro/1.0 (tree-inventory)'})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
        addr = data.get('address', {})
        return (addr.get('city') or addr.get('town') or
                addr.get('village') or addr.get('municipality') or
                addr.get('county') or '').strip()
    except Exception:
        return ''

# ---------- GPKG import: field-detection helpers ----------

_GPKG_FIELD_CANDIDATES = {
    'custom_id':          ['custom_id', 'name', '_numero', '_name', 'id_albero', 'numero'],
    'uuid':               ['uuid', 'silvae_uuid'],
    'species':            ['species', '_tassonomi', 'specie', 'nome_scientifico', 'taxon', 'cmt'],
    'species_ita':        ['_nome ital', '_nome_ital', 'nome_italiano', 'nome_comune'],
    'condition':          ['condition', 'condizione', '_classe vt', '_classe_vt'],
    'cpc':                ['cpc', '_classe vt', '_classe_vt'],
    'age':                ['age', '_f. fisiol', '_f_fisiol'],
    'address':            ['address', "_localita'", "localita'", '_localita', 'localita', 'indirizzo', 'via'],
    'height':             ['height', '_altezza', 'altezza', 'h_albero'],
    'crown_diameter_m':   ['crown_diameter_m', '_diametro', 'diametro_chioma'],
    'circonferenza_cm':   ['circonferenza_cm', '_circonfer', '_circonferenza', 'circonferenza'],
    'localizzazione':     ['localizzazione'],
    'location':           ['location'],
    'stazione_raw':       ['_stazione', 'stazione'],
    'next_check':         ['next_check', '_da contro', '_da_contro', 'prossima_ispezione', 'data_controllo'],
    'next_check_fb':      ['_rivedere'],
    'longitude':          ['longitude', 'xcoord', 'x', 'lon'],
    'latitude':           ['latitude', 'ycoord', 'y', 'lat'],
    'geom':               ['geom', 'geometry', 'the_geom', 'shape'],
    'dimora':             ['dimora'],
    'stadio_sviluppo':    ['stadio_sviluppo'],
    'posizione_sociale':  ['posizione_sociale'],
    'vincoli':            ['vincoli'],
    'tree_height_m':      ['tree_height_m'],
    'trunk_diameter_cm':  ['trunk_diameter_cm'],
    'branch_diam_cm':     ['branch_diam_cm'],
    'branch_length_m':    ['branch_length_m'],
    'branch_height_m':    ['branch_height_m'],
    'target_height_m':    ['target_height_m'],
    'post_tree_height_m':    ['post_tree_height_m'],
    'post_circonferenza_cm': ['post_circonferenza_cm'],
    'post_branch_diam_cm':   ['post_branch_diam_cm'],
    'post_branch_length_m':  ['post_branch_length_m'],
    'post_branch_height_m':  ['post_branch_height_m'],
    'post_target_height_m':  ['post_target_height_m'],
    'pericolo_rami':      ['pericolo_rami'],
    'pericolo_tronco':    ['pericolo_tronco'],
    'pericolo_colletto':  ['pericolo_colletto'],
    'pericolo_zolla':     ['pericolo_zolla'],
    'bersaglio_chioma_tipo':  ['bersaglio_chioma_tipo'],
    'bersaglio_chioma_value': ['bersaglio_chioma_value'],
    'bersaglio_chioma_flow':  ['bersaglio_chioma_flow'],
    'bersaglio_chioma':       ['bersaglio_chioma'],
    'bersaglio_ramo_tipo':    ['bersaglio_ramo_tipo'],
    'bersaglio_ramo_value':   ['bersaglio_ramo_value'],
    'bersaglio_ramo_flow':    ['bersaglio_ramo_flow'],
    'bersaglio_ramo':         ['bersaglio_ramo'],
    'moltiplicatore':     ['moltiplicatore'],
    'monitoraggio':       ['monitoraggio'],
    'urgenza':            ['urgenza'],
    'comments':           ['comments', 'desc'],
    'actions':            ['actions'],
    'conflitti_list':     ['conflitti'],
    'agenti_carie':       ['agenti_carie'],
    'altri_patogeni':     ['altri_patogeni'],
    'prescrizioni_val':   ['prescrizioni_val'],
    'prescrizioni_mit':   ['prescrizioni_mit'],
    'prescrizioni_col':   ['prescrizioni_col'],
}

def _gpkg_detect_C(cols):
    """Auto-detect field mapping from GPKG column names."""
    lc = {c.lower(): c for c in cols}
    C = {}
    for field, candidates in _GPKG_FIELD_CANDIDATES.items():
        for cand in candidates:
            if cand.lower() in lc:
                C[field] = lc[cand.lower()]
                break
        else:
            C[field] = None
    return C

def _gpkg_user_C(cols, user_mapping):
    """Build field mapping from explicit user config {gpkg_col: silvae_field}."""
    col_set = set(cols)
    C = {f: None for f in _GPKG_FIELD_CANDIDATES}
    for gpkg_col, silvae_field in user_mapping.items():
        if silvae_field and silvae_field in C and gpkg_col in col_set:
            C[silvae_field] = gpkg_col
    return C

def _gpkg_inspect_mapping(cols):
    """Return user-facing auto-mapping for the inspect endpoint: {gpkg_col: silvae_field}."""
    C = _gpkg_detect_C(cols)
    internal = {'stazione_raw', 'next_check_fb', 'geom'}
    result = {}
    for field, gpkg_col in C.items():
        if field in internal or not gpkg_col:
            continue
        if gpkg_col not in result:
            result[gpkg_col] = field
    if C.get('stazione_raw') and C['stazione_raw'] not in result:
        result[C['stazione_raw']] = 'location'
    if C.get('next_check_fb') and C['next_check_fb'] not in result:
        result[C['next_check_fb']] = 'next_check'
    return result

def _set_geom(tree):
    """Write PostGIS geom from lat/lon — silently skipped if PostGIS is unavailable."""
    if not tree.id or not tree.latitude or not tree.longitude:
        return
    try:
        db.session.execute(
            text("UPDATE tree SET geom = ST_SetSRID(ST_MakePoint(:lon,:lat),4326) WHERE id=:id"),
            {'lon': tree.longitude, 'lat': tree.latitude, 'id': tree.id}
        )
    except Exception:
        db.session.rollback()

def _gpkg_read_table(f_or_path):
    """Open a GPKG file object or path, return (cols, rows, table_name) or raise."""
    import_path = None
    try:
        if hasattr(f_or_path, 'read'):
            with tempfile.NamedTemporaryFile(suffix='.gpkg', delete=False) as tmp:
                f_or_path.save(tmp.name)
                import_path = tmp.name
            path = import_path
        else:
            path = f_or_path
        src = sqlite3.connect(path)
        src.row_factory = sqlite3.Row
        cur = src.cursor()
        try:
            cur.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features' LIMIT 1")
            r = cur.fetchone()
            table_name = r[0] if r else None
        except Exception:
            table_name = None
        if not table_name:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'gpkg_%' AND name NOT LIKE 'rtree_%' "
                        "AND name NOT LIKE 'sqlite_%'")
            rows_t = cur.fetchall()
            table_name = rows_t[0][0] if rows_t else None
        if not table_name:
            src.close()
            raise ValueError('Nessuna tabella features trovata nel file GPKG')
        cur.execute(f"PRAGMA table_info('{table_name}')")
        cols = [r[1] for r in cur.fetchall()]
        cur.execute(f"SELECT * FROM '{table_name}'")
        rows = [dict(r) for r in cur.fetchall()]
        src.close()
        return cols, rows, table_name
    finally:
        if import_path:
            try: os.unlink(import_path)
            except Exception: pass

def _import_row_record(row, C):
    """Converte una riga del file (GPKG/GPX) nel dizionario di campi canonici
    di `Tree` atteso da `_upsert_tree`, secondo la mappatura colonne `C`.
    Coordinate: colonne x/y se presenti, altrimenti il blob geometria."""
    def gs(key):
        col = C.get(key)
        if not col: return None
        v = row.get(col)
        return str(v).strip() or None if v is not None else None

    def gf(key):
        col = C.get(key)
        return _gpkg_parse_float(row.get(col)) if col else None

    def gi(key):
        col = C.get(key)
        if not col: return None
        try: return int(str(row.get(col)).strip())
        except: return None

    def gcsvjson(key):
        col = C.get(key)
        return _gpkg_csv_to_json(row.get(col)) if col else None

    rec = {}
    lon, lat = gf('longitude'), gf('latitude')
    if (lon is None or lat is None) and C.get('geom'):
        blob = row.get(C['geom'])
        if blob:
            lon, lat = _gpkg_point(blob)
    if lon is not None and lat is not None:
        rec['latitude'], rec['longitude'] = lat, lon

    rec['custom_id'] = gs('custom_id')
    rec['uuid']      = gs('uuid')
    rec['species']   = gs('species') or gs('species_ita')
    rec['condition'] = gs('condition')

    for key in ('address','height','age','cpc','location',
                'dimora','stadio_sviluppo','posizione_sociale',
                'localizzazione','vincoli',
                'pericolo_rami','pericolo_tronco',
                'pericolo_colletto','pericolo_zolla',
                'bersaglio_chioma_tipo','bersaglio_chioma_value',
                'bersaglio_ramo_tipo','bersaglio_ramo_value',
                'monitoraggio','urgenza','comments','actions'):
        rec[key] = gs(key)
    if rec['cpc'] and rec['cpc'].upper() == 'ABBATTUO':
        rec['cpc'] = 'ABBATTUTO'

    staz = gs('stazione_raw')
    if staz and not rec['localizzazione'] and not rec['location']:
        localiz_vals = [v.lower() for v in dd.localizzazione]
        if staz.lower() in localiz_vals:
            rec['localizzazione'] = staz
        else:
            rec['location'] = staz

    for key in ('tree_height_m','circonferenza_cm','trunk_diameter_cm',
                'crown_diameter_m','branch_diam_cm','branch_length_m',
                'branch_height_m','target_height_m',
                'post_tree_height_m','post_circonferenza_cm',
                'post_branch_diam_cm','post_branch_length_m',
                'post_branch_height_m','post_target_height_m',
                'bersaglio_chioma_flow','bersaglio_ramo_flow'):
        rec[key] = gf(key)

    rec['moltiplicatore'] = gi('moltiplicatore')

    for key in ('conflitti_list','agenti_carie','altri_patogeni',
                'prescrizioni_val','prescrizioni_mit','prescrizioni_col'):
        rec[key] = gcsvjson(key)

    rec['next_check'] = _gpkg_parse_date(gs('next_check')) or _gpkg_parse_date(gs('next_check_fb'))
    return rec

@app.route('/import/gpkg/inspect', methods=['POST'])
@app.route('/import/gpx/inspect', methods=['POST'])
@auth_required
def inspect_gpkg_route():
    f = request.files.get('file')
    if not f:
        return jsonify({'message': 'Nessun file inviato'}), 400
    try:
        cols, rows, _ = _read_import_file(f)
    except Exception as e:
        return jsonify({'message': f'Errore lettura file: {e}'}), 400

    skip = {'fid', 'geom', 'geometry', 'the_geom', 'shape'}
    display_cols = [c for c in cols if c.lower() not in skip]
    sample = {}
    if rows:
        for k in display_cols:
            v = rows[0].get(k)
            if not isinstance(v, (bytes, bytearray)):
                sample[k] = str(v) if v is not None else ''
    return jsonify({
        'columns':      display_cols,
        'auto_mapping': _gpkg_inspect_mapping(cols),
        'sample':       sample,
    })

@app.route('/import/gpkg', methods=['POST'])
@app.route('/import/gpx', methods=['POST'])
@auth_required
def import_gpkg_route():
    if (denied := _city_readonly()): return denied
    user_id   = request.user.get('user_id')
    role      = request.user.get('role')
    user_city = request.user.get('city')

    if 'file' not in request.files:
        return jsonify({'message': 'Nessun file inviato'}), 400

    f           = request.files['file']
    city        = (request.form.get('city') or '').strip()
    on_conflict = request.form.get('on_conflict', 'skip')

    if not city:
        if role in ('user', 'city') and user_city:
            city = user_city
        # else: city will be auto-detected from coordinates after parsing the file

    if not f.filename:
        return jsonify({'message': 'Nessun file selezionato'}), 400

    try:
        cols, rows, _ = _read_import_file(f)
    except Exception as e:
        return jsonify({'message': f'Errore lettura file: {e}'}), 400

    # --- Column detection ------------------------------------------------
    mapping_json = request.form.get('mapping')
    if mapping_json:
        try:
            C = _gpkg_user_C(cols, json.loads(mapping_json))
        except (ValueError, TypeError):
            return jsonify({'message': 'Mapping JSON non valido'}), 400
    else:
        C = _gpkg_detect_C(cols)

    # --- Auto-detect comune from first valid coordinate if city not provided ---
    city_autodetected = False
    if not city:
        for row in rows:
            lat = lon = None
            if C['latitude'] and C['longitude']:
                lat = _gpkg_parse_float(row.get(C['latitude']))
                lon = _gpkg_parse_float(row.get(C['longitude']))
            if (lat is None or lon is None) and C['geom']:
                blob = row.get(C['geom'])
                if blob:
                    lon, lat = _gpkg_point(blob)
            if lat is not None and lon is not None:
                city = _reverse_geocode_comune(lat, lon)
                city_autodetected = bool(city)
                break
        if not city:
            return jsonify({'message': 'Comune non rilevabile dalle coordinate. Inseriscilo manualmente.'}), 400

    # --- Main loop ---------------------------------------------------------
    scope = _role_tree_query(role, user_id, user_city)
    counts = {'created': 0, 'updated': 0, 'unchanged': 0, 'skipped': 0}
    errors = 0
    error_details = []

    for row in rows:
        record = _import_row_record(row, C)
        if not record.get('custom_id'):
            counts['skipped'] += 1
            continue
        try:
            outcome, _, _ = _upsert_tree(record, city=city, on_conflict=on_conflict,
                                         user_id=user_id, scope=scope, strict_uuid=False)
            db.session.commit()
            counts[outcome] += 1
        except Exception as e:
            db.session.rollback()
            errors += 1
            error_details.append(f"fid={row.get('fid','?')} id={record.get('custom_id')}: {e}")

    # `inserted` conta, come prima, le righe scritte o già allineate.
    inserted = counts['created'] + counts['updated'] + counts['unchanged']
    skipped  = counts['skipped']
    return jsonify({'inserted': inserted, 'skipped': skipped, 'errors': errors,
                    **counts,
                    'total': len(rows), 'city': city, 'city_autodetected': city_autodetected,
                    'error_details': error_details})

# -----------------------
# QGIS — layer GeoJSON per il plugin (qgis.md §6.1)
# -----------------------
QGIS_SCHEMA_VERSION = 1

def _qgis_stat_label(group, key):
    if group == 'na': return 'Non valutato'
    e = palette.by_key(group, key)
    return e['label'] if e else ''

def _qgis_properties(t, owners):
    """Attributi piatti di un albero per QGIS: i campi di tree_to_dict con le
    liste come stringhe separate da virgola, le diagnosi come testo, il JSON
    del rischio esploso in colonne di sola lettura e la casella della barra
    statistiche (`stat_bucket`) su cui è categorizzato lo stile."""
    d = tree_to_dict(t)
    props = {}
    for k, v in d.items():
        if k in ('rischio', 'owner_id'):
            continue
        if k.startswith('diag_'):
            props[k] = '; '.join(f"{x.get('caratt', '')}: {x.get('giudizio', '')}"
                                 for x in (v or []) if isinstance(x, dict))
        elif isinstance(v, list):
            props[k] = ', '.join(str(x) for x in v)
        else:
            props[k] = v
    props['owner'] = owners.get(t.owner_id, '')

    group, key = _tree_bucket(t)
    props['stat_bucket'] = 'na' if group == 'na' else f'{group}:{key}'
    props['stat_label']  = _qgis_stat_label(group, key)
    props['cond_classe'] = _cond_key(t)
    props['cond_label']  = _qgis_stat_label('cond', props['cond_classe']) if props['cond_classe'] else ''

    r = d.get('rischio') or {}
    att, res = r.get('attuale') or {}, r.get('residuo') or {}
    props['rischio_classe'] = _worst_risk_of(att)
    props['rischio_label']  = _risk_label(props['rischio_classe'])
    for part in _RISK_PARTS:
        props[f'rischio_{part}'] = _risk_category((att.get(part) or {}).get('risk_description')) or ''
    props['rischio_residuo_classe'] = _worst_risk_of(res)
    props['rischio_json'] = json.dumps(r, ensure_ascii=False) if r else ''
    return props

@app.route('/qgis/style.qml', methods=['GET'])
def qgis_style_qml():
    """Stile QGIS categorizzato generato da tools/palette.py.
    `?by=stat|rischio|condizione` (default stat), `?field=` per una colonna
    rinominata, `?labels=0` senza etichette. Pubblico come /palette.css."""
    by = request.args.get('by', qgis_style.DEFAULT_STYLE)
    if by not in qgis_style.STYLES:
        return jsonify({'message': f'by deve essere uno di: {", ".join(qgis_style.STYLES)}'}), 400
    field = _san_gpkg_ident(request.args.get('field') or '') or None
    labels = request.args.get('labels', '1') not in ('0', 'false', 'no')
    body = qgis_style.qml(by, field=field, labels=labels)
    resp = app.response_class(body, mimetype='application/xml')
    resp.headers['Content-Disposition'] = f'attachment; filename="silvae_{by}.qml"'
    return resp

@app.route('/qgis/features', methods=['GET'])
@auth_required
def qgis_features():
    """FeatureCollection GeoJSON (WGS84) degli alberi visibili al chiamante.
    Parametri: `city` (obbligatorio salvo `ids`), `ids=1,2,3`,
    `since=<ISO 8601>` (solo alberi con updated_at successivo: pull
    incrementale), `bbox=minlon,minlat,maxlon,maxlat`."""
    city  = (request.args.get('city') or '').strip()
    since = (request.args.get('since') or '').strip()
    bbox  = (request.args.get('bbox') or '').strip()

    # Ritiro di un invio dalla cassetta postale: gli id sono quelli depositati,
    # i dati sono sempre quelli correnti.
    delivery = None
    delivery_param = request.args.get('delivery')
    if delivery_param:
        try:
            delivery = db.session.get(QgisDelivery, int(delivery_param))
        except (TypeError, ValueError):
            delivery = None
        if not delivery or delivery.user_id != request.user['user_id']:
            return jsonify({'message': 'Invio non trovato'}), 404
        city = city or (delivery.city or '')
    elif not city and not request.args.get('ids'):
        return jsonify({'message': 'Indicare il comune (city) oppure gli id (ids)'}), 400

    # Timestamp PRIMA della query: il prossimo pull con since=generated_at
    # non deve perdere un albero modificato mentre questa risposta si forma.
    generated_at = datetime.now(timezone.utc).isoformat()
    q = _scoped_tree_query()
    if delivery:
        q = q.filter(Tree.id.in_(json.loads(delivery.tree_ids)))
    elif city:
        q = q.filter(Tree.city == city)
    if since:
        dt = _parse_iso_dt(since)
        if dt is None:
            return jsonify({'message': 'since non valido: usare ISO 8601'}), 400
        q = q.filter(Tree.updated_at > dt)
    if bbox:
        try:
            minlon, minlat, maxlon, maxlat = (float(x) for x in bbox.split(','))
        except ValueError:
            return jsonify({'message': 'bbox non valido: minlon,minlat,maxlon,maxlat'}), 400
        q = q.filter(Tree.longitude.between(minlon, maxlon), Tree.latitude.between(minlat, maxlat))

    trees = q.order_by(Tree.id).all()
    owner_ids = {t.owner_id for t in trees if t.owner_id}
    owners = {u.id: u.username for u in User.query.filter(User.id.in_(owner_ids)).all()} if owner_ids else {}
    features = []
    for t in trees:
        geom = ({'type': 'Point', 'coordinates': [t.longitude, t.latitude]}
                if t.latitude is not None and t.longitude is not None else None)
        features.append({'type': 'Feature', 'id': t.id, 'geometry': geom,
                         'properties': _qgis_properties(t, owners)})
    info = {'schema': QGIS_SCHEMA_VERSION, 'city': city or None,
            'count': len(features), 'generated_at': generated_at}
    if delivery:
        delivery.fetched_at = datetime.now(timezone.utc)
        db.session.commit()
        info['delivery'] = delivery.to_dict()
    body = {'type': 'FeatureCollection', 'features': features, 'silvae': info}
    # json.dumps e non jsonify: l'ordine dei campi (id, uuid, custom_id, …)
    # è quello che QGIS mostra nella tabella attributi.
    resp = app.response_class(json.dumps(body, ensure_ascii=False), mimetype='application/geo+json')
    resp.headers['X-Silvae-Schema'] = str(QGIS_SCHEMA_VERSION)
    return resp

QGIS_PUSH_MAX_FEATURES = 2000
# Campi derivati che il push può *leggere* (servono all'abbinamento o al
# controllo dei conflitti) e che quindi non vanno segnalati come ignorati.
_PUSH_READ_ONLY_USED = {'uuid', 'updated_at'}

def _qgis_push_record(props, mapping, geometry):
    """Proprietà di una feature → record canonico per `_upsert_tree`.

    Riusa la conversione dell'import da file (`_import_row_record`), così i
    numeri, le date e le liste separate da virgola si comportano allo stesso
    modo da qualunque parte arrivino. La **geometria vince** sulle colonne
    latitude/longitude, che in un layer QGIS restano quelle dell'ultimo
    scaricamento se si sposta il punto."""
    cols = list(props.keys())
    C = _gpkg_user_C(cols, mapping)
    record = _import_row_record(props, C)
    if geometry and geometry.get('type') == 'Point':
        coords = geometry.get('coordinates') or []
        if len(coords) >= 2:
            record['longitude'], record['latitude'] = float(coords[0]), float(coords[1])
    return record

def _qgis_push_mapping(props, user_mapping):
    """Mappatura colonna→campo per una feature: quella indicata dall'utente,
    completata dall'auto-mappatura per le colonne rimaste fuori."""
    auto = _gpkg_inspect_mapping(list(props.keys()))
    if not user_mapping:
        return auto
    mapping = dict(auto)
    mapping.update({k: v for k, v in user_mapping.items() if v})
    for col, field in user_mapping.items():        # '' = «non importare»
        if not field:
            mapping.pop(col, None)
    return mapping

@app.route('/qgis/mapping', methods=['POST'])
@auth_required
def qgis_mapping():
    """Mappatura proposta per le colonne di un layer QGIS (stessa
    auto-mappatura dell'import da file) più l'elenco dei campi scrivibili,
    per la finestra di mappatura del plugin."""
    cols = (request.json or {}).get('columns') or []
    if not isinstance(cols, list):
        return jsonify({'message': 'columns deve essere una lista di nomi di colonna'}), 400
    cols = [str(c) for c in cols]
    fields = [f for f in _GPKG_FIELD_CANDIDATES
              if f not in ('geom', 'stazione_raw', 'next_check_fb')
              and f not in _DERIVED_TREE_FIELDS or f == 'uuid']
    return jsonify({'mapping': _gpkg_inspect_mapping(cols),
                    'fields': sorted(set(fields)),
                    'derived': sorted(_DERIVED_TREE_FIELDS)})

@app.route('/qgis/features', methods=['POST'])
@auth_required
def qgis_push_features():
    """Scrittura da QGIS: FeatureCollection GeoJSON in ingresso.

    Body: {type: FeatureCollection, features: [...], city, on_conflict:
    'update'|'skip', mapping: {colonna: campo}, dry_run: bool, force: bool}.

    Ogni feature passa per la stessa logica della webapp (`_upsert_tree`):
    ricalcolo di bersaglio, valore ecologico e rischio, campi derivati
    ignorati, owner mai cambiato, abbinamento solo tra gli alberi visibili.
    Ogni albero modificato conserva lo **snapshot precedente** in una
    `Inspection` (qgis.md §6.2 punto 5). Con `dry_run` non scrive nulla ed è
    l'anteprima del diff."""
    if (denied := _city_readonly()): return denied
    data = request.json or {}
    feats = data.get('features')
    if not isinstance(feats, list) or not feats:
        return jsonify({'message': 'Nessuna feature da inviare'}), 400
    if len(feats) > QGIS_PUSH_MAX_FEATURES:
        return jsonify({'message': f'Troppe feature in una sola chiamata '
                                   f'(massimo {QGIS_PUSH_MAX_FEATURES}); invia a blocchi'}), 413
    city = (data.get('city') or '').strip()
    if not city:
        return jsonify({'message': 'Indicare il comune (city)'}), 400
    on_conflict = data.get('on_conflict', 'update')
    dry_run = bool(data.get('dry_run'))
    force   = bool(data.get('force'))
    user_mapping = data.get('mapping') or {}
    if not isinstance(user_mapping, dict):
        return jsonify({'message': 'mapping deve essere un oggetto {colonna: campo}'}), 400

    role, user_id, user_city = (request.user.get(k) for k in ('role', 'user_id', 'city'))
    username = request.user.get('username')
    scope = _role_tree_query(role, user_id, user_city)

    out = {'created': [], 'updated': [], 'unchanged': [], 'skipped': [],
           'conflicts': [], 'errors': []}
    ignored = set()
    inspections = []
    pending = []          # (entry della risposta, albero) da completare dopo il flush

    for i, feat in enumerate(feats):
        props = (feat or {}).get('properties') or {}
        try:
            mapping = _qgis_push_mapping(props, user_mapping)
            for col, field in mapping.items():
                if field in _DERIVED_TREE_FIELDS and field not in _PUSH_READ_ONLY_USED:
                    ignored.add(field)
            record = _qgis_push_record(props, mapping, (feat or {}).get('geometry'))
            existing = _match_tree(record, city, scope, strict_uuid=True)

            # Conflitto: la feature dice fin dove QGIS era allineato —
            # `updated_at` (la versione ricevuta al pull) e `silvae_synced_at`
            # (l'ultimo invio riuscito, scritto dal plugin). Vale il più
            # recente dei due: dopo un invio il layer è allineato anche se il
            # suo `updated_at` è rimasto indietro. Se il server è ancora più
            # avanti, qualcun altro ha modificato nel frattempo.
            if existing is not None and not force:
                seen = max(filter(None, (_parse_iso_dt(props.get('updated_at')),
                                         _parse_iso_dt(props.get('silvae_synced_at')))),
                           default=None)
                server = _as_utc(existing.updated_at)
                if seen and server and server > seen:
                    out['conflicts'].append({
                        'src': i, 'id': existing.id, 'uuid': existing.uuid,
                        'custom_id': existing.custom_id,
                        'server_updated_at': server.isoformat(),
                        'server_updated_by': existing.updated_by,
                        'seen_updated_at': seen.isoformat()})
                    continue

            before = tree_to_dict(existing) if existing is not None else None
            outcome, tree, changed = _upsert_tree(
                record, city=city, on_conflict=on_conflict, user_id=user_id,
                scope=scope, existing=existing)

            # `uuid` e `id` di un albero nuovo esistono solo dopo il flush:
            # l'entry viene completata più sotto.
            entry = {'src': i, 'uuid': tree.uuid, 'custom_id': tree.custom_id}
            pending.append((entry, tree))
            if outcome == 'skipped':
                entry['id'] = tree.id
                entry['reason'] = 'albero già presente (on_conflict=skip)'
            elif outcome == 'created':
                inspections.append((tree, None, []))
            elif outcome == 'updated':
                entry['id'] = tree.id
                entry['changed'] = changed
                inspections.append((tree, before, changed))
            else:                                   # unchanged
                entry['id'] = tree.id
            out[outcome].append(entry)
        except ValueError as e:
            out['errors'].append({'src': i, 'message': str(e)})
        except Exception as e:                      # riga malformata: non blocca le altre
            out['errors'].append({'src': i, 'message': f'{type(e).__name__}: {e}'})

    if dry_run:
        db.session.rollback()
    else:
        db.session.flush()                          # assegna id e uuid ai nuovi alberi
        for tree, before, changed in inspections:
            db.session.add(_qgis_inspection(tree, before, changed, user_id, username))
        db.session.commit()
        for entry, tree in pending:                 # id/uuid definitivi
            entry['id'], entry['uuid'] = tree.id, tree.uuid

    out['ignored_fields'] = sorted(ignored)
    out['dry_run'] = dry_run
    out['counts'] = {k: len(out[k]) for k in
                     ('created', 'updated', 'unchanged', 'skipped', 'conflicts', 'errors')}
    return jsonify(out), 200

def _qgis_inspection(tree, before, changed, user_id, username):
    """Ispezione che documenta una scrittura da QGIS. Per un albero esistente
    conserva lo `snapshot` **precedente** alla modifica (è l'annulla per
    albero, qgis.md §13); per un albero nuovo è l'ispezione iniziale, come in
    `add_tree`."""
    if before is None:
        return _make_inspection(tree, user_id, username)
    insp = _make_inspection(tree, user_id, username)
    insp.snapshot = json.dumps(before)
    insp.condition = before.get('condition')
    insp.comments = ('Sincronizzazione da QGIS — campi modificati: '
                     + (', '.join(changed) if changed else 'nessuno'))[:2000]
    insp.actions = ''
    return insp

def _as_utc(dt):
    """datetime con fuso (SQLite lo perde) o None."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def _parse_iso_dt(value):
    """Stringa ISO 8601 → datetime UTC, o None se vuota/non valida.

    Tollera il `+` del fuso diventato uno spazio: in una query string un `+`
    non codificato si decodifica come spazio, quindi l'`updated_at` che
    abbiamo restituito noi («…T09:12:33+00:00») torna come «…T09:12:33 00:00»
    e `fromisoformat` lo rifiuterebbe. Si ritenta solo dopo il primo
    fallimento, sostituendo l'ultimo spazio: le stringhe già valide — compreso
    il separatore data/ora scritto a spazio — non vengono toccate.
    """
    if not value:
        return None
    s = str(value).strip().replace('Z', '+00:00')
    tentativi = [s]
    if ' ' in s:
        testa, _, coda = s.rpartition(' ')
        tentativi.append(f'{testa}+{coda}')
    for t in tentativi:
        try:
            return _as_utc(datetime.fromisoformat(t))
        except ValueError:
            continue
    return None

def _purge_expired_deliveries():
    """Cancella gli invii scaduti (nessuno scheduler: si fa alla prima
    chiamata utile). Ritorna il numero di righe rimosse."""
    n = (QgisDelivery.query
         .filter(QgisDelivery.expires_at.isnot(None),
                 QgisDelivery.expires_at < datetime.now(timezone.utc))
         .delete(synchronize_session=False))
    if n:
        db.session.commit()
    return n

@app.route('/qgis/deliveries', methods=['POST'])
@auth_required
def qgis_delivery_create():
    """«Invia a QGIS» dalla webapp: deposita un invio per l'utente corrente.
    Body: {city, ids: [...], polygon: [[lat, lon], …] opzionale, title opzionale}.
    Gli id vengono filtrati con la visibilità del chiamante."""
    if request.user.get('auth') == 'api_token':
        return jsonify({'message': 'Gli invii si creano dalla webapp, non dal plugin.'}), 403
    data = request.json or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'message': 'Nessun albero da inviare'}), 400
    if len(ids) > DELIVERY_MAX_TREES:
        return jsonify({'message': f'Troppi alberi in un solo invio (massimo {DELIVERY_MAX_TREES})'}), 400
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify({'message': 'Lista di id non valida'}), 400

    role, user_id, user_city = (request.user.get(k) for k in ('role', 'user_id', 'city'))
    visible = [t.id for t in _role_tree_query(role, user_id, user_city)
               .filter(Tree.id.in_(ids)).all()]
    if not visible:
        return jsonify({'message': 'Nessuno degli alberi indicati è visibile al tuo account'}), 404

    polygon = data.get('polygon') or None
    if polygon is not None:
        try:
            polygon = [[float(p[0]), float(p[1])] for p in polygon]
        except (TypeError, ValueError, IndexError):
            return jsonify({'message': 'Poligono non valido'}), 400

    city = (data.get('city') or '').strip() or None
    if not city:
        cities = {t.city for t in Tree.query.filter(Tree.id.in_(visible)).all()}
        city = cities.pop() if len(cities) == 1 else None
    title = (data.get('title') or '').strip() or (
        f"{city or 'Alberi'} — {len(visible)} alber{'o' if len(visible) == 1 else 'i'}"
        f" del {datetime.now(timezone.utc).strftime('%d/%m')}")

    now = datetime.now(timezone.utc)
    d = QgisDelivery(user_id=user_id, city=city, title=title[:160],
                     tree_ids=json.dumps(visible), count=len(visible),
                     polygon=json.dumps(polygon) if polygon else None,
                     created_at=now, expires_at=now + timedelta(days=DELIVERY_TTL_DAYS))
    db.session.add(d)
    db.session.commit()
    _purge_expired_deliveries()
    return jsonify({**d.to_dict(), 'requested': len(ids)}), 201

@app.route('/qgis/deliveries', methods=['GET'])
@auth_required
def qgis_delivery_list():
    """Invii in attesa dell'utente (i non ritirati per primi). `?all=1` include
    anche quelli già ritirati."""
    _purge_expired_deliveries()
    q = QgisDelivery.query.filter_by(user_id=request.user['user_id'])
    if request.args.get('all') not in ('1', 'true', 'yes'):
        q = q.filter(QgisDelivery.fetched_at.is_(None))
    rows = q.order_by(QgisDelivery.fetched_at.isnot(None), QgisDelivery.created_at.desc()).all()
    return jsonify([d.to_dict() for d in rows])

@app.route('/qgis/deliveries/<int:delivery_id>', methods=['DELETE'])
@auth_required
def qgis_delivery_delete(delivery_id):
    d = db.session.get(QgisDelivery, delivery_id)
    if not d or d.user_id != request.user['user_id']:
        return jsonify({'message': 'Invio non trovato'}), 404
    db.session.delete(d)
    db.session.commit()
    return jsonify({'message': 'Invio eliminato'})

# -----------------------
# Voice intent (Groq NLU fallback)
# -----------------------
GROQ_SYSTEM = """Sei un assistente per un'app di censimento alberi urbani.
Estrai intent e parametri dalla frase italiana dell'utente.
Intent possibili:
  OPEN_TREE       params: { customId }
  EDIT_TREE       params: { customId }
  OPEN_HISTORY    params: { customId }
  LOCATE_TREE     params: { customId }
  NEARBY_RADIUS   params: { radius }   (radius in metres, integer)
  NEARBY_TOGGLE   params: {}
  FILTER_ADDRESS   params: { address }  (street name or locality to search, e.g. "Pollenzo" or "via Roma")
  FILTER_CONDITION params: { label }   (Ottimo|Buono|Discreto|Scarso|Critico|Morto)
  RESET_FILTERS   params: {}
  ADD_TREE        params: {}
  SWITCH_MAP      params: {}
  SWITCH_LIST     params: {}
  COUNT_TREES     params: {}
Rispondi SOLO con JSON valido: {"intent":"...","params":{...}}
Se non riesci a determinare l'intent rispondi: {"intent":null,"params":{}}"""

@app.route('/api/voice_intent', methods=['POST'])
@auth_required
def voice_intent():
    data = request.get_json()
    transcript = (data or {}).get('transcript', '').strip()
    if not transcript:
        return jsonify({'intent': None, 'params': {}}), 200

    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return jsonify({'error': 'GROQ_API_KEY not set'}), 503

    try:
        client = GroqClient(api_key=api_key)
        resp = client.chat.completions.create(
            model='llama-3.1-8b-instant',
            messages=[
                {'role': 'system', 'content': GROQ_SYSTEM},
                {'role': 'user',   'content': transcript},
            ],
            temperature=0,
            max_tokens=80,
        )
        raw = resp.choices[0].message.content.strip()
        result = json.loads(raw)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# -----------------------
# Frontend static serving
# -----------------------
# Tavolozza colori (tools/palette.py) come variabili CSS: caricata da index.html
# prima di style.css, quindi senza autenticazione.
@app.route('/palette.css')
def palette_css():
    resp = app.response_class(palette.css_vars(), mimetype='text/css')
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

@app.route('/palette', methods=['GET'])
def palette_json():
    return jsonify(palette.as_dict())

@app.route('/')
def serve_index():
    return send_from_directory('frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('frontend', path)

# -----------------------
# Bootstrap
# -----------------------
with app.app_context():
    if not User.query.filter_by(role='superuser').first():
        su = User(username='admin', role='superuser', city=None)
        su.set_password('admin')
        db.session.add(su); db.session.commit()
        print("Created default superuser: admin / admin")
    # Ensure the demo accounts exist and start from a clean demo state.
    try:
        reset_demo()
        print(f"Demo accounts ready: {DEMO_USERNAME} / {DEMO_PASSWORD}"
              f"  |  {DEMO_CITY_USERNAME} / {DEMO_CITY_PASSWORD}")
    except Exception as e:
        print(f"[DEMO] Seeding skipped: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

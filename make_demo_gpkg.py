#!/usr/bin/env python3
"""Generate demo.gpkg with 100 synthetic trees in Turin."""
import sqlite3, struct, random, os

random.seed(42)

SPECIES = [
    "Platanus × acerifolia", "Tilia cordata", "Acer platanoides",
    "Quercus robur", "Pinus sylvestris", "Robinia pseudoacacia",
    "Aesculus hippocastanum", "Fraxinus excelsior", "Ulmus minor",
    "Celtis australis", "Sophora japonica", "Ginkgo biloba",
    "Cercis siliquastrum", "Catalpa bignonioides", "Liriodendron tulipifera",
    "Liquidambar styraciflua", "Prunus avium", "Betula pendula",
]

CONDITIONS = ["Good", "Good", "Good", "Fair", "Fair", "Poor", "Excellent", "Critical"]

STREETS = [
    "Corso Vittorio Emanuele II", "Via Roma", "Corso Re Umberto",
    "Via Po", "Corso Francia", "Via Garibaldi", "Corso Cairoli",
    "Via Nizza", "Corso Massimo d'Azeglio", "Via Sacchi",
    "Corso Giulio Cesare", "Via Bertola", "Corso Vinzaglio",
    "Via Lagrange", "Corso Duca degli Abruzzi", "Via Cernaia",
    "Corso Matteotti", "Via della Rocca", "Corso Moncalieri",
]

DIMORA = ["Parco", "Viale alberato", "Piazza", "Giardino scolastico", "Area verde"]
STADIO = ["Giovane", "Maturo", "Adulto", "Senescente"]
POSIZ  = ["Dominante", "Codominante", "Dominato", "Oppresso"]
LOCALI = ["Parco urbano", "Strada", "Piazza", "Cortile", "Area verde privata"]
MONIT  = ["Annuale", "Biennale", "Straordinario"]
URGENZ = ["Bassa", "Media", "Alta", "Nessuna"]
PERIC  = ["A", "B", "C", "D"]

# Turin bounding box: lat 45.01–45.12, lon 7.60–7.78
def rand_coords():
    lat = round(random.uniform(45.01, 45.12), 6)
    lon = round(random.uniform(7.60,  7.78),  6)
    return lat, lon

def make_point(lon, lat):
    # GeoPackage geometry binary: GP magic + flags + srs_id + WKB point
    return b'GP\x00\x01' + struct.pack('<i', 4326) + struct.pack('<BIdd', 1, 1, lon, lat)

NEXT_CHECKS = [
    "2025-03-15", "2025-06-01", "2025-09-20", "2026-01-10",
    "2026-04-05", "2026-07-30", "2026-11-15", "2027-02-28",
]

trees = []
for i in range(1, 101):
    lat, lon = rand_coords()
    species   = random.choice(SPECIES)
    condition = random.choice(CONDITIONS)
    street    = random.choice(STREETS)
    num       = random.randint(1, 200)
    address   = f"{street} {num}"
    h_m       = round(random.uniform(4.0, 22.0), 1)
    circ      = round(random.uniform(30.0, 280.0), 1)
    trunk_d   = round(circ / 3.14159, 1)
    crown_d   = round(random.uniform(2.0, 14.0), 1)
    age       = str(random.randint(5, 120))
    trees.append({
        'id':                    i,
        'custom_id':             f"TO-{i:04d}",
        'city':                  'Torino',
        'address':               address,
        'latitude':              lat,
        'longitude':             lon,
        'species':               species,
        'condition':             condition,
        'age':                   age,
        'cpc':                   '',
        'location':              '',
        'height':                f"{h_m} m",
        'dimora':                random.choice(DIMORA),
        'stadio_sviluppo':       random.choice(STADIO),
        'posizione_sociale':     random.choice(POSIZ),
        'localizzazione':        random.choice(LOCALI),
        'vincoli':               '',
        'tree_height_m':         h_m,
        'circonferenza_cm':      circ,
        'trunk_diameter_cm':     trunk_d,
        'crown_diameter_m':      crown_d,
        'branch_diam_cm':        round(random.uniform(2.0, 20.0), 1),
        'branch_length_m':       round(random.uniform(1.0, 8.0), 1),
        'branch_height_m':       round(random.uniform(2.0, 10.0), 1),
        'target_height_m':       round(h_m * random.uniform(0.6, 0.9), 1),
        'post_tree_height_m':    None,
        'post_circonferenza_cm': None,
        'post_branch_diam_cm':   None,
        'post_branch_length_m':  None,
        'post_branch_height_m':  None,
        'post_target_height_m':  None,
        'pericolo_rami':         random.choice(PERIC),
        'pericolo_tronco':       random.choice(PERIC),
        'pericolo_colletto':     random.choice(PERIC),
        'pericolo_zolla':        random.choice(PERIC),
        'bersaglio_chioma_tipo': '',
        'bersaglio_chioma_value':'',
        'bersaglio_chioma_flow': None,
        'bersaglio_chioma':      None,
        'bersaglio_ramo_tipo':   '',
        'bersaglio_ramo_value':  '',
        'bersaglio_ramo_flow':   None,
        'bersaglio_ramo':        None,
        'moltiplicatore':        None,
        'monitoraggio':          random.choice(MONIT),
        'urgenza':               random.choice(URGENZ),
        'next_check':            random.choice(NEXT_CHECKS),
        'comments':              f"Albero n.{i} — rilievo demo Torino.",
        'actions':               '',
        'conflitti':             '',
        'agenti_carie':          '',
        'altri_patogeni':        '',
        'prescrizioni_val':      '',
        'prescrizioni_mit':      '',
        'prescrizioni_col':      '',
    })

OUT = os.path.join(os.path.dirname(__file__), 'demo.gpkg')
if os.path.exists(OUT):
    os.unlink(OUT)

conn = sqlite3.connect(OUT)
cur  = conn.cursor()
cur.execute('PRAGMA application_id = 1196444487')
cur.execute('PRAGMA user_version   = 10200')
conn.commit()

cur.executescript("""
    CREATE TABLE gpkg_spatial_ref_sys (
        srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY,
        organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
        definition TEXT NOT NULL, description TEXT
    );
    INSERT INTO gpkg_spatial_ref_sys VALUES
        ('Undefined cartesian SRS', -1, 'NONE', -1, 'undefined', NULL),
        ('Undefined geographic SRS',  0, 'NONE',  0, 'undefined', NULL),
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
        id INTEGER, custom_id TEXT, city TEXT, address TEXT,
        latitude REAL, longitude REAL, species TEXT, condition TEXT,
        age TEXT, cpc TEXT, location TEXT, height TEXT,
        dimora TEXT, stadio_sviluppo TEXT, posizione_sociale TEXT,
        localizzazione TEXT, vincoli TEXT,
        tree_height_m REAL, circonferenza_cm REAL, trunk_diameter_cm REAL,
        crown_diameter_m REAL, branch_diam_cm REAL, branch_length_m REAL,
        branch_height_m REAL, target_height_m REAL,
        post_tree_height_m REAL, post_circonferenza_cm REAL,
        post_branch_diam_cm REAL, post_branch_length_m REAL,
        post_branch_height_m REAL, post_target_height_m REAL,
        pericolo_rami TEXT, pericolo_tronco TEXT,
        pericolo_colletto TEXT, pericolo_zolla TEXT,
        bersaglio_chioma_tipo TEXT, bersaglio_chioma_value TEXT,
        bersaglio_chioma_flow REAL, bersaglio_chioma INTEGER,
        bersaglio_ramo_tipo TEXT, bersaglio_ramo_value TEXT,
        bersaglio_ramo_flow REAL, bersaglio_ramo INTEGER,
        moltiplicatore INTEGER, monitoraggio TEXT, urgenza TEXT,
        next_check TEXT, comments TEXT, actions TEXT,
        conflitti TEXT, agenti_carie TEXT, altri_patogeni TEXT,
        prescrizioni_val TEXT, prescrizioni_mit TEXT, prescrizioni_col TEXT
    );
""")

lats = [t['latitude']  for t in trees]
lons = [t['longitude'] for t in trees]
cur.execute(
    "INSERT INTO gpkg_contents (table_name,data_type,identifier,srs_id,min_x,min_y,max_x,max_y) "
    "VALUES ('alberi','features','alberi',4326,?,?,?,?)",
    (min(lons), min(lats), max(lons), max(lats))
)
cur.execute("INSERT INTO gpkg_geometry_columns VALUES ('alberi','geom','POINT',4326,0,0)")

COLS = [
    'id','custom_id','city','address','latitude','longitude','species','condition',
    'age','cpc','location','height','dimora','stadio_sviluppo','posizione_sociale',
    'localizzazione','vincoli','tree_height_m','circonferenza_cm','trunk_diameter_cm',
    'crown_diameter_m','branch_diam_cm','branch_length_m','branch_height_m','target_height_m',
    'post_tree_height_m','post_circonferenza_cm','post_branch_diam_cm','post_branch_length_m',
    'post_branch_height_m','post_target_height_m',
    'pericolo_rami','pericolo_tronco','pericolo_colletto','pericolo_zolla',
    'bersaglio_chioma_tipo','bersaglio_chioma_value','bersaglio_chioma_flow','bersaglio_chioma',
    'bersaglio_ramo_tipo','bersaglio_ramo_value','bersaglio_ramo_flow','bersaglio_ramo',
    'moltiplicatore','monitoraggio','urgenza','next_check','comments','actions',
    'conflitti','agenti_carie','altri_patogeni','prescrizioni_val','prescrizioni_mit','prescrizioni_col',
]

INSERT = f"INSERT INTO alberi (geom, {', '.join(COLS)}) VALUES (?, {', '.join(['?']*len(COLS))})"
for t in trees:
    cur.execute(INSERT, [make_point(t['longitude'], t['latitude'])] + [t[c] for c in COLS])

conn.commit()
conn.close()

size_kb = os.path.getsize(OUT) // 1024
print(f"Created {OUT} — {len(trees)} trees — {size_kb} KB")

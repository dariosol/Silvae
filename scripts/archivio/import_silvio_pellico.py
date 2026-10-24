#!/usr/bin/env python3

# ============================================================================
# NON ESEGUIRE. Superato dal tab «Importa» della webapp (POST /import/gpkg).
#
# L'import e' gia' stato fatto: gli alberi sono in produzione. OWNER_ID = 29
# punta a un utente che non esiste (gli id vanno da 1 a 8), quindi lo script
# fallirebbe comunque con un errore di chiave esterna; il docstring dice
# «id=4», in contraddizione con il codice.
#
# Tenuto perche' questo file aveva una struttura tutta sua (tabella `pellico`,
# colonna LOCALITA' senza underscore, _name invece di name): se quei dati
# tornassero a dare grane, qui c'e' la mappatura che era servita.
# ============================================================================

"""
Import trees from file_da_importare/silvio pellico.gpkg into trees_db.
Assigns city='Bra', owner=Guido (id=4).

Differences from CENSIMENTO COMPLETO CON COORD:
  - table name : pellico
  - address col: LOCALITA'  (no leading underscore)
  - name col   : _name
"""

import sqlite3
import psycopg2
from datetime import datetime

GPKG     = "file_da_importare/silvio pellico.gpkg"
DSN      = "postgresql://postgres:c0st4m4gn4@localhost/trees_db"
CITY     = "Bra"
OWNER_ID = 29  # Guido


def parse_float(val):
    if val is None:
        return None
    try:
        return float(str(val).replace(',', '.').strip())
    except (ValueError, TypeError):
        return None


def parse_date(val):
    if not val:
        return None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def pick_condition(*candidates):
    for c in candidates:
        if c and str(c).strip():
            return str(c).strip().upper()
    return '—'


def main():
    src = sqlite3.connect(GPKG)
    src.row_factory = sqlite3.Row
    cur = src.cursor()
    cur.execute("SELECT * FROM pellico")
    rows = cur.fetchall()
    src.close()

    dst = psycopg2.connect(DSN)
    dcur = dst.cursor()

    CHECK = "SELECT 1 FROM tree WHERE custom_id = %s AND city = %s LIMIT 1"

    INSERT = """
        INSERT INTO tree (
            custom_id, city, species, condition,
            latitude, longitude, geom,
            address, height,
            crown_diameter_m, circonferenza_cm,
            localizzazione, next_check,
            owner_id
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
            %s, %s,
            %s, %s,
            %s, %s,
            %s
        )
    """

    inserted = skipped = errors = 0

    for row in rows:
        name       = str(row['_name']).strip() if row['_name'] else str(row['fid'])
        lon        = row['xcoord']
        lat        = row['ycoord']
        species    = (row['_TASSONOMI'] or row['_NOME ITAL'] or 'Sconosciuta').strip()
        condition  = pick_condition(row['_CLASSE VT'], row['_F. FISIOL'])
        address    = (row["LOCALITA'"] or '').strip() or None
        height     = (str(row['_ALTEZZA']).strip().upper() if row['_ALTEZZA'] else None)
        crown_diam = parse_float(row['_DIAMETRO'])
        circonf    = parse_float(row['_CIRCONFER'])
        localiz    = (str(row['_STAZIONE']).strip() if row['_STAZIONE'] else None)
        next_chk   = parse_date(row['_DA CONTRO'])

        if not lat or not lon:
            print(f"  [SKIP] fid={row['fid']} — no coordinates")
            skipped += 1
            continue

        dcur.execute(CHECK, (name, CITY))
        if dcur.fetchone():
            skipped += 1
            continue

        try:
            dcur.execute(INSERT, (
                name, CITY, species, condition,
                lat, lon, lon, lat,
                address, height,
                crown_diam, circonf,
                localiz, next_chk,
                OWNER_ID,
            ))
            inserted += 1
        except Exception as e:
            print(f"  [ERROR] fid={row['fid']} name={name}: {e}")
            dst.rollback()
            errors += 1
            continue

    dst.commit()
    dst.close()

    print(f"\nDone — inserted: {inserted}, skipped (duplicates/no coords): {skipped}, errors: {errors}")


if __name__ == '__main__':
    main()

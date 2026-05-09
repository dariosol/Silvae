#!/usr/bin/env python3
"""
Import trees from file_da_importare/CENSIMENTO COMPLETO CON COORD.gpkg
into trees_db. Assigns city='Bra', owner=Guido (id=4).

Field mapping:
  name          -> custom_id
  _LOCALITA'    -> address
  _TASSONOMI    -> species  (fallback: _NOME ITAL)
  _CLASSE VT    -> condition (fallback: _F. FISIOL, then '—')
  _ALTEZZA      -> height
  _DIAMETRO     -> crown_diameter_m
  _CIRCONFER    -> circonferenza_cm
  _STAZIONE     -> localizzazione
  _DA CONTRO    -> next_check
  xcoord/ycoord -> longitude/latitude + PostGIS geom (SRID 4326)
"""

import sqlite3
import psycopg2
from datetime import datetime

GPKG = "file_da_importare/CENSIMENTO COMPLETO CON COORD.gpkg"
DSN  = "postgresql://postgres:c0st4m4gn4@localhost/trees_db"
CITY = "Bra"
OWNER_ID = 4  # Guido


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
    cur.execute("SELECT * FROM 'CENSIMENTO COMPLETO CON COORD'")
    rows = cur.fetchall()
    src.close()

    dst = psycopg2.connect(DSN)
    dcur = dst.cursor()

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
        ON CONFLICT (custom_id, city) DO NOTHING
    """

    inserted = skipped = errors = 0

    for row in rows:
        name       = str(row['name']).strip() if row['name'] else str(row['fid'])
        lon        = row['xcoord']
        lat        = row['ycoord']
        species    = (row['_TASSONOMI'] or row['_NOME ITAL'] or 'Sconosciuta').strip()
        condition  = pick_condition(row['_CLASSE VT'], row['_F. FISIOL'])
        address    = (row["_LOCALITA'"] or '').strip() or None
        height     = (str(row['_ALTEZZA']).strip().upper() if row['_ALTEZZA'] else None)
        crown_diam = parse_float(row['_DIAMETRO'])
        circonf    = parse_float(row['_CIRCONFER'])
        localiz    = (str(row['_STAZIONE']).strip() if row['_STAZIONE'] else None)
        next_chk   = parse_date(row['_DA CONTRO'])

        if not lat or not lon:
            print(f"  [SKIP] fid={row['fid']} — no coordinates")
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
            if dcur.rowcount:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  [ERROR] fid={row['fid']} name={name}: {e}")
            dst.rollback()
            errors += 1
            continue

        if inserted % 250 == 0 and inserted:
            dst.commit()
            print(f"  ... {inserted} inserted so far")

    dst.commit()
    dst.close()

    print(f"\nDone — inserted: {inserted}, skipped (duplicates/no coords): {skipped}, errors: {errors}")


if __name__ == '__main__':
    main()

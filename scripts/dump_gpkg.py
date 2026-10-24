#!/usr/bin/env python3
import argparse
import sqlite3
import json

parser = argparse.ArgumentParser(description='Dump rows from a GeoPackage file')
parser.add_argument('file', help='Path to the .gpkg file')
parser.add_argument('-n', type=int, default=10, help='Number of rows to dump (default: 10)')
parser.add_argument('--offset', type=int, default=0, help='Row offset (default: 0)')
args = parser.parse_args()

conn = sqlite3.connect(args.file)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'gpkg_%' AND name NOT LIKE 'rtree_%' AND name NOT LIKE 'sqlite_%'")
tables = [r[0] for r in cur.fetchall()]
if not tables:
    print('Nessuna tabella dati trovata.')
    raise SystemExit(1)
table = tables[0]

cur.execute(f"SELECT count(*) FROM '{table}'")
total = cur.fetchone()[0]
print(f"Tabella: {table}  |  Totale righe: {total}  |  Offset: {args.offset}  |  N: {args.n}\n")

cur.execute(f"SELECT * FROM '{table}' LIMIT {args.n} OFFSET {args.offset}")
rows = cur.fetchall()
conn.close()

for i, row in enumerate(rows):
    print(f"--- [{args.offset + i}] ---")
    for key in row.keys():
        if key in ('geom',):
            continue
        print(f"  {key}: {row[key]}")
    print()

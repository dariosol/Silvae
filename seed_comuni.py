#!/usr/bin/env python3
"""
Seed the 'comune' table from matteocontrini/comuni-json (GitHub).
Run once: python seed_comuni.py
"""
import json
import urllib.request
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db, Comune

URL = "https://raw.githubusercontent.com/matteocontrini/comuni-json/master/comuni.json"

def seed():
    with app.app_context():
        existing = Comune.query.count()
        if existing > 0:
            print(f"Table already has {existing} comuni. Use --force to re-seed.")
            if '--force' not in sys.argv:
                return

        print(f"Downloading comuni from {URL} ...")
        with urllib.request.urlopen(URL, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        print(f"Downloaded {len(data)} comuni. Clearing table...")
        Comune.query.delete()
        db.session.commit()

        batch = []
        for entry in data:
            batch.append(Comune(
                nome      = entry['nome'],
                provincia = entry['provincia']['nome'],
                sigla     = entry.get('sigla', ''),
                regione   = entry['regione']['nome'],
                codice    = entry['codice'],
            ))
        db.session.bulk_save_objects(batch)
        db.session.commit()
        print(f"Seeded {len(batch)} comuni successfully.")

if __name__ == '__main__':
    seed()

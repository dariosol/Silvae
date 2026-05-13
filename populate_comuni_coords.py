#!/usr/bin/env python3
"""
Populate latitude/longitude for all comuni from comuni-json dataset.
Run once: python populate_comuni_coords.py
"""
import json, urllib.request, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import app, db, Comune

URL = "https://raw.githubusercontent.com/matteocontrini/comuni-json/master/comuni.json"

def run():
    print(f"Downloading comuni-json from {URL} ...")
    with urllib.request.urlopen(URL, timeout=30) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    print(f"Downloaded {len(data)} entries.")

    # Build lookup: codice → coordinate
    coord_map = {}
    for entry in data:
        c = entry.get('coordinate', {})
        if c.get('lat') and c.get('lng'):
            coord_map[entry['codice']] = (float(c['lat']), float(c['lng']))

    with app.app_context():
        updated = skipped = 0
        comuni = Comune.query.all()
        for comune in comuni:
            coords = coord_map.get(comune.codice)
            if coords:
                comune.latitude, comune.longitude = coords
                updated += 1
            else:
                skipped += 1
        db.session.commit()
        print(f"Updated: {updated}, skipped (no match): {skipped}")

if __name__ == '__main__':
    run()

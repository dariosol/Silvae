#!/usr/bin/env python3

# ============================================================================
# NON FUNZIONA PIU', e non servirebbe comunque a nessuno.
#
# Cerca `entry['coordinate']['lat'/'lng']` nel dataset comuni-json, ma quella
# fonte non espone piu' il campo `coordinate`: oggi i record hanno solo nome,
# codice, zona, regione, provincia, sigla, codiceCatastale, cap, popolazione.
# Verificato: 0 record su 7904 lo contengono, quindi lo script aggiorna zero
# righe e stampa «skipped (no match): 7904».
#
# Inoltre nessuna parte dell'applicazione legge comune.latitude/longitude: le
# colonne esistono e restano NULL senza conseguenze. Se un giorno servisse
# centrare la mappa su un comune, tanto vale prendere le coordinate da
# Nominatim, che l'app usa gia' per la geocodifica.
# ============================================================================

"""
Populate latitude/longitude for all comuni from comuni-json dataset.
Run once: python populate_comuni_coords.py
"""
import json, urllib.request, sys, os
# La radice del progetto, dove sta app.py: questo script vive in scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

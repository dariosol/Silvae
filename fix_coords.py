"""
fix_coords.py
Geocode each tree's address and update lat/lon + geom in the database.

Each unique street is geocoded once (cached), then a small random offset
(±50 m) is applied so trees on the same street are not stacked on the map.
Nominatim requires <= 1 request/second; this script sleeps 1.1 s per query.

Run once:  python fix_coords.py
"""
import random
import time

import requests

from app import app, db, Tree

NOMINATIM = 'https://nominatim.openstreetmap.org/search'
HEADERS   = {'User-Agent': 'SilvaePro/1.0 (d.soldi89@gmail.com)'}

_cache: dict = {}   # (street, city) -> (lat, lon) or (None, None)


def _geocode(street: str, city: str):
    key = (street.lower(), city.lower())
    if key in _cache:
        return _cache[key]
    query = f'{street}, {city}, Italy'
    try:
        resp = requests.get(
            NOMINATIM,
            params={'q': query, 'format': 'json', 'limit': 1},
            headers=HEADERS,
            timeout=10,
        )
        data = resp.json()
        result = (float(data[0]['lat']), float(data[0]['lon'])) if data else (None, None)
    except Exception as exc:
        print(f'    Nominatim error for "{query}": {exc}')
        result = (None, None)
    _cache[key] = result
    time.sleep(1.1)   # respect 1 req/s policy
    return result


def _parse_address(address: str, fallback_city: str):
    """'Via Sacchi, 42, Torino' -> ('Via Sacchi', 'Torino')"""
    parts = [p.strip() for p in address.split(',')]
    if len(parts) >= 3:
        return parts[0], parts[-1]
    if len(parts) == 2:
        # could be "Via Sacchi, Torino" or "Via Sacchi, 42"
        try:
            int(parts[1])          # second part is a number → no city
            return parts[0], fallback_city
        except ValueError:
            return parts[0], parts[1]
    return address, fallback_city


def fix():
    with app.app_context():
        trees   = Tree.query.all()
        updated = 0
        skipped = 0

        for tree in trees:
            if not tree.address:
                skipped += 1
                continue

            street, city = _parse_address(tree.address, tree.city or '')
            if not city:
                print(f'  SKIP {tree.custom_id}: no city for "{tree.address}"')
                skipped += 1
                continue

            base_lat, base_lon = _geocode(street, city)
            if base_lat is None:
                print(f'  NOT FOUND: {tree.custom_id} — "{street}, {city}"')
                skipped += 1
                continue

            # ±50 m jitter so trees on the same street are distinct on the map
            lat = round(base_lat + random.uniform(-0.0005, 0.0005), 6)
            lon = round(base_lon + random.uniform(-0.0005, 0.0005), 6)

            tree.latitude  = lat
            tree.longitude = lon
            tree.geom      = f'SRID=4326;POINT({lon} {lat})'
            db.session.commit()
            print(f'  {tree.custom_id:10s} {street}, {city}  →  {lat:.5f}, {lon:.5f}')
            updated += 1

        print(f'\nDone — {updated} updated, {skipped} skipped.')


if __name__ == '__main__':
    fix()

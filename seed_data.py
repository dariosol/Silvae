"""
Seed the database with 10 trees in Roma and 50 trees in Torino, owner = Dario.
Run once:  python seed_data.py
"""
import random
from datetime import date, timedelta
from app import app, db, Tree, Inspection, User
from sqlalchemy.exc import IntegrityError

# ── Config ────────────────────────────────────────────────
OWNER_USERNAME = 'Dario'
CITIES = {
    'Roma':   {'n': 10, 'lat': (41.870, 41.950), 'lon': (12.440, 12.570)},
    'Torino': {'n': 50, 'lat': (45.030, 45.120), 'lon': (7.620,  7.730)},
}

# ── Reference data ────────────────────────────────────────
SPECIES = [
    'Platanus hispanica',   # Platano — very common in Italian cities
    'Tilia cordata',        # Tiglio
    'Quercus robur',        # Quercia
    'Acer campestre',       # Acero campestre
    'Pinus pinea',          # Pino domestico
    'Robinia pseudoacacia', # Robinia
    'Celtis australis',     # Bagolaro
    'Sophora japonica',     # Sofora
    'Cercis siliquastrum',  # Albero di Giuda
    'Fraxinus ornus',       # Orniello
    'Cupressus sempervirens',# Cipresso
    'Laurus nobilis',       # Alloro
    'Olea europaea',        # Olivo
    'Betula pendula',       # Betulla
    'Populus nigra',        # Pioppo nero
]

CONDITIONS = [
    ('Good',     0.45),
    ('Fair',     0.30),
    ('Poor',     0.15),
    ('Critical', 0.10),
]

STREETS_TORINO = [
    'Via Po', 'Corso Vittorio Emanuele II', 'Via Garibaldi', 'Corso Francia',
    'Via Roma', 'Piazza Castello', 'Corso Re Umberto', 'Via Lagrange',
    'Corso Cairoli', 'Via Amendola', 'Lungo Po Diaz', 'Via Nizza',
    'Corso Moncalieri', 'Via Sacchi', 'Via Cernaia', 'Corso Massimo',
    'Piazza Vittorio Veneto', 'Via Accademia Albertina', 'Corso Orbassano',
    'Via Millelire', 'Via Tiepolo', 'Corso Siracusa', 'Via Chatillon',
]

STREETS_ROMA = [
    'Via del Corso', 'Via Appia Antica', 'Viale dei Fori Imperiali',
    'Via Nazionale', 'Via Veneto', 'Viale Aventino', 'Via Ostiense',
    'Via Tuscolana', 'Piazza Navona', 'Via della Conciliazione',
]

LOCATION_DESCS = [
    'Park entrance', 'Along the main avenue', 'Near the fountain',
    'Garden perimeter', 'Central roundabout', 'School courtyard',
    'Pedestrian walkway', 'Parking lot border', 'Riverside promenade',
    'Town square', 'Cemetery lane', 'Sports field border',
]

COMMENTS = [
    'Tree in good vegetative state.',
    'Some signs of branch dieback at the crown.',
    'Recent pruning performed. Recovery expected.',
    'Trunk wound from past storm damage, partially healed.',
    'Roots interfering with pavement, monitoring required.',
    'Healthy bark with good crown density.',
    'Visible signs of fungal infection on lower trunk.',
    'Minor aphid infestation on foliage.',
    'Crown thinning observed, possible water stress.',
    'Dead wood present, requires removal.',
    'Epicormic growth at trunk base.',
    '',  # some trees have no comments
    '',
]

ACTIONS_LIST = [
    'Routine inspection only.',
    'Crown lifting performed.',
    'Dead wood removed.',
    'Fungicide treatment applied.',
    'Irrigation increased.',
    'Trunk cavity filled.',
    'Support stake installed.',
    'Soil aeration performed.',
    '',
    '',
]

INSPECTORS = ['Dario']


def weighted_choice(choices):
    """choices = list of (value, weight)"""
    values, weights = zip(*choices)
    return random.choices(values, weights=weights, k=1)[0]


def rand_date_past(max_days=730):
    """Random date within the last max_days days."""
    return date.today() - timedelta(days=random.randint(1, max_days))


def next_check_date():
    """Random future date 30–365 days from now."""
    return date.today() + timedelta(days=random.randint(30, 365))


def seed():
    with app.app_context():
        owner = User.query.filter_by(username=OWNER_USERNAME).first()
        if not owner:
            print(f"User '{OWNER_USERNAME}' not found. Aborting.")
            return

        total_added = 0
        total_inspections = 0

        for city, cfg in CITIES.items():
            streets = STREETS_TORINO if city == 'Torino' else STREETS_ROMA
            prefix  = 'TOR' if city == 'Torino' else 'ROM'

            # Find highest existing index for this city/prefix to avoid collisions
            existing = db.session.query(Tree.custom_id)\
                         .filter(Tree.city == city,
                                 Tree.owner_id == owner.id)\
                         .all()
            used_nums = set()
            for (cid,) in existing:
                if cid.startswith(prefix + '-'):
                    try:
                        used_nums.add(int(cid.split('-')[1]))
                    except (IndexError, ValueError):
                        pass

            added_this_city = 0
            idx = 1
            while added_this_city < cfg['n']:
                while idx in used_nums:
                    idx += 1

                custom_id = f"{prefix}-{idx:03d}"
                lat = round(random.uniform(*cfg['lat']), 6)
                lon = round(random.uniform(*cfg['lon']), 6)
                street    = random.choice(streets)
                address   = f"{street}, {city}"
                species   = random.choice(SPECIES)
                condition = weighted_choice(CONDITIONS)
                height    = round(random.uniform(4, 22), 1)
                trunk_d   = round(random.uniform(15, 120), 1)
                crown_d   = round(random.uniform(3, 14), 1)
                age_yrs   = random.randint(5, 120)
                location  = random.choice(LOCATION_DESCS)
                comments  = random.choice(COMMENTS)
                actions   = random.choice(ACTIONS_LIST)
                cpc       = f"CPC-{random.randint(1000, 9999)}"

                tree = Tree(
                    custom_id=custom_id,
                    latitude=lat,
                    longitude=lon,
                    address=address,
                    city=city,
                    species=species,
                    condition=condition,
                    comments=comments,
                    actions=actions,
                    height=str(height),
                    trunk_diameter_cm=trunk_d,
                    crown_diameter_m=crown_d,
                    age=f"{age_yrs} years",
                    location=location,
                    cpc=cpc,
                    next_check=next_check_date(),
                    geom=f'SRID=4326;POINT({lon} {lat})',
                    owner_id=owner.id
                )
                db.session.add(tree)
                try:
                    db.session.flush()   # get tree.id without full commit
                except IntegrityError:
                    db.session.rollback()
                    idx += 1
                    continue

                # ── Generate 1-4 past inspections for this tree ──────────
                n_inspections = random.randint(1, 4)
                insp_dates = sorted(
                    [rand_date_past(max_days=1095) for _ in range(n_inspections)]
                )  # ascending so we build history forward in time
                cond_history = condition  # most recent condition
                for i, insp_date in enumerate(insp_dates):
                    # earlier inspections might have had different condition
                    if i < len(insp_dates) - 1:
                        past_cond = weighted_choice(CONDITIONS)
                    else:
                        past_cond = cond_history
                    db.session.add(Inspection(
                        tree_id=tree.id,
                        date=insp_date,
                        condition=past_cond,
                        comments=random.choice(COMMENTS),
                        actions=random.choice(ACTIONS_LIST),
                        inspector_id=owner.id,
                        inspector_name=owner.username
                    ))
                    total_inspections += 1

                db.session.commit()
                added_this_city += 1
                total_added += 1
                idx += 1

            print(f"  {city}: {added_this_city} trees added.")

        print(f"\nDone — {total_added} trees, {total_inspections} inspection records.")


if __name__ == '__main__':
    seed()

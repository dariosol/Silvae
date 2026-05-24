"""
ARETE ORD sheet calculator - replicates the risk calculations from sheet 4 (ORD).

Sheet structure recap
---------------------
The ORD sheet computes two risk assessments for a tree:
  1. RISCHIO ATTUALE  – current risk, using the tree's measured dimensions
  2. RISCHIO RESIDUO  – residual risk after a prescribed intervention, using
                        potentially modified dimensions

Each assessment covers four failure modes:
  • Rottura branche/rami     (branch failure)
  • Rottura tronco/castello  (trunk/scaffold failure)
  • Rottura colletto         (collar failure)
  • Ribaltamento zolla       (root-plate sliding/tipping)

For every failure mode the sheet combines three independent 1-7 classes:
  P – Pericolo  (failure probability, user-assessed field observation, 1=highest)
  B – Bersaglio (target/exposure class, derived from occupancy, 1=highest)
  I – Impulso   (momentum class, computed from tree geometry, 1=highest)

The risk key is the 3-digit string str(B)+str(I)+str(P) which is looked up in
the risk matrix (from sheet A) to obtain the risk ratio string (e.g. "1:20k").

Class scale (same for all three):
  1 = worst / most exposed / highest energy
  7 = best  / least exposed / lowest energy
"""

import math


# ---------------------------------------------------------------------------
# RISK MATRIX  (sheet A, AM4:AN346)
# Key = str(bersaglio_class) + str(impulso_class) + str(pericolo_class)
# Value = risk ratio string
# ---------------------------------------------------------------------------
RISK_MATRIX: dict[str, str] = {
    '111': '1:3',    '112': '1:20',   '113': '1:200',  '114': '1:2k',
    '115': '1:20k',  '116': '1:200k', '117': '1:1M',
    '121': '1:20',   '122': '1:100',  '123': '1:1k',   '124': '1:12k',
    '125': '1:130k', '126': '1:1M',   '127': '<1:1M',
    '131': '1:200',  '132': '1:1k',   '133': '1:12k',  '134': '1:120k',
    '135': '1:1M',   '136': '<1:1M',  '137': '<1:1M',
    '141': '1:2k',   '142': '1:12k',  '143': '1:120k', '144': '1:1M',
    '145': '<1:1M',  '146': '<1:1M',  '147': '<1:1M',
    '151': '1:20k',  '152': '1:120k', '153': '1:1M',   '154': '<1:1M',
    '155': '<1:1M',  '156': '<1:1M',  '157': '<1:1M',
    '161': '1:200k', '162': '1:1M',   '163': '<1:1M',  '164': '<1:1M',
    '165': '<1:1M',  '166': '<1:1M',  '167': '<1:1M',
    '171': '1:1M',   '172': '<1:1M',  '173': '<1:1M',  '174': '<1:1M',
    '175': '<1:1M',  '176': '<1:1M',  '177': '<1:1M',

    '211': '1:20',   '212': '1:100',  '213': '1:1k',   '214': '1:10k',
    '215': '1:120k', '216': '1:1M',   '217': '<1:1M',
    '221': '1:100',  '222': '1:800',  '223': '1:8k',   '224': '1:80k',
    '225': '1:800k', '226': '<1:1M',  '227': '<1:1M',
    '231': '1:1k',   '232': '1:8k',   '233': '1:80k',  '234': '1:800k',
    '235': '<1:1M',  '236': '<1:1M',  '237': '<1:1M',
    '241': '1:12k',  '242': '1:80k',  '243': '1:800k', '244': '<1:1M',
    '245': '<1:1M',  '246': '<1:1M',  '247': '<1:1M',
    '251': '1:130k', '252': '1:800k', '253': '<1:1M',  '254': '<1:1M',
    '255': '<1:1M',  '256': '<1:1M',  '257': '<1:1M',
    '261': '1:1M',   '262': '<1:1M',  '263': '<1:1M',  '264': '<1:1M',
    '265': '<1:1M',  '266': '<1:1M',  '267': '<1:1M',
    '271': '<1:1M',  '272': '<1:1M',  '273': '<1:1M',  '274': '<1:1M',
    '275': '<1:1M',  '276': '<1:1M',  '277': '<1:1M',

    '311': '1:200',  '312': '1:1k',   '313': '1:12k',  '314': '1:120k',
    '315': '1:1M',   '316': '<1:1M',  '317': '<1:1M',
    '321': '1:1k',   '322': '1:8k',   '323': '1:80k',  '324': '1:800k',
    '325': '<1:1M',  '326': '<1:1M',  '327': '<1:1M',
    '331': '1:12k',  '332': '1:80k',  '333': '1:800k', '334': '<1:1M',
    '335': '<1:1M',  '336': '<1:1M',  '337': '<1:1M',
    '341': '1:120k', '342': '1:800k', '343': '<1:1M',  '344': '<1:1M',
    '345': '<1:1M',  '346': '<1:1M',  '347': '<1:1M',
    '351': '1:1M',   '352': '<1:1M',  '353': '<1:1M',  '354': '<1:1M',
    '355': '<1:1M',  '356': '<1:1M',  '357': '<1:1M',
    '361': '<1:1M',  '362': '<1:1M',  '363': '<1:1M',  '364': '<1:1M',
    '365': '<1:1M',  '366': '<1:1M',  '367': '<1:1M',
    '371': '<1:1M',  '372': '<1:1M',  '373': '<1:1M',  '374': '<1:1M',
    '375': '<1:1M',  '376': '<1:1M',  '377': '<1:1M',

    '411': '1:2k',   '412': '1:12k',  '413': '1:130k', '414': '1:1M',
    '415': '<1:1M',  '416': '<1:1M',  '417': '<1:1M',
    '421': '1:12k',  '422': '1:80k',  '423': '1:800k', '424': '<1:1M',
    '425': '<1:1M',  '426': '<1:1M',  '427': '<1:1M',
    '431': '1:120k', '432': '1:800k', '433': '<1:1M',  '434': '<1:1M',
    '435': '<1:1M',  '436': '<1:1M',  '437': '<1:1M',
    '441': '1:1M',   '442': '<1:1M',  '443': '<1:1M',  '444': '<1:1M',
    '445': '<1:1M',  '446': '<1:1M',  '447': '<1:1M',
    '451': '<1:1M',  '452': '<1:1M',  '453': '<1:1M',  '454': '<1:1M',
    '455': '<1:1M',  '456': '<1:1M',  '457': '<1:1M',
    '461': '<1:1M',  '462': '<1:1M',  '463': '<1:1M',  '464': '<1:1M',
    '465': '<1:1M',  '466': '<1:1M',  '467': '<1:1M',
    '471': '<1:1M',  '472': '<1:1M',  '473': '<1:1M',  '474': '<1:1M',
    '475': '<1:1M',  '476': '<1:1M',  '477': '<1:1M',

    '511': '1:20k',  '512': '1:120k', '513': '1:1M',   '514': '<1:1M',
    '515': '<1:1M',  '516': '<1:1M',  '517': '<1:1M',
    '521': '1:130k', '522': '1:800k', '523': '<1:1M',  '524': '<1:1M',
    '525': '<1:1M',  '526': '<1:1M',  '527': '<1:1M',
    '531': '1:1M',   '532': '<1:1M',  '533': '<1:1M',  '534': '<1:1M',
    '535': '<1:1M',  '536': '<1:1M',  '537': '<1:1M',
    '541': '<1:1M',  '542': '<1:1M',  '543': '<1:1M',  '544': '<1:1M',
    '545': '<1:1M',  '546': '<1:1M',  '547': '<1:1M',
    '551': '<1:1M',  '552': '<1:1M',  '553': '<1:1M',  '554': '<1:1M',
    '555': '<1:1M',  '556': '<1:1M',  '557': '<1:1M',
    '561': '<1:1M',  '562': '<1:1M',  '563': '<1:1M',  '564': '<1:1M',
    '565': '<1:1M',  '566': '<1:1M',  '567': '<1:1M',
    '571': '<1:1M',  '572': '<1:1M',  '573': '<1:1M',  '574': '<1:1M',
    '575': '<1:1M',  '576': '<1:1M',  '577': '<1:1M',

    '611': '1:200k', '612': '1:1M',   '613': '<1:1M',  '614': '<1:1M',
    '615': '<1:1M',  '616': '<1:1M',  '617': '<1:1M',
    '621': '1:1M',   '622': '<1:1M',  '623': '<1:1M',  '624': '<1:1M',
    '625': '<1:1M',  '626': '<1:1M',  '627': '<1:1M',
    '631': '<1:1M',  '632': '<1:1M',  '633': '<1:1M',  '634': '<1:1M',
    '635': '<1:1M',  '636': '<1:1M',  '637': '<1:1M',
    '641': '<1:1M',  '642': '<1:1M',  '643': '<1:1M',  '644': '<1:1M',
    '645': '<1:1M',  '646': '<1:1M',  '647': '<1:1M',
    '651': '<1:1M',  '652': '<1:1M',  '653': '<1:1M',  '654': '<1:1M',
    '655': '<1:1M',  '656': '<1:1M',  '657': '<1:1M',
    '661': '<1:1M',  '662': '<1:1M',  '663': '<1:1M',  '664': '<1:1M',
    '665': '<1:1M',  '666': '<1:1M',  '667': '<1:1M',
    '671': '<1:1M',  '672': '<1:1M',  '673': '<1:1M',  '674': '<1:1M',
    '675': '<1:1M',  '676': '<1:1M',  '677': '<1:1M',

    '711': '1:1M',   '712': '<1:1M',  '713': '<1:1M',  '714': '<1:1M',
    '715': '<1:1M',  '716': '<1:1M',  '717': '<1:1M',
    '721': '<1:1M',  '722': '<1:1M',  '723': '<1:1M',  '724': '<1:1M',
    '725': '<1:1M',  '726': '<1:1M',  '727': '<1:1M',
    '731': '<1:1M',  '732': '<1:1M',  '733': '<1:1M',  '734': '<1:1M',
    '735': '<1:1M',  '736': '<1:1M',  '737': '<1:1M',
    '741': '<1:1M',  '742': '<1:1M',  '743': '<1:1M',  '744': '<1:1M',
    '745': '<1:1M',  '746': '<1:1M',  '747': '<1:1M',
    '751': '<1:1M',  '752': '<1:1M',  '753': '<1:1M',  '754': '<1:1M',
    '755': '<1:1M',  '756': '<1:1M',  '757': '<1:1M',
    '761': '<1:1M',  '762': '<1:1M',  '763': '<1:1M',  '764': '<1:1M',
    '765': '<1:1M',  '766': '<1:1M',  '767': '<1:1M',
    '771': '<1:1M',  '772': '<1:1M',  '773': '<1:1M',  '774': '<1:1M',
    '775': '<1:1M',  '776': '<1:1M',  '777': '<1:1M',
}

# ---------------------------------------------------------------------------
# RISK LEVEL DESCRIPTIONS  (sheet A, AP4:AQ21)
# ---------------------------------------------------------------------------
RISK_LEVEL: dict[str, str] = {
    '1:3':    'rischio inaccettabile - abbattimento o eliminazione del rischio',
    '1:20':   'rischio inaccettabile - abbattimento o eliminazione del rischio',
    '1:100':  'rischio inaccettabile - abbattimento o eliminazione del rischio',
    '1:200':  'rischio inaccettabile - abbattimento o eliminazione del rischio',
    '1:800':  'rischio inaccettabile - abbattimento o eliminazione del rischio',
    '1:1k':   'rischio inaccettabile - abbattimento o eliminazione del rischio',
    '1:2k':   'rischio tollerabile per accordo se il valore è molto elevato',
    '1:8k':   'rischio tollerabile per accordo se il valore è molto elevato',
    '1:10k':  'rischio tollerabile per accordo ma inaccettabile se imposto a terzi',
    '1:12k':  'rischio tollerabile per accordo ma inaccettabile se imposto a terzi',
    '1:20k':  'rischio tollerabile se ALARP - valutare costi/benefici del controllo',
    '1:80k':  'rischio tollerabile se ALARP - valutare costi/benefici del controllo',
    '1:120k': 'rischio tollerabile se ALARP - valutare costi/benefici del controllo',
    '1:130k': 'rischio tollerabile se ALARP - valutare costi/benefici del controllo',
    '1:200k': 'rischio tollerabile - individuare interventi affinché rimanga ALARP',
    '1:800k': 'rischio tollerabile - individuare interventi affinché rimanga ALARP',
    '1:1M':   'rischio tollerabile - individuare interventi affinché rimanga ALARP',
    '<1:1M':  'rischio largamente accettabile',
}

# Risk ratio → approximate annual probability (for sorting/comparison)
RISK_PROBABILITY: dict[str, float] = {
    '1:3':    1/3,     '1:20':   1/20,    '1:100':  1/100,   '1:200':  1/200,
    '1:800':  1/800,   '1:1k':   1/1000,  '1:2k':   1/2000,  '1:8k':   1/8000,
    '1:10k':  1/10000, '1:12k':  1/12000, '1:20k':  1/20000, '1:80k':  1/80000,
    '1:120k': 1/120000,'1:130k': 1/130000,'1:200k': 1/200000,'1:800k': 1/800000,
    '1:1M':   1/1e6,   '<1:1M':  1e-11,
}

# Ascending (probability, ratio) pairs for "+bers" reverse lookup.
# Mirrors sheet A, AR23:AS73.  VLOOKUP TRUE semantics: find the largest
# threshold ≤ the query probability and return the associated ratio string.
_PROB_THRESHOLDS: list[tuple[float, str]] = [
    (1e-11,        '<1:1M'),
    (1/1_000_000,  '1:1M'),
    (1/800_000,    '1:800k'),
    (1/200_000,    '1:200k'),
    (1/130_000,    '1:130k'),
    (1/120_000,    '1:120k'),
    (1/80_000,     '1:80k'),
    (1/20_000,     '1:20k'),
    (1/12_000,     '1:12k'),
    (1/10_000,     '1:10k'),
    (1/8_000,      '1:8k'),
    (1/2_000,      '1:2k'),
    (1/1_000,      '1:1k'),
    (1/800,        '1:800'),
    (1/200,        '1:200'),
    (1/100,        '1:100'),
    (1/20,         '1:20'),
    (1/3,          '1:3'),
]


def probability_to_risk_ratio(prob: float) -> str:
    """Convert an annual probability to a risk ratio string.

    Used for the '+bers' (multiple simultaneous targets) calculation:
    multiply the base probability by the moltiplicatore (n) and call this
    function to get the corresponding risk class string.
    Replicates VLOOKUP(prob, A!AR23:AS73, 2, TRUE) from the ORD sheet.
    """
    result = '<1:1M'
    for threshold, ratio in _PROB_THRESHOLDS:
        if prob >= threshold:
            result = ratio
    return result


# ---------------------------------------------------------------------------
# BERSAGLIO TYPE → CLASS lookup tables  (ORD sheet, BQ column)
# ---------------------------------------------------------------------------

# Ordered descriptions for each type (index 0 = class 1, index 6 = class 7)
BERSAGLIO_PROPRIETA_VALUES: list[str] = [
    "danni da € 600'000 a 3'000'000",
    "danni da € 60'000 a € 600'000",
    "danni da € 6'000 a € 60'000",
    "danni da € 600 a € 6'000",
    "danni da € 60 a € 600",
    "danni da € 6 a € 60",
    "danni da € 3 a € 6",
]

BERSAGLIO_OCCUPAZIONE_VALUES: list[str] = [
    "da 5 ore/giorno a costante",
    "da 29 min/giorno a 5 h/giorno",
    "da 3 a 29 min/giorno",
    "da 2 min/sett. a 3 min/giorno",
    "da 0,9 min/mese a 2 min/sett.",
    "da 1 min/anno a 0,9 min/mese",
    "da 0,5 a 1 min/anno",
]

# Description → class 1-7
BERSAGLIO_PROPRIETA_MAP: dict[str, int] = {
    v: i + 1 for i, v in enumerate(BERSAGLIO_PROPRIETA_VALUES)
}
BERSAGLIO_OCCUPAZIONE_MAP: dict[str, int] = {
    v: i + 1 for i, v in enumerate(BERSAGLIO_OCCUPAZIONE_VALUES)
}

# All selectable target types (matches C32/N32 in the ORD sheet)
BERSAGLIO_TIPI: list[str] = [
    "proprietà",
    "occupazione",
    "pedoni/ciclisti",
    "traffico 30 Km/h",
    "traffico 50 km/h",
    "traffico 70 Km/h",
    "traffico 90 Km/h",
    "traffico 110 km/h",
]


def bersaglio_value_to_class(tipo: str, value: str) -> int | None:
    """Convert a target-type + value description to a bersaglio class (1-7).

    Returns None for types (pedoni/traffico) where the class depends on flow rate.
    """
    if tipo == "proprietà":
        return BERSAGLIO_PROPRIETA_MAP.get(value)
    if tipo == "occupazione":
        return BERSAGLIO_OCCUPAZIONE_MAP.get(value)
    return None


def bersaglio_flow_to_class(tipo: str, flow: float, zone_width_m: float) -> int | None:
    """Compute bersaglio class (1-7) from flow rate for pedestrian/traffic types.

    Replicates BA/BB column formulas (pedoni) and BD-BH column formulas (traffico)
    from the ORD sheet.

    Args:
        tipo:         "pedoni/ciclisti" or "traffico NN Km/h" / "traffico NN km/h"
        flow:         pedestrians/hour for pedoni; vehicles/day for traffico
        zone_width_m: hazard zone width —
                        chioma: (crown_diam_m + tree_height_m) / 2
                        ramo:   branch_length_m * 1.25
    Returns:
        Class 1–7 or None if inputs are invalid / tipo not flow-based.
    """
    import re as _re
    if zone_width_m <= 0 or flow < 0:
        return None

    if tipo == "pedoni/ciclisti":
        # BA6 = zone_width / walking_speed  (seconds to traverse the zone)
        # BA8 = 3600 / BA6                  (max pedestrians/hour)
        walking_speed = 10.0 / 9.0           # 4 km/h = 1.1111… m/s
        t_pass = zone_width_m / walking_speed
        max_flow = 3600.0 / t_pass
        # Class lower-bounds in pedoni/ora (same geometric progression as traffic)
        lower = [max_flow / d for d in (5, 50, 500, 5_000, 50_000, 500_000)]
    else:
        m = _re.search(r'(\d+)', tipo)
        if not m:
            return None
        speed_kmh = float(m.group(1))
        v_ms      = speed_kmh * 1000.0 / 3600.0
        # BD27 = v²/(2·9.8·0.5),  BD28 = BD27/v = v/9.8  (time to stop)
        t_stop    = v_ms / 9.8
        t_cross   = zone_width_m / v_ms
        # BD31 = MIN(86400/t_stop, 86400/t_cross) / 1.3  → max vehicles/day
        v1 = min(86400.0 / t_stop, 86400.0 / t_cross) / 1.3
        # Class lower-bounds in auto/giorno
        lower = [v1 / d for d in (5, 50, 500, 5_000, 50_000, 500_000)]

    for cls, lb in enumerate(lower, start=1):
        if flow >= lb:
            return cls
    return 7


def bersaglio_flow_unit(tipo: str) -> str:
    """Return the expected flow unit string for a given target type."""
    if tipo == "pedoni/ciclisti":
        return "pedoni/ora"
    if tipo.startswith("traffico"):
        return "auto/giorno"
    return ""


# ---------------------------------------------------------------------------
# PERICOLO (danger/failure probability) descriptions  (sheet A, B4:C14)
# ---------------------------------------------------------------------------
PERICOLO_DESCRIPTION: dict = {
    1: "Segni, sintomi e difetti gravissimi - Probabilità di cedimento nell'anno 1/1-1/5",
    2: "Segni, sintomi e difetti gravi - Probabilità di cedimento nell'anno 1/5-1/50",
    3: "Segni, sintomi e difetti significativi - Probabilità di cedimento nell'anno 1/50-1/500",
    4: "Segni, sintomi e difetti incerti - Probabilità di cedimento nell'anno 1/500-1/5K",
    5: "Segni, sintomi e difetti moderati - Probabilità di cedimento nell'anno 1/5K-1/50K",
    6: "Segni, sintomi e difetti bassi - Probabilità di cedimento nell'anno 1/50K-1/500k",
    7: "Segni, sintomi e difetti trascurabili - Probabilità di cedimento nell'anno 1/500K-1/1M",
    0: "Valutazione sospesa - necessario approfondimento",
}

# Bersaglio (exposure/target) class descriptions for guidance
BERSAGLIO_DESCRIPTION: dict[int, str] = {
    1: "Esposizione massima (es. >100 pedoni/ora, traffico intenso continuo)",
    2: "Esposizione molto alta",
    3: "Esposizione alta",
    4: "Esposizione media",
    5: "Esposizione bassa",
    6: "Esposizione molto bassa",
    7: "Esposizione minima (es. <1 passaggio/anno)",
}

# Impulso (momentum) class thresholds in kg⋅m/s
IMPULSO_THRESHOLDS = [
    (5,     7),   # < 5      kg⋅m/s  → class 7
    (10,    6),   # < 10     kg⋅m/s  → class 6
    (50,    5),   # < 50     kg⋅m/s  → class 5
    (100,   4),   # < 100    kg⋅m/s  → class 4
    (1000,  3),   # < 1000   kg⋅m/s  → class 3
    (10000, 2),   # < 10000  kg⋅m/s  → class 2
    (None,  1),   # ≥ 10000  kg⋅m/s  → class 1
]


# ---------------------------------------------------------------------------
# CORE FUNCTIONS
# ---------------------------------------------------------------------------

def impulso_to_class(momentum_kgms: float) -> int:
    """Convert momentum (kg·m/s) to impulso class 1-7 (1=highest energy)."""
    for threshold, cls in IMPULSO_THRESHOLDS:
        if threshold is None or momentum_kgms < threshold:
            return cls
    return 1


def calc_crown_momentum(
    circumference_cm: float,
    tree_height_m: float,
    target_height_m: float,
) -> float:
    """
    Compute the momentum (kg·m/s) for a falling tree crown.

    Replicates cell J33:
      (PI/4 * (circ_cm/100/PI)^2 * height * 0.75 * 900) * sqrt(3 * g * (height - target_h))

    The first term approximates the trunk/crown mass from trunk cross-section;
    the second term uses sqrt(3·g·h) for a pivoting fall (rigid-body rotation).
    """
    if tree_height_m <= target_height_m:
        return 0.0
    diam_m = circumference_cm / 100.0 / math.pi
    area_m2 = math.pi / 4.0 * diam_m ** 2
    mass_kg = area_m2 * tree_height_m * 0.75 * 900.0
    velocity = math.sqrt(3.0 * 9.8 * (tree_height_m - target_height_m))
    return mass_kg * velocity


def calc_branch_momentum(
    branch_diam_cm: float,
    branch_length_m: float,
    branch_height_m: float,
    target_height_m: float,
) -> float:
    """
    Compute the momentum (kg·m/s) for a falling branch.

    Replicates cell S33:
      (PI/4 * (diam_cm/100)^2 * length * 0.75 * 900) * sqrt(2 * g * (branch_h - target_h))

    Uses free-fall velocity sqrt(2·g·h).
    """
    if branch_height_m <= target_height_m:
        return 0.0
    diam_m = branch_diam_cm / 100.0
    area_m2 = math.pi / 4.0 * diam_m ** 2
    mass_kg = area_m2 * branch_length_m * 0.75 * 900.0
    velocity = math.sqrt(2.0 * 9.8 * (branch_height_m - target_height_m))
    return mass_kg * velocity


def calc_risk(
    bersaglio_class: int,
    impulso_class: int,
    pericolo_class: int,
) -> str:
    """
    Look up the risk ratio string from the 3-class combination.

    The key is str(B)+str(I)+str(P) (bersaglio + impulso + pericolo),
    each an integer 1-7 (lower = more dangerous).
    Returns a risk ratio string like "1:20k" or "<1:1M".
    Returns "SOSPESO" when pericolo_class == 0 (assessment suspended).
    """
    if pericolo_class == 0:
        return "SOSPESO"
    key = f"{bersaglio_class}{impulso_class}{pericolo_class}"
    return RISK_MATRIX.get(key, '<1:1M')


def risk_description(ratio: str) -> str:
    """Return the human-readable risk level description for a ratio string."""
    return RISK_LEVEL.get(ratio, 'non determinato')


# ---------------------------------------------------------------------------
# HIGH-LEVEL ASSESSMENT
# ---------------------------------------------------------------------------

def assess_tree(
    # --- General dimensions ---
    tree_height_m: float,       # H  (C9)
    circumference_cm: float,    # Circ at 1.3m, used as proxy for mass  (G9 → H9 = circ = diam*PI)
    crown_diam_m: float,        # D ch  (I9)
    branch_diam_cm: float,      # D br  (L9)
    branch_length_m: float,     # L br  (N9)
    branch_height_m: float,     # H br  (Q9)
    target_height_m: float,     # H bers – height of the exposed target above ground (S9)

    # --- Pericolo classes (1-7 or 0) – user-assessed field observation ---
    pericolo_rami: int,         # failure prob. for branches/limbs   (E35 ← E26)
    pericolo_tronco: int,       # failure prob. for trunk/scaffold   (E36 ← E27)
    pericolo_colletto: int,     # failure prob. for collar           (E37 ← E28)
    pericolo_zolla: int,        # failure prob. for root-plate       (E38 ← E29)

    # --- Bersaglio classes (1-7) – derived from target occupancy ---
    bersaglio_chioma: int,      # exposure class for crown fall target  (G32 "Bersaglio Albero")
    bersaglio_ramo: int,        # exposure class for branch fall target (R32 "Bersaglio Rami")

    # --- Moltiplicatore – number of simultaneous targets (H32, default 1) ---
    # When > 1 the final risk is: probability_to_risk_ratio(base_prob * n).
    # Mirrors ORD sheet column Z ("+bers") logic.
    moltiplicatore: int = 1,

    # --- Post-intervention dimensions (default = same as current) ---
    post_tree_height_m: float | None = None,
    post_circumference_cm: float | None = None,
    post_branch_diam_cm: float | None = None,
    post_branch_length_m: float | None = None,
    post_branch_height_m: float | None = None,
    post_target_height_m: float | None = None,
) -> dict:
    """
    Compute RISCHIO ATTUALE and RISCHIO RESIDUO for all four failure modes.

    Returns a dict with keys:
      attuale / residuo → each a dict with keys:
        crown_momentum_kgms, crown_impulso_class,
        branch_momentum_kgms, branch_impulso_class,
        rami, tronco, colletto, zolla  → each a dict with:
          pericolo_class, bersaglio_class, impulso_class,
          risk_key, risk_ratio, risk_description
    """

    def _assess(
        h_m, circ_cm, br_diam, br_len, br_h, tgt_h,
        p_rami, p_tronco, p_colletto, p_zolla,
        b_chioma, b_ramo,
    ):
        crown_mom = calc_crown_momentum(circ_cm, h_m, tgt_h)
        branch_mom = calc_branch_momentum(br_diam, br_len, br_h, tgt_h)
        crown_imp_cls = impulso_to_class(crown_mom)
        branch_imp_cls = impulso_to_class(branch_mom)

        def _risk_entry(pericolo, bersaglio, imp_cls):
            ratio_1bers = calc_risk(bersaglio, imp_cls, pericolo)
            # "+bers": multiply the base probability by moltiplicatore (n > 1
            # means n simultaneous people in the hazard zone), then convert
            # back to a risk ratio string via the sheet-A reverse lookup.
            if moltiplicatore > 1 and ratio_1bers != 'SOSPESO':
                base_prob = RISK_PROBABILITY.get(ratio_1bers, 0.0)
                ratio_plusbers = probability_to_risk_ratio(base_prob * moltiplicatore)
            else:
                ratio_plusbers = ratio_1bers
            displayed = ratio_plusbers
            return {
                'pericolo_class': pericolo,
                'bersaglio_class': bersaglio,
                'impulso_class': imp_cls,
                'risk_key': f"{bersaglio}{imp_cls}{pericolo}",
                'risk_ratio': displayed,
                'risk_ratio_1bers': ratio_1bers,
                'risk_ratio_plusbers': ratio_plusbers,
                'risk_description': risk_description(displayed),
            }

        return {
            'crown_momentum_kgms': round(crown_mom, 2),
            'crown_impulso_class': crown_imp_cls,
            'branch_momentum_kgms': round(branch_mom, 2),
            'branch_impulso_class': branch_imp_cls,
            # Branches/rami use the BRANCH impulso and RAMO bersaglio
            'rami': _risk_entry(p_rami, b_ramo, branch_imp_cls),
            # Trunk, collar, root-plate use CROWN impulso and CHIOMA bersaglio
            'tronco':  _risk_entry(p_tronco,   b_chioma, crown_imp_cls),
            'colletto': _risk_entry(p_colletto, b_chioma, crown_imp_cls),
            'zolla':   _risk_entry(p_zolla,    b_chioma, crown_imp_cls),
        }

    # --- current assessment ---
    attuale = _assess(
        tree_height_m, circumference_cm,
        branch_diam_cm, branch_length_m, branch_height_m, target_height_m,
        pericolo_rami, pericolo_tronco, pericolo_colletto, pericolo_zolla,
        bersaglio_chioma, bersaglio_ramo,
    )

    # --- post-intervention (residual) assessment ---
    residuo = _assess(
        post_tree_height_m   if post_tree_height_m   is not None else tree_height_m,
        post_circumference_cm if post_circumference_cm is not None else circumference_cm,
        post_branch_diam_cm  if post_branch_diam_cm  is not None else branch_diam_cm,
        post_branch_length_m if post_branch_length_m is not None else branch_length_m,
        post_branch_height_m if post_branch_height_m is not None else branch_height_m,
        post_target_height_m if post_target_height_m is not None else target_height_m,
        pericolo_rami, pericolo_tronco, pericolo_colletto, pericolo_zolla,
        bersaglio_chioma, bersaglio_ramo,
    )

    return {'attuale': attuale, 'residuo': residuo}


# ---------------------------------------------------------------------------
# VALORE ECOLOGICO  (ORD sheet, row 10)
# ---------------------------------------------------------------------------

# Stadio sviluppo → anni (used to annualise bio increment)  A!BL4:BN10, col 3
_STADIO_ANNI: dict[str, int] = {
    'plantula': 10, 'giovane pianta': 20, 'albero giovane': 30,
    'albero adulto': 40, 'albero maturo': 60,
    'albero senescente': 80, 'albero veterano': 100,
}

# Health-condition description → deduction %  (A!AU35:AV45)
CONDIZIONE_SALUTE_ECOLOGICA: list[tuple[str, int]] = [
    ('Condizioni vegetative e fitosanitarie ottimali. Albero integro', 0),
    ('Condizioni vegetative e/o fitosanitarie ottimali. Albero lievemente alterato nella struttura', 5),
    ('Condizioni vegetative e/o fitosanitarie buone o comunque non tali da condizionare la salute e la vigoria', 15),
    ('Condizioni vegetative e/o fitosanitarie buone o comunque non tali da condizionare la salute e la vigoria. Albero strutturalmente alterato', 20),
    ("Condizioni vegetative e/o fitosanitarie mediocri, che limitano l'efficienza funzionale. Salute e/o vigoria ridotte", 25),
    ('Condizioni vegetative e/o fitosanitarie mediocri. Albero strutturalmente alterato', 30),
    ("Condizioni vegetative e/o fitosanitarie scadenti, che ne condizionano la salute e l'aspettativa di vita", 40),
    ('Condizioni vegetative e/o fitosanitarie scadenti. Albero molto alterato strutturalmente', 50),
    ('Condizioni vegetative e/o fitosanitarie pessime', 60),
    ('Condizioni vegetative e/o fitosanitarie pessime. Albero fortemente deperiente, strutturalmente molto alterato', 70),
    ('Albero morto in piedi', 90),
]
_CONDIZIONE_SALUTE_MAP: dict[str, int] = {desc: pct for desc, pct in CONDIZIONE_SALUTE_ECOLOGICA}

# Posizione sociale → VLOOKUP column index (2-10)  A!BQ3:BY3
_POS_SOCIALE_COL: dict[str, int] = {
    'oppressa': 2, 'dominata': 3, 'intermedia': 4, 'codominante': 5,
    'dominante margine': 6, 'dominante interna': 7, 'predominante': 8,
    'libera (p giovane)': 9, 'isolata': 10,
}

# A!BP4:BY24: deduction% → [coeff per pos_sociale oppressa..isolata]
# Coefficients for column indices 2-10 (list index = col - 2)
_SALUTE_POS_COEFFS: dict[int, list[float]] = {
     0: [0.80, 0.85, 0.90, 0.92, 0.96, 0.94, 0.98, 1.00, 1.00],
     5: [0.75, 0.80, 0.85, 0.87, 0.91, 0.89, 0.93, 0.95, 0.95],
    10: [0.70, 0.75, 0.80, 0.82, 0.86, 0.84, 0.88, 0.90, 0.90],
    15: [0.65, 0.70, 0.75, 0.77, 0.81, 0.79, 0.83, 0.85, 0.85],
    20: [0.60, 0.65, 0.70, 0.72, 0.76, 0.74, 0.78, 0.80, 0.80],
    25: [0.55, 0.60, 0.65, 0.67, 0.71, 0.69, 0.73, 0.75, 0.75],
    30: [0.50, 0.55, 0.60, 0.62, 0.66, 0.64, 0.68, 0.70, 0.70],
    35: [0.45, 0.50, 0.55, 0.57, 0.61, 0.59, 0.63, 0.65, 0.65],
    40: [0.40, 0.45, 0.50, 0.52, 0.56, 0.54, 0.58, 0.60, 0.60],
    45: [0.35, 0.40, 0.45, 0.47, 0.51, 0.49, 0.53, 0.55, 0.55],
    50: [0.30, 0.35, 0.40, 0.42, 0.46, 0.44, 0.48, 0.50, 0.50],
    55: [0.25, 0.30, 0.35, 0.37, 0.41, 0.39, 0.43, 0.45, 0.45],
    60: [0.20, 0.25, 0.30, 0.32, 0.36, 0.34, 0.38, 0.40, 0.40],
    65: [0.15, 0.20, 0.25, 0.27, 0.31, 0.29, 0.33, 0.35, 0.35],
    70: [0.10, 0.15, 0.20, 0.22, 0.26, 0.24, 0.28, 0.30, 0.30],
    75: [0.05, 0.10, 0.15, 0.17, 0.21, 0.19, 0.23, 0.25, 0.25],
    80: [0.00, 0.05, 0.10, 0.12, 0.16, 0.14, 0.18, 0.20, 0.20],
    85: [0.00, 0.00, 0.05, 0.07, 0.11, 0.09, 0.13, 0.15, 0.15],
    90: [0.00, 0.00, 0.00, 0.02, 0.06, 0.04, 0.08, 0.10, 0.10],
    95: [0.00, 0.00, 0.00, 0.00, 0.01, 0.00, 0.03, 0.05, 0.05],
   100: [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
}

# Unit market prices (A!BN19:BN22)
_PREZZO_BIO  = 0.55   # €/kg biomassa
_PREZZO_CO2  = 1.00   # €/kg CO2 annuo
_PREZZO_O2   = 5.00   # €/kg O2 annuo
_PREZZO_IA   = 10.00  # €/kg intercettazione acqua annua


def calc_ecological_value(
    trunk_diameter_cm: float,
    tree_height_m: float,
    stadio_sviluppo: str,
    posizione_sociale: str,
    condizione_salute_ecologica: str,
) -> dict | None:
    """
    Compute ecological value metrics — replicates ORD sheet row 10.

    Returns dict with keys:
      bio_kg, co2_kg_anno, o2_kg_anno, ia_kg_anno, valore_ecologico (€)
    Returns None if any required input is missing or unrecognised.
    """
    if not trunk_diameter_cm or trunk_diameter_cm <= 0:
        return None
    if not tree_height_m or tree_height_m <= 0:
        return None
    anni   = _STADIO_ANNI.get(stadio_sviluppo)
    pos_col = _POS_SOCIALE_COL.get(posizione_sociale)
    deduct  = _CONDIZIONE_SALUTE_MAP.get(condizione_salute_ecologica)
    if anni is None or pos_col is None or deduct is None:
        return None

    # G10 = PI/4 * (diam_m)^2 * H * 0.9 * 900
    diam_m = trunk_diameter_cm / 100.0
    bio_kg = math.pi / 4.0 * diam_m ** 2 * tree_height_m * 0.9 * 900.0

    if condizione_salute_ecologica == 'Albero morto in piedi':
        co2_kg_anno = 0.0
        o2_kg_anno  = 0.0
        ia_kg_anno  = 0.0
    else:
        coeff = _SALUTE_POS_COEFFS[deduct][pos_col - 2]
        base  = (bio_kg / anni) * coeff          # J10 base
        co2_kg_anno = base                        # J10
        o2_kg_anno  = base / 44.01 * 31.999 * 0.9  # M10
        ia_kg_anno  = ((bio_kg * 0.2) / anni) * coeff  # O10

    valore_ecologico = (
        bio_kg       * _PREZZO_BIO +
        co2_kg_anno  * _PREZZO_CO2 +
        o2_kg_anno   * _PREZZO_O2  +
        ia_kg_anno   * _PREZZO_IA
    )

    return {
        'bio_kg':           round(bio_kg, 2),
        'co2_kg_anno':      round(co2_kg_anno, 2),
        'o2_kg_anno':       round(o2_kg_anno, 2),
        'ia_kg_anno':       round(ia_kg_anno, 2),
        'valore_ecologico': round(valore_ecologico, 2),
    }


def print_report(result: dict) -> None:
    """Print a human-readable assessment report."""
    labels = {
        'rami':     'Rottura branche/rami',
        'tronco':   'Rottura tronco/castello',
        'colletto': 'Rottura colletto',
        'zolla':    'Ribaltamento zolla radicale',
    }
    for phase in ('attuale', 'residuo'):
        title = 'RISCHIO ATTUALE' if phase == 'attuale' else 'RISCHIO RESIDUO'
        d = result[phase]
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}")
        print(f"  Chioma → impulso: {d['crown_momentum_kgms']:.1f} kg·m/s  (class {d['crown_impulso_class']})")
        print(f"  Ramo   → impulso: {d['branch_momentum_kgms']:.1f} kg·m/s  (class {d['branch_impulso_class']})")
        for key, label in labels.items():
            e = d[key]
            p, b, i = e['pericolo_class'], e['bersaglio_class'], e['impulso_class']
            ratio = e['risk_ratio']
            desc  = e['risk_description']
            print(f"\n  {label}")
            print(f"    Pericolo {p}  ×  Bersaglio {b}  ×  Impulso {i}  →  {ratio}")
            print(f"    {desc}")


# ---------------------------------------------------------------------------
# EXAMPLE
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    result = assess_tree(
        # Current dimensions
        tree_height_m=15.0,
        circumference_cm=120.0,   # trunk circumference at 1.3 m
        crown_diam_m=8.0,
        branch_diam_cm=12.0,
        branch_length_m=4.0,
        branch_height_m=8.0,
        target_height_m=1.8,      # standing person

        # Pericolo (1=worst … 7=best, 0=suspended)
        pericolo_rami=4,
        pericolo_tronco=5,
        pericolo_colletto=6,
        pericolo_zolla=6,

        # Bersaglio (1=most exposed … 7=least exposed)
        bersaglio_chioma=3,
        bersaglio_ramo=3,

        # Post-intervention: branches pruned → reduced branch length
        post_branch_length_m=2.5,
        post_branch_height_m=8.0,
    )

    print_report(result)

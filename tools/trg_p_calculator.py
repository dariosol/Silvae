"""
ARETE TRG-P sheet calculator - replicates the calculations from sheet 2 (TRG-P).

TRG-P = Triage for tree populations (TRIAGE - P, popolamenti arborei).
It is a faster screening tool compared to the full ORD assessment.

Key differences from ORD
-------------------------
- Single risk assessment (no post-intervention / residuo)
- Different pericolo scale: uses the *triage* danger descriptions (A!B17:C23)
  rather than the quantitative failure-probability descriptions used by ORD
- Risk output mapped to a triage intervention category (1-6)
- Includes an ornamental value estimate (Valore Ornamentale)

Risk calculation logic
----------------------
Same 3-class key as ORD: str(B) + str(I) + str(P)
  B = Bersaglio class 1-7  (exposure/target occupancy)
  I = Impulso class 1-7    (computed from tree geometry, 1=highest energy)
  P = Pericolo class 1-7   (triage danger perception, 1=most dangerous)

The per-failure-mode risk ratio is looked up in the same risk matrix as ORD.
Then each ratio is mapped to a numeric triage category (1-6) and the
*worst* (lowest number) across all four failure modes drives the overall
triage intervention label.

Failure modes
-------------
  • Rottura branche/rami     (branch failure)   → uses branch impulso + ramo bersaglio
  • Rottura tronco/castello  (trunk failure)    → uses crown impulso + chioma bersaglio
  • Rottura colletto         (collar failure)   → uses crown impulso + chioma bersaglio
  • Rib./sciv. zolla         (root-plate)       → uses crown impulso + chioma bersaglio

Ornamental value (Valore Ornamentale)
--------------------------------------
Computed via a piecewise logistic model that combines:
  • Tree size (circumference, crown diameter, height)
  • Locality factors (dimora, stadio sviluppo, posizione sociale, localizzazione, vincoli)
  • Species baseline value
  • Phytosanitary/health depreciation percentage
The result is the depreciated ornamental value in €.
"""

import math
from typing import Literal

# Re-use the shared risk matrix and impulso helpers from ord_calculator
from tools.ord_calculator import (
    RISK_MATRIX,
    RISK_PROBABILITY,
    impulso_to_class,
    calc_crown_momentum,
    calc_branch_momentum,
)


# ---------------------------------------------------------------------------
# PERICOLO (triage danger) descriptions  (sheet A, B17:C23)
# Different from ORD – these are qualitative triage observations, not
# quantitative failure-probability brackets.
# ---------------------------------------------------------------------------
PERICOLO_TRIAGE_DESCRIPTION: dict[int, str] = {
    1: "Segni sintomi e difetti molto gravi, connessi strettamente con un possibile cedimento immediato",
    2: "Segni sintomi e difetti gravi, connessi strettamente con un possibile cedimento imminente",
    3: "Segni sintomi e difetti significativi, connessi strett. con un possibile cedimento in cond. critiche",
    4: "Segni sintomi e difetti incerti, connessi occasionalmente con un possibile cedimento",
    5: "Segni sintomi e difetti moderati, non chiaramente connessi con un possibile cedimento",
    6: "Segni sintomi e difetti modesti, non connessi con un possibile cedimento",
    7: "Segni sintomi e difetti trascurabili o sostanzialmente assenti",
    0: "Valutazione sospesa",
}

# ---------------------------------------------------------------------------
# RISK LEVEL descriptions for triage  (sheet A, AP24:AQ41)
# Different wording from ORD's AP4:AQ21
# ---------------------------------------------------------------------------
TRIAGE_RISK_LEVEL: dict[str, str] = {
    '1:3':    "EMERGENZA - Risoluzione dell'emergenza",
    '1:20':   "EMERGENZA - Risoluzione dell'emergenza",
    '1:100':  "EMERGENZA - Risoluzione dell'emergenza",
    '1:200':  "EMERGENZA - Risoluzione dell'emergenza",
    '1:800':  "EMERGENZA - Risoluzione dell'emergenza",
    '1:1k':   "EMERGENZA - Risoluzione dell'emergenza",
    '1:2k':   "EMERGENZA - Valutazione immediata - risoluzione dell'emergenza",
    '1:8k':   "EMERGENZA - Valutazione immediata - risoluzione dell'emergenza",
    '1:10k':  "URGENZA - Valutazione urgente",
    '1:12k':  "URGENZA - Valutazione urgente",
    '1:20k':  "MODERATA - valutazione opportuna entro breve tempo",
    '1:80k':  "MODERATA - valutazione opportuna entro breve tempo",
    '1:120k': "MODERATA - valutazione opportuna entro breve tempo",
    '1:130k': "MODERATA - valutazione opportuna entro breve tempo",
    '1:200k': "BASSA - valutazione opportuna ma non urgente",
    '1:800k': "BASSA - valutazione opportuna ma non urgente",
    '1:1M':   "BASSA - valutazione opportuna ma non urgente",
    '<1:1M':  "DIFFERIBILE - valutazione procrastinabile",
}

# Risk ratio → triage numeric category 1-6  (sheet TRG-P, AA26:AB43)
# 1 = most urgent (EMERGENZA), 6 = least urgent (DIFFERIBILE)
RISK_TO_TRIAGE_CAT: dict[str, int] = {
    '1:3':    1, '1:20':   1, '1:100':  1, '1:200':  1,
    '1:800':  1, '1:1k':   1,
    '1:2k':   2, '1:8k':   2,
    '1:10k':  3, '1:12k':  3,
    '1:20k':  4, '1:80k':  4, '1:120k': 4, '1:130k': 4,
    '1:200k': 5, '1:800k': 5, '1:1M':   5,
    '<1:1M':  6,
}

# Triage category → intervention label  (sheet A, AP44:AQ49)
TRIAGE_INTERVENTION: dict[int, str] = {
    1: "Risoluzione dell'emergenza",
    2: "Valutazione immediata - risoluzione dell'emergenza",
    3: "Valutazione urgente",
    4: "Valutazione opportuna entro breve tempo",
    5: "Valutazione opportuna ma non urgente",
    6: "Valutazione procrastinabile",
}


# ---------------------------------------------------------------------------
# ORNAMENTAL VALUE PARAMETERS  (sheet A)
# ---------------------------------------------------------------------------

# Sigmoid parameters for size components (rows 5-7, cols AY:BE)
#   (k, x0, threshold, k_plateau, threshold_plateau)  per dimension
_SIZE_SIGMOID_PARAMS = {
    # circumference at 1.3m (H9, cm): two-part logistic
    'circ': {
        'k_ascending':  45.0,   # AY5
        'x0_ascending': 0.15,   # AZ5
        'scale_asc':    2200.0, # BA5
        'threshold':    350.0,  # BB5
        'k_descending': 40.0,   # BC5
        'x0_desc':      0.06,   # BD5
        'scale_desc':   4500.0, # BE5
    },
    # crown diameter (J9, m): single logistic
    'crown_diam': {'k': 12.0, 'x0': 0.4, 'scale': 100.0},  # AY6, AZ6, BA6
    # tree height (C9, m): single logistic
    'height':     {'k': 35.0, 'x0': 0.22,'scale': 125.0},  # AY7, AZ7, BA7
}

# Ornamental value piecewise-sigmoid parameters by phytosanitary fitness class
# Fitness A=optimum … E=incoherent  (sheet A, BA8:BE12)
_FITNESS_PARAMS: dict[str, dict] = {
    'A': {'threshold': 0.59, 'k1': 12.0, 'k2': 12.0, 'x02': 0.58},
    'B': {'threshold': 0.66, 'k1': 15.0, 'k2':  9.5, 'x02': 0.65},
    'C': {'threshold': 0.72, 'k1': 17.0, 'k2':  8.6, 'x02': 0.72},
    'D': {'threshold': 0.77, 'k1': 19.0, 'k2':  8.3, 'x02': 0.79},
    'E': {'threshold': 0.82, 'k1': 21.0, 'k2':  8.2, 'x02': 0.86},
}

# Locality / context bonus factors (sheet A, various lookup tables)
DIMORA_SCORE: dict[str, float] = {}      # A!V4:W27  – location type bonus
STADIO_SCORE: dict[str, float] = {}      # A!S4:T10  – development stage bonus
POS_SOCIALE_SCORE: dict[str, float] = {}# A!Y4:Z12  – social position bonus
LOCALIZ_SCORE: dict[str, float] = {}    # A!AB4:AC11 – localization bonus
VINCOLI_SCORE: dict[str, float] = {}    # A!AE4:AF9  – regulatory constraint bonus (already embedded below)

VINCOLI_SCORE = {
    '---': 0.0,
    '> soglia comunale': 6.0,
    'paesaggistico': 8.0,
    'dichiaraz. di rilevanza': 10.0,
    'storico-architettonico': 12.0,
    'monumentale': 14.0,
}

# Phytosanitary/health depreciation % (sheet A, AU35:AV45)
HEALTH_DEPRECIATION: dict[str, float] = {
    'Condizioni ottimali – albero integro': 0.0,
    'Condizioni ottimali – lievemente alterato': 5.0,
    'Condizioni buone': 15.0,
    'Condizioni buone – albero strutturalmente alterato': 20.0,
    'Condizioni mediocri': 25.0,
    'Condizioni mediocri – albero strutturalmente alterato': 30.0,
    'Condizioni scadenti': 40.0,
    'Condizioni scadenti – albero molto alterato': 50.0,
    'Condizioni pessime': 60.0,
    'Condizioni pessime – albero fortemente deperiente': 70.0,
    'Albero morto in piedi': 90.0,
}


# ---------------------------------------------------------------------------
# ORNAMENTAL VALUE FUNCTIONS
# ---------------------------------------------------------------------------

def _sigmoid(k: float, x: float, x0: float) -> float:
    """Standard logistic: 1 / (1 + exp(-k*(x - x0)))"""
    return 1.0 / (1.0 + math.exp(-k * (x - x0)))


def calc_size_value(
    circumference_cm: float,
    crown_diam_m: float,
    tree_height_m: float,
) -> float:
    """
    Compute the composite tree-size value in [0,1].

    Replicates AE3 + AE4 + AE5 → AE6.
    Each dimension is mapped through a logistic to [0,1], then combined as:
      composite = MAX + (1 - MAX) * ((SUM - MAX) / 2)
    This gives the maximum score weighted by the other two.
    """
    p = _SIZE_SIGMOID_PARAMS

    # Circumference: two-part logistic (below/above threshold)
    cp = p['circ']
    if circumference_cm < cp['threshold']:
        s_circ = _sigmoid(cp['k_ascending'],  circumference_cm / cp['scale_asc'],  cp['x0_ascending'])
    else:
        s_circ = _sigmoid(cp['k_descending'], circumference_cm / cp['scale_desc'], cp['x0_desc'])

    s_crown = _sigmoid(p['crown_diam']['k'], crown_diam_m  / p['crown_diam']['scale'], p['crown_diam']['x0'])
    s_height= _sigmoid(p['height']['k'],     tree_height_m / p['height']['scale'],     p['height']['x0'])

    max_s = max(s_circ, s_crown, s_height)
    sum_s = s_circ + s_crown + s_height
    return max_s + (1 - max_s) * ((sum_s - max_s) / 2)


def calc_locality_factor(
    dimora_score: float = 0.0,
    stadio_score: float = 0.0,
    pos_sociale_score: float = 0.0,
    localiz_score: float = 0.0,
    vincoli_score: float = 0.0,
) -> float:
    """
    Compute locality/context bonus factor [0,1].

    Replicates AE7 = (AB2 + AB4 + AB6 + AB8 + AB10) / 100.
    Pass the numeric score for each category (from the respective lookup table).
    """
    return (dimora_score + stadio_score + pos_sociale_score + localiz_score + vincoli_score) / 100.0


def calc_combined_value(size_value: float, locality_factor: float) -> float:
    """
    Combine size and locality into one score [0,1].
    Replicates AE8 = AE6 + (1 - AE6) * AE7
    """
    return size_value + (1.0 - size_value) * locality_factor


def calc_ornamental_value(
    combined_value: float,
    species_baseline_eur: float,
    fitness_class: Literal['A', 'B', 'C', 'D', 'E'],
    health_depreciation_pct: float,
) -> dict:
    """
    Compute ornamental value after applying species baseline, fitness, and health.

    Replicates AE11 (theoretical value) and AE12 (depreciated value).

    Parameters
    ----------
    combined_value        : AE8 – combined size+locality score [0,1]
    species_baseline_eur  : AE9 – species baseline ornamental value in €
                            (from A!AI4:AK110, column AK = the value in €)
    fitness_class         : AE10 – phytosanitary coherence class A-E
    health_depreciation_pct : AB12 – health depreciation % (0-90)

    Returns
    -------
    dict with 'theoretical_eur' and 'depreciated_eur'
    """
    fp = _FITNESS_PARAMS[fitness_class]
    threshold = fp['threshold']
    k1, k2, x02 = fp['k1'], fp['k2'], fp['x02']

    if combined_value == 0:
        theoretical = 0.0
    elif combined_value < threshold:
        theoretical = species_baseline_eur * _sigmoid(k2, combined_value, x02)
    else:
        theoretical = species_baseline_eur * _sigmoid(k1, combined_value, threshold)

    depreciated = theoretical - theoretical * (health_depreciation_pct / 100.0)
    return {
        'theoretical_eur': round(theoretical, 2),
        'depreciated_eur': round(depreciated, 2),
    }


# ---------------------------------------------------------------------------
# CORE RISK ASSESSMENT
# ---------------------------------------------------------------------------

def calc_risk_ratio(
    bersaglio_class: int,
    impulso_class: int,
    pericolo_class: int,
) -> str:
    """
    Look up the risk ratio string for the given 3-class combination.

    Returns "SOSPESO" when pericolo_class == 0.
    Same logic as ORD – key = str(B)+str(I)+str(P).
    """
    if pericolo_class == 0:
        return "SOSPESO"
    key = f"{bersaglio_class}{impulso_class}{pericolo_class}"
    return RISK_MATRIX.get(key, '<1:1M')


def triage_category(risk_ratio: str) -> int | None:
    """Convert a risk ratio string to triage category 1-6 (None if suspended)."""
    if risk_ratio == "SOSPESO":
        return None
    return RISK_TO_TRIAGE_CAT.get(risk_ratio, 6)


def assess_tree(
    # --- General dimensions ---
    tree_height_m: float,       # H  (C9)
    circumference_cm: float,    # Circ at 1.3m  (H9 = E9*PI(), so pass circ directly)
    crown_diam_m: float,        # D ch  (I9)
    branch_diam_cm: float,      # D br  (L9)
    branch_length_m: float,     # L br  (N9)
    branch_height_m: float,     # H br  (Q9)
    target_height_m: float,     # H bers  (S9/T9)

    # --- Pericolo triage classes (1-7, or 0=sospeso) ---
    pericolo_rami: int,         # E11
    pericolo_tronco: int,       # E12
    pericolo_colletto: int,     # E13
    pericolo_zolla: int,        # E14

    # --- Bersaglio classes (1-7, 1=most exposed) ---
    bersaglio_chioma: int,      # I17 – from C18 dropdown
    bersaglio_ramo: int,        # R17 – from M18 dropdown
) -> dict:
    """
    Compute TRIAGE DEL RISCHIO for all four failure modes.

    Returns a dict with:
      crown_momentum_kgms, crown_impulso_class,
      branch_momentum_kgms, branch_impulso_class,
      rami, tronco, colletto, zolla  → each a dict with:
        pericolo_class, bersaglio_class, impulso_class,
        risk_key, risk_ratio, triage_risk_level, triage_category
      overall_triage_category  (int 1-6, worst/lowest across failure modes)
      overall_triage_action    (str)
    """
    crown_mom  = calc_crown_momentum(circumference_cm, tree_height_m, target_height_m)
    branch_mom = calc_branch_momentum(branch_diam_cm, branch_length_m, branch_height_m, target_height_m)
    crown_imp  = impulso_to_class(crown_mom)
    branch_imp = impulso_to_class(branch_mom)

    def _entry(pericolo, bersaglio, imp):
        ratio = calc_risk_ratio(bersaglio, imp, pericolo)
        cat   = triage_category(ratio)
        return {
            'pericolo_class':     pericolo,
            'bersaglio_class':    bersaglio,
            'impulso_class':      imp,
            'risk_key':           f"{bersaglio}{imp}{pericolo}" if pericolo else "SOSPESO",
            'risk_ratio':         ratio,
            'triage_risk_level':  TRIAGE_RISK_LEVEL.get(ratio, 'non determinato'),
            'triage_category':    cat,
        }

    results = {
        'crown_momentum_kgms':  round(crown_mom,  2),
        'crown_impulso_class':  crown_imp,
        'branch_momentum_kgms': round(branch_mom, 2),
        'branch_impulso_class': branch_imp,
        'rami':     _entry(pericolo_rami,     bersaglio_ramo,   branch_imp),
        'tronco':   _entry(pericolo_tronco,   bersaglio_chioma, crown_imp),
        'colletto': _entry(pericolo_colletto, bersaglio_chioma, crown_imp),
        'zolla':    _entry(pericolo_zolla,    bersaglio_chioma, crown_imp),
    }

    # Overall triage = worst (minimum) category across all non-suspended modes
    cats = [
        results[k]['triage_category']
        for k in ('rami', 'tronco', 'colletto', 'zolla')
        if results[k]['triage_category'] is not None
    ]
    overall = min(cats) if cats else None
    results['overall_triage_category'] = overall
    results['overall_triage_action']   = TRIAGE_INTERVENTION.get(overall, 'non determinato') if overall else 'SOSPESO'

    return results


def print_report(result: dict) -> None:
    """Print a human-readable triage report."""
    labels = {
        'rami':     'Rottura branche/rami',
        'tronco':   'Rottura tronco/castello',
        'colletto': 'Rottura colletto',
        'zolla':    'Ribaltamento/sciv. zolla radicale',
    }
    print(f"\n{'='*70}")
    print("  TRIAGE DEL RISCHIO (TRG-P)")
    print(f"{'='*70}")
    print(f"  Chioma → impulso: {result['crown_momentum_kgms']:.1f} kg·m/s  (class {result['crown_impulso_class']})")
    print(f"  Ramo   → impulso: {result['branch_momentum_kgms']:.1f} kg·m/s  (class {result['branch_impulso_class']})")

    for key, label in labels.items():
        e = result[key]
        p, b, i = e['pericolo_class'], e['bersaglio_class'], e['impulso_class']
        ratio = e['risk_ratio']
        cat   = e['triage_category']
        level = e['triage_risk_level']
        print(f"\n  {label}")
        print(f"    Pericolo {p}  ×  Bersaglio {b}  ×  Impulso {i}  →  {ratio}  [cat. {cat}]")
        print(f"    {level}")

    overall = result['overall_triage_category']
    action  = result['overall_triage_action']
    print(f"\n{'─'*70}")
    print(f"  RISULTATO TRIAGE:  categoria {overall}  →  {action}")
    print(f"{'─'*70}")


# ---------------------------------------------------------------------------
# EXAMPLE
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    # Risk triage
    result = assess_tree(
        tree_height_m=15.0,
        circumference_cm=120.0,
        crown_diam_m=8.0,
        branch_diam_cm=12.0,
        branch_length_m=4.0,
        branch_height_m=8.0,
        target_height_m=1.8,

        # Triage pericolo (1=gravissimo … 7=trascurabile)
        pericolo_rami=3,
        pericolo_tronco=4,
        pericolo_colletto=5,
        pericolo_zolla=5,

        # Bersaglio (1=massima esposizione … 7=minima)
        bersaglio_chioma=3,
        bersaglio_ramo=3,
    )
    print_report(result)

    # Ornamental value example
    size_val = calc_size_value(
        circumference_cm=120.0,
        crown_diam_m=8.0,
        tree_height_m=15.0,
    )
    locality = calc_locality_factor(
        dimora_score=20.0,
        stadio_score=10.0,
        pos_sociale_score=15.0,
        localiz_score=5.0,
        vincoli_score=0.0,
    )
    combined = calc_combined_value(size_val, locality)
    orn = calc_ornamental_value(
        combined_value=combined,
        species_baseline_eur=110000.0,   # e.g. Platanus x acerifolia
        fitness_class='B',
        health_depreciation_pct=20.0,
    )

    print(f"\n{'='*70}")
    print("  VALORE ORNAMENTALE")
    print(f"{'='*70}")
    print(f"  Size value (AE6):     {size_val:.4f}")
    print(f"  Locality factor (AE7):{locality:.4f}")
    print(f"  Combined (AE8):       {combined:.4f}")
    print(f"  Valore teorico (AE11):  € {orn['theoretical_eur']:,.2f}")
    print(f"  Valore deprezzato (AE12):€ {orn['depreciated_eur']:,.2f}")

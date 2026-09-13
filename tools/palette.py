"""
Tavolozza dei colori di Silvae Pro — UNICA fonte di verità.

Ogni colore che rappresenta una classe di rischio ARETE o una condizione
VTA/CPC (badge, chip statistici, marker sulla mappa, stile QGIS) parte da
qui.  Per cambiare un colore si modifica questo file: la webapp lo riceve
come variabili CSS da `GET /palette.css` e il frontend le legge da lì; lo
stile QGIS (.qml) viene generato dagli stessi valori.

Per ogni categoria:
  main  colore pieno (marker mappa, simbolo QGIS, pallino nella tabella)
  fg    colore del testo dei badge / chip
  bg    colore di sfondo dei badge / chip
"""

# Classi di rischio ORD (fase attuale, peggiore tra rami/tronco/colletto/zolla).
# Le chiavi coincidono con riskStatCategory() nel frontend e _risk_category() in app.py.
RISK = [
    {'key': 'accettabile',   'label': 'Accettabile',   'main': '#2d6a4f', 'fg': '#2d6a4f', 'bg': '#d4edda',
     'hint': 'rischio largamente accettabile'},
    {'key': 'alarp',         'label': 'ALARP',         'main': '#d9a400', 'fg': '#856404', 'bg': '#fef3cd',
     'hint': 'rischio tollerabile / ALARP'},
    {'key': 'accordo',       'label': 'Per accordo',   'main': '#e67e22', 'fg': '#9a4a06', 'bg': '#ffe5cc',
     'hint': 'tollerabile per accordo, inaccettabile se imposto a terzi'},
    {'key': 'inaccettabile', 'label': 'Inaccettabile', 'main': '#c0392b', 'fg': '#c0392b', 'bg': '#fde8e8',
     'hint': 'rischio inaccettabile — intervento necessario'},
    {'key': 'na',            'label': 'Non valutato',  'main': '#adb5bd', 'fg': '#6c757d', 'bg': '#e9ecef',
     'hint': 'rischio non calcolato o sospeso'},
]

# Condizione / classe VTA-CPC. Le chiavi coincidono con condCategory() nel frontend.
CONDITION = [
    {'key': 'good',  'label': 'Ottimo',           'cpc': 'A',        'main': '#2d6a4f', 'fg': '#1b5e2a', 'bg': '#d8f3dc'},
    {'key': 'buono', 'label': 'Buono',            'cpc': 'B',        'main': '#52b788', 'fg': '#2d6a4f', 'bg': '#eaf7ef'},
    {'key': 'fair',  'label': 'Discreto',         'cpc': 'C',        'main': '#e67e22', 'fg': '#9a4a06', 'bg': '#ffe5cc'},
    {'key': 'poor',  'label': 'Scarso / Critico', 'cpc': 'C/D, D',   'main': '#c0392b', 'fg': '#842029', 'bg': '#f8d7da'},
    {'key': 'other', 'label': 'Non classificato', 'cpc': '',         'main': '#adb5bd', 'fg': '#495057', 'bg': '#e9ecef'},
]

GROUPS = {'risk': RISK, 'cond': CONDITION}


def by_key(group, key):
    """Voce della tavolozza per gruppo ('risk'|'cond') e chiave, o None."""
    return next((e for e in GROUPS[group] if e['key'] == key), None)


def css_vars():
    """Blocco `:root { ... }` con una variabile per colore:
    --risk-<key>, --risk-<key>-fg, --risk-<key>-bg e idem --cond-<key>."""
    lines = [':root {']
    for group, entries in GROUPS.items():
        for e in entries:
            lines.append(f"  --{group}-{e['key']}: {e['main']};")
            lines.append(f"  --{group}-{e['key']}-fg: {e['fg']};")
            lines.append(f"  --{group}-{e['key']}-bg: {e['bg']};")
    lines.append('}')
    return '\n'.join(lines) + '\n'


def as_dict():
    """Rappresentazione JSON-friendly (per API o strumenti esterni)."""
    return {g: [dict(e) for e in entries] for g, entries in GROUPS.items()}

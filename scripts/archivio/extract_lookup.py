import openpyxl

import os
# Percorsi calcolati dalla posizione dello script, così funziona su qualunque
# macchina e da qualunque cartella (prima erano cablati su /home/dario).
RADICE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join(RADICE, 'Schede_Rilevamento_ARETE',
                        'Schede_Rilevamento_ARETE_DEMO_ver.2.0.xlsm')
USCITA = os.path.join(RADICE, 'Schede_Rilevamento_ARETE', 'lookup_tables.py')


# Load the workbook
wb = openpyxl.load_workbook(TEMPLATE)

# Get sheet A
sheet = wb['A']

# Initialize dict
lookup_dict = {}

# Iterate through rows
for row in sheet.iter_rows(values_only=True):
    if row[10] and row[11]:  # Assuming columns 10 and 11 (0-indexed 10 and 11)
        name = row[10].strip()
        code = row[11].strip()
        lookup_dict[code] = name

# Write to file
with open(USCITA, 'w') as f:
    f.write('# Lookup tables from sheet A\n')
    f.write('species_lookup = {\n')
    for code, name in lookup_dict.items():
        f.write(f'    "{code}": "{name}",\n')
    f.write('}\n')
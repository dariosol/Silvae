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

# Print all data
for row in sheet.iter_rows(values_only=True):
    print(row)
import openpyxl

# Load the workbook
wb = openpyxl.load_workbook('/home/dario/tree_project/Schede_Rilevamento_ARETE/Schede_Rilevamento_ARETE_DEMO_ver.2.0.xlsm')

# Get sheet A
sheet = wb['A']

# Print all data
for row in sheet.iter_rows(values_only=True):
    print(row)
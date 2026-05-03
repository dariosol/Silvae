import pandas as pd

# Read the Excel sheet
df = pd.read_excel('/home/dario/tree_project/Schede_Rilevamento_ARETE/Schede_Rilevamento_ARETE_DEMO_ver.2.0.xlsm', sheet_name='A', header=None)

# Define the columns for the categories
categories = {
    "monitoraggio": 4,
    "urgenza": 6,
    "conflitti": 8,
    "agenti_di_carie": 13,
    "altri_patogeni": 15,
    "prescrizioni_valutative": 46,  # Assuming CONDIZIONI FITOSANITARIE
    "prescrizione_migrazione": 41,  # Assuming RISCHIO PER L'ORDINARIA or something
}

# Extract lists
lists = {}
for name, col in categories.items():
    values = df.iloc[3:, col].dropna().tolist()  # Start from row 3
    lists[name] = values

# Print the lists
for name, lst in lists.items():
    print(f"{name}: {lst}")

# Now, write to the lookup_tables.py file
with open('/home/dario/tree_project/Schede_Rilevamento_ARETE/lookup_tables.py', 'a') as f:
    f.write('\n# Additional lookup lists\n')
    for name, lst in lists.items():
        f.write(f'{name} = {lst}\n')
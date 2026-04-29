"""
Dropdown choices for the ORD (and TRG-P) sheet of the ARETE form.

Sources
-------
- Diagnostic defect lists (caratteri): hidden columns AA-AK of the ORD sheet
- General data dropdowns: sheet A, various columns
- Pericolo keys: sheet A, B4:B14

Sheet section → dropdowns used
-------------------------------
DATI GENERALI (rows 6-9)
  dimora          → cell C7, choices from `dimora`
  stadio_sviluppo → cell M7, choices from `stadio_sviluppo`
  pos_sociale     → cell J7, choices from `posizione_sociale`  (A!Y4:Y12)
  localizzazione  → cell G7, choices from `localizzazione`
  vincoli         → cell S7, choices from `vincoli`

DIAGNOSI – CARATTERI (rows 14-24, columns per anatomical part)
  Each cell shows a dropdown of anatomical characters / defects / symptoms.
  Alongside every entry the professional selects a severity judgment:
    'ps' = poco significativo
    's'  = significativo
    'ms' = molto significativo
  (Judgment choices are in `giudizio_severita`)

  zolla_radicale     → columns B-F, rows 14-24  (AA2:AA45)
  caratteri_colletto → columns G-K, rows 14-24  (AC2:AC62)
  caratteri_fusto    → columns L-P, rows 14-19  (AE2:AE70)
  caratteri_castello → columns L-P, rows 20-24  (AG2:AG64)
  caratteri_rami     → columns Q-T, rows 14-19  (AI2:AI75)
  caratteri_chioma   → columns Q-T, rows 20-24  (AK2:AK37)

GRADO DI PERICOLO (rows 26-29)
  E26-E29 → choices from `pericolo_keys` (numeric 1-7 + suspension codes)

BERSAGLIO (rows 31-33 for current, rows 50-52 for residual)
  The bersaglio class cells (B33, M33, B52, M52) are driven by the target-type
  selection (BQ7/BQ20) and show time/occupancy descriptions; the class 1-7
  is then resolved via VLOOKUP. See ord_calculator.py for the class-based API.
"""

# ---------------------------------------------------------------------------
# DIAGNOSTIC SECTION – anatomical part characters / defects / symptoms
# ---------------------------------------------------------------------------

# ORD sheet, AA2:AA45  – zolla radicale, stazione, radici
zolla_radicale: list[str] = [
    # Caratteri stazione
    'compattazione',
    'competizione radicale',
    'erosione',
    'pavimentazione',
    'ristagno idrico',
    'rottura suolo (fessure)',
    'scavi o trincee',
    'sollevamento manufatti',
    # Caratteri zolla
    'platea radicale',
    'ricarico zolla',
    'sollevamento zolla',
    'sprofondamento zolla',
    'zolla asimmetrica',
    'zolla danneggiata',
    'zolla limitata / ridotta',
    'zolla/suolo separati',
    # Caratteri radici
    'esploratrici esposte',
    'polloni radicali',
    'noduli in superficie',
    'radici affioranti',
    'radici avventizie',
    'radici avvolgenti',
    'radici decorticate',
    'radici esposte',
    'radici fini visibili',
    'radici migranti',
    'radici non visibili',
    'radici scoperte',
    'radici strozzanti',
    'radici tagliate',
    # Difetti bio / strutturali
    'carie/marciume radicale',
    'carpofori',
    'ferite aperte',
    'ferite richiuse',
    'Inclusione/contatto',
    'legno disfunzionale',
    'necrosi radicali',
    'non valutabile',
]

# ORD sheet, AC2:AC62  – colletto
caratteri_colletto: list[str] = [
    # Caratteri morfologici
    'colletto a contrafforti',
    'colletto a gradino',
    'colletto a imbuto',
    'colletto a palafitta',
    'colletto asimmetrico',
    'colletto azzampato',
    'colletto cilindrico',
    'colletto cordonato',
    'colletto normale',
    'colletto ovalizzato',
    'colletto sepolto',
    'collo bottiglia',
    'affondam in comprex',
    'cordoni xilematici',
    'cordoni non più attivi',
    'corna di ariete',
    'cucitura',
    'piatto morfologico',
    'pieghe a molla',
    'pieghe fisarmonica',
    'polloni',
    'ponte xilematico su cretto',
    'rialzamento in traz.',
    'rigonf. anello',
    'spiralizzazione fibre',
    'succhioni',
    # Difetti strutturali
    'abrasioni',
    'apertura',
    'aree funzionali inattive',
    'bruciatura',
    'bucature',
    'carie basale',
    'carpofori',
    'cavità',
    'cretti elicoidali',
    'cretti orizz',
    'cretti vert.',
    'danni alburno/cortic',
    'delaminazione',
    'depressione',
    'essudati/resinaz',
    'ferite richiuse',
    'fessure',
    'gibbosità',
    'incavo',
    'inclusione/contatto',
    'legno da ferita attivo',
    'legno disfunzionale',
    'legno reazione insuff',
    'neoplasie/cancri',
    'penetrazione',
    # Difetti bio
    'alteraz da animali',
    'batteriosi',
    'insetti/danni insetti',
    'parassiti/epifite',
    'non valutabile',
]

# ORD sheet, AE2:AE70  – fusto (trunk / main stem)
caratteri_fusto: list[str] = [
    # Caratteri morfologici
    'fusto regolare',
    'fusto bi (tri)forcato',
    'fusto policormico',
    'fusto asimmetrico',
    'fusto costolato',
    'fusto sciabolato',
    'perdita leader',
    'aree funzionali inattive',
    'carico in punta',
    'cordoni xilematici',
    'corna di ariete',
    'cucitura',
    'inclinaz. Arcuatura',
    'inclinaz. Sciabolatura',
    'inclinazione lineare',
    'piega a S',
    'pieghe fisarmonica',
    'ponte xilematico su cretto',
    'reiterati ageotropi',
    'reiterati ortotropi',
    'reiterati plagiotropi',
    'rigonf. anello',
    'sinuosità',
    'snellezza',
    'spiralizzazione fibre',
    'strozzatura',
    # Difetti strutturali
    'abrasioni',
    'apertura',
    'bombatura',
    'bruciatura',
    'bucature',
    'carie',
    'carpofori',
    'cavità',
    'corteccia inclusa',
    "cretti all'inserz.",
    'cretti elicoidali',
    'cretti orizz',
    'cretti vert.',
    'danni alburno/cortic',
    'delaminazione',
    "deprex all'inserz.",
    'deviazione',
    'essudati/resinaz',
    'ferite radiali',
    'ferite richiuse',
    'fessure',
    'Getti epicormici',
    'gibbosità',
    'incavo',
    'inclusione/anastomosi',
    'inserzione stretta',
    'legno da ferita attivo',
    'legno disfunzionale',
    'legno reazione insuff',
    'monconi',
    'mozziconi',
    'neoplasie/cancri',
    'scosciature',
    # Difetti bio
    'alteraz da animali',
    'batteriosi',
    'insetti/danni insetti',
    'parassiti/epifite',
    'non valutabile',
]

# ORD sheet, AG2:AG64  – castello (scaffold branches)
caratteri_castello: list[str] = [
    # Caratteri morfologici
    'cast. con sbrancamento',
    'castello a cespuglio',
    'castello a torrioni',
    'castello allargato',
    'castello assente',
    'castello regolare',
    'codominanza',
    'aree funzionali inattive',
    'corna di ariete',
    'cucitura',
    'pieghe fisarmonica',
    'reiterati ageotropi',
    'reiterati ortotropi',
    'reiterati plagiotropi',
    'rigonf. anello',
    'spiralizzazione fibre',
    'ponte xilematico su cretto',
    'colonne xilematiche',
    # Difetti strutturali
    'abrasioni',
    'apertura',
    'bombatura',
    'bruciatura',
    'bucature',
    'carie',
    'carpofori',
    'cavità',
    'corteccia inclusa',
    "cretti all'inserz.",
    'cretti elicoidali',
    'cretti orizz',
    'cretti vert.',
    'danni alburno/cortic',
    'delaminazione',
    'ferite radiali',
    'ferite richiuse',
    'fessure',
    'gibbosità',
    'incavo',
    'inclusione/anastomosi',
    'inserzione debole',
    'inserzione stretta',
    'legno da ferita attivo',
    'legno disfunzionale',
    'legno reazione insuff',
    'monconi',
    'mozziconi',
    'naso bulldog',
    'naso pinocchio',
    'neoplasie/cancri',
    'resinaz/essudati',
    'rigonfiamenti',
    'scosciature',
    'subsidenza',
    # Difetti bio
    'alteraz da animali',
    'batteriosi',
    'insetti/danni insetti',
    'parassiti/epifite',
    'non valutabile',
]

# ORD sheet, AI2:AI75  – ramificazione (branches / limbs)
caratteri_ramificazione: list[str] = [
    # Caratteri morfologici
    "conforme all'habitus",
    'rami candel/pennello',
    'rami sinuosi/arcuati',
    'ramificaz insufficiente',
    'ramificaz lacunosa',
    'aree funzionali inattive',
    'branca deperiente',
    'capitozzatura',
    'cedimenti pregressi',
    'corna di ariete',
    'cucitura',
    'disseccamenti branche',
    'disseccamenti rami',
    'disseccamenti ramuli',
    'end loading/codaleone',
    'fusticini epicormici',
    'pali su branche',
    'pali su fusto',
    'pieghe fisarmonica',
    'pipe',
    'rami patenti',
    'reiterati ageotropi',
    'reiterati ortotropi',
    'reiterati plagiotropi',
    'ricacci',
    'snellezza, ecc. L/D',
    'sostituti',
    'torsioni/pieghe',
    'unità minimali',
    'zampe di cane',
    # Difetti strutturali
    'abrasioni',
    'apertura',
    'banderuole',
    'bombatura',
    'bruciatura',
    'bucature',
    'carie',
    'carpofori',
    'cavità',
    'cavità a bicchiere',
    'corteccia inclusa',
    "cretti all'inserz.",
    'cretti elicoidali',
    'cretti orizz',
    'cretti vert.',
    'danni alburno/cortic',
    'delaminazione (t. sventura)',
    'ferite radiali',
    'ferite richiuse',
    'fessure',
    'incavo',
    'inclusione/anastomosi',
    'inser debole',
    'inserz orizzont',
    'inserzione stretta',
    'legno da ferita attivo',
    'legno disfunzionale',
    'legno reazione insuff',
    'monconi',
    'mozziconi',
    'neoplasie/cancri',
    'resinaz/essudati',
    'sbusidenza',
    'scosciature',
    # Difetti bio
    'alteraz da animali',
    'batteriosi',
    'insetti/danni insetti',
    'parassiti/epifite',
    'non valutabile',
]

# ORD sheet, AK2:AK37  – chioma (crown)
caratteri_chioma: list[str] = [
    # Caratteri morfologici
    "conforme all'habitus",
    'chioma a bandiera',
    'chioma a pennello',
    'chioma asimmetrica',
    'chioma diradata',
    'chioma esposta',
    'chioma lacunosa',
    'chioma separata',
    'chioma spalcata',
    'chioma ridotta',
    'chioma sana',
    'chioma stressata',
    'chioma resiliente',
    'ripiegamento della chioma',
    'discesa della cima',
    'deperim. irreversibile',
    'assenza leader',
    'compress laterale',
    'compress superior',
    'conflitti in chioma',
    'discontinuità corona',
    'LCR  ridotto',
    'trasparenza',
    'conflitto sostituti (false cime)',
    'nido di cicogna',
    'microfillia',
    'alteraz cromatica',
    'alteraz morfologica',
    'galle',
    'insetti o loro nidi',
    'necrosi fogliari',
    'non valutabile',
]

# ---------------------------------------------------------------------------
# GENERAL DATA SECTION (rows 6-9)
# ---------------------------------------------------------------------------

# A!V4:V27  – type of planting location (DIMORA, cell C7)
dimora: list[str] = [
    'prato',
    'scarpata',
    'terrapieno',
    'terreno coltivato',
    'terreno incolto',
    'buco asfalto',
    'area di pertinenza',
    'banchina stradale',
    'rimboschimento',
    'tornello',
    'aiuola',
    'bosco',
    'aiuola spartitraffico',
    'alberata stradale',
    'parcheggio',
    'gruppo/boschetto',
    'giardino recente',
    'filare arboreo',
    'piazza',
    'cimitero',
    'parco recente',
    'giardino storico',
    'parco storico',
]

# A!S4:S10  – development stage (STADIO DI SVILUPPO, cell M7)
stadio_sviluppo: list[str] = [
    'plantula',
    'giovane pianta',
    'albero giovane',
    'albero adulto',
    'albero maturo',
    'albero senescente',
    'albero veterano',
]

# A!Y4:Y12  – social position in stand (POSIZIONE SOCIALE, cell J7)
posizione_sociale: list[str] = [
    'oppressa',
    'dominata',
    'intermedia',
    'codominante',
    'dominante margine',
    'dominante interna',
    'predominante',
    'libera (p giovane)',
    'isolata',
]

# A!AB4:AB11 – localization / urban context (LOCALIZ, cell G7)
localizzazione: list[str] = [
    'aree rurali',
    'aree rurali urbaniz.',
    'aree industriali',
    'periferia recente',
    'periferia antica',
    'luoghi villeggiatura',
    'centro città',
    'centro storico',
]

# A!AE4:AE9  – regulatory constraints (Vincoli, cell S7)
vincoli: list[str] = [
    '---',
    '> soglia comunale',
    'paesaggistico',
    'dichiaraz. di rilevanza',
    'storico-architettonico',
    'monumentale',
]

# ---------------------------------------------------------------------------
# DIAGNOSTIC SEVERITY JUDGMENT  (cells F/K/P/U 15-24 of the ORD sheet)
# Applied to each observed defect entry.
# ---------------------------------------------------------------------------
# ORD!Y5:Y8
giudizio_severita: list[str] = [
    'ps',   # poco significativo
    's',    # significativo
    'ms',   # molto significativo
]

# ---------------------------------------------------------------------------
# PERICOLO – failure probability inputs (E26-E29 / E11-E14 in TRG-P)
# ---------------------------------------------------------------------------

# ORD pericolo keys with descriptions (sheet A, B4:C14)
pericolo_ord: dict = {
    1:           "Segni, sintomi e difetti gravissimi - Probabilità di cedimento nell'anno 1/1-1/5",
    2:           "Segni, sintomi e difetti gravi - Probabilità di cedimento nell'anno 1/5-1/50",
    3:           "Segni, sintomi e difetti significativi - Probabilità di cedimento nell'anno 1/50-1/500",
    4:           "Segni, sintomi e difetti incerti - Probabilità di cedimento nell'anno 1/500-1/5K",
    5:           "Segni, sintomi e difetti moderati - Probabilità di cedimento nell'anno 1/5K-1/50K",
    6:           "Segni, sintomi e difetti bassi - Probabilità di cedimento nell'anno 1/50K-1/500k",
    7:           "Segni, sintomi e difetti trascurabili - Probabilità di cedimento nell'anno 1/500K-1/1M",
    '0 x sospet':   'Valutazione sospesa - VALUTAZIONE SOSPESA',
    '0 x difetto':  'Valutazione sospesa - VALUTAZIONE SOSPESA',
    '0 x costituz': 'Valutazione sospesa - VALUTAZIONE SOSPESA',
    'N.S.':          'Non significativo',
}

# TRG-P pericolo keys with descriptions (sheet A, B17:C23)
pericolo_trg: dict[int, str] = {
    1: "Segni sintomi e difetti molto gravi, connessi strettamente con un possibile cedimento immediato",
    2: "Segni sintomi e difetti gravi, connessi strettamente con un possibile cedimento imminente",
    3: "Segni sintomi e difetti significativi, connessi strett. con un possibile cedimento in cond. critiche",
    4: "Segni sintomi e difetti incerti, connessi occasionalmente con un possibile cedimento",
    5: "Segni sintomi e difetti moderati, non chiaramente connessi con un possibile cedimento",
    6: "Segni sintomi e difetti modesti, non connessi con un possibile cedimento",
    7: "Segni sintomi e difetti trascurabili o sostanzialmente assenti",
}

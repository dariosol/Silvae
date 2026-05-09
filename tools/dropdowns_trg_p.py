"""
Dropdown choices for the TRG-P (Triage - Popolamenti Arborei) sheet of the ARETE form.

TRG-P differences vs ORD
-------------------------
- NO anatomical diagnostic defect columns (no per-part defect observation).
  TRG-P is a fast triage form: the professional enters a single qualitative
  pericolo class (1-7) per failure mode directly.
- Single risk assessment only (no RISCHIO RESIDUO).
- Pericolo classes are qualitative triage observations, not quantitative
  failure-probability brackets — use `pericolo_trg` from dropdowns_ord.py.
- Ornamental value (Valore Ornamentale) computed via piecewise logistic;
  requires `coerenza_fitoclimatica` and `condizioni_salute` below.

Shared items
------------
The following dropdowns are identical to ORD and are imported from dropdowns_ord:
  dimora, stadio_sviluppo, posizione_sociale, localizzazione, vincoli,
  pericolo_trg, giudizio_severita

Sheet section → dropdowns used
-------------------------------
DATI GENERALI (rows 6-9)
  dimora           → cell B7,  choices from `dimora`        (dropdowns_ord)
  localizzazione   → cell E7,  choices from `localizzazione` (dropdowns_ord)
  posizione_sociale→ cell I7,  choices from `posizione_sociale` (dropdowns_ord)
  stadio_sviluppo  → cell M7,  choices from `stadio_sviluppo` (dropdowns_ord)
  specie           → cell I6,  choices from `species_list`

GRADO DI PERICOLO PERCEPITO (rows 10-14)
  B11-B14 → choices from `pericolo_trg`  (dropdowns_ord)

VALUTAZIONE BERSAGLIO E IMPULSO (rows 15-18)
  BD5  / BD18 : Tipo di Bersaglio → choices from `bersaglio_tipo`
  C18:H18     : Bersaglio chioma class descriptions (BD7:BD13, formula-driven)
  M18:Q18     : Bersaglio rami class descriptions  (BD20:BD26, formula-driven)
  The class description cells are populated automatically from the
  tipo-di-bersaglio selection. Pass the class (1-7) directly to
  trg_p_calculator.py — see bersaglio_manufatti / bersaglio_occupazione for
  the class-to-description mapping.

VALORE ORNAMENTALE
  coerenza_fitoclimatica → fitness class A-E used as input to ornamental calc
  condizioni_salute      → health condition description → depreciation %
"""

# ---------------------------------------------------------------------------
# BERSAGLIO TIPO  (sheet A, BG4:BG11)
# The user selects one of these 8 target types; the sheet then auto-populates
# the bersaglio class (1-7) descriptions via IF/VLOOKUP formulas.
# ---------------------------------------------------------------------------

bersaglio_tipo: list[str] = [
    'proprietà',          # class resolved via manufatti damage-value brackets
    'occupazione',        # class resolved via occupancy-time brackets
    'pedoni/ciclisti',    # class resolved via transit-time calculation
    'traffico 30 km/h',   # class resolved via vehicle-transit-time calculation
    'traffico 50 km/h',
    'traffico 70 km/h',
    'traffico 90 km/h',
    'traffico 110 km/h',
]

# ---------------------------------------------------------------------------
# BERSAGLIO MANUFATTI – property / asset damage brackets (sheet A, BI4:BJ10)
# Used when bersaglio_tipo == 'proprietà'
# Class 1 = highest damage, class 7 = lowest damage
# ---------------------------------------------------------------------------

bersaglio_manufatti: dict[int, str] = {
    1: "danni da € 600'000 a 3'000'000",
    2: "danni da € 60'000 a € 600'000",
    3: "danni da € 6'000 a € 60'000",
    4: "danni da € 600 a € 6'000",
    5: "danni da € 60 a € 600",
    6: "danni da € 6 a € 60",
    7: "danni da € 3 a € 6",
}

# ---------------------------------------------------------------------------
# BERSAGLIO OCCUPAZIONE – occupancy / exposure-time brackets (sheet A, BI13:BJ19)
# Used when bersaglio_tipo == 'occupazione'
# Class 1 = highest exposure, class 7 = lowest exposure
# ---------------------------------------------------------------------------

bersaglio_occupazione: dict[int, str] = {
    1: "da 5 ore/giorno a costante",
    2: "da 29 min/giorno a 5 h/giorno",
    3: "da 3 a 29 min/giorno",
    4: "da 2 min/sett. a 3 min/giorno",
    5: "da 0,9 min/mese a 2 min/sett.",
    6: "da 1 min/anno a 0,9 min/mese",
    7: "da 0,5 a 1 min/anno",
}

# ---------------------------------------------------------------------------
# COERENZA FITOCLIMATICA  (sheet A, AE12:AF16)
# Fitness class used in the ornamental value calculation (trg_p_calculator.py).
# Passed as the `fitness_class` parameter (key 'A'–'E').
# ---------------------------------------------------------------------------

coerenza_fitoclimatica: dict[str, str] = {
    'A': 'A: optimum',
    'B': 'B: elevata',
    'C': 'C: buona',
    'D': 'D: scadente',
    'E': 'E: incoerente',
}

# ---------------------------------------------------------------------------
# CONDIZIONI SALUTE E VIGORIA  (sheet A, AU35:AV45)
# Maps health-condition description → health depreciation percentage.
# The depreciation % is passed as `health_depreciation_pct` to
# trg_p_calculator.calc_ornamental_value().
# ---------------------------------------------------------------------------

condizioni_salute: dict[str, int] = {
    "Condizioni vegetative e fitosanitarie ottimali. Albero integro": 0,
    "Condizioni vegetative e/o fitosanitarie ottimali. Albero lievemente alterato nella struttura": 5,
    "Condizioni vegetative e/o fitosanitarie buone o comunque non tali da condizionare la salute e la vigoria": 15,
    "Condizioni vegetative e/o fitosanitarie buone o comunque non tali da condizionare la salute e la vigoria. Albero strutturalmente alterato": 20,
    "Condizioni vegetative e/o fitosanitarie mediocri, che limitano l'efficienza funzionale. Salute e/o vigoria ridotte": 25,
    "Condizioni vegetative e/o fitosanitarie mediocri. Albero strutturalmente alterato": 30,
    "Condizioni vegetative e/o fitosanitarie scadenti, che ne condizionano la salute e l'aspettativa di vita": 40,
    "Condizioni vegetative e/o fitosanitarie scadenti. Albero molto alterato strutturalmente": 50,
    "Condizioni vegetative e/o fitosanitarie pessime": 60,
    "Condizioni vegetative e/o fitosanitarie pessime. Albero fortemente deperiente, strutturalmente molto alterato": 70,
    "Albero morto in piedi": 90,
}

# ---------------------------------------------------------------------------
# SPECIES LIST  (sheet A, K5:L244)
# Full botanical name → species code used elsewhere in the ARETE system.
# 240 entries; the user can add custom species in the yellow cells of sheet A.
# ---------------------------------------------------------------------------

species_list: list[tuple[str, str]] = [
    ('Abies alba L. - abete bianco', 'ABE'),
    ('Abies cephalonica Loudon - abete greco', 'ABE'),
    ('Abies nebrodensis (Lojac.) Mattei - abete dei Nebrodi', 'ABE'),
    ('Abies nordmanniana (S.) Spach - abete del Caucaso', 'ABE'),
    ('Acacia dealbata Link - mimosa', 'MIM'),
    ('Acer campestre L. - acero campestre', 'ACE'),
    ('Acer monspessulanum L. - acero minore', 'ACE'),
    ('Acer negundo L. - acero americano', 'ACE'),
    ('Acer opulifolium Chaix - acero alpino', 'ACE'),
    ('Acer platanoides L. - acero riccio', 'ACE'),
    ('Acer pseudoplatanus L. - acero di monte', 'ACE'),
    ('Acer rubrum L. - acero scarlatto', 'ACE'),
    ('Acer saccharum Marsh. - acero del Canada', 'ACE'),
    ('Aesculus hippocastanum L. - ippocastano', 'HIP'),
    ('Aesculus pavia L. - pavia', 'AES'),
    ('Ailanthus altissima Swingle - ailanto', 'AIL'),
    ('Albizzia julibrissin Durazzo - gaggia', 'ALB'),
    ('Alnus cordata (Loisel.) - ontano napoletano', 'ONT'),
    ('Alnus glutinosa L. - ontano nero', 'ONT'),
    ('Alnus incana Moench. - ontano bianco', 'ONT'),
    ('Alnus spp. - ontano', 'ONT'),
    ('Araucaria bidwilli Hook. - araucaria', 'ARA'),
    ('Araucaria heterophylla (excelsa) - pino di Norfolk', 'ARA'),
    ('Araucaria cunninghamii Mudie  - araucaria', 'ARA'),
    ('Arbutus unedo L. - corbezzolo', 'ARB'),
    ('Bauhinia purpurea L.', 'BAU'),
    ('Betula nigra', 'BET'),
    ('Betula papyrifera', 'BET'),
    ('Betula pendula Roth. - betulla bianca', 'BET'),
    ('Betula pubescens Ehrh. - betulla pelosa', 'BET'),
    ('Brachychiton acerifolius', 'BRA'),
    ('Brachychiton populneus', 'BRA'),
    ('Brachychiton sp.', 'BRA'),
    ('Biota orientalis - biota', 'BIO'),
    ('Broussonetia papyrifera Vent. - moro da carta', 'BRO'),
    ('Calocedrus decurrens - cedro della California', 'CAL'),
    ('Carpinus betulus L. - carpino bianco', 'CAB'),
    ('Carya ovata  (Mill.) - noce bianco', 'CAR'),
    ('Castanea sativa Miller - castagno', 'CAS'),
    ('Casuarina spp. - casuarina', 'CAU'),
    ('Catalpa bignonioides Walt. - catalpa', 'CAT'),
    ("Cedrus atlantica - cedro dell'Atlante", 'CED'),
    ("Cedrus atlantica var. glauca - cedro dell'Atlante", 'CED'),
    ("Cedrus deodara G.Don - cedro dell'Himalaia", 'CED'),
    ('Cedrus libani Richard - cedro del Libano', 'CED'),
    ('Celtis australis L. - bagolaro', 'CEL'),
    ('Celtis occidentalis L. - bagolaro occidentale', 'CEL'),
    ('Ceratonia siliqua L. - carrubo', 'CER'),
    ('Cercidiphyllum japonicum', 'CJA'),
    ('Cercis siliquastrum L. - albero di giuda', 'SIL'),
    ('Chamaecyparis lawsoniana - Lawson', 'LAW'),
    ('Chamaecyparis nootkatensis - cipresso di Nootka', 'NOT'),
    ('Chorisia speciosa', 'CHO'),
    ('Cinnamomum camphora - canfora', 'CAN'),
    ('Citrus sinensis Pers. - arancio', 'CIT'),
    ('Citrus aurantium', 'CIT'),
    ('Citrus reticulata', 'CIT'),
    ('Cordia francisci', 'COR'),
    ('Corylus avellana L. - nocciolo', 'NOC'),
    ('Corylus colurna', 'NOC'),
    ('Cryptomeria japonica Don - criptomeria', 'CRY'),
    ('Cupressocyparis leylandi', 'CRY'),
    ("Cupressus arizonica - cipresso dell'Arizona", 'ARZ'),
    ('Cupressus macrocarpa - cipresso Monterey', 'CIP'),
    ('Cupressus sempervirens L. - cipresso', 'CIP'),
    ('Cydonia oblonga - cotogno', 'CYD'),
    ('Diospyros kaki L. - diospero', 'DIO'),
    ('Diospyros virginiana', 'DIO'),
    ('Eryobotria japonica L. - nespolo giapponese', 'ERJ'),
    ('Erythrina sp. (E. christa-galli, ecc.)', 'ERY'),
    ('Eucaliptus globulus - eucalipto', 'EUC'),
    ('Eucaliptus camaldulensis - eucalipto', 'EUC'),
    ('Eucalyptus gunnii', 'EUC'),
    ('Fagus sylvatica L. - faggio', 'FAG'),
    ('Ficus carica L. - fico', 'FIC'),
    ('Ficus nitida', 'FIC'),
    ('Ficus elastica', 'FIC'),
    ('Ficus magnolioides', 'FIC'),
    ('Ficus microcarpa', 'FIC'),
    ('Firmiana simplex', 'FIR'),
    ('Fraxinus excelsior L. - frassino maggiore', 'FRA'),
    ('Fraxinus ornus L. - orniello', 'FRA'),
    ('Fraxinus oxycarpa - frassino meridionale', 'FRA'),
    ('Ginkgo biloba L. - ginkgo', 'GIN'),
    ('Gleditsia triacanthos L. - spino di Giuda', 'GLE'),
    ('Ilex aquifoliumL. - agrifoglio', 'ILX'),
    ('Grevillea robusta', 'GRE'),
    ("Hesperocyparis glabra Bartel - cip.dell'Ariz. glabro", 'HES'),
    ('Jacaranda mimosifolia', 'JAC'),
    ('Juglans nigra L. - noce nero', 'NOC'),
    ('Juglans regia L. - noce comune', 'NOC'),
    ('Juniperus communis L. - ginepro comune', 'GIN'),
    ('Juniperus oxycedrus L. - ginepro rosso', 'GIN'),
    ('Juniperus virginiana L. - ginepro della Virginia', 'GIN'),
    ('Koelreuteria paniculata Laxm. - koelreuteria', 'KOE'),
    ('Laburnum anagyroides', 'LAB'),
    ('Lagunaria patersonii', 'LAP'),
    ('Lagerstroemia indica L. - albero San Bartolomeo', 'LAG'),
    ('Larix decidua Miller - larice', 'LAR'),
    ('Larix kaempferi (Lamb.) - larice giapponese', 'LAR'),
    ('Laurus nobilis L. - alloro', 'LAU'),
    ('Ligustrum lucidum Ait. - ligustro lucido', 'LIG'),
    ('Liquidambar styraciflua L. - liquidambar', 'LIQ'),
    ('Liriodendron tulipifera L. - albero dei tulipani', 'LIR'),
    ('Maclura pomifera Schneider - maclura', 'MAC'),
    ('Magnolia denudata - magnolia yulan', 'MAG'),
    ('Magnolia grandiflora L. - magnolia', 'MAG'),
    ('Magnolia obovata - magnolia giapponese', 'MAG'),
    ('Magnolia stellata - magnolia stellata', 'MAG'),
    ('Magnolia x soulangeana Solu. Bod.- magnolia', 'MAG'),
    ('Liriodendron tulipifera - albero dei tulipani', 'LIR'),
    ('Maclura pomifera - maclura', 'MAC'),
    ('Magnolia denudata - magnolia yulan', 'MAG'),
    ('Magnolia grandiflora - magnolia', 'MAG'),
    ('Magnolia obovata - magnolia giapponese', 'MAG'),
    ('Magnolia stellata - magnolia stellata', 'MAG'),
    ('Magnolia x soulangeana - magnolia', 'MAG'),
    ('Malus floribunda - melo da fiore', 'MAL'),
    ('Malus sylvestris - melo', 'MAL'),
    ('Melia azedarach - albero dei rosari', 'MEL'),
    ('Mespilus germanica - nespolo', 'MES'),
    ('Metasequoia glyptostroboides - metasequoia', 'MET'),
    ('Morus alba - gelso bianco', 'GEL'),
    ('Morus nigra - gelso nero', 'GEL'),
    ('Musa paradisiaca - banano', 'BAN'),
    ('Nerium oleander - oleandro', 'NER'),
    ('Nyssa sylvatica', 'NYS'),
    ('Olea europea - olivo', 'OLI'),
    ('Ostrya carpinifolia - carpino nero', 'OST'),
    ('Parrotia persica - parrozia', 'PAR'),
    ('Paulownia tomentosa - paulownia', 'PAU'),
    ('Phillirea latifolia - fillirea', 'PHI'),
    ('Phellodendron amurense', 'PHE'),
    ('Phoenix canariensis - palma delle Canarie', 'PHO'),
    ('Phoenix dactylifera - palma da datteri', 'PHO'),
    ('Phytolacca dioica - fitolacca', 'PHY'),
    ('Picea abies - abete rosso', 'PIC'),
    ('Picea pungens - abete del Colorado', 'PIC'),
    ('Pinus brutia - pino calabrese', 'PIN'),
    ('Pinus canariensis - pino delle Canarie', 'PIN'),
    ('Pinus cembra - pino cembro', 'PIN'),
    ("Pinus halepensis - pino d'Aleppo", 'HAL'),
    ('Pinus mugo - pino montano', 'PIN'),
    ('Pinus nigra - pino nero', 'NIG'),
    ('Pinus pinaster - pino marittimo', 'PIN'),
    ('Pinus pinea - pino domestico', 'PPI'),
    ("Pinus ponderosa - pino giallo dell'ovest", 'PIN'),
    ('Pinus radiata - pino insigne', 'PIN'),
    ('Pinus strobus - pino strobo', 'PIN'),
    ('Pinus sylvestris - pino silvestre', 'SYL'),
    ('Pinus uncinata - pino uncinato', 'PIN'),
    ("Pinus wallichiana - pino dell'Himalaia", 'PIN'),
    ('Pistacia terebinthus - terebinto', 'PIS'),
    ('Platanus occidentalis - platano comune', 'PLA'),
    ('Platanus orientalis - platano orientale', 'PLA'),
    ('Platanus x acerifolia - platano ibrido', 'PLA'),
    ('Platycladus orientalis', 'PLO'),
    ('Populus alba - pioppo bianco', 'POP'),
    ('Populus canescens - pioppo gatterino', 'POP'),
    ('Populus nigra - pioppo nero', 'POP'),
    ('Populus nigra var. italica - pioppo cipressino', 'POP'),
    ('Populus spp. - pioppo', 'POP'),
    ('Populus tremula - pioppo tremolo', 'POP'),
    ('Prunus amygdalus - mandorlo', 'PRU'),
    ('Prunus armeniaca - albicocco', 'PRU'),
    ('Prunus avium - ciliegio', 'PRU'),
    ('Prunus  - mirabolano', 'PRU'),
    ('Prunus domestica - susino', 'PRU'),
    ('Prunus glandulosa - mandorlo da fiore', 'PRU'),
    ('Prunus laurocerasus L. - lauroceraso', 'PRU'),
    ('Prunus pissardi', 'PRU'),
    ('Prunus serrulata', 'PRU'),
    ('Prunus subhirtella', 'PRU'),
    ('Pseudotsuga menziesii - abete di Douglas', 'DOU'),
    ('Ptelea trifoliata - olmo di Samaria', 'PTE'),
    ('Pterocarya fraxinifolia - noce del Caucaso', 'PTF'),
    ('Pyrus calleriana', 'PYR'),
    ('Pyrus pyraster - pero selvatico', 'PYR'),
    ('Quercus cerris - cerro', 'CER'),
    ('Quercus frainetto - farnetto', 'FRA'),
    ('Quercus ilex - leccio', 'LEC'),
    ('Quercus palustris - quercia delle paludi', 'QUE'),
    ('Quercus petraea - rovere', 'ROV'),
    ('Quercus pubescens - roverella', 'PUB'),
    ('Quercus robur - farnia', 'FAR'),
    ('Quercus rubra - quercia rossa', 'QUE'),
    ('Quercus suber - sughera', 'SUG'),
    ('Quercus trojana', 'QTR'),
    ('Rhamnus alaternus - alaterno', 'RHA'),
    ('Rhus typhina - sommaco', 'RHU'),
    ('Robinia pseudoacacia - robinia', 'ROB'),
    ('Salix alba - salice bianco', 'SAL'),
    ('Salix babylonica  salice piangente', 'SAL'),
    ('Salix caprea - salicone', 'SAL'),
    ('Salix daphnoides - salice nero', 'SAL'),
    ('Salix spp. - salice', 'SAL'),
    ('Sequoia sempervirens - sequoia', 'SEQ'),
    ('Sequoiadendron giganteum - sequoia gigante', 'SEQ'),
    ('Schinus molle', 'SCH'),
    ('Sophora japonica - sofora', 'SOF'),
    ('Sorbus aria - sorbo montano', 'SOR'),
    ('Sorbus aucaparia - sorbo degli uccellatori', 'SOR'),
    ('Sorbus domestica - sorbo domestico', 'SOR'),
    ('Sorbus torminalis - ciavardello', 'SOR'),
    ('Styphnolobium japonicum', 'STY'),
    ('Tamarix gallica - tamerice', 'TAM'),
    ('Taxodium disticum - cipresso calvo', 'TAX'),
    ('Taxus baccata - tasso', 'TAS'),
    ('Thuja occidentalis - tuia', 'THU'),
    ('Thuja orientalis - albero della vita', 'THU'),
    ('Thuja plicata  - tuia gigante', 'THU'),
    ('Tilia cordata - tiglio selvatico', 'TIG'),
    ('Tilia platyphyllos - tiglio nostrano', 'TIG'),
    ('Tilia sp. - tiglio', 'TIG'),
    ('Tilia x europaea - tiglio ibrido', 'TIG'),
    ('Tilia x vulgaris - tiglio ibrido', 'TIG'),
    ('Trachycarpus fortunei - trachycarpus', 'TRA'),
    ('Tsuga canadensis - tsuga canadese', 'TSU'),
    ('Ulmus glabra - olmo montano', 'ULM'),
    ('Ulmus maior', 'ULM'),
    ('Ulmus minor - olmo campestre', 'ULM'),
    ('Ulmus parvifolia', 'ULM'),
    ('Ulmus procera', 'ULM'),
    ('Ulmus pumila - olmo siberiano', 'ULM'),
    ('Washingtonia filifera - washingtonia', 'WAS'),
    ('Washingtonia robusta - washingtonia', 'WAS'),
    ('Yucca spp.', 'JUC'),
    ('Zelkova carpinifolia - zelkova', 'ZEL'),
    ('Zelkova spp.', 'ZEL'),
    ('Ziziphus jujuba - giuggiolo comune', 'ZIZ'),
    # Palme (palms section)
    ('Brahea armata', 'BRA'),
    ('Chamaerops humilis L. - palma nana', 'CHA'),
    ('Jubaea chilensis', 'JUB'),
    ('Phoenix canariensis C. - palma delle Canarie', 'PHO'),
    ('Phoenix dactylifera L. - palma da datteri', 'PHO'),
    ('Trachycarpus fortunei Wendl. - trachycarpus', 'TRA'),
    ('Washingtonia filifera Wendl. - washingtonia', 'WAS'),
    ('Washingtonia robusta - washingtonia', 'WAS'),
    ('Yucca spp.', 'JUC'),
]

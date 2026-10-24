# Silvae Pro — Prossimi passi

Proposte di sviluppo ancora aperte, con il ragionamento che le motiva. Non è
un impegno di roadmap: è il materiale per decidere cosa fare dopo e,
soprattutto, perché.

Quello che è già stato fatto non è elencato qui: lo racconta il
[README](../README.md), e per il ponte con QGIS il piano e lo stato per fasi
stanno in [`qgis.md`](qgis.md).

---

## La domanda di partenza

Gli agronomi che userebbero Silvae Pro **oggi usano QGIS** per mappare gli
alberi. La domanda non è quindi "cosa manca a Silvae rispetto a QGIS", ma
"quale posto occupa Silvae in un flusso di lavoro in cui QGIS resta".

## Il posizionamento

La tentazione è aggiungere a Silvae le cose che fa QGIS. È una guerra persa:
QGIS ha vent'anni di geoprocessing alle spalle e non lo si raggiunge.

La posizione difendibile è l'opposta. **Silvae Pro è il sistema di
registrazione della valutazione ARETE** — protocollo, ruoli, storico delle
ispezioni, schede ufficiali, tracciabilità della responsabilità professionale.
Nulla di tutto questo QGIS lo farà mai, perché non è un GIS a mancargli: è il
dominio.

Ne segue che le funzioni utili sono di due tipi soltanto:

1. quelle che rendono Silvae **un cittadino di prima classe nel flusso QGIS**
   che gli agronomi non abbandoneranno;
2. quelle che eliminano i **motivi residui di aprire QGIS**.

Tutto ciò che non ricade in una delle due categorie va guardato con sospetto.

---

## Vincoli tecnici da tenere presenti

Chi raccoglie queste proposte deve conoscere i paletti dell'ambiente, perché
alcuni hanno già condizionato scelte di progetto.

| Vincolo | Conseguenza |
|---|---|
| **PostGIS non installabile** sul Postgres gestito di Railway | Nessun lavoro spaziale nel database. Le coordinate sono due `float` (`latitude`/`longitude`) e tutto il resto si fa altrove. |
| **GDAL / GEOS non disponibili** sull'immagine di default | Niente `geopandas`, `shapely`, `fiona`. L'export GeoPackage è scritto a mano con `struct` e `sqlite3` in [`app.py`](../app.py). |
| **LibreOffice assente** | Le schede ARETE escono in `.xlsx`; la cartella `pdf/` dello zip resta vuota (già documentato nel README). |
| **Timeout di Gunicorn a 120 s** (`Procfile`) | Qualunque operazione per-albero che superi i due minuti va spezzata o spostata in background. È il limite che oggi blocca le schede di un comune intero (vedi **E1**). |
| **Riga di richiesta HTTP a 4094 byte** (`--limit-request-line`) | Una URL non può elencare più di ~660 id. Export e report accettano per questo anche `POST` con gli id nel corpo; chi aggiunge endpoint nuovi che prendono liste di id deve ricordarselo. |
| **Il frontend carica un comune alla volta**, interamente in memoria ([`frontend/app.js`](../frontend/app.js), `fetchTrees`) | Ricerca, ordinamento, selezione per area e statistiche lavorano in memoria e restano istantanei fino a qualche migliaio di alberi (Bra ne ha 2648). Oltre le **decine di migliaia per singolo comune** serve una ristrutturazione: paginazione lato server, risposta di `/trees` «leggera» senza i JSON di rischio e diagnosi, marker per bounding box. Non serve PostGIS neanche per quello: basta un filtro `latitude BETWEEN … AND longitude BETWEEN …` su due colonne indicizzate. |

**Nota importante**: l'assenza di PostGIS *non* blocca nessuna delle proposte
qui sotto. Il lavoro spaziale già oggi non passa dal database — la selezione
per area è un ray casting in JavaScript (`_pointInPolygon` in
[`frontend/app.js`](../frontend/app.js)). GeoJSON, GPX, QML e QLR sono formati di
**serializzazione**: leggono due float e li impaginano. Non richiedono
librerie, estensioni né immagini custom.

---

## E — Limiti emersi dall'uso su dati veri

*Piccoli, concreti, con una causa già misurata.*

### E1. Schede ARETE di un comune intero

Generare le schede richiede **circa 450 ms per albero** (misurato: 20 schede
`.xlsx` in 9,0 s, senza la conversione PDF che su Railway non c'è). Contro il
timeout di 120 s di Gunicorn il tetto pratico è di **circa 260 alberi per
richiesta**: per i 2648 di Bra servirebbero venti minuti.

Non è un problema di URL — quello è risolto, `?city=` e `POST` prendono un
comune intero in un colpo — è il tempo di compilazione del template ufficiale,
un file Excel per albero.

**Cosa serve**: spostare la generazione in background (un *job* che prepara lo
zip e lo mette a disposizione per il download, come la cassetta postale fa per
QGIS), oppure spezzare in blocchi lato client e unire gli zip. La prima strada
è più pulita e riusa un'idea già nel progetto; la seconda si fa solo nel
frontend.

**Sforzo**: 1-2 giorni per la versione a blocchi; 3-4 per il job in background.

### E2. Tabella dei comuni vuota in produzione

`scripts/seed_comuni.py` riempie la tabella `comune` con i 7904 comuni
italiani, ma **non è mai stato lanciato sul database di produzione**: la
tabella ha 0 righe, quindi `GET /comuni/search` restituisce sempre una lista
vuota e l'autocompletamento del comune non suggerisce nulla in tre punti
dell'interfaccia (scheda albero, creazione utente, importazione).

Si scrive comunque a mano e si salva, quindi nulla è rotto — ma è proprio il
caso in cui nascono i doppioni ortografici, lo stesso problema che il
censimento di Bra ha nella colonna `_LOCALITA'` (vedi **B1**).

**Cosa serve**: lanciare lo script una volta contro la produzione. Scrive solo
nella tabella `comune`, che è vuota.

**Sforzo**: un comando.

---

## A — Interoperabilità con QGIS

Il grosso è fatto: plugin, lettura, scrittura, cassetta postale e conflitti
(fasi 0-4 di [`qgis.md`](qgis.md), tutte chiuse). Resta la **fase 5 —
packaging**: `plugins.xml` privato, `User.qgis_enabled` come paywall, i18n,
guida utente con schermate. È descritta in `qgis.md` §10-11 e non si duplica
qui.

### A1. Campo quota nel GPX

In importazione il tag `ele` dei waypoint viene scartato, perché nel modello
non esiste un campo quota. Da valutare se serve davvero: la quota di un albero
urbano raramente entra nella valutazione, ma i GPS da campo la scrivono sempre
e buttarla via è una perdita silenziosa.

**Sforzo**: mezza giornata, più una colonna sul modello.

---

## B — Colmare il divario geometrico

*Silvae oggi conosce solo punti. L'agronomo in QGIS ha già molto altro.*

### B1. Aree e popolamenti come entità di primo livello

Poligoni con un nome: parchi, giardini scolastici, viali, popolamenti, lotti
di gara. Un livello **tra il comune e il singolo albero**, che oggi non
esiste ed è proprio quello in cui l'agronomo lavora.

**Non presuppone QGIS.** Il poligono può arrivare da tre origini, in
quest'ordine di importanza:

1. **Disegnato in Silvae.** Lo strumento c'è già: la *selezione per area*
   sulla mappa disegna un poligono e calcola gli alberi contenuti
   (`_pointInPolygon` in [`frontend/app.js`](../frontend/app.js)). Oggi quel
   poligono vive nella sessione e sparisce. B1 è, in sostanza, un pulsante
   **«Salva come area»** che gli dà un nome e lo mette nel database.
2. **Importato** da `.gpkg`/GeoJSON, per chi i perimetri li ha già in QGIS:
   stesso meccanismo del tab Importa, con geometria poligonale invece che
   punti. È una porta in più, non un prerequisito.
3. **Proposto da fonti pubbliche.** OpenStreetMap ha già i poligoni di
   parchi, giardini e aree verdi (la stessa fonte usata per la geocodifica):
   un «proponi aree da OSM per questo comune» fa partire un comune nuovo con
   le aree già pronte. Da fare dopo, senza librerie GIS.

**Il caso concreto**: nel censimento di Bra la colonna `_LOCALITA'` ha 72
valori — Piazza Roma, Giardino Rocca, Viale Rimembranze… *Quelle sono le
aree*, ma come testo libero, quindi con doppioni ortografici
(`V.le  Madonna fiori` / `Viale Maddonna dei Fiori`). Un poligono disegnato
una volta assegna gli alberi per posizione e sostituisce l'etichetta a mano.

**Perché**: sblocca le statistiche per area (gli stessi chip di
rischio/condizione già fatti a livello di comune, ma «per il Giardino della
Rocca»), filtri/export/schede «tutti gli alberi di quest'area» senza
ridisegnare il poligono ogni volta, l'assegnazione dei lavori e — soprattutto
— il collegamento naturale con il **TRG-P**, che è un protocollo *per
popolamenti* ed è già implementato in
[`tools/trg_p_calculator.py`](../tools/trg_p_calculator.py) senza avere un
oggetto a cui agganciarsi.

**Cosa serve**: tabella `area` (nome, comune, poligono come GeoJSON in una
colonna di testo, note); il punto-nel-poligono in Python con le stesse venti
righe già scritte in JavaScript, calcolato al salvataggio dell'area e
all'inserimento/spostamento di un albero; filtro per area nel tab Alberi e
sulla mappa; import poligonale opzionale. **Non** usare `shapely`: dipende
da GEOS compilato e ripropone il problema di PostGIS. Per qualche migliaio di
alberi e qualche decina di aree il calcolo in Python è istantaneo.

**Sforzo**: una settimana per disegno + salvataggio + filtri + statistiche;
l'import poligonale e la proposta da OSM sono aggiunte separate.

### B2. Filari

Geometria lineare. I viali alberati sono il caso d'uso urbano più comune e
oggi diventano una collana di punti scollegati.

**Sforzo**: pochi giorni se fatto dopo B1, che ne prepara l'impalcatura.

### B3. Campionamento sistematico

Si disegna un poligono sulla mappa, si sceglie il passo della griglia, Silvae
genera i plot con ID progressivi, esportabili in GPX e GPKG.

**Perché**: su un popolamento di 5.000 alberi il censimento totale non si
ripaga, lo screening a campione sì. È una funzione che in QGIS richiede cinque
passaggi (griglia regolare, ritaglio sulla maschera, calcolo campi,
etichettatura, export) e in Silvae uno — e si aggancia a un motore di calcolo,
il TRG-P, che esiste già e oggi non rende nulla.

**Sforzo**: pochi giorni, ma ha senso solo insieme a B1 e all'esposizione del
TRG-P.

---

## C — Togliere i motivi di aprire QGIS

### C1. Basemap catastale e ortofoto ufficiali (WMS)

Leaflet consuma WMS senza problemi, e oggi la mappa usa solo OSM e l'ortofoto
ArcGIS.

**Perché**: il bersaglio «proprietà» del calcolo ARETE si valuta guardando i
confini catastali. Oggi, per vederli, l'agronomo apre QGIS. Catasto e ortofoto
del Geoportale Nazionale sono direttamente pertinenti al dominio.

**Sforzo**: mezza giornata per il meccanismo, più il tempo di verificare
licenze e disponibilità dei servizi.

### C2. Legenda sulla mappa web e colorazione per specie

I marker sono già colorati per classe di rischio e condizione, e il filtro per
categoria è condiviso fra lista e mappa. Mancano due cose:

- una **legenda** sulla mappa web (la tavola per la relazione ce l'ha già,
  generata da [`tools/map_render.py`](../tools/map_render.py));
- la colorazione **per specie**, utile per leggere la composizione di un
  viale a colpo d'occhio. Richiede una tavolozza generata (le specie sono
  decine), separata da quella delle classi in
  [`tools/palette.py`](../tools/palette.py), che resta dedicata a rischio e
  condizione.

**Sforzo**: 1 giorno.

### C3. Rifiniture della tavola per la relazione

`GET /report/map` produce una A4 con basemap, marker, ID, legenda, scala e
nord. Rimasto fuori, da valutare solo se qualcuno lo chiede: PDF vettoriale
(testo selezionabile) via `fpdf2`, più pagine per aree grandi, scelta manuale
del livello di zoom.

**Sforzo**: 1-2 giorni, a seconda di quante delle tre.

---

## D — Le due che gli agronomi chiedono a prescindere da QGIS

### D1. Foto georeferenziate sull'albero

Oggi non esiste alcun supporto per allegati. In una perizia VTA la foto del
difetto è metà del valore probatorio. Anche QGIS lo fa male (widget allegati):
farlo bene qui è un vantaggio netto, non un pareggio.

**Sforzo**: qualche giorno, più la decisione su dove si archiviano i file
(il filesystem di Railway è effimero: serve uno storage esterno).

### D2. Lavoro offline

Nel mondo QGIS questo è QField. Silvae è una webapp e in un parco senza campo
non funziona.

Una risposta parziale esiste già: il GPKG scaricato dal plugin QGIS si apre in
QField, si porta in campo e al ritorno si rimanda con *Invia a Silvae*. Resta
scoperto chi usa solo la webapp dal telefono.

**Perché**: è lo sforzo maggiore dell'elenco — PWA, coda di sincronizzazione,
risoluzione dei conflitti — ma è anche la ragione per cui un rilevatore
potrebbe rifiutare lo strumento a prescindere da quanto è buono tutto il resto.

**Sforzo**: settimane.

---

## Ordine consigliato

1. **E2** (un comando) e **E1** (le schede di un comune): sono difetti su
   funzioni che i clienti usano già, non funzioni nuove.
2. **C1** (WMS catastale) e **D1** (foto): il miglior rapporto valore/fatica
   tra le proposte sostanziali.
3. **Fase 5 di [`qgis.md`](qgis.md)** — packaging del plugin: serve prima di
   poter vendere il modulo QGIS.
4. **B1 + B3 + TRG-P in interfaccia**: la scommessa strategica: apre un
   mercato diverso (gestione di popolamenti, non perizie su singoli alberi)
   usando un motore di calcolo già scritto.
5. **C2**, **C3**, **A1**: rifiniture, quando qualcuno le chiede.
6. **D2** — quando il prodotto è abbastanza maturo da giustificarne il costo.

## Cose da non fare

- **Inseguire QGIS sul geoprocessing.** Buffer, intersezioni, analisi di rete:
  se un agronomo ne ha bisogno, ha già QGIS aperto. Meglio dargli il dato
  pulito che una versione peggiore dei suoi strumenti.
- **Introdurre `shapely`, `geopandas` o `fiona`.** Dipendono da GEOS e GDAL
  compilati e non si installano sull'immagine Railway di default. Lo stesso
  muro di PostGIS.
- **Rincorrere PostGIS come prerequisito.** Non serve a nulla di quanto sopra.
  Se un giorno servisse davvero (query spaziali server-side su decine di
  migliaia di alberi), la via è eseguire l'immagine `postgis/postgis` come
  servizio invece del Postgres gestito — da verificare sulla Railway del
  momento, e al prezzo di gestirsi backup e aggiornamenti.
- **Ottimizzare per la scala prima di averla.** Il carico è già «un comune
  alla volta», che basta fino alle migliaia di alberi; oltre le decine di
  migliaia *per comune* serve una ristrutturazione (paginazione, query per
  bounding box lato server, clustering server-side), non una libreria in più.

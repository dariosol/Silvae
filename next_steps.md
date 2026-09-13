# Silvae Pro — Prossimi passi

Proposte di sviluppo, con il ragionamento che le motiva. Non è un impegno di
roadmap: è il materiale per decidere cosa fare dopo e, soprattutto, perché.

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
| **GDAL / GEOS non disponibili** sull'immagine di default | Niente `geopandas`, `shapely`, `fiona`. L'export GeoPackage è scritto a mano con `struct` e `sqlite3` in [`app.py`](app.py). |
| **LibreOffice assente** | Le schede ARETE escono in `.xlsx`; la cartella `pdf/` dello zip resta vuota (già documentato nel README). |
| **Il frontend carica tutti gli alberi visibili** in un colpo solo ([`frontend/app.js`](frontend/app.js), `fetchTrees`) | Al login il selettore è su «Tutti i comuni» e `/trees` viene chiamato senza filtro: per un agronomo con più comuni o per il superuser scarica *tutto*. Ricerca, ordinamento, selezione per area e statistiche funzionano in memoria. Regge qualche migliaio di alberi; è il vero limite di scala del progetto — vedi **P0**. |

**Nota importante**: l'assenza di PostGIS *non* blocca nessuna delle proposte
qui sotto. Il lavoro spaziale già oggi non passa dal database — la selezione
per area è un ray casting in JavaScript (`_pointInPolygon` in
[`frontend/app.js`](frontend/app.js)). GeoJSON, GPX, QML e QLR sono formati di
**serializzazione**: leggono due float e li impaginano. Non richiedono
librerie, estensioni né immagini custom.

---

## P0 — Caricare gli alberi solo dopo aver scelto il comune

*Priorità sopra tutto il resto: è il limite di scala reale, e la prima parte
costa poche ore.*

### Com'è oggi

Al login `citySelect` vale `""` («Tutti i comuni») e `fetchTrees()` chiama
`GET /trees` **senza filtro**: il server restituisce tutti gli alberi visibili
al ruolo (tutti quelli dell'agronomo, tutti quelli del comune, *tutti quelli
del database* per il superuser) e il browser li tiene in memoria. Il filtro
per comune esiste già lato server (`?city=`), ma scatta solo quando l'utente
cambia il selettore. Con il censimento di Bra (2 501 alberi) più altri comuni
si superano subito le migliaia di righe, ognuna con il JSON completo di
`rischio`, diagnosi e prescrizioni.

### Proposta

1. **Nessun caricamento finché non c'è un comune selezionato.** Al login il
   tab Alberi mostra un invito («Seleziona un comune per vedere gli alberi»)
   invece della lista; la mappa mostra il comune scelto. Si chiama `/trees`
   solo con `?city=`.
2. **Selezione automatica quando la scelta è obbligata**: se l'utente vede un
   solo comune (il caso tipico di `city` e di molti agronomi) lo si seleziona
   da soli, e l'esperienza resta quella di oggi.
3. **Ricordare l'ultimo comune** scelto (`localStorage`), così al login
   successivo si riparte da lì senza clic.
4. **Pulsante «Mostra tutti»** per chi ne ha davvero bisogno (superuser,
   agronomo che vuole la vista d'insieme): esplicito, con il conteggio
   accanto («Mostra tutti · 4 120 alberi») così si sa cosa si sta chiedendo.

### Cosa cambia nel codice

Quasi tutto in [`frontend/app.js`](frontend/app.js): `fetchTrees()` esce
subito se `citySelect` è vuoto e non è stato premuto «Mostra tutti»;
`populateCities()` seleziona il comune unico o l'ultimo usato; le chiamate a
`fetchTrees()` dopo import/aggiunta/eliminazione restano invariate perché
lavorano già sul comune corrente. Lato server basta aggiungere un
`GET /trees/count` (o un campo nella risposta di `/cities`) per il numero
accanto a «Mostra tutti». Nessuna migrazione, nessuna nuova dipendenza.

**Sforzo**: mezza giornata.

### Cosa NON risolve, e quando servirà

Dopo questo passo il carico è *per comune*: 2 500 alberi di Bra si caricano
comunque tutti insieme, e va bene — ricerca, chip statistici e selezione per
area continuano a lavorare in memoria e restano istantanei. Il passo
successivo, da fare solo quando un singolo comune supera le decine di
migliaia di alberi, è strutturale: paginazione lato server, risposta di
`/trees` «leggera» (senza i JSON di rischio/diagnosi, caricati sul dettaglio)
e marker calcolati per bounding box della mappa. Non serve PostGIS neanche
per quello: un filtro `latitude BETWEEN … AND longitude BETWEEN …` su due
colonne indicizzate basta.

---

## A — Interoperabilità con QGIS

*Poco lavoro, ritorno sproporzionato. Usa quasi solo codice esistente.*

### A1. Stile QGIS pronto (`.qml`)

File di stile che colora gli alberi per classe di rischio ARETE e per
condizione VTA, con gli stessi colori della webapp.

**Perché**: l'agronomo apre il GPKG esportato e vede subito la mappa tematica
giusta, senza configurare nulla. La mappa in QGIS e quella in Silvae si
somigliano, il che vale più di quanto sembri per la fiducia nello strumento.

**Stato**: il prerequisito è fatto — i colori stanno in un posto solo,
[`tools/palette.py`](tools/palette.py) (vedi README, sezione *Palette*). Il
`.qml` verrà **generato** da lì, non scritto a mano: cambiando un colore in
`palette.py` cambiano webapp, mappa e stile QGIS insieme.

#### Da discutere con l'agronomo prima di implementare

1. **Ha già un `.qml` di riferimento?** Se in studio usano uno stile
   consolidato (colori, simboli, etichette che i comuni conoscono), conviene
   fare il **contrario**: importare *quello* in Silvae, cioè leggere i colori
   dal suo `.qml` e travasarli in `palette.py`, così la webapp si adegua allo
   standard che l'agronomo usa già e non viceversa. Un `.qml` è XML: la parte
   che ci interessa è il renderer categorizzato (`<categories>` con
   `value`/`label`/`symbol` e il `color` di ogni simbolo), facile da leggere.
   Da chiedere: il file, e su quale campo/valori è categorizzato.

2. **Colorare per rischio o per condizione?** In QGIS un layer ha uno stile
   attivo alla volta. Proposta: due stili — *rischio ARETE* (predefinito) e
   *condizione VTA* — selezionabili dal menu stili del layer. Chiedere quale
   preferisce come predefinito nella pratica (per la relazione al comune
   probabilmente il rischio, per il monitoraggio fitosanitario la condizione).

3. **Come deve arrivare lo stile in QGIS.** Tre modalità, non esclusive:
   - **dentro il `.gpkg`** (tabella `layer_styles`, stile marcato come
     predefinito): QGIS lo applica da solo quando aggiungi il layer — nessun
     passaggio manuale. È la modalità consigliata di default, dato che il
     GPKG lo scriviamo noi in `export_gpkg`;
   - **`.qml` accanto al file** con lo stesso nome (`alberi.gpkg` +
     `alberi.qml`): QGIS lo carica automaticamente, ma si perde se si rinomina
     o sposta uno dei due;
   - **`.qml` scaricabile a parte** dal tab Esporta: serve comunque per i GPKG
     esportati in passato, per layer già presenti nei progetti QGIS
     dell'agronomo, o per riapplicarlo dopo modifiche
     (*Proprietà layer → Simbologia → Stile → Carica stile*).

4. **Etichette e simbolo.** Oltre al colore: vuole l'ID albero come etichetta
   sul punto? Dimensione del simbolo fissa o proporzionale (es. al diametro
   della chioma)? Un contorno diverso per gli alberi con rischio non
   calcolato? Sono tutte cose che il `.qml` può contenere e che oggi la
   webapp non rappresenta — deciderle con lui evita di generare uno stile che
   poi sovrascrive a mano.

5. **Campo `rischio` nel GPKG.** Oggi nell'export il rischio è spalmato su
   più colonne (rami/tronco/colletto/zolla, attuale/residuo); uno stile
   categorizzato ha bisogno di **una** colonna con la categoria peggiore
   (`accettabile` / `alarp` / `accordo` / `inaccettabile` / vuoto), come già
   fatto per il GPX. Va aggiunta all'export GPKG e — se si segue il punto 1 —
   i valori devono coincidere con quelli su cui è categorizzato il suo
   `.qml`.

**Cosa serve**: un generatore XML in Python (`tools/qgis_style.py`) che
produce il renderer categorizzato dai valori di `palette.py`; un endpoint
`GET /export/qml?by=rischio|condizione`; l'inserimento in `layer_styles`
dentro `export_gpkg`; la colonna `rischio` nel GPKG. Nessuna dipendenza
esterna (solo `xml.etree`, come per il GPX). Se si parte dal `.qml`
dell'agronomo, in più uno script una-tantum che ne estrae i colori.

**Sforzo**: mezza giornata per la generazione; un'altra mezza per
l'inserimento nel GPKG e i test in QGIS. Sostanzialmente invariato se si
parte dal suo `.qml`.

### A2. Layer live invece del file scaricato

Endpoint GeoJSON in sola lettura più un file `.qlr` (QGIS Layer Definition)
che lo punta, con lo stile di A1 già incorporato.

**Perché**: è il passaggio che cambia il posizionamento. Oggi il ponte con
QGIS esiste ma è manuale — esporti un file, lo apri, lo modifichi, lo
reimporti, e ogni passaggio è un'occasione per disallineare i dati. Con un
layer live l'agronomo aggiunge *una volta* «Silvae — Torino» tra i suoi layer
e da lì in poi vede sempre il dato corrente. Silvae smette di essere il posto
da cui si esporta e diventa la fonte del dato.

**Cosa serve**: un `FeatureCollection` costruito con `json.dumps` sopra lo
stesso filtro per ruolo degli altri export. Da decidere: come autenticare la
richiesta, dato che QGIS non gestisce bene i token in header — probabilmente
un token d'accesso al layer, revocabile, passato in query string.

**Sforzo**: 1 giorno, il grosso è la decisione sull'autenticazione.

### A3. Export GPX per il GPS — ✅ fatto (settembre 2026)

Import ed export GPX sono disponibili (`/import/gpx`, `/export/gpx`, tab
Importa/Esporta, barra di selezione e selezione per area). Resta da valutare
un campo quota (`ele`), oggi scartato in importazione.

Dalla selezione per area sulla mappa: i waypoint degli alberi da ispezionare,
caricabili su un GPS da campo o sul telefono.

**Perché**: è il passo finale del flusso di campionamento forestale standard
(cfr. la lezione 14.5 del manuale QGIS). Gli agronomi vanno sul posto e devono
ritrovare l'albero.

**Cosa serve**: XML banale, e le coordinate sono già in WGS84 — nessuna
riproiezione.

**Sforzo**: mezza giornata.

### A4. Round-trip sicuro (esporta → QGIS → reimporta)

Oggi il conflitto in importazione si risolve per `custom_id` con `skip` o
`update`. Per un ciclo affidabile servono tre cose: una chiave stabile (UUID)
che sopravviva ai rinomini, un `updated_at` per accorgersi delle modifiche
concorrenti, e soprattutto un'**anteprima del diff** prima di applicare
(«12 modificati, 3 nuovi, 1 scomparso — conferma»).

**Perché**: senza, reimportare è un atto di fede. È la funzione che rende il
ponte con QGIS utilizzabile su dati veri e non solo su dimostrazioni.

**Sforzo**: 2-3 giorni, e tocca il modello dati.

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
   (`_pointInPolygon` in [`frontend/app.js`](frontend/app.js)). Oggi quel
   poligono vive nella sessione e sparisce. B1 è, in sostanza, un pulsante
   **«Salva come area»** che gli dà un nome e lo mette nel database.
2. **Importato** da `.gpkg`/GeoJSON, per chi i perimetri li ha già in QGIS:
   stesso meccanismo del tab Importa, con geometria poligonale invece che
   punti. È una porta in più, non un prerequisito.
3. **Proposto da fonti pubbliche.** OpenStreetMap ha già i poligoni di
   parchi, giardini e aree verdi (la stessa fonte usata per la geocodifica):
   un «proponi aree da OSM per questo comune» fa partire un comune nuovo con
   le aree già pronte. Da fare dopo, senza librerie GIS.

**Il caso concreto**: nel censimento di Bra
(`file_da_importare/CENSIMENTO COMPLETO CON COORD.gpkg`) la colonna
`_LOCALITA'` ha 72 valori — Piazza Roma, Giardino Rocca, Viale Rimembranze…
*Quelle sono le aree*, ma come testo libero, quindi con doppioni ortografici
(`V.le  Madonna fiori` / `Viale Maddonna dei Fiori`). Un poligono disegnato
una volta assegna gli alberi per posizione e sostituisce l'etichetta a mano.

**Perché**: sblocca le statistiche per area (gli stessi chip di
rischio/condizione già fatti a livello di comune, ma «per il Giardino della
Rocca»), filtri/export/schede «tutti gli alberi di quest'area» senza
ridisegnare il poligono ogni volta, l'assegnazione dei lavori e — soprattutto
— il collegamento naturale con il **TRG-P**, che è un protocollo *per
popolamenti* ed è già implementato in
[`tools/trg_p_calculator.py`](tools/trg_p_calculator.py) senza avere un
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

### C1. Mappa PDF per la relazione

Per mettere una mappa nella relazione al comune, oggi si apre il compositore
di stampa di QGIS. Un «genera mappa PDF» dell'area selezionata — con legenda
per classe di rischio, scala e nord — elimina un intero giro esterno e si
sposa con le schede ARETE già generate.

**Sforzo**: qualche giorno. Attenzione: il rendering lato server di una mappa
è meno banale di quanto sembri, e LibreOffice non è disponibile — valutare la
generazione lato client.

### C2. Basemap catastale e ortofoto ufficiali (WMS)

Leaflet consuma WMS senza problemi, e oggi la mappa usa solo OSM e l'ortofoto
ArcGIS.

**Perché**: il bersaglio «proprietà» del calcolo ARETE si valuta guardando i
confini catastali. Oggi, per vederli, l'agronomo apre QGIS. Catasto e ortofoto
del Geoportale Nazionale sono direttamente pertinenti al dominio.

**Sforzo**: mezza giornata per il meccanismo, più il tempo di verificare
licenze e disponibilità dei servizi.

### C3. Mappa tematica in-app

Colorazione per rischio, condizione o specie, con legenda, e filtri sulla
mappa coerenti con i chip statistici del tab Alberi.

**Sforzo**: 1-2 giorni.

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

**Perché**: è lo sforzo maggiore dell'elenco — PWA, coda di sincronizzazione,
risoluzione dei conflitti — ma è anche la ragione per cui un rilevatore
potrebbe rifiutare lo strumento a prescindere da quanto è buono tutto il resto.

**Sforzo**: settimane.

---

## Ordine consigliato

0. **P0** — caricare solo il comune selezionato, con «Mostra tutti». Poche
   ore, toglie il limite di scala più vicino.
1. **A1 + A2** (A3 GPX già fatto) — stile QML, layer live. Giorni, non settimane;
   riusano codice esistente e cambiano il posizionamento del prodotto.
2. **C2** (WMS catastale) e **D1** (foto) — il miglior rapporto
   valore/fatica tra le proposte sostanziali.
3. **A4** — quando il ponte con QGIS comincia a essere usato su dati veri.
4. **B1 + B3 + TRG-P in interfaccia** — la scommessa strategica: apre un
   mercato diverso (gestione di popolamenti, non perizie su singoli alberi)
   usando un motore di calcolo già scritto.
5. **D2** — quando il prodotto è abbastanza maturo da giustificarne il costo.

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
- **Ottimizzare per la scala prima di averla.** Il limite vero non è PostGIS:
  è il caricamento di tutti gli alberi nel browser. **P0** lo riporta a «un
  comune alla volta», che basta fino alle migliaia di alberi; oltre le decine
  di migliaia *per comune* serve una ristrutturazione (paginazione, query per
  bounding box lato server, clustering server-side), non una libreria in
  più.

# Script di servizio

Utilità da riga di comando, fuori dall'applicazione. Nessuna di queste è
necessaria per far girare Silvae Pro: l'app parte, crea il suo schema e crea
l'utente `admin` da sola.

Si lanciano **dalla radice del progetto**, con l'ambiente virtuale attivo:

```bash
source flaskenv/bin/activate
python scripts/<nome>.py
```

Leggono `DATABASE_URL` dal `.env` come `app.py`, quindi **agiscono sul database
che quella variabile indica**. Per provarne una senza rischi, puntala altrove:

```bash
DATABASE_URL=sqlite:///prova.db python scripts/<nome>.py
```

---

## In uso

| Script | Cosa fa | Quando serve |
|---|---|---|
| `seed_comuni.py` | Scarica i 7904 comuni italiani da [comuni-json](https://github.com/matteocontrini/comuni-json) e riempie la tabella `comune`. Idempotente: se la tabella non è vuota si ferma, salvo `--force` | Una volta per database. **In produzione la tabella è vuota**: finché lo resta, l'autocompletamento del comune nei form non suggerisce nulla |
| `create_admin.py` | Reimposta la password di `admin` a `password`, creando l'utente se manca | In locale, quando si è perso l'accesso. **Non** su un server pubblico |
| `dump_gpkg.py` | Stampa le prime righe di un `.gpkg` (`-n`, `--offset`) senza bisogno di QGIS | Per capire com'è fatto un file prima di importarlo, o perché un import ha dato un risultato strano |
| `make_demo_gpkg.py` | Genera `demo.gpkg` nella radice: 100 alberi sintetici a Torino, seme fisso | Per provare il tab «Importa» senza usare dati di clienti |

## `archivio/` — non eseguire

Codice che ha fatto il suo lavoro e non va più lanciato, tenuto perché la
conoscenza che contiene può servire. Ognuno ha in testa un avviso che spiega
perché. In breve:

| Script | Perché è in archivio |
|---|---|
| `fix_coords.py` | Sovrascriveva lat/lon di **tutti** gli alberi con la geocodifica dell'indirizzo più un offset casuale di ±50 m. Oggi in produzione ci sono migliaia di alberi con coordinate GPS vere: le distruggerebbe |
| `import_gpkg.py` | Import del censimento di Bra. `OWNER_ID = 4` oggi è `demo_user`, i cui alberi vengono cancellati a ogni accesso alla demo. Conserva la mappatura delle colonne del censimento (`_LOCALITA'`, `_TASSONOMI`, `_CLASSE VT`, …) |
| `import_silvio_pellico.py` | Import di `silvio pellico.gpkg`, già fatto. `OWNER_ID = 29` non esiste. Conserva la mappatura particolare di quel file (tabella `pellico`, `LOCALITA'` senza underscore, `_name` invece di `name`) |
| `seed_data.py` | Popolava un database vuoto con 60 alberi finti intestati a `Dario`, che in produzione è un utente reale |
| `populate_comuni_coords.py` | Cercava `coordinate` nel dataset comuni-json, campo che la fonte non espone più: aggiorna 0 righe su 7904. E nessuna parte dell'app legge `comune.latitude`/`longitude` |
| `temp_read.py` | Stampa tutte le celle del foglio `A` del template ARETE |
| `extract_lookup.py` | Estrae da quel foglio una tabella di lookup nome → codice |
| `inspect_sheet.py` | Estrae le liste dei menu a tendina per categoria. Richiede **pandas**, che non è in `requirements.txt` |

I tre ultimi sono gli strumenti con cui sono nate `tools/lookup_tables.py` e
`tools/dropdowns_ord.py`. **Serviranno di nuovo** il giorno che ARETE pubblica
una versione nuova del template: scrivono una bozza in
`Schede_Rilevamento_ARETE/lookup_tables.py`, da confrontare a mano con i file
veri in `tools/`, che restano la fonte usata dall'applicazione.

Gli import da file oggi si fanno dal tab **Importa** della webapp
(`POST /import/gpkg`, `POST /import/gpx`), che ha anteprima, mappatura delle
colonne, gestione dei conflitti e — soprattutto — non sbaglia il proprietario.

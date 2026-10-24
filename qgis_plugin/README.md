# Plugin QGIS «Silvae Pro»

Collega QGIS a Silvae Pro: carica gli alberi di un comune in un GeoPackage
locale, con lo stile per classe di rischio ARETE / condizione VTA generato
dalla stessa palette della webapp, e li aggiorna in modo incrementale.
Piano completo e stato di avanzamento in [`../qgis.md`](../qgis.md).

**Fasi 1-4** (questa versione, 0.4.0): collegamento con token API, *Carica da
Silvae* (GPKG locale, stile, aggiornamento incrementale), *Invii in attesa*
(ritiro di quanto mandato dalla webapp con «Invia a QGIS»), *Invia a
Silvae* (mappatura colonne, anteprima, scrittura del collegamento nel
layer) e risoluzione dei conflitti. Non ancora: invio delle sole feature
modificate — oggi parte tutto il layer, o la selezione.

## Installazione

1. Crea lo zip del plugin (dalla cartella del repository):
   ```bash
   cd qgis_plugin && zip -r silvae_qgis.zip silvae_qgis -x '*/__pycache__/*'
   ```
2. In QGIS (3.28 o successivo): *Plugin → Gestisci e installa plugin →
   Installa da ZIP* → scegli `silvae_qgis.zip`.
3. Compare il menu *Vettore → Silvae Pro* e un pulsante «Carica da Silvae» in
   barra strumenti.

## Uso

1. Nella webapp: nome utente in alto → **Il mio account** → **Token API per
   QGIS** → *Crea token*. Copia il token (`slv_…`): non sarà più visibile.
2. In QGIS: *Silvae Pro → Collegamento a Silvae…* → URL del server e token →
   *Verifica* → *Salva*.
3. *Silvae Pro → Carica da Silvae…* → comune, cartella (di default quella del
   progetto), stile → *Carica*. Nasce `silvae_<comune>.gpkg` (layer `alberi`),
   aggiunto al progetto e già colorato.
4. Ripetendo *Carica da Silvae* sullo stesso progetto vengono scaricati solo
   gli alberi modificati o nuovi dall'ultimo caricamento (per `uuid`); gli
   alberi cancellati sul server restano nel file. *Riscarica tutto* rifà il
   file da zero.
5. **Invia a Silvae**: seleziona il layer nel pannello dei layer (può essere
   il tuo, con le tue colonne) e apri *Silvae Pro → Invia a Silvae…*. Scegli
   il comune, eventualmente «solo le feature selezionate», controlla la
   corrispondenza delle colonne e premi **Anteprima**: il server dice quanti
   alberi verrebbero creati, aggiornati, lasciati invariati o sono in
   conflitto, senza scrivere nulla. Con **Invia** la scrittura avviene e il
   plugin aggiunge al layer le colonne `silvae_uuid`, `silvae_id` e
   `silvae_synced_at`: da lì in poi il layer è collegato e gli invii
   successivi aggiornano gli stessi alberi. La mappatura resta salvata nel
   progetto.
   **Conflitti**: se un albero è stato modificato nella webapp dopo il tuo
   ultimo allineamento, quella feature non viene scritta e si apre la
   finestra dei conflitti: in alto l'elenco degli alberi con i campi
   discordanti e chi li ha modificati, in basso il confronto valore per
   valore. Per ciascuno scegli *Tieni la versione di QGIS* (sovrascrive
   Silvae), *Prendi la versione di Silvae* (sovrascrive il layer locale,
   posizione compresa) o *Decidi più tardi* (predefinito: non cambia nulla e
   l'albero resta in conflitto). I pulsanti in fondo applicano la stessa
   scelta a tutti.
6. **Invii in attesa**: nella webapp, dal tab Esporta, dalla barra di
   selezione della tabella o dalla selezione per area sulla mappa, premi
   *Invia a QGIS*. In QGIS apri *Silvae Pro → Invii in attesa*: l'elenco si
   aggiorna ogni 30 secondi; doppio clic su una riga (o *Ritira*) scarica
   quegli alberi nel GPKG del comune e, se l'invio veniva da una selezione
   per area, disegna il perimetro come layer temporaneo. Un invio ritirato
   esce dall'elenco; *Elimina* lo rimuove dal server.

Il GPKG è una copia di lavoro: funziona offline e si apre in QField. Il
campo `uuid` è la chiave che lo tiene collegato a Silvae — non cancellarlo.

## Struttura

```
silvae_qgis/
├── metadata.txt        versione, requisiti (QGIS ≥ 3.28)
├── __init__.py         classFactory
├── plugin.py           menu, barra strumenti, azioni
├── api.py              client HTTP (QgsBlockingNetworkRequest, token Bearer)
├── settings.py         URL, token, ultimo comune (QgsSettings)
├── layer_store.py      GPKG locale: creazione, upsert per uuid, stile
├── pull.py             «Carica da Silvae» e ritiro degli invii
├── push.py             «Invia a Silvae»: GeoJSON, blocchi, collegamento
├── mapping.py          corrispondenza colonne ↔ campi, salvata nel progetto
├── conflicts.py        confronto e risoluzione dei conflitti
└── ui/                 finestre Collegamento, Carica, Invia e Conflitti, dock Invii
```

Il token è salvato in `QgsSettings` (file .ini del profilo). Il passaggio al
gestore autenticazioni cifrato di QGIS riguarda solo `settings.py`.

## Sviluppo e test

Il cuore del plugin (client, GPKG, pull) non dipende da `iface` e si prova
senza aprire QGIS, con il PyQGIS di sistema contro l'app avviata in locale:

```bash
# terminale 1: server con un DB SQLite di prova
DATABASE_URL=sqlite:///prova.db SECRET_KEY=x python -c "import app; app.app.run(port=5077)"
# terminale 2: PyQGIS di sistema (non il venv)
/usr/bin/python3 -c "import sys; sys.path.insert(0,'qgis_plugin'); ..."
```

Le finestre si costruiscono anche offscreen (`QT_QPA_PLATFORM=offscreen`)
con un `iface` finto: vedi lo storico dei test in `qgis.md` §12.

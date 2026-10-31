# Silvae Pro — Sistema di Gestione Alberi con Protocollo ARETE

Applicazione web per il censimento e la valutazione del rischio degli alberi urbani, conforme al **Protocollo ARETE** (Analisi del Rischio degli Elementi Arborei in ambiente urbano).

> Fonte: "Protocollo Areté® per la Valutazione del Rischio Arboreo [ver. 4.0] - ARBORETE® ([http://www.protocolloarete.it](http://www.protocolloarete.it))".

---

## Funzionalità principali

- **Censimento alberi** con dati dendrologici completi (specie, dimensioni, coordinate GPS o indirizzo)
- **Valutazione del rischio ORD** secondo il protocollo ARETE: prodotto di Bersaglio (B), Inclinazione (I) e Probabilità (P)
- **Calcolo automatico del bersaglio** da tipo di uso del suolo e flusso (pedoni, traffico, proprietà, occupazione)
- **Valore ecologico**: stima di biomassa, CO₂ sequestrata, O₂ prodotto, intercettazione acqua e valore monetario (€)
- **Statistiche della vista**: conteggio degli alberi visibili per classe di rischio ORD e per condizione VTA, con la quota di alberi non valutabili (NA); i contatori sono **cliccabili** e filtrano la lista
- **Mappa interattiva** (Leaflet) con clustering, marker colorati per classe di rischio, ID albero nel popup e **selezione per area** (poligono disegnato sulla mappa) per esportare o generare le schede degli alberi inclusi
- **Esportazione** in formato Excel (.xlsx), GeoPackage (.gpkg) e waypoint GPX (.gpx), con scelta dei campi da esportare
- **Mappa per la relazione**: tavola A4 in PNG o PDF con basemap OpenStreetMap o ortofoto, alberi colorati per classe di rischio/condizione, ID, perimetro dell'area, legenda, barra di scala e nord — generata sul server senza librerie GIS né browser (vedi [Mappa per la relazione](#mappa-per-la-relazione))
- **Schede di rilevamento ARETE** (foglio ORD): una scheda per albero generata dal **template ufficiale** `Schede_Rilevamento_ARETE_DEMO_ver.2.0.xlsm`, compilata coi dati del database e restituita in uno .zip con le cartelle `excel/` (.xlsx) e `pdf/` (se LibreOffice è disponibile sul server)
- **Triage TRG-P** (popolamenti arborei): calcolatore di screening rapido con categoria di intervento 1–6 e valore ornamentale ([`tools/trg_p_calculator.py`](tools/trg_p_calculator.py)) — *modulo di calcolo pronto, non ancora esposto nell'interfaccia/API*
- **Importazione** da file GeoPackage (.gpkg) o waypoint GPX (.gpx, es. rilievi GPS o esportati da QGIS) — compatibile con i censimenti ARETE e con i file esportati dall'app, con anteprima e mappatura colonne
- **Input vocale** per la compilazione delle schede (Web Speech API + parsing dell'intento tramite Groq)
- **Geocodifica** diretta e inversa degli indirizzi (Nominatim/OpenStreetMap) e autocompletamento dei comuni italiani
- **Autenticazione JWT** multi-utente con tre ruoli (`superuser`, `city`, `user`) e reset password via email
- **Tab Algoritmo ARETE** con documentazione tecnica integrata nella webapp

---

## Protocollo ARETE — Calcolo del Rischio

Il rischio ORD è calcolato come prodotto **B · I · P** con tre fattori da 1 a 7:

| Fattore | Significato |
|---------|-------------|
| **B** — Bersaglio | Vulnerabilità dell'area colpibile (persone, proprietà, traffico) |
| **I** — Inclinazione | Propensione della chioma/ramo a cadere |
| **P** — Probabilità | Probabilità di cedimento strutturale dell'albero |

Il valore BIP (1–343) è poi classificato:
- **Rischio accettabile** (verde): descrizione positiva
- **ALARP / tollerabile per accordo** (arancione)
- **Rischio inaccettabile** (rosso): intervento necessario

### Tipi di bersaglio supportati

| Tipo | Input richiesto | Calcolo |
|------|----------------|---------|
| Proprietà | Valore € | Scala logaritmica a 7 classi |
| Occupazione | Ore/giorno | Scala a 7 classi |
| Pedoni/Ciclisti | Flusso (pedoni/ora) | Formula con larghezza zona e velocità pedonale |
| Traffico (30/50/70/90 km/h) | Flusso (auto/giorno) | Formula con t_stop e t_attraversamento |

La larghezza della zona è calcolata automaticamente:
- **Chioma**: `(diametro_chioma + altezza_albero) / 2`
- **Ramo**: `lunghezza_ramo × 1.25`

Un **moltiplicatore** opzionale (es. 2 per zone scolastiche) scala la classe bersaglio finale.

La logica di calcolo è implementata in [`tools/ord_calculator.py`](tools/ord_calculator.py), con le tabelle di lookup e i valori dei menu a tendina in [`tools/lookup_tables.py`](tools/lookup_tables.py) e [`tools/dropdowns_ord.py`](tools/dropdowns_ord.py). Il calcolo è allineato al foglio ORD della scheda ufficiale ARETE (vedi [Schede di rilevamento](#schede-di-rilevamento-arete)).

Il **triage TRG-P** (screening rapido per popolamenti arborei, foglio 2 del modulo ARETE) è implementato in [`tools/trg_p_calculator.py`](tools/trg_p_calculator.py) e [`tools/dropdowns_trg_p.py`](tools/dropdowns_trg_p.py): stessa matrice di rischio B·I·P, ma con classe di pericolo qualitativa, valutazione singola (senza rischio residuo), categoria di intervento 1–6 e stima del valore ornamentale. Il modulo è utilizzabile da Python ma non è ancora collegato a endpoint o tab della webapp.

---

## Stack tecnologico

- **Backend**: Python 3.12 (vedi `.python-version`), Flask 3.1, SQLAlchemy 2.0, psycopg2-binary
- **Database**: PostgreSQL (le coordinate sono memorizzate come `latitude`/`longitude` numeriche; **PostGIS non è richiesto**)
- **Frontend**: HTML5, CSS3, JavaScript vanilla, Leaflet.js, Font Awesome
- **Autenticazione**: JWT (PyJWT) per la webapp, **token API** longevi e revocabili (`slv_…`) per i client esterni come il plugin QGIS; password hash con `werkzeug.security`
- **Export/Schede**: openpyxl (Excel e scheda ARETE), Pillow (loghi nella scheda), LibreOffice *(opzionale, per la conversione in PDF)*
- **Geocodifica**: geopy + Nominatim (OpenStreetMap)
- **Input vocale**: Web Speech API (browser) + Groq (`llama-3.1-8b-instant`) per il riconoscimento dell'intento
- **Email**: SMTP (Gmail) per il reset password
- **Deploy**: Gunicorn + Railway (o qualsiasi host con PostgreSQL)

---

## Struttura del progetto

```
tree_project/
├── app.py                      # Backend Flask: API, modelli, autenticazione, import/export
├── tools/
│   ├── ord_calculator.py       # Logica calcolo ARETE (B·I·P, bersaglio, classi, valore ecologico)
│   ├── ord_scheda.py           # Compila la scheda ARETE (foglio ORD) dal template .xlsm → .xlsx/.pdf
│   ├── trg_p_calculator.py     # Calcolatore triage TRG-P (popolamenti arborei)
│   ├── lookup_tables.py        # Tabelle di lookup (specie, patologie, prescrizioni, ...)
│   ├── dropdowns_ord.py        # Valori dei menu a tendina ORD
│   ├── dropdowns_trg_p.py      # Valori dei menu a tendina TRG-P
│   ├── palette.py              # Colori di rischio e condizione: UNICA fonte (webapp, mappa, QGIS)
│   ├── qgis_style.py           # Stile QGIS (.qml) generato dalla palette
│   ├── map_render.py           # Tavola cartografica PNG/PDF (tessere basemap + Pillow)
│   ├── fonts/                  # DejaVu Sans, usato dalla tavola cartografica
│   └── report_templates.py     # Registro dei template di scheda (ARETE .xlsx, base HTML)
├── Schede_Rilevamento_ARETE/
│   └── Schede_Rilevamento_ARETE_DEMO_ver.2.0.xlsm   # Template ufficiale della scheda
├── frontend/
│   ├── index.html              # Interfaccia principale (multi-tab)
│   ├── app.js                  # Logica frontend (fetch, mappa, form, esportazione)
│   ├── voice.js                # Input vocale (Web Speech API + intent Groq)
│   ├── style.css               # Stili dell'applicazione
│   ├── images/                 # Loghi (usati anche nella scheda ARETE)
│   └── tests/                  # Verifiche del frontend su jsdom (run.sh, serve Docker)
├── qgis_plugin/
│   └── silvae_qgis/            # Plugin QGIS «Silvae Pro» (vedi qgis_plugin/README.md e docs/qgis.md)
├── docs/                       # Documentazione: piano QGIS, prossimi passi, calcolo ARETE
│   ├── qgis.md                 # Piano e stato del ponte con QGIS
│   ├── next_steps.md           # Proposte di sviluppo ancora aperte
│   └── calculus.md             # Calcolo ARETE in dettaglio (non in git: protocollo ARETE)
├── scripts/                    # Utilità da riga di comando (vedi scripts/README.md)
│   ├── seed_comuni.py          # Riempie la tabella dei comuni italiani
│   ├── create_admin.py         # Reimposta la password di admin
│   ├── dump_gpkg.py            # Ispeziona un .gpkg senza QGIS
│   ├── make_demo_gpkg.py       # Genera demo.gpkg per provare l'importazione
│   └── archivio/               # Script che hanno fatto il loro lavoro: NON eseguire
├── test_locale.py              # Avvio rapido in locale (anche con SQLite, senza PostgreSQL)
├── test_flask_api.py           # Test dell'API
├── Procfile                    # Configurazione Gunicorn per Railway
├── .python-version             # Versione Python per Railway (3.12)
├── requirements.txt            # Dipendenze Python
├── .env                        # Variabili d'ambiente locali (non in git)
├── .env.example                # Template variabili d'ambiente
└── .gitignore
```

---

## Setup locale

### Prerequisiti

- Python 3.12 (consigliato; ≥ 3.10 funziona in locale)
- PostgreSQL
- *(opzionale)* LibreOffice (`libreoffice-calc`) per ottenere anche i PDF delle schede ARETE

### 1. Clona il repository

```bash
git clone <url-repository>
cd tree_project
```

### 2. Crea e attiva l'ambiente virtuale

```bash
python3 -m venv flaskenv
source flaskenv/bin/activate        # Linux/Mac
# flaskenv\Scripts\activate         # Windows
```

### 3. Installa le dipendenze

```bash
pip install -r requirements.txt
```

### 4. Crea il database PostgreSQL

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE trees_db;
```

### 5. Configura le variabili d'ambiente

Copia `.env.example` in `.env` e modifica i valori:

```bash
cp .env.example .env
```

```ini
DATABASE_URL=postgresql://postgres:tuapassword@localhost/trees_db
SECRET_KEY=chiave-segreta-lunga-e-casuale

# Opzionali:
# Reset password via Gmail SMTP (SMTP_PASSWORD = App Password Gmail)
SMTP_USER=tua.gmail@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
APP_BASE_URL=http://localhost:5000
# Input vocale (parsing intento)
GROQ_API_KEY=gsk_...

# Registrazione pubblica (disabilitata di default finché non si è in produzione)
REGISTRATION_ENABLED=false
# Credenziali degli account demo (default: demo_user / demo_password, demo_city / demo_city_password)
# DEMO_USERNAME=demo_user
# DEMO_PASSWORD=demo_password
# DEMO_CITY_USERNAME=demo_city
# DEMO_CITY_PASSWORD=demo_city_password
```

> Le variabili `SMTP_*`, `APP_BASE_URL` e `GROQ_API_KEY` sono opzionali: senza di esse il reset password stampa solo il link in console e l'input vocale è disabilitato.

### 6. Avvia l'applicazione

```bash
python app.py
```

Lo schema del database viene creato e aggiornato automaticamente all'avvio (nessuna migrazione manuale necessaria). Al primo avvio viene creato un utente amministratore predefinito **`admin` / `admin`** (ruolo `superuser`) — **cambia subito la password**.

L'app è disponibile su: `http://127.0.0.1:5000`

> **Nota**: il warning *"Do not use the development server in a production environment"* è normale durante lo sviluppo locale.

### Avvio rapido senza PostgreSQL

Per provare l'interfaccia senza configurare un database, `test_locale.py` avvia l'app su un file SQLite locale (`test_locale.db`, ignorato da git) e apre il browser:

```bash
python test_locale.py --sqlite            # zero-setup, DB SQLite locale
python test_locale.py --port 8000         # porta diversa
python test_locale.py --no-browser        # non aprire il browser
```

Senza `--sqlite` usa `DATABASE_URL` (PostgreSQL) come `app.py`.

---

## Ruoli utente

| Ruolo | Permessi |
|-------|----------|
| **superuser** | Accesso completo: gestione utenti, città, tutti gli alberi (lettura e scrittura) |
| **city** (comune) | **Sola lettura** sugli alberi del proprio comune: li visualizza, li esporta e genera le schede; collega gli agronomi (`user`) al comune. Il selettore dei comuni mostra solo il suo (gli altri comuni del database non gli vengono elencati) |
| **user** (agronomo) | Censisce, modifica e valuta i propri alberi nei comuni a cui è collegato |

L'accesso agli alberi è filtrato per comune tramite il modello `CityMembership` (relazione città ↔ agronomi).

L'utente `city` **non può modificare gli alberi**: l'interfaccia è la stessa degli altri ruoli, ma qualsiasi tentativo di salvataggio (aggiunta, modifica, eliminazione, ispezione, importazione) viene rifiutato dal backend con `403` e il messaggio *"Solo gli utenti agronomi possono modificare i campi degli alberi: l'utente comune ha accesso in sola lettura."*, mostrato nella barra di stato. Il controllo è centralizzato in `_city_readonly()` in [`app.py`](app.py).

### Onboarding di un comune e collegamento degli agronomi

1. Il `superuser` crea l'account del comune dal tab **Gestione** (ruolo `city`, nome del comune, email opzionale) con una **password temporanea** e la comunica al comune.
2. Il comune accede e apre **Il mio account** (pulsante nell'header, disponibile per tutti i ruoli): qui **cambia la password** (richiede quella attuale; `POST /change-password`) e imposta la propria **email**, necessaria per il recupero password con "Password dimenticata" (`PATCH /me`).
3. Ogni agronomo (ruolo `user`) ha un **codice agronomo** univoco e permanente nel formato `AGR-XXXX-XXXX`, generato una volta sola alla creazione dell'account (e assegnato automaticamente agli account esistenti al primo avvio/login). L'agronomo lo vede nell'header dell'app e lo copia con un clic.
4. Il comune inserisce il codice nel pannello **Agronomi del Comune** (tab Gestione) per collegare l'agronomo: da quel momento vede i suoi alberi. Il collegamento per il ruolo `city` avviene **solo tramite codice**.
5. Il `superuser` può fare la stessa associazione da un pannello identico, scegliendo il comune da un selettore e inserendo il codice **oppure** lo username dell'agronomo; nella lista utenti vede i codici di tutti gli agronomi.
6. **Assistenza**: dalla lista utenti il `superuser` può modificare l'**email** di qualsiasi account e impostargli una **nuova password** temporanea (`PATCH /admin/users/<id>`), ad es. per un utente che non riesce più ad accedere.

Gli utenti vengono creati da un `superuser` (qualsiasi ruolo) o da un `city` (solo agronomi del proprio comune). La **registrazione pubblica** (`/register` + link "Crea account") è **disabilitata di default**: si riattiva impostando `REGISTRATION_ENABLED=true` e ripristinando il link nel frontend (vedi commenti in `frontend/index.html` e `frontend/app.js`).

### Token API (client esterni)

Oltre al JWT di `/login` (che scade e congela ruolo e comune), un utente può creare da `POST /me/tokens` dei **token API** nel formato `slv_…`, pensati per client che restano collegati a lungo — in primo luogo il plugin QGIS (vedi [`docs/qgis.md`](docs/qgis.md)). Si usano nello stesso header `Authorization: Bearer slv_…`; in DB è salvato solo l'hash SHA-256, ruolo e comune vengono riletti dall'utente a ogni richiesta e la revoca (`DELETE /me/tokens/<id>`) è immediata. Un token API non può creare altri token; gli account demo non ne hanno. Il ruolo `city` può usarli in sola lettura come nella webapp.

---

## Account demo

Due account preconfigurati permettono di mostrare l'applicazione a potenziali clienti senza toccare dati reali. Vengono creati automaticamente all'avvio e **ripristinati a ogni login** a uno stato fisso: chiunque entri vede sempre la stessa demo di **Torino** (6 alberi), e le modifiche fatte durante la sessione non sopravvivono all'accesso successivo.

| Account | Credenziali (default) | Ruolo | Mostra |
|---------|----------------------|-------|--------|
| **demo_user** | `demo_user` / `demo_password` | `user` (agronomo) | Censimento e valutazione dei 6 alberi demo |
| **demo_city** | `demo_city` / `demo_city_password` | `city` (comune) | Gestione comunale, collegato **solo** a `demo_user` |

Caratteristiche:

- **Isolamento**: gli alberi demo appartengono a `demo_user` e non sono visibili agli altri utenti; sono esclusi anche dalla vista e dagli export del `superuser`.
- **Reset a ogni login**: all'accesso di uno dei due account, gli alberi demo e il collegamento `demo_city → demo_user` vengono ricreati identici (eventuali modifiche/collegamenti aggiunti durante la demo vengono azzerati).
- **Sola lettura per le azioni amministrative**: gli account demo non possono creare utenti né modificare i collegamenti agronomi (le relative funzioni sono visibili ma bloccate), così la demo resta un sandbox non persistente.

Le credenziali sono personalizzabili con le variabili d'ambiente `DEMO_USERNAME`, `DEMO_PASSWORD`, `DEMO_CITY_USERNAME`, `DEMO_CITY_PASSWORD`.

---

## Deploy su Railway

### 1. Crea il progetto su Railway

- Crea un nuovo progetto su [railway.app](https://railway.app)
- Aggiungi un servizio **PostgreSQL** dal marketplace Railway
- Collega il tuo repository GitHub

### 2. Variabili d'ambiente su Railway

Nel servizio dell'app, imposta le variabili:

| Variabile | Valore |
|-----------|--------|
| `DATABASE_URL` | Copiare dalla variabile `DATABASE_URL` del servizio PostgreSQL Railway |
| `SECRET_KEY` | Stringa casuale lunga (es. generata con `openssl rand -hex 32`) |
| `SMTP_USER` / `SMTP_PASSWORD` | *(opzionale)* Credenziali Gmail per il reset password |
| `APP_BASE_URL` | *(opzionale)* URL pubblico dell'app (per i link di reset) |
| `GROQ_API_KEY` | *(opzionale)* API key Groq per l'input vocale |
| `REGISTRATION_ENABLED` | *(opzionale)* `true` per riabilitare la registrazione pubblica (default `false`) |
| `DEMO_*` | *(opzionale)* Credenziali degli account demo (vedi sezione [Account demo](#account-demo)) |
| `SCHEDA_WORK_DIR` | *(opzionale)* Cartella di lavoro temporanea per la generazione delle schede (default `.scheda_work/` nel progetto) |

> Railway usa `postgres://` come prefisso — l'app lo converte automaticamente in `postgresql://`.

> **PDF delle schede su Railway**: l'immagine di default di Railway **non include LibreOffice**, quindi lo .zip delle schede contiene solo la cartella `excel/` (la cartella `pdf/` resta vuota). Per avere anche i PDF serve un'immagine con LibreOffice (es. un `Dockerfile` custom o una configurazione Nixpacks che installi `libreoffice`); l'app rileva `libreoffice`/`soffice` nel `PATH` automaticamente.

### 3. Deploy

Ogni push sul branch principale avvia il deploy automatico. Il `Procfile` istruisce Railway ad avviare Gunicorn:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --preload
```

---

## Interfaccia utente — Tab

| Tab | Contenuto |
|-----|-----------|
| **Alberi** | Tabella degli alberi con ricerca, ordinamento, aggiunta/modifica/cancellazione, e **barra statistiche** con i conteggi per categoria (vedi [Statistiche della vista](#statistiche-della-vista)). Gli alberi si caricano **solo dopo aver scelto un comune** nel selettore in alto (per `city` è automatico); la voce *Carica tutti gli alberi* in fondo al menu richiede esplicitamente tutti quelli visibili all'account |
| **Mappa** | Mappa Leaflet con marker e clustering, filtri per città e indirizzo, **barra statistiche** con filtro per categoria (condiviso con il tab Alberi), ID albero nel popup e **selezione per area**: si disegna un poligono sulla mappa e si esportano gli alberi contenuti, se ne generano le schede o la **mappa per la relazione** (PNG/PDF) |
| **Gestione** | Pannello amministratore: gestione utenti, città, agronomi, reset password |
| **Esporta** | Esportazione in Excel (.xlsx), GeoPackage (.gpkg) o GPX (.gpx), **mappa per la relazione** (PNG/PDF), **schede ARETE** e **Invia a QGIS** — intera raccolta o selezione manuale, con **scelta dei campi da esportare** (esclusione singoli campi) |
| **Importa** | Importazione da file .gpkg o .gpx (censimenti esterni, rilievi GPS o file esportati dall'app) con anteprima, mappatura colonne e gestione conflitti (skip/update) |
| **Algoritmo** | Documentazione tecnica del calcolo ARETE integrata nella webapp |

---

## Schede di rilevamento ARETE

La generazione delle schede **non reimpagina** i dati: parte dal template ufficiale [`Schede_Rilevamento_ARETE/Schede_Rilevamento_ARETE_DEMO_ver.2.0.xlsm`](Schede_Rilevamento_ARETE/) (foglio **ORD**) e scrive i valori del database nelle celle corrispondenti. Layout, etichette, celle unite e stili restano identici all'originale.

- **Niente macro**: l'output è `.xlsx`, il VBA viene scartato.
- **Valori, non formule**: dove il DB ha già il risultato calcolato (es. il rischio) viene scritto come valore.
- **Loghi**: i loghi in `frontend/images/` vengono inseriti nella scheda (richiede Pillow).
- **Output**: uno `.zip` (`schede_albero.zip`) con `excel/` (un `.xlsx` per albero, nome basato sull'ID personalizzato) e `pdf/` (i PDF corrispondenti, convertiti con LibreOffice in un'unica invocazione headless). Se LibreOffice non è installato, `pdf/` resta vuota.
- La mappa campo→cella è `CELL_MAP` in [`tools/ord_scheda.py`](tools/ord_scheda.py): è il punto da modificare se un valore deve finire in una cella diversa.

I template disponibili sono registrati in [`tools/report_templates.py`](tools/report_templates.py):

| ID | Nome | Formato |
|----|------|---------|
| `scheda_arete` *(default)* | Scheda di rilevamento ARETE (ORD) | .zip con .xlsx (+ .pdf) |
| `scheda_base` | Scheda albero (base HTML) | HTML segnaposto, una pagina per albero |

Le schede si generano dal tab **Esporta** (tutti gli alberi visibili o selezione manuale) oppure dalla **Mappa** tramite la selezione per area.

---

## Import / Export GPX

Il formato GPX (waypoint) è il ponte con i GPS da campo, gli smartphone e QGIS (*Esporta → Salva come → GPX*). È gestito senza librerie esterne (`xml.etree`).

**Import** (`POST /import/gpx`): ogni `<wpt>` diventa un albero. La mappatura automatica riconosce `lat`/`lon` (coordinate), `name` → ID albero, `cmt` → specie, `desc` → note; gli eventuali figli di `<extensions>` (attributi scritti da QGIS o da Silvae Pro) sono proposti come colonne aggiuntive nella finestra di mappatura, come per il GPKG. `ele` e `sym` vengono ignorati (non esiste un campo quota). Comune, conflitti (`skip`/`update`) e dedup per coordinate funzionano come per il GPKG.

**Export** (`GET /export/gpx`): GPX 1.1 in WGS84, un `<wpt>` per albero con `name` = ID, `cmt` = specie, `desc` = riassunto leggibile (specie, condizione, CPC, classe di rischio, indirizzo, comune), `sym` = `Flag, Blue`, e in `<extensions>` i campi Silvae (`custom_id`, `uuid`, `city`, `species`, `condition`, `cpc`, `address`, `rischio`, `next_check`, `comments`) che QGIS mostra come attributi del layer. Nei file generati da Silvae (`creator="Silvae Pro"`) `cmt` e `desc` vengono ignorati alla reimportazione, perché derivati dai campi in `<extensions>`. Disponibile dal tab **Esporta**, dalla barra di selezione della tabella e dalla selezione per area sulla mappa.

---

## Importazione: abbinamento e regole di scrittura

Ogni albero ha un **`uuid`** stabile (generato alla creazione, presente nei GPKG e GPX esportati) e i campi **`updated_at` / `updated_by`** con data e utente dell'ultima modifica, restituiti da `/trees` e `/tree/<id>`. L'importazione da file (`/import/gpkg`, `/import/gpx`) passa per un'unica funzione, `_upsert_tree` in [`app.py`](app.py), la stessa usata dal plugin QGIS in `POST /qgis/features` ([`docs/qgis.md`](docs/qgis.md)):

- **Abbinamento** con un albero esistente, cercato **solo tra gli alberi visibili** a chi importa (i propri per l'agronomo): prima per `uuid`, poi per **coordinate** (entro ~10 cm), infine per `custom_id` + comune ma solo se la riga non ha coordinate. Con le coordinate non si abbina mai per `custom_id`, perché nei censimenti la numerazione riparte per località e alberi diversi condividono lo stesso numero. Un `uuid` sconosciuto (albero cancellato, o file esportato da un altro account) non è un errore: si prosegue con gli altri criteri e, se l'albero è nuovo, l'uuid viene riusato quando è libero.
- **Un valore vuoto nel file non tocca il campo**: in modalità `update` si sovrascrivono solo i valori presenti, quindi un file con poche colonne non cancella ciò che il database ha già. L'owner dell'albero non cambia mai.
- **I campi derivati vengono ignorati** anche se presenti nel file (`rischio`, classi `bersaglio_chioma`/`bersaglio_ramo`, valori ecologici, `city`, `owner_id`, `uuid`): il server li ricalcola — quindi anche gli alberi importati hanno il **rischio ORD** calcolato, se i campi ARETE sono completi.
- La risposta riporta `created`, `updated`, `unchanged`, `skipped`, `errors` (oltre a `inserted` = creati + aggiornati + già allineati, per compatibilità): reimportare lo stesso file dà tutti `unchanged`.

---

## Mappa per la relazione

Dal tab **Esporta** (alberi caricati o selezionati in tabella), dalla barra di selezione della tabella o dalla **selezione per area** sulla mappa si genera una **tavola cartografica A4** da inserire nella relazione al comune: `GET /report/map`.

- **Sfondo**: OpenStreetMap (default) oppure ortofoto Esri World Imagery — le stesse basemap della mappa web. Le tessere vengono scaricate dal server, cucite e ritagliate sull'inquadratura degli alberi (zoom frazionario, fino a 2 livelli oltre quello nativo ingrandendo le tessere, come sulla mappa web; una tessera mancante viene sostituita dal quadrante della tessera padre).
- **Contenuto**: un marker per albero colorato con la stessa casella della [barra statistiche](#statistiche-della-vista) (rischio ORD se calcolato, altrimenti condizione VTA/CPC, altrimenti NA) e i colori di [`tools/palette.py`](tools/palette.py); l'ID albero come etichetta (omessa oltre i 200 alberi, dove i marker si rimpiccioliscono); il perimetro dell'area selezionata; legenda con i conteggi per classe; barra di scala; freccia del nord; attribuzione della basemap; titolo con comune, numero di alberi e data.
- **Formato**: `pdf` (pagina A4, orientamento scelto in base alla forma dell'inquadratura) o `png` a 250 dpi, per incollarla in un documento. Il PDF è la stessa immagine impaginata da Pillow (JPEG interno): un'unica pipeline, nessun browser, LibreOffice o libreria GIS sul server.
- **Implementazione**: [`tools/map_render.py`](tools/map_render.py) non conosce il dominio — riceve punti già colorati e le voci della legenda da `report_map()` in [`app.py`](app.py). Usa solo `urllib`, Pillow e i font DejaVu in `tools/fonts/`. Le tessere sono in una cache in memoria per processo (`lru_cache`), e le richieste a OSM portano lo User-Agent `SilvaePro-MapExport` come richiesto dalla tile usage policy.

---

## Condizione dell'albero

Il campo **Condizione** (campo `condition` nel database) rappresenta lo stato vegetativo/fitosanitario dell'albero ed è visualizzato tramite badge colorati in tabella, schede e popup della mappa.

Quando è presente il **CPC**, la condizione assume il valore della classe CPC (il CPC "vince"). Il colore segue la classe CPC (A/B/C/C/D/D); in assenza di CPC vale la corrispondenza sul testo (case-insensitive). Le lettere di classe hanno la priorità sui sinonimi testuali:

| Categoria | Classe CPC | Parole chiave | Colore |
|-----------|-----------|--------------|--------|
| **Ottimo** | `A` | `ottimo`, `eccellente` | Verde |
| **Buono** | `B` | `buono` | Verdino (verde chiaro) |
| **Discreto** | `C` | `discreto`, `mediocre` | Arancione |
| **Scarso / Critico** | `C/D`, `D` | `scarso`, `critico`, `morto`, `abbattuto` | Rosso |
| **Non classificato** | — | qualsiasi altro valore | Grigio |

I valori consigliati da inserire nel form ispezioni sono: **Buono**, **Discreto**, **Scarso**.

Durante l'importazione da file `.gpkg`, le classi VTA nel campo `_CLASSE VT` vengono convertite automaticamente:

| Classe VTA | Condizione salvata |
|---|---|
| `A` | Ottimo |
| `B` | Buono |
| `C` | Discreto |
| `C/D` | Scarso |
| `D` | Critico |
| `ABBATTUTO` | Abbattuto (invariato) |

Valori già in forma testuale (es. file esportati da Silvae Pro) vengono lasciati invariati.

---

## Colori di rischio e condizione (palette)

Tutti i colori che rappresentano una **classe di rischio ARETE** o una **condizione VTA/CPC** — badge, chip statistici, bordo delle righe, marker sulla mappa — sono definiti **una volta sola** in [`tools/palette.py`](tools/palette.py). Per ciascuna categoria ci sono tre valori: `main` (colore pieno: marker, pallini, simboli QGIS), `fg` e `bg` (testo e sfondo dei badge).

Il flusso è:

1. `GET /palette.css` genera un blocco `:root { --risk-<chiave>, --risk-<chiave>-fg, --risk-<chiave>-bg, --cond-<chiave>, … }` dalla palette; [`index.html`](frontend/index.html) lo carica **prima** di `style.css`.
2. [`style.css`](frontend/style.css) usa solo quelle variabili (classi `.cb-*`, `.risk-*`, `.tr-*`, `.cond-dot`, `.tl-dot-*`) — nessun esadecimale per rischio/condizione.
3. [`app.js`](frontend/app.js) le legge con `paletteVar()` / `condColor()` / `riskColors()` per i marker Leaflet e i colori inline.
4. `GET /palette` restituisce la stessa tavolozza in JSON, per strumenti esterni.

Le chiavi delle categorie (`accettabile`, `alarp`, `accordo`, `inaccettabile`, `na`; `good`, `buono`, `fair`, `poor`, `other`) sono le stesse usate da `riskStatCategory()`/`condCategory()` nel frontend e da `_risk_category()` in `app.py`. **Per cambiare un colore si modifica solo `palette.py`**: webapp e mappa lo ricevono al ricaricamento, e lo stile QGIS (`GET /qgis/style.qml`, generato da [`tools/qgis_style.py`](tools/qgis_style.py)) dagli stessi valori.

### Stile QGIS

[`tools/qgis_style.py`](tools/qgis_style.py) genera un `.qml` con renderer categorizzato ed etichetta sull'ID albero, in tre varianti: `stat` (colonna `stat_bucket`: rischio ORD se calcolato, altrimenti condizione VTA/CPC, altrimenti NA — la stessa casella della barra statistiche), `rischio` (`rischio_classe`) e `condizione` (`cond_classe`). Le tre colonne sono nel GPKG esportato e nel GeoJSON di `/qgis/features`; nel GPKG lo stile `stat` è anche **incorporato** nella tabella `layer_styles` come predefinito, quindi QGIS colora il layer da solo all'apertura (se la colonna viene rinominata lo stile la segue; se viene esclusa non c'è stile). Lo stile è scaricabile a parte da `/qgis/style.qml` per layer già presenti nei progetti (*Proprietà layer → Simbologia → Stile → Carica stile*).

---

## Plugin QGIS

In [`qgis_plugin/silvae_qgis/`](qgis_plugin/) c'è il plugin «Silvae Pro» per QGIS (≥ 3.28): si collega con un **token API** (creato da «Il mio account»), scarica gli alberi di un comune in un GeoPackage locale già colorato e li aggiorna in modo incrementale. Installazione e uso in [`qgis_plugin/README.md`](qgis_plugin/README.md); piano e stato in [`docs/qgis.md`](docs/qgis.md).

### Da QGIS a Silvae

Il plugin manda le feature di un qualsiasi layer a `POST /qgis/features`: la corrispondenza colonna → campo si decide una volta (la propone `POST /qgis/mapping`, stessa auto-mappatura dell'import da file) e resta salvata nel progetto QGIS. Ogni scrittura passa per la stessa funzione della webapp, quindi valgono le regole dell'[importazione](#importazione-abbinamento-e-regole-di-scrittura): campi derivati ignorati e ricalcolati, valori vuoti che non cancellano, owner invariato, abbinamento solo tra gli alberi visibili. In più:

- **anteprima**: con `dry_run` il server esegue tutto senza scrivere e risponde con il diff (`created`, `updated` con l'elenco dei campi cambiati, `unchanged`, `skipped`, `conflicts`, `errors`, `ignored_fields`);
- **conflitti**: la feature dice fin dove QGIS era allineato — il più recente fra l'`updated_at` ricevuto al pull e il `silvae_synced_at` scritto dal plugin all'ultimo invio riuscito; se qualcuno ha modificato quell'albero dopo, la feature finisce in `conflicts` e **non** viene scritta, a meno di `force`. Il plugin apre allora una finestra di confronto campo per campo dove si sceglie, albero per albero, se far vincere QGIS o Silvae;
- **storico**: ogni albero modificato da QGIS conserva in una `Inspection` lo **snapshot precedente** alla modifica, con l'elenco dei campi cambiati — un annulla per albero;
- **collegamento**: dopo un invio riuscito il plugin scrive `silvae_uuid` (più `silvae_id` e `silvae_synced_at`) nel layer di partenza, così gli invii successivi aggiornano invece di duplicare.

### Invia a QGIS (cassetta postale)

Un browser non può parlare con QGIS sul computer dell'utente, quindi il server fa da tramite. Il pulsante **Invia a QGIS** — nel tab Esporta, nella barra di selezione della tabella e nella selezione per area sulla mappa (dove parte anche il perimetro disegnato) — deposita un *invio* con gli **id** degli alberi; il plugin lo trova nel dock *Invii in attesa* e lo ritira. Poiché l'invio conserva gli id e non i dati, al ritiro arrivano sempre i valori correnti. Gli invii sono personali (li ritira chi li ha creati), scadono dopo 7 giorni e si possono eliminare da entrambe le parti.

---

## Statistiche della vista

Sopra la tabella del tab **Alberi** una barra riassume gli alberi **attualmente visibili** (quindi dopo i filtri per ID, indirizzo e "Vicino a me", su tutte le pagine — non solo quella corrente).

La barra si apre e chiude con il pulsante **Statistiche** nella barra strumenti: su schermi larghi è aperta di default, su telefono parte chiusa per lasciare spazio alla lista; la scelta viene ricordata nel browser (`localStorage`). Se la barra è chiusa mentre è attivo un filtro per categoria, il pulsante mostra la categoria filtrata (es. *Scarso*), così è chiaro perché la lista è ridotta.

Ogni albero finisce in **una sola** casella, scelta con la prima fonte disponibile:

| # | Fonte | Categorie |
|---|-------|-----------|
| 1 | **Rischio ORD** calcolato (`rischio.attuale`) | Accettabile · ALARP · Per accordo · Inaccettabile |
| 2 | **Classe VTA/CPC** (`A`, `B`, `C`, `C/D`, `D`) | Ottimo · Buono · Discreto · Scarso |
| 3 | **Condizione** testuale (Ottimo, Buono, Discreto, …) | come sopra |
| 4 | nessuna delle precedenti | **NA** — non valutabile |

Quando il rischio è calcolato si usa la classe **peggiore** tra rami, tronco, colletto e zolla della valutazione *attuale*. Un albero i cui valori risultano tutti `SOSPESO` non conta come valutato e ricade sulla fonte successiva.

Rischio e condizione restano su **due assi distinti**: sono mostrati in due gruppi separati e non vengono fusi in un'unica scala, perché misurano cose diverse (il rischio per i bersagli vs. lo stato fitosanitario della pianta). I totali dei tre gruppi sommano sempre agli alberi in vista.

**Anche sulla mappa**: la stessa barra compare nel tab Mappa (pulsante *Statistiche* accanto al filtro per indirizzo), calcolata sugli alberi attualmente mostrati (dopo il filtro per indirizzo). Il filtro per categoria è **unico** per lista e mappa: un chip attivato sulla mappa filtra anche la tabella e viceversa, e la selezione per area considera solo gli alberi filtrati.

**Filtro per categoria**: un clic su un contatore riduce la lista a quella sola categoria; un secondo clic (o il pulsante *Mostra tutti*) lo rimuove. I conteggi restano quelli dell'insieme non filtrato, così si può passare da una categoria all'altra. Il filtro si combina con gli altri filtri e con la modalità **Seleziona**, quindi è possibile isolare per esempio gli alberi `NA`, selezionarli tutti ed esportarli o generarne le schede. Si azzera al cambio di comune.

Il calcolo è interamente lato client in [`frontend/app.js`](frontend/app.js) (`treeStatBucket`, `computeTreeStats`, `renderTreeStats`): non richiede endpoint dedicati, perché `rischio`, `cpc` e `condition` sono già nella risposta di `/trees`.

---

## API principali

### Autenticazione e utenti

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/login` | Autenticazione, restituisce JWT |
| `GET`  | `/me` | Dati dell'utente autenticato (inclusi `email` e, per gli agronomi, `agronomer_code`) |
| `PATCH` | `/me` | Aggiorna l'email del proprio account (`{"email": "..."}`, stringa vuota per rimuoverla) |
| `GET`  | `/me/tokens` | Token API attivi dell'utente (nome, prefisso, ultimo uso) |
| `POST` | `/me/tokens` | Crea un token API (`{"name": "..."}`); il token in chiaro `slv_…` è nella risposta **una sola volta**. Solo con JWT, non da account demo |
| `DELETE` | `/me/tokens/<id>` | Revoca un token API |
| `POST` | `/register` | Auto-registrazione (ruolo `user`) — **disabilitato** salvo `REGISTRATION_ENABLED=true` |
| `POST` | `/forgot-password` | Invia il link di reset password via email |
| `POST` | `/reset-password` | Imposta una nuova password tramite token |
| `POST` | `/change-password` | Cambia la password dell'utente loggato (`current_password`, `new_password`) |
| `POST` | `/add_user` | Crea un utente (solo `city`/`superuser`; `email` opzionale) |
| `GET`  | `/users` | Lista utenti visibili al chiamante (con `agronomer_code` per il `superuser`) |
| `PATCH` | `/admin/users/<id>` | Il `superuser` aggiorna `email` e/o `password` di un utente (account demo esclusi) |

### Città e agronomi

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST`   | `/admin/cities` | Crea una città (solo `superuser`) |
| `GET`    | `/cities` | Comuni per il selettore in alto: tutti quelli presenti per `superuser` e `user`; **solo il proprio** per `city` |
| `GET`    | `/comuni/search` | Autocompletamento comuni italiani (`?q=`) |
| `GET`    | `/city/agronomers` | Agronomi collegati al comune (`?city_user_id=` per il `superuser`) |
| `POST`   | `/city/agronomers` | Collega un agronomo al comune tramite `code` (codice agronomo); il `superuser` può usare anche `username` e `city_user_id` |
| `DELETE` | `/city/agronomers/<id>` | Scollega un agronomo |

### Alberi e valutazioni

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET`    | `/trees` | Lista alberi (filtri: city, address, species, page) |
| `GET`    | `/tree/<id>` | Dettaglio albero per ID |
| `GET`    | `/tree/custom/<custom_id>` | Dettaglio albero per ID personalizzato |
| `POST`   | `/add_tree` | Aggiunge un nuovo albero *(non consentito a `city`)* |
| `PATCH`  | `/tree/<id>` | Aggiorna dati albero *(non consentito a `city`)* |
| `DELETE` | `/tree/<id>` | Elimina albero *(non consentito a `city`)* |
| `DELETE` | `/trees/bulk` | Elimina più alberi in blocco *(non consentito a `city`)* |
| `POST`   | `/calculate_risk` | Calcola il rischio ORD per un albero (solo calcolo, nessuna scrittura) |
| `GET`    | `/tree/<id>/inspections` | Storico valutazioni rischio |
| `POST`   | `/tree/<id>/inspections` | Aggiunge una valutazione/ispezione *(non consentito a `city`)* |
| `GET`    | `/dropdowns` | Valori per i menu a tendina (specie, tipi bersaglio, …) |

### Import / Export

> **Selezione degli alberi negli export e nei report.** Tutti gli endpoint di
> esportazione e di report (`/export/excel`, `/export/gpkg`, `/export/gpx`,
> `/report/scheda`, `/report/map`) accettano gli stessi parametri in **`GET`
> nella query string** e in **`POST` nel corpo JSON**, e rispondono in modo
> identico. Senza `ids` si esportano tutti gli alberi visibili; con `city` tutti
> quelli di un comune; con `ids` solo quelli indicati.
>
> La forma `POST` esiste perché gli id di una selezione non entrano nella URL:
> la riga di richiesta che Gunicorn accetta è 4094 byte
> (`--limit-request-line`), cioè circa **660 id**, oltre i quali la richiesta
> viene rifiutata con `400` prima di arrivare a Flask. Nel corpo quel tetto non
> c'è, e la webapp usa sempre `POST`. Nel corpo i valori si mandano nella loro
> forma naturale (`ids` lista di numeri, `exclude` lista, `rename` oggetto,
> `polygon` lista di coppie `[lat, lon]`); in query string restano stringhe
> (`ids=1,2,3`, `exclude` e `rename` come JSON, `polygon=lat,lon;lat,lon`).
> La visibilità per ruolo è la stessa nei due casi: si esporta solo ciò che
> l'account può vedere, e un id non visibile viene semplicemente ignorato.

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` `POST` | `/export/excel` | Esporta alberi in Excel (`ids`, `city`, `exclude` opzionali) |
| `GET`  | `/export/excel/columns` | Gruppi e intestazioni delle colonne Excel (per la scelta dei campi da esportare) |
| `GET` `POST` | `/export/gpkg` | Esporta alberi in GeoPackage — attributi ARETE + geometria (`ids`, `city`, `rename`, `exclude` opzionali), con le colonne di categoria `stat_bucket`/`rischio_classe`/`cond_classe` e lo **stile QGIS predefinito** incorporato (`layer_styles`) |
| `GET`  | `/export/gpkg/columns` | Nomi/tipi di default delle colonne del GPKG (per rinomina/esclusione in export) |
| `POST` | `/import/gpkg/inspect` | Anteprima colonne e mappatura automatica di un .gpkg |
| `POST` | `/import/gpkg` | Importa alberi da .gpkg (multipart: `file`, `city`, `on_conflict=skip\|update`) *(non consentito a `city`)* |
| `GET` `POST` | `/export/gpx` | Esporta alberi come waypoint GPX 1.1 (`ids`, `city` opzionali) — vedi [Import / Export GPX](#import--export-gpx) |
| `POST` | `/import/gpx/inspect` | Anteprima colonne e mappatura automatica di un .gpx (stessa risposta di `/import/gpkg/inspect`) |
| `POST` | `/import/gpx` | Importa alberi dai waypoint di un .gpx (stessi parametri di `/import/gpkg`) *(non consentito a `city`)* |

### Report — Schede albero

Stesso filtro per ruolo e stessa selezione `ids` degli export (vedi [Schede di rilevamento ARETE](#schede-di-rilevamento-arete)).

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET`  | `/report/templates` | Elenco dei template di scheda disponibili |
| `GET` `POST` | `/report/scheda` | Genera le schede albero (`ids`, `city`, `template` opzionali; default `scheda_arete` → `schede_albero.zip`) |
| `GET` `POST` | `/report/map` | Tavola cartografica A4 (`basemap=osm\|satellite`, `format=pdf\|png`, `ids`, `city`, `polygon` opzionali) — vedi [Mappa per la relazione](#mappa-per-la-relazione) |

### Geocodifica e voce

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/test_geocode` | Geocodifica un indirizzo → coordinate |
| `POST` | `/reverse_geocode` | Coordinate → indirizzo e città |
| `POST` | `/api/voice_intent` | Riconosce l'intento da un trascritto vocale (Groq) |

### Palette e QGIS

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/palette.css` | Variabili CSS `--risk-*` / `--cond-*` generate da [`tools/palette.py`](tools/palette.py) (senza autenticazione) |
| `GET` | `/palette` | La stessa tavolozza in JSON |
| `GET` | `/qgis/style.qml` | Stile QGIS categorizzato generato dalla palette (`?by=stat\|rischio\|condizione`, `?field=` colonna rinominata, `?labels=0`); senza autenticazione |
| `GET` | `/qgis/features` | FeatureCollection GeoJSON (WGS84) degli alberi visibili, con attributi piatti per QGIS (`?city=` o `?ids=`; `?since=<ISO 8601>` per il pull incrementale su `updated_at`; `?bbox=`; `?delivery=<id>` per ritirare un invio) — usato dal plugin QGIS |
| `POST` | `/qgis/features` | **Scrittura da QGIS**: FeatureCollection GeoJSON in ingresso (`city` obbligatorio, `mapping` colonne→campi, `on_conflict`, `dry_run` per l'anteprima, `force`) — stessa logica della webapp, con ricalcolo del rischio e snapshot dello stato precedente |
| `POST` | `/qgis/mapping` | Mappatura proposta per le colonne di un layer (`{columns: [...]}`) e campi scrivibili — per la finestra di mappatura del plugin |
| `POST` | `/qgis/deliveries` | «Invia a QGIS»: deposita un invio (`{city, ids, polygon?, title?}`) per il proprio plugin |
| `GET` | `/qgis/deliveries` | Invii in attesa dell'utente (`?all=1` include quelli già ritirati) |
| `DELETE` | `/qgis/deliveries/<id>` | Elimina un invio |

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'dotenv'`**
```bash
pip install python-dotenv
```

**`password authentication failed`**
Verifica che `DATABASE_URL` in `.env` corrisponda alle credenziali PostgreSQL locali.

**Il reset password non invia email**
`SMTP_USER`/`SMTP_PASSWORD` non sono impostati: il link di reset viene stampato nella console del server. `SMTP_PASSWORD` deve essere una *App Password* Gmail, non la password normale.

**L'input vocale non risponde (errore 503 `GROQ_API_KEY not set`)**
Imposta la variabile d'ambiente `GROQ_API_KEY`.

**L'app su Railway non si avvia**
Controlla che la variabile `DATABASE_URL` sia impostata correttamente.

**Lo .zip delle schede non contiene i PDF (cartella `pdf/` vuota)**
LibreOffice non è disponibile sul server. In locale: `sudo apt install libreoffice-calc`. Su Railway l'immagine di default non lo include: serve un `Dockerfile`/configurazione Nixpacks che installi `libreoffice` (vedi [Deploy su Railway](#deploy-su-railway)). Gli `.xlsx` in `excel/` vengono comunque generati.

**I loghi non compaiono nella scheda ARETE**
Verifica che `Pillow` sia installato (`pip install Pillow`) e che le immagini siano presenti in `frontend/images/`.

---

## Licenza

MIT License

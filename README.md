# Silvae Pro — Sistema di Gestione Alberi con Protocollo ARETE

Applicazione web per il censimento e la valutazione del rischio degli alberi urbani, conforme al **Protocollo ARETE** (Analisi del Rischio degli Elementi Arborei in ambiente urbano).

> Fonte: "Protocollo Areté® per la Valutazione del Rischio Arboreo [ver. 4.0] - ARBORETE® ([http://www.protocolloarete.it](http://www.protocolloarete.it))".

---

## Funzionalità principali

- **Censimento alberi** con dati dendrologici completi (specie, dimensioni, coordinate GPS o indirizzo)
- **Valutazione del rischio ORD** secondo il protocollo ARETE: prodotto di Bersaglio (B), Inclinazione (I) e Probabilità (P)
- **Calcolo automatico del bersaglio** da tipo di uso del suolo e flusso (pedoni, traffico, proprietà, occupazione)
- **Valore ecologico**: stima di biomassa, CO₂ sequestrata, O₂ prodotto, intercettazione acqua e valore monetario (€)
- **Mappa interattiva** (Leaflet) con clustering e marker colorati per classe di rischio
- **Esportazione** in formato Excel (.xlsx) e GeoPackage (.gpkg)
- **Report "schede albero"** da template selezionabile — una scheda per albero *(placeholder, in sviluppo)*
- **Importazione** da file GeoPackage (.gpkg) — compatibile con i censimenti ARETE e con i file esportati dall'app, con anteprima e mappatura colonne
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

La logica di calcolo è implementata in [`tools/ord_calculator.py`](tools/ord_calculator.py), con le tabelle di lookup e i valori dei menu a tendina in [`tools/lookup_tables.py`](tools/lookup_tables.py) e [`tools/dropdowns_ord.py`](tools/dropdowns_ord.py).

---

## Stack tecnologico

- **Backend**: Python 3.10+, Flask 3.1, SQLAlchemy 2.0, psycopg2-binary
- **Database**: PostgreSQL (le coordinate sono memorizzate come `latitude`/`longitude` numeriche; **PostGIS non è richiesto**)
- **Frontend**: HTML5, CSS3, JavaScript vanilla, Leaflet.js, Font Awesome
- **Autenticazione**: JWT (PyJWT), password hash con `werkzeug.security`
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
│   ├── lookup_tables.py        # Tabelle di lookup (specie, patologie, prescrizioni, ...)
│   ├── dropdowns_ord.py        # Valori dei menu a tendina ORD
│   └── report_templates.py     # Template schede albero per i report (placeholder)
├── frontend/
│   ├── index.html              # Interfaccia principale (multi-tab)
│   ├── app.js                  # Logica frontend (fetch, mappa, form, esportazione)
│   ├── voice.js                # Input vocale (Web Speech API + intent Groq)
│   └── style.css               # Stili dell'applicazione
├── Procfile                    # Configurazione Gunicorn per Railway
├── requirements.txt            # Dipendenze Python
├── .env                        # Variabili d'ambiente locali (non in git)
├── .env.example                # Template variabili d'ambiente
└── .gitignore
```

---

## Setup locale

### Prerequisiti

- Python ≥ 3.10
- PostgreSQL

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

---

## Ruoli utente

| Ruolo | Permessi |
|-------|----------|
| **superuser** | Accesso completo: gestione utenti, città, tutti gli alberi |
| **city** | Gestisce gli alberi del proprio comune e collega gli agronomi (`user`) al comune |
| **user** (agronomo) | Censisce e valuta gli alberi dei comuni a cui è collegato |

L'accesso agli alberi è filtrato per comune tramite il modello `CityMembership` (relazione città ↔ agronomi).

Gli utenti vengono creati da un `superuser` (qualsiasi ruolo) o da un `city` (solo agronomi del proprio comune). La **registrazione pubblica** (`/register` + link "Crea account") è **disabilitata di default**: si riattiva impostando `REGISTRATION_ENABLED=true` e ripristinando il link nel frontend (vedi commenti in `frontend/index.html` e `frontend/app.js`).

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

> Railway usa `postgres://` come prefisso — l'app lo converte automaticamente in `postgresql://`.

### 3. Deploy

Ogni push sul branch principale avvia il deploy automatico. Il `Procfile` istruisce Railway ad avviare Gunicorn:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --preload
```

---

## Interfaccia utente — Tab

| Tab | Contenuto |
|-----|-----------|
| **Alberi** | Tabella degli alberi con ricerca, ordinamento, aggiunta/modifica/cancellazione |
| **Mappa** | Mappa Leaflet con marker e clustering, filtri per città |
| **Gestione** | Pannello amministratore: gestione utenti, città, agronomi, reset password |
| **Esporta** | Esportazione in Excel (.xlsx) o GeoPackage (.gpkg) e report schede albero — intera raccolta o selezione manuale, con **scelta dei campi da esportare** (esclusione singoli campi) |
| **Importa** | Importazione da file .gpkg (censimenti esterni o file esportati dall'app) con anteprima, mappatura colonne e gestione conflitti (skip/update) |
| **Algoritmo** | Documentazione tecnica del calcolo ARETE integrata nella webapp |

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

## API principali

### Autenticazione e utenti

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/login` | Autenticazione, restituisce JWT |
| `GET`  | `/me` | Dati dell'utente autenticato |
| `POST` | `/register` | Auto-registrazione (ruolo `user`) — **disabilitato** salvo `REGISTRATION_ENABLED=true` |
| `POST` | `/forgot-password` | Invia il link di reset password via email |
| `POST` | `/reset-password` | Imposta una nuova password tramite token |
| `POST` | `/add_user` | Crea un utente (solo `city`/`superuser`) |
| `GET`  | `/users` | Lista utenti visibili al chiamante |

### Città e agronomi

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST`   | `/admin/cities` | Crea una città (solo `superuser`) |
| `GET`    | `/cities` | Lista delle città presenti |
| `GET`    | `/comuni/search` | Autocompletamento comuni italiani (`?q=`) |
| `GET`    | `/city/agronomers` | Agronomi collegati al comune |
| `POST`   | `/city/agronomers` | Collega un agronomo al comune |
| `DELETE` | `/city/agronomers/<id>` | Scollega un agronomo |

### Alberi e valutazioni

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET`    | `/trees` | Lista alberi (filtri: city, address, species, page) |
| `GET`    | `/tree/<id>` | Dettaglio albero per ID |
| `GET`    | `/tree/custom/<custom_id>` | Dettaglio albero per ID personalizzato |
| `POST`   | `/add_tree` | Aggiunge un nuovo albero |
| `PATCH`  | `/tree/<id>` | Aggiorna dati albero |
| `DELETE` | `/tree/<id>` | Elimina albero |
| `DELETE` | `/trees/bulk` | Elimina più alberi in blocco |
| `POST`   | `/calculate_risk` | Calcola il rischio ORD per un albero |
| `GET`    | `/tree/<id>/inspections` | Storico valutazioni rischio |
| `POST`   | `/tree/<id>/inspections` | Aggiunge una valutazione/ispezione |
| `GET`    | `/dropdowns` | Valori per i menu a tendina (specie, tipi bersaglio, …) |

### Import / Export

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET`  | `/export/excel` | Esporta alberi in Excel (`?ids=1,2,3` e `?exclude=` opzionali) |
| `GET`  | `/export/excel/columns` | Gruppi e intestazioni delle colonne Excel (per la scelta dei campi da esportare) |
| `GET`  | `/export/gpkg` | Esporta alberi in GeoPackage — attributi ARETE + geometria (`?ids=`, `?rename=`, `?exclude=` opzionali) |
| `GET`  | `/export/gpkg/columns` | Nomi/tipi di default delle colonne del GPKG (per rinomina/esclusione in export) |
| `POST` | `/import/gpkg/inspect` | Anteprima colonne e mappatura automatica di un .gpkg |
| `POST` | `/import/gpkg` | Importa alberi da .gpkg (multipart: `file`, `city`, `on_conflict=skip\|update`) |

### Report — Schede albero *(placeholder)*

Generazione di un report con una **scheda per albero** a partire da un *template* selezionabile. La struttura è già cablata (filtro per ruolo e selezione `ids` come gli export); resa attuale segnaposto in attesa dei requisiti definitivi (vedi [`tools/report_templates.py`](tools/report_templates.py)).

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET`  | `/report/templates` | Elenco dei template di scheda disponibili |
| `GET`  | `/report/scheda` | Genera le schede albero (`?ids=` e `?template=` opzionali) |

### Geocodifica e voce

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/test_geocode` | Geocodifica un indirizzo → coordinate |
| `POST` | `/reverse_geocode` | Coordinate → indirizzo e città |
| `POST` | `/api/voice_intent` | Riconosce l'intento da un trascritto vocale (Groq) |

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

---

## Licenza

MIT License

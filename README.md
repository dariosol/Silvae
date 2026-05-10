# Silvae Pro — Sistema di Gestione Alberi con Protocollo ARETE

Applicazione web per il censimento e la valutazione del rischio degli alberi urbani, conforme al **Protocollo ARETE** (Analisi del Rischio degli Elementi Arborei in ambiente urbano).

---

## Funzionalità principali

- **Censimento alberi** con dati dendrologici completi (specie, dimensioni, coordinate GPS o indirizzo)
- **Valutazione del rischio ORD** secondo il protocollo ARETE: matrice 7×7×7 di Bersaglio (B), Inclinazione (I) e Probabilità (P)
- **Calcolo automatico del bersaglio** da tipo di uso del suolo e flusso (pedoni, traffico, proprietà, occupazione)
- **Mappa interattiva** (Leaflet) con clustering e marker colorati per classe di rischio
- **Esportazione** in formato Excel (.xlsx) e GeoPackage (.gpkg)
- **Importazione** da file GeoPackage (.gpkg) — compatibile con i censimenti ARETE e con i file esportati dall'app
- **Autenticazione JWT** multi-utente con ruolo amministratore
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

---

## Stack tecnologico

- **Backend**: Python 3.10+, Flask 3.1, SQLAlchemy 2.0, GeoAlchemy2, psycopg2
- **Database**: PostgreSQL con estensione PostGIS
- **Frontend**: HTML5, CSS3, JavaScript vanilla, Leaflet.js, Font Awesome
- **Autenticazione**: JWT (PyJWT), password hash con `werkzeug.security`
- **Deploy**: Gunicorn + Railway (o qualsiasi host con PostgreSQL/PostGIS)

---

## Struttura del progetto

```
tree_project/
├── app.py                          # Backend Flask: API, modelli, autenticazione
├── Schede_Rilevamento_ARETE/
│   └── ord_calculator.py           # Logica calcolo ARETE (B·I·P, bersaglio, classi)
├── frontend/
│   ├── index.html                  # Interfaccia principale (multi-tab)
│   └── app.js                      # Logica frontend (fetch, mappa, form, esportazione)
├── Procfile                        # Configurazione Gunicorn per Railway
├── requirements.txt                # Dipendenze Python
├── .env                            # Variabili d'ambiente locali (non in git)
├── .env.example                    # Template variabili d'ambiente
└── .gitignore
```

---

## Setup locale

### Prerequisiti

- Python ≥ 3.10
- PostgreSQL con estensione PostGIS

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

### 4. Configura PostgreSQL e PostGIS

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE trees_db;
\c trees_db
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 5. Configura le variabili d'ambiente

Copia `.env.example` in `.env` e modifica i valori:

```bash
cp .env.example .env
```

```ini
DATABASE_URL=postgresql://postgres:tuapassword@localhost/trees_db
SECRET_KEY=chiave-segreta-lunga-e-casuale
```

### 6. Avvia l'applicazione

```bash
python app.py
```

Lo schema del database viene creato e aggiornato automaticamente all'avvio (nessuna migrazione manuale necessaria).

L'app è disponibile su: `http://127.0.0.1:5000`

> **Nota**: il warning *"Do not use the development server in a production environment"* è normale durante lo sviluppo locale.

---

## Deploy su Railway

### 1. Crea il progetto su Railway

- Crea un nuovo progetto su [railway.app](https://railway.app)
- Aggiungi un servizio **PostgreSQL** dal marketplace Railway
- Collega il tuo repository GitHub

### 2. Abilita PostGIS

Railway non abilita PostGIS automaticamente. Aprire la console del database PostgreSQL (tab **Query** su Railway) ed eseguire:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 3. Variabili d'ambiente su Railway

Nel servizio dell'app, imposta le variabili:

| Variabile | Valore |
|-----------|--------|
| `DATABASE_URL` | Copiare dalla variabile `DATABASE_URL` del servizio PostgreSQL Railway |
| `SECRET_KEY` | Stringa casuale lunga (es. generata con `openssl rand -hex 32`) |

> Railway usa `postgres://` come prefisso — l'app lo converte automaticamente in `postgresql://`.

### 4. Deploy

Ogni push sul branch principale avvia il deploy automatico. Il `Procfile` istruisce Railway ad avviare Gunicorn:

```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

---

## Interfaccia utente — Tab

| Tab | Contenuto |
|-----|-----------|
| **Alberi** | Tabella degli alberi con ricerca, ordinamento, aggiunta/modifica/cancellazione |
| **Mappa** | Mappa Leaflet con marker e clustering, filtri per città |
| **Gestione** | Pannello amministratore: gestione utenti, reset password |
| **Esporta** | Esportazione in Excel (.xlsx) o GeoPackage (.gpkg) — intera raccolta o selezione manuale |
| **Importa** | Importazione da file .gpkg (censimenti esterni o file esportati dall'app) con gestione conflitti (skip/update) |
| **Algoritmo** | Documentazione tecnica del calcolo ARETE integrata nella webapp |

---

## Condizione dell'albero

Il campo **Condizione** (campo `condition` nel database) rappresenta lo stato vegetativo/fitosanitario dell'albero ed è visualizzato tramite badge colorati in tabella, schede e popup della mappa.

Il rilevamento avviene per corrispondenza sul testo (case-insensitive):

| Categoria | Parole chiave | Colore |
|-----------|--------------|--------|
| **Buono** | `buono`, `eccellente`, `ottimo` | Verde |
| **Discreto** | `discreto`, `mediocre` | Giallo |
| **Scarso / Critico** | `scarso`, `critico`, `morto` | Rosso |
| **Non classificato** | qualsiasi altro valore | Grigio |

I valori consigliati da inserire nel form ispezioni sono: **Buono**, **Discreto**, **Scarso**.

---

## API principali

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/login` | Autenticazione, restituisce JWT |
| `POST` | `/register` | Registrazione nuovo utente (solo admin) |
| `GET` | `/trees` | Lista alberi (filtri: city, address, species, page) |
| `POST` | `/add_tree` | Aggiunge un nuovo albero |
| `PATCH` | `/tree/<id>` | Aggiorna dati albero |
| `DELETE` | `/tree/<id>` | Elimina albero |
| `POST` | `/calculate_risk` | Calcola il rischio ORD per un albero |
| `GET` | `/tree/<id>/inspections` | Storico valutazioni rischio |
| `GET` | `/export/excel` | Esporta alberi in Excel (parametro opzionale `?ids=1,2,3` per selezione) |
| `GET` | `/export/gpkg` | Esporta alberi in GeoPackage — tutti gli attributi ARETE + geometria (parametro opzionale `?ids=`) |
| `POST` | `/import/gpkg` | Importa alberi da file .gpkg (multipart: `file`, `city`, `on_conflict=skip\|update`) |
| `GET` | `/dropdowns` | Valori per i menu a tendina (specie, tipi bersaglio, …) |
| `GET` | `/cities` | Lista delle città presenti |

---

## Troubleshooting

**Errore `ST_AsEWKB` o colonna `geom` mancante**
```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```
Poi riavvia l'app: lo schema viene ricreato automaticamente.

**`ModuleNotFoundError: No module named 'dotenv'`**
```bash
pip install python-dotenv
```

**`password authentication failed`**
Verifica che `DATABASE_URL` in `.env` corrisponda alle credenziali PostgreSQL locali.

**L'app su Railway non si avvia**
Controlla che la variabile `DATABASE_URL` sia impostata e che PostGIS sia stato abilitato manualmente con `CREATE EXTENSION IF NOT EXISTS postgis;`.

---

## Licenza

MIT License

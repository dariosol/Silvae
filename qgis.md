# Silvae Pro ⇄ QGIS — Plugin con cassetta postale

Piano di sviluppo per il collegamento bidirezionale tra Silvae Pro e QGIS
senza passare da file esportati e reimportati a mano. Complementa
[`next_steps.md`](next_steps.md) (sezione A) e ne assorbe A2 e A4.

---

## 1. Obiettivo

L'agronomo lavora in QGIS su un layer suo, con colonne sue. Deve poter:

- **QGIS → Silvae**: mandare a Silvae gli alberi nuovi o modificati del suo
  layer con un pulsante, decidendo la corrispondenza delle colonne **una
  volta sola**, e senza creare doppioni se preme due volte;
- **Silvae → QGIS**: dalla webapp (tab Esporta, barra di selezione della
  tabella, selezione per area sulla mappa) premere «Invia a QGIS» e trovarsi
  quegli alberi in QGIS, già con lo stile per classe di rischio;
- **correggere le posizioni** in QGIS e rimandarle a Silvae;
- vedere in QGIS il **rischio calcolato da Silvae** senza poterlo modificare
  (il calcolo ARETE resta di competenza esclusiva dell'App).

## 2. Il vincolo che dà forma alla soluzione

Un browser non può parlare con QGIS sul PC dell'utente. Quindi «Invia a QGIS»
dalla webapp non può spingere nulla direttamente: il server fa da
**cassetta postale**. La webapp deposita un *invio* (quali alberi, per chi);
il plugin QGIS, autenticato, lo trova e lo carica. Nessun server locale sulla
macchina dell'agronomo, nessun URL scheme, funziona da qualsiasi rete.

Scartati: mini HTTP server dentro il plugin su `localhost` (firewall, blocchi
`https → http://localhost`, QGIS deve essere già aperto), URL scheme
`silvae://` (QGIS non lo registra, servirebbe un installer per OS).

## 3. Architettura

```
┌──────────────────┐   HTTPS + token API    ┌───────────────────────┐
│  QGIS + plugin   │ ─────────────────────► │  Silvae Pro (Flask)   │
│                  │ ◄───────────────────── │                       │
│  layer locale    │   GeoJSON in/out,      │  Tree + Inspection    │
│  (GPKG progetto) │   invii in attesa      │  QgisDelivery         │
└──────────────────┘                        │  ApiToken             │
                                            └───────────▲───────────┘
                                                        │ «Invia a QGIS»
                                            ┌───────────┴───────────┐
                                            │  webapp (frontend)    │
                                            └───────────────────────┘
```

Tre pezzi:

| Pezzo | Dove | Cosa fa |
|---|---|---|
| **Server** | [`app.py`](app.py) | Token API, endpoint GeoJSON in/out, cassetta postale, `updated_at` + UUID sul modello. Tutte le scritture passano dalla logica esistente (`apply_tree_fields`, `_calc_rischio`, `_make_inspection`, `_city_readonly`). |
| **Webapp** | [`frontend/app.js`](frontend/app.js), [`frontend/index.html`](frontend/index.html) | Pulsante «Invia a QGIS» nei tre punti di selezione; pannello token in «Il mio account». |
| **Plugin QGIS** | nuovo repository `silvae-qgis` | Login, *Carica da Silvae*, *Invia a Silvae*, *Invii in attesa*, mappatura colonne, GPKG locale, `silvae_uuid` nel layer dell'agronomo. |

Nessuna nuova dipendenza Python sul server (GeoJSON con `json`, GPKG già
scritto a mano). Il plugin usa solo PyQGIS e `QgsNetworkAccessManager`
(niente `requests`, che in QGIS non è garantito).

---

## 4. Modello dati (prerequisito di tutto)

Colonne nuove su `Tree`, aggiunte con lo stesso meccanismo `ALTER TABLE …
ADD COLUMN` già in [`app.py:292`](app.py#L292):

| Colonna | Tipo | Perché |
|---|---|---|
| `uuid` | `String(36)`, unique, indicizzata | Chiave stabile per il collegamento con il layer dell'agronomo. `custom_id` è rinominabile e unico solo per comune: non può fare da chiave. Generata alla creazione; **backfill** una tantum per gli alberi esistenti all'avvio. |
| `updated_at` | `DateTime(timezone=True)` | Rilevare modifiche concorrenti e permettere il pull incrementale (`?since=`). Impostata in `add_tree`, `update_tree`, import, `POST /qgis/features`, e nel backfill (= `now`). |
| `updated_by` | `String(80)` | Chi ha fatto l'ultima modifica (username), utile per capire «l'ha cambiato QGIS o la webapp?». |

Tabelle nuove:

```
ApiToken
  id, user_id (FK user), name (es. "QGIS portatile"), token_hash (sha256),
  prefix (primi 8 char, per riconoscerlo in lista), created_at,
  last_used_at, revoked_at

QgisDelivery                       -- la cassetta postale
  id, user_id (FK user: destinatario = chi ha premuto il pulsante),
  city, title (es. "Bra — selezione area 20/09"), tree_ids (JSON array),
  polygon (JSON [[lat,lon],…] o NULL), count,
  created_at, fetched_at (NULL finché il plugin non lo scarica),
  expires_at (created_at + 7 giorni)
```

`QgisDelivery` conserva **gli id, non i dati**: il plugin al momento del
ritiro scarica lo stato corrente degli alberi, così un invio non è mai
stantio.

---

## 5. Autenticazione: token API

Il JWT di `/login` scade ([`generate_token`](app.py#L626), 24 h di default) e
contiene ruolo e comune: non va conservato in un plugin. Serve un token
**longevo e revocabile**.

- Generazione da «Il mio account» (`POST /me/tokens` → mostra il token in
  chiaro **una sola volta**), lista (`GET /me/tokens`: nome, prefisso, ultimo
  uso), revoca (`DELETE /me/tokens/<id>`).
- Formato: `slv_` + 40 caratteri casuali (`secrets.token_urlsafe`). In DB solo
  l'hash.
- Uso: header `Authorization: Bearer slv_…`. `auth_required` prova prima il
  JWT; se il token inizia con `slv_` cerca l'hash in `ApiToken`, verifica che
  non sia revocato, ricostruisce `request.user` dall'utente (ruolo e comune
  **letti ora dal DB**, non congelati nel token) e aggiorna `last_used_at`.
- Ruolo `city`: può generare token e usarli in sola lettura (pull, invii);
  `POST /qgis/features` risponde 403 via `_city_readonly()`, come oggi.
- Account demo: nessun token (coerente con il sandbox non persistente).

---

## 6. API server

Tutti gli endpoint sotto `/qgis/…`, tutti con `@auth_required`, visibilità
tramite `_scoped_tree_query()` ([`app.py:2084`](app.py#L2084)), che è già la
logica degli export.

### 6.1 `GET /qgis/features` — Silvae → QGIS

Parametri: `city` (obbligatorio salvo `ids`/`delivery`), `ids=1,2,3`,
`delivery=<id>` (prende gli id dall'invio e lo marca `fetched_at`),
`since=<ISO datetime>` (solo alberi con `updated_at > since`: pull
incrementale), `bbox=minlon,minlat,maxlon,maxlat` (opzionale).

Risposta: `FeatureCollection` GeoJSON, WGS84, un punto per albero.
`properties` = campi di `tree_to_dict()` **appiattiti**:

- campi semplici così come sono;
- JSON array (`conflitti_list`, `agenti_carie`, `altri_patogeni`,
  `prescrizioni_*`) come stringa separata da virgola, con
  `_gpkg_jlist` ([`app.py:1779`](app.py#L1779)) — lo stesso formato del GPKG;
- `diag_*` come testo `caratt: giudizio; …` (sola lettura);
- `rischio` esploso in colonne di sola lettura: `rischio_classe` (categoria
  peggiore, stessa di GPX/`_risk_category`), `rischio_rami`,
  `rischio_tronco`, `rischio_colletto`, `rischio_zolla`,
  `rischio_residuo_classe`; più `rischio_json` con il JSON intero per chi lo
  vuole;
- `stat_bucket`: la casella della barra statistiche (rischio → CPC → NA),
  la stessa colonna su cui è categorizzato lo stile QGIS;
- sempre presenti: `id`, `uuid`, `updated_at`, `updated_by`, `owner`
  (username), `city`.

Header di risposta `X-Silvae-Schema: 1` per versionare il formato.

### 6.2 `POST /qgis/features` — QGIS → Silvae

Body: `FeatureCollection` GeoJSON + `city` + `on_conflict` (`skip` |
`update`, default `update`) + `mapping` opzionale (`{colonna_sorgente:
campo_silvae}`) + `dry_run` (bool).

Semantica per ogni feature, nell'ordine:

1. **Abbinamento** (`_match_tree` in [`app.py`](app.py), condiviso con
   l'import da file): `uuid` se presente → albero esistente (errore se non
   visibile: lo si segnala, non si crea — `strict_uuid=True`; l'import da
   file è permissivo e prosegue con gli altri criteri, perché il file può
   venire da un altro account); altrimenti **coordinate** entro ~10 cm;
   `custom_id`+comune solo se la riga non ha coordinate. Non si abbina mai
   per `custom_id` quando le coordinate ci sono: nei censimenti la
   numerazione riparte per località (nel file di Bra «7» compare due volte
   in due punti diversi) e si perderebbero alberi. Quindi un punto spostato
   **senza** uuid è un albero nuovo: il plugin scrive `silvae_uuid` nel
   layer al primo push proprio per questo.
2. **Mappatura colonne**: `mapping` esplicito, poi l'auto-mappatura di
   `_gpkg_inspect_mapping` ([`app.py:2356`](app.py#L2356)) per le colonne
   non mappate, poi nomi canonici di `tree_to_dict`.
3. **Campi accettati** (vedi §7). I derivati vengono **ignorati con avviso**,
   mai scritti.
4. **Scrittura** tramite `apply_tree_fields` → ricalcolo bersaglio, valore
   ecologico, `condition` da `cpc`, `rischio` via `_calc_rischio`, come in
   `update_tree`.
5. **Snapshot**: per ogni albero **esistente** che viene modificato si crea
   una `Inspection` con lo `snapshot` dello stato **prima** della modifica
   (`inspector_name` = utente del token, `comments` = «Sincronizzazione da
   QGIS» + elenco dei campi cambiati), qualunque sia il campo — anche una
   sola correzione di posizione. Serve da "annulla" per albero e da traccia
   di chi ha fatto cosa. Gli alberi nuovi ricevono l'ispezione iniziale come
   in `add_tree`. Se nessun campo cambia, nessuna ispezione.
6. **Conflitto**: se la feature porta `updated_at` (quello ricevuto al pull) e
   il server ha un `updated_at` più recente, la feature va in `conflicts`
   senza scrivere, salvo `force=true` per quella feature.

Risposta (per `dry_run` identica ma senza scritture — è l'**anteprima del
diff** di A4):

```json
{
  "created":  [{"src": 12, "id": 3021, "uuid": "…", "custom_id": "BRA-0412"}],
  "updated":  [{"src": 3,  "id": 2988, "uuid": "…", "changed": ["latitude","longitude","cpc"]}],
  "skipped":  [{"src": 7,  "reason": "custom_id già presente (on_conflict=skip)"}],
  "conflicts":[{"src": 9,  "id": 2990, "server_updated_at": "…", "server_updated_by": "mario"}],
  "errors":   [{"src": 15, "message": "coordinate mancanti"}],
  "ignored_fields": ["rischio_classe", "valore_ecologico"]
}
```

`src` è l'indice della feature nel body: il plugin lo usa per scrivere
`uuid`/`id` nel layer dell'agronomo.

Limite: 2 000 feature per chiamata (il plugin spezza in blocchi). `--timeout
120` di Gunicorn regge, ma l'import è per-riga con reverse-geocoding
eventuale: **nessuna** geocodifica automatica del comune in questo endpoint
(`city` obbligatorio), per non fare chiamate Nominatim in serie.

### 6.3 Cassetta postale

| Metodo | Endpoint | Chi | Cosa |
|---|---|---|---|
| `POST` | `/qgis/deliveries` | webapp (JWT) | `{city, ids:[…], polygon?, title?}` → crea l'invio per l'utente corrente. `ids` filtrati per visibilità (`_role_tree_query`); la risposta riporta `count` e `requested`, così la webapp dice quanti sono stati saltati. Rifiutato ai token API (un invio si crea dalla webapp). Massimo 20 000 alberi. |
| `GET` | `/qgis/deliveries` | plugin | Invii dell'utente non scaduti, i non ritirati prima; `?all=1` include i ritirati. |
| `GET` | `/qgis/features?delivery=<id>` | plugin | Ritiro: alberi correnti dell'invio + `polygon`; marca `fetched_at`. |
| `DELETE` | `/qgis/deliveries/<id>` | entrambi | Elimina. |

Gli invii scaduti (7 giorni) vengono cancellati alla prima chiamata utile
(niente scheduler). Un invio è **personale**: il superuser che «invia a QGIS»
ritira dal proprio plugin. Se in futuro serve mandare a un altro utente,
basta un campo `recipient_id` — non ora.

### 6.4 Stile

`GET /qgis/style.qml?by=rischio|condizione|stat` — il generatore A1 di
`next_steps.md`, dai valori di [`tools/palette.py`](tools/palette.py),
categorizzato su `stat_bucket` (default), `rischio_classe` o la classe CPC.
Il plugin lo scarica e lo applica al layer; non è in-linea nel plugin così
la palette resta in un posto solo.

---

## 7. Campi: scrivibili da QGIS vs derivati

Deciso in conversazione (settembre 2026). Regola: **si scrive tutto tranne
ciò che è risultato di un calcolo**; il calcolo lo fa il server a ogni
scrittura.

**Scrivibili** (passano da `apply_tree_fields` + ricalcolo):

- posizione: `latitude`, `longitude` (insieme, come in `update_tree`);
- identità/luogo: `custom_id` (con cautela: l'abbinamento preferito è
  `uuid`), `address`, `location`, `next_check`;
- anagrafica: `species`, `age`, `height`, `dimora`, `stadio_sviluppo`,
  `posizione_sociale`, `localizzazione`, `vincoli`;
- dimensioni (input del rischio, ricalcolato): `trunk_diameter_cm`,
  `crown_diameter_m`, `tree_height_m`, `circonferenza_cm`, `branch_diam_cm`,
  `branch_length_m`, `branch_height_m`, `target_height_m`, i sei `post_*`;
- valutazione: `cpc`, `condition` (ignorata se `cpc` presente: la
  sovrascrive il server), `comments`, `actions`, `monitoraggio`, `urgenza`,
  `condizione_salute_ecologica`;
- input ARETE (giudizi dell'agronomo, ricalcolato il rischio):
  `pericolo_rami/tronco/colletto/zolla`, `bersaglio_chioma_tipo/value/flow`,
  `bersaglio_ramo_tipo/value/flow`, `moltiplicatore`;
- liste (stringa separata da virgola → JSON con `_gpkg_csv_to_json`):
  `conflitti_list`, `agenti_carie`, `altri_patogeni`, `prescrizioni_val`,
  `prescrizioni_mit`, `prescrizioni_col`.

**Derivati, mai scritti** (se arrivano finiscono in `ignored_fields`):

- `rischio` e le colonne `rischio_*` / `stat_bucket`;
- `bersaglio_chioma`, `bersaglio_ramo` (classe 1–7 calcolata) — nota: oggi
  `apply_tree_fields` li accetta in `simple[]`; l'endpoint QGIS li toglie
  dal dizionario prima di chiamarla;
- `bio_kg`, `co2_kg_anno`, `o2_kg_anno`, `ia_kg_anno`, `valore_ecologico`;
- `id`, `uuid`, `owner_id`/`owner`, `city` (cambio comune = operazione
  amministrativa, non un edit di layer), `updated_at`, `updated_by`;
- `diag_*` (sola lettura: si compilano solo nella webapp);
- tabella `Inspection` (v2: seconda collection in sola lettura).

---

## 8. Webapp

- **«Invia a QGIS»** accanto a Esporta/Schede/Mappa in: tab Esporta (alberi
  caricati o selezione manuale), barra di selezione della tabella
  (`exportSelected`), selezione per area sulla mappa (`areaSelectedIds` +
  poligono). Chiama `POST /qgis/deliveries`; lo stato mostra «Inviato a QGIS:
  42 alberi. Apri QGIS → Silvae → Invii in attesa».
- **«Il mio account»** → sezione *Token API per QGIS*: crea (nome), lista con
  prefisso e ultimo uso, revoca. Testo di aiuto con il link al plugin.
- Nessun altro cambiamento: lista, mappa e statistiche restano come sono.

---

## 9. Plugin QGIS (`silvae-qgis`)

### 9.1 Struttura

```
silvae_qgis/
├── metadata.txt            # nome, versione, qgisMinimumVersion=3.28 (LTR)
├── __init__.py             # classFactory
├── plugin.py               # menu/toolbar, wiring
├── api.py                  # client HTTP (QgsNetworkAccessManager), token, errori
├── settings.py             # QgsSettings: URL server, token (in QgsAuthManager), ultimo comune
├── layer_store.py          # GPKG locale: crea/aggiorna tabella, indice su uuid
├── mapping.py              # mappatura colonne + persistenza nel progetto (QgsProject customProperties)
├── sync.py                 # diff locale/server, conflitti
├── ui/
│   ├── login_dialog.ui/.py
│   ├── pull_dialog.ui/.py      # Carica da Silvae (comune, filtro, dove salvare)
│   ├── push_dialog.ui/.py      # Invia a Silvae (layer, mappatura, anteprima diff)
│   ├── deliveries_dock.ui/.py  # Invii in attesa (dock laterale)
│   └── conflicts_dialog.ui/.py
├── resources/  (icone)
└── i18n/       (it, en)
```

### 9.2 Funzioni

**Login.** URL del server (default `https://<dominio>`), token incollato una
volta; salvato nel gestore autenticazioni di QGIS (cifrato), non in chiaro.
`GET /me` per verificare e mostrare «connesso come mario (agronomo)».

**Carica da Silvae.** Scelta del comune (`GET /cities`), opzionale bbox
della vista corrente. Scarica `GET /qgis/features`, scrive in un **GPKG
locale** nella cartella del progetto (`silvae_<comune>.gpkg`, layer `alberi`)
e lo aggiunge al progetto con lo stile scaricato. Se il GPKG esiste già:
pull incrementale con `since=` (ultimo pull salvato nel progetto) e
aggiornamento per `uuid`. Il GPKG locale, non un layer in memoria, perché
sopravvive alla chiusura, funziona offline e si apre in **QField** (va in
campo, torna, «Invia a Silvae»: una risposta parziale a D2).

**Invii in attesa.** Dock laterale con `GET /qgis/deliveries`; aggiornamento
automatico ogni 30 s mentre il dock è aperto (`QTimer`), pulsante manuale.
Doppio clic su un invio → ritiro, GPKG locale, layer aggiunto (o aggiornato),
zoom all'estensione, poligono dell'area come layer temporaneo se presente.

**Invia a Silvae.** Sorgente: layer scelto (qualsiasi provider: shapefile,
GPKG, memoria, Postgres suo) e «solo feature selezionate» / «solo modificate
dall'ultimo invio». Passi:

1. Riproiezione in EPSG:4326 se serve (`QgsCoordinateTransform`).
2. **Mappatura colonne**: finestra a due colonne (colonna del layer → campo
   Silvae), precompilata dall'auto-mappatura (`POST /qgis/features` con
   `dry_run=true` e le sole intestazioni, oppure logica locale che replica
   `_gpkg_inspect_mapping`: meglio chiedere al server, una fonte sola).
   Salvata nel progetto per quel layer: la volta dopo non si rivede.
3. **Anteprima** (`dry_run=true`): «12 nuovi, 3 aggiornati, 1 saltato, 2 in
   conflitto, 0 errori» con tabella dei dettagli. Conferma.
4. Invio a blocchi; barra di avanzamento; risposta consolidata.
5. **Scrittura di ritorno nel layer dell'agronomo**: campi `silvae_uuid`,
   `silvae_id`, `silvae_synced_at` (creati se mancano, con conferma; se il
   layer non è editabile — es. CSV — si propone di salvare i risultati in un
   GPKG accanto). Da qui in poi il suo layer è *collegato*: gli invii
   successivi aggiornano per `uuid`.

**Conflitti.** Una feature è in conflitto se il server è stato modificato
dopo il punto fino a cui QGIS era allineato — il più recente fra
l'`updated_at` ricevuto al pull e il `silvae_synced_at` scritto dall'ultimo
invio riuscito. Il push non la scrive e la elenca in `conflicts`; il plugin
apre la finestra di confronto campo per campo (i campi calcolati dal server
non compaiono) con tre scelte per albero: «tieni la versione di QGIS»
(reinvio con `force`), «prendi la versione di Silvae» (valori e posizione
del server scritti nel layer locale), «decidi più tardi» (predefinito: non
scrive da nessuna parte e l'albero resta in conflitto).

**Correzione posizioni.** Nessuna funzione dedicata: si spostano i punti nel
GPKG locale (o nel layer suo) e si usa «Invia a Silvae» → `latitude`/
`longitude` aggiornati, con lo snapshot precedente in `Inspection`.

### 9.3 Cosa il plugin NON fa

- Non calcola il rischio e non mostra il form ARETE: per la valutazione
  completa si apre la webapp e si cerca l'albero (nessun deep link, per
  ora).
- Non gestisce utenti, comuni, schede: sono della webapp.
- Non tocca il database direttamente.

---

## 10. Distribuzione e modello a pagamento

- Il repository ufficiale dei plugin QGIS accetta **solo GPL** e il codice
  Python è leggibile: il plugin non può essere il prodotto venduto.
- Modello: **plugin gratuito, servizio a pagamento**. Il token funziona solo
  per un account attivo; sul server si aggiunge `User.qgis_enabled` (o un
  piano) e `auth_required` rifiuta i token API di chi non lo ha. È il
  server a fare da paywall, dove sta già tutto.
- Distribuzione: (a) repository ufficiale (massima visibilità, GPL v2+), o
  (b) **repository privato** su `https://<dominio>/qgis/plugins.xml`, che
  QGIS supporta nativamente (*Plugin → Impostazioni → Repository*) e può
  essere protetto da credenziali. Si può fare (b) subito e (a) quando è
  maturo. Aggiornamenti: QGIS li propone da solo leggendo `plugins.xml`.
- Versione minima QGIS: 3.28 LTR (Python 3.9, Qt5). Qt6/QGIS 4: da tenere
  d'occhio, evitare API deprecate.

---

## 11. Fasi e sforzo

| Fase | Contenuto | Sforzo | Rilascio |
|---|---|---|---|
| **0. Modello** — ✅ fatto (settembre 2026, branch `qgis`) | `uuid`, `updated_at`, `updated_by` + backfill; `ApiToken` con `GET/POST/DELETE /me/tokens` e token `slv_…` accettati da `auth_required`; `_upsert_tree`/`_match_tree`/`_import_row_record` estratti dall'import, che ora ricalcola il rischio, ignora i derivati, non tocca i campi vuoti né l'owner e abbina solo tra gli alberi visibili; `uuid` nei GPKG/GPX esportati | 1–2 giorni | Nessun cambiamento visibile nell'interfaccia (il pannello token è in fase 1) |
| **1. Lettura** — ✅ fatto (settembre 2026) | `GET /qgis/features` (city/ids/since/bbox, proprietà piatte, `cond_classe`, `generated_at` calcolato prima della query), `GET /qgis/style.qml` + [`tools/qgis_style.py`](tools/qgis_style.py) e stile incorporato in `layer_styles` del GPKG esportato (A1 completa, con le colonne `stat_bucket`/`rischio_classe`/`cond_classe`); pannello token in «Il mio account»; plugin in [`qgis_plugin/silvae_qgis/`](qgis_plugin/) con login, *Carica da Silvae*, GPKG locale, stile, pull incrementale per uuid. Verificato headless con PyQGIS 3.34 (caricamento GeoJSON, stile, upsert, finestre offscreen). Scostamenti: plugin in una sottocartella di questo repository e non in un repository separato; token in `QgsSettings` e non nel gestore autenticazioni (solo `settings.py` da cambiare); `Cache-Control: no-store` sulle risposte JSON perché la cache di rete di QGIS riusava `/me` di un altro token | 3–4 giorni | Layer Silvae in QGIS sempre aggiornato (= A2) |
| **2. Cassetta postale** — ✅ fatto (settembre 2026) | `QgisDelivery` + `POST/GET /qgis/deliveries`, `DELETE /qgis/deliveries/<id>` e ritiro con `GET /qgis/features?delivery=<id>` (marca `fetched_at`, porta i dati **correnti**); scadenza a 7 giorni ripulita alla prima chiamata utile; «Invia a QGIS» nei tre punti della webapp (tab Esporta, barra di selezione, selezione per area col perimetro); dock *Invii in attesa* nel plugin con aggiornamento ogni 30 s, ritiro (doppio clic) ed eliminazione. Verificato headless: deposito → elenco → ritiro → GPKG+stile+perimetro → secondo ritiro che aggiorna lo stesso file → dati correnti dopo una modifica → eliminazione | 2 giorni | «Invia a QGIS» funziona |
| **3. Scrittura** — ✅ fatto (settembre 2026) | `POST /qgis/features` (mappatura colonne, `dry_run` come anteprima del diff, `ignored_fields`, conflitti su `updated_at`, `force`, snapshot pre-modifica in `Inspection`, massimo 2000 feature per chiamata) e `POST /qgis/mapping` (auto-mappatura e campi scrivibili, unica fonte); plugin: *Invia a Silvae* con finestra di mappatura salvata nel progetto, anteprima, invio a blocchi di 500 e scrittura di `silvae_uuid`/`silvae_id`/`silvae_synced_at` nel layer dell'agronomo. Aggiunta rispetto al piano: su un layer senza la colonna `updated_at` il conflitto si basa su `silvae_synced_at` scritto dal plugin. Verificato headless con un layer in EPSG:32632 e colonne proprie: riproiezione, anteprima che non scrive, creazione, collegamento, aggiornamento senza doppioni, spostamento del punto, conflitto e `force`, round-trip del layer scaricato | 4–5 giorni | Flusso completo QGIS → Silvae (= A4 senza file) |
| **4. Conflitti e sync** — ✅ fatto (settembre 2026) | finestra di risoluzione: elenco degli alberi in conflitto, confronto campo per campo QGIS↔Silvae, scelta per ciascuno (tieni QGIS → reinvio con `force`; prendi Silvae → i valori del server scritti nel layer, geometria compresa; decidi più tardi = predefinito) e pulsanti «tutti». `updated_at`, `force` e il pull incrementale `since=` erano già nelle fasi 1-3. Corretti due difetti emersi nel ciclo completo: un albero disegnato dentro il layer di Silvae tornava dal pull come riga nuova (ora il push riempie la colonna `uuid` del layer invece di aggiungere `silvae_uuid`), e due invii senza pull in mezzo davano un conflitto falso (ora «visto fin qui» è il più recente fra `updated_at` e `silvae_synced_at`) | 2–3 giorni | Uso su dati veri con più persone |
| **5. Packaging** | `plugins.xml` privato, `qgis_enabled`, i18n, guida utente con schermate, pagina nel README | 2 giorni | Vendibile |

Totale indicativo: **3–4 settimane** di lavoro effettivo, con un rilascio
utile già dopo la fase 1.

## 12. Test

- **Server**: test in `test_flask_api.py` per token (creazione, uso, revoca,
  city read-only, demo senza token), `GET /qgis/features` (scoping per
  ruolo, `since`, `delivery`), `POST /qgis/features` (crea/aggiorna per
  uuid e custom_id, derivati ignorati, ricalcolo `rischio`, snapshot
  pre-modifica in `Inspection` a ogni aggiornamento, conflitto su `updated_at`, `dry_run` senza
  scritture), cassetta postale (scadenza, `fetched_at`).
- **Plugin**: test unitari senza QGIS per `mapping.py` e `sync.py` (puro
  Python); prova manuale su QGIS 3.28 e 3.34+ con: shapefile con nomi di
  colonna del censimento di Bra (`_LOCALITA'`, `_CLASSE VT`), layer in
  memoria, layer in EPSG:32632; round-trip completo: pull → sposta 3 punti
  → push → pull con `since` → conflitto simulato modificando dalla webapp.
- **Carico**: 2 500 alberi (Bra) in pull e push a blocchi entro il timeout
  di Gunicorn.

## 13. Sicurezza dei dati esistenti

**Migrazione (fase 0)**: solo `ALTER TABLE … ADD COLUMN` nullable, come per
le colonne aggiunte finora ([`app.py:290`](app.py#L290)); backfill di `uuid`
solo dove `NULL`, `updated_at = now`; indice unico su `uuid` creato **dopo**
il backfill. `pg_dump` prima del deploy. Nessuna riga o colonna eliminata.

**Push da QGIS** — i punti in cui la logica di import attuale
([`app.py:2616`](app.py#L2616)) sarebbe pericolosa se riusata tale e quale,
e la regola che `_upsert_tree` deve rispettare:

| Rischio | Regola |
|---|---|
| Abbinamento per coordinate su tutto il comune → si sovrascrive (e si "ruba", con `owner_id = user_id`) un albero di un altro agronomo | Cercare solo in `_scoped_tree_query()`; **mai** modificare `owner_id`. |
| Colonne vuote nel layer che in `update` cancellano valori buoni | Un valore vuoto/`NULL` nel push **non tocca** il campo; svuotare si fa dalla webapp. |
| Modifiche concorrenti dalla webapp | `updated_at` + `conflicts` + `dry_run` (§6.2); senza `force` non si scrive. |
| Punto spostato e rimandato senza `uuid` → doppione | Inevitabile senza chiave (abbinare per `custom_id` perderebbe alberi nei censimenti con numerazione per località, vedi §6.2): l'uuid è nei GPKG/GPX esportati e il plugin lo scrive nel layer al primo push. |

Protezioni per costruzione: **nessuna cancellazione** da QGIS (un albero
sparito dal layer resta su Silvae); le `Inspection` sono storico che si
accumula, e a ogni push che modifica un albero se ne salva lo snapshot
**precedente** (§6.2 punto 5): un "annulla" per albero.

## 14. Decisioni prese

Prese:
- le scritture passano **solo** dall'API (mai dal DB), il rischio lo calcola
  il server;
- chiave di collegamento: `uuid` (non `custom_id`); senza uuid decidono le
  coordinate, mai il `custom_id` se le coordinate ci sono (§6.2);
- copia locale in GPKG, non layer in memoria;
- invii personali (chi preme il pulsante li ritira);
- plugin gratuito, servizio a pagamento;
- `city` obbligatorio in `POST /qgis/features`: nessuna geocodifica
  automatica del comune (una chiamata Nominatim per riga non regge su un
  push di migliaia di alberi); il plugin lo chiede prima dell'invio;
- non esiste un `.qml` di riferimento dello studio: lo stile QGIS viene
  **generato** da [`tools/palette.py`](tools/palette.py) (chiude il punto 1
  di A1 in `next_steps.md`); se in futuro l'agronomo ne adotta uno, si
  travasano i colori in `palette.py`, non viceversa;
- ogni modifica da QGIS a un albero esistente salva una `Inspection` con lo
  snapshot precedente, anche per la sola posizione (sicurezza prima della
  purezza semantica: si distingue con `comments = "Sincronizzazione da
  QGIS"`);
- le `diag_*` si compilano **solo nella webapp**: da QGIS sono in sola
  lettura (testo appiattito), e non è previsto renderle scrivibili;
- gli invii sono solo personali: «Invia a QGIS» a un collega
  (`recipient_id`) non ora, eventualmente in futuro;
- nessun deep link `/#tree/<id>` per ora: il plugin non ha «Apri in
  Silvae»; per la valutazione si apre la webapp e si cerca l'albero.

Nessuna questione aperta: il piano è pronto per la fase 0.

# Test del frontend

Verifiche della guardia «uscire senza salvare» del form albero. Girano su
jsdom: caricano `index.html` e `app.js` veri, con `fetch`, `L` (Leaflet) e
`voiceInit` finti, e non richiedono un browser né un server.

Si eseguono con Docker, senza installare nulla sulla macchina:

```bash
cd frontend/tests && ./run.sh
```

Lo script scarica `node:22-alpine`, installa `jsdom` dentro il container e
stampa l'elenco delle verifiche. Esce con codice diverso da zero se qualcuna
fallisce.

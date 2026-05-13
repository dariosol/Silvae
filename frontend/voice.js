// Voice command interface for Silvae Pro (Italian)
// Depends on globals from app.js: state, showStatus, switchTab, showTreeView,
// resetForm, openEditForm, openHistory, toggleNearby, renderPage, condClass
(function () {
    'use strict';

    const DIGIT_WORDS = {
        zero:'0', uno:'1', due:'2', tre:'3', quattro:'4',
        cinque:'5', sei:'6', sette:'7', otto:'8', nove:'9'
    };

    // Italian compound number words common in field distance commands
    const COMPOUND_NUMS = [
        [/\bduemila\b/gi,     '2000'],
        [/\bmille\b/gi,       '1000'],
        [/\bnovecento\b/gi,   '900'],
        [/\bottocento\b/gi,   '800'],
        [/\bsettecento\b/gi,  '700'],
        [/\bseicento\b/gi,    '600'],
        [/\bcinquecento\b/gi, '500'],
        [/\bquattrocento\b/gi,'400'],
        [/\btrecento\b/gi,    '300'],
        [/\bduecento\b/gi,    '200'],
        [/\bcento\b/gi,       '100'],
    ];

    // Italian words that must NOT be collapsed with following digits
    const STOP_WORDS = new Set([
        'di','da','in','il','la','lo','le','li','gli','un','una','uno',
        'al','dal','del','per','nel','sul','col','con','tra','fra',
        'ma','se','su','a','e','o','i'
    ]);

    let recognition  = null;
    let listening    = false;
    let speechOn     = true;

    // ── Init ──────────────────────────────────────────────────────────────────
    function voiceInit() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) {
            const btn = document.getElementById('voiceBtn');
            if (btn) btn.style.display = 'none';
            return;
        }
        recognition = new SR();
        recognition.lang            = 'it-IT';
        recognition.continuous      = false;
        recognition.interimResults  = false;
        recognition.maxAlternatives = 3;

        recognition.onstart  = () => setListening(true);
        recognition.onend    = () => setListening(false);
        recognition.onerror  = e => {
            setListening(false);
            if (e.error !== 'no-speech') showStatus('Microfono: ' + e.error, 'warning');
        };
        recognition.onresult = e => {
            for (let i = 0; i < e.results[0].length; i++) {
                const transcript = e.results[0][i].transcript.trim();
                const intent = parseIntent(transcript);
                if (intent) { dispatchIntent(intent); return; }
            }
            // regex missed — try Groq NLU fallback
            const raw = e.results[0][0].transcript.trim();
            callGroqFallback(raw);
        };
    }

    function startListening() {
        if (!recognition) { showStatus('Comandi vocali non supportati su questo browser', 'warning'); return; }
        if (listening) { recognition.stop(); return; }
        try { recognition.start(); } catch (_) { /* already started */ }
    }

    function setListening(on) {
        listening = on;
        const btn = document.getElementById('voiceBtn');
        if (!btn) return;
        btn.classList.toggle('voice-listening', on);
        btn.title = on ? 'In ascolto… (tocca per fermare)' : 'Comando vocale (it)';
    }

    // ── Feedback ──────────────────────────────────────────────────────────────
    function voiceFeedback(msg, level) {
        showStatus('🎤 ' + msg, level || 'info');
        if (!speechOn) return;
        const u = new SpeechSynthesisUtterance(msg);
        u.lang = 'it-IT'; u.rate = 1.05;
        speechSynthesis.cancel();
        speechSynthesis.speak(u);
    }

    // ── Text normalisation ────────────────────────────────────────────────────
    function normalizeText(text) {
        let s = text.toLowerCase();
        // Single digit words: "zero" → "0" etc.
        Object.entries(DIGIT_WORDS).forEach(([w, d]) => {
            s = s.replace(new RegExp('\\b' + w + '\\b', 'g'), d);
        });
        // Compound Italian number words: "cinquecento" → "500" etc.
        COMPOUND_NUMS.forEach(([re, val]) => { s = s.replace(re, val); });
        // Collapse letter+space+digits into IDs ("ROM 007" → "ROM007"),
        // but skip common Italian stop words ("di 500" must NOT become "DI500")
        s = s.replace(/\b([a-z]{1,6})\s+([\d][\s\d]{0,11})/g, (full, letters, digits) => {
            if (STOP_WORDS.has(letters)) return full;
            return letters.toUpperCase() + digits.replace(/\s/g, '');
        });
        // "TOR - 001" → "TOR-001"
        s = s.replace(/([A-Z]{1,6})\s*-\s*(\d+)/g, '$1-$2');
        return s;
    }

    function findTree(customId) {
        if (!customId) return null;
        const up = customId.toUpperCase();
        const bare = up.replace(/-/g, '');
        return (state.allTrees || []).find(t => {
            const tid = t.custom_id.toUpperCase();
            return tid === up || tid.replace(/-/g, '') === bare;
        }) || null;
    }

    // ── Intent definitions ────────────────────────────────────────────────────
    // Order matters: more specific patterns first.
    const INTENTS = [

        // STORICO / HISTORY
        {
            re: /(?:storico|cronologia|ispezioni\s+(?:di|dell[ao])|storia)\s+(?:albero\s+|dell[ao]\s+albero\s+)?([A-Z0-9]{1,8}(?:-\d{1,4})?)/i,
            intent: 'OPEN_HISTORY',
            params: m => ({ customId: m[1].toUpperCase() })
        },

        // LOCATE ON MAP
        {
            re: /(?:dov['’\s][èe]|posizione|sulla\s+mappa|mostrami\s+sulla\s+mappa)\s+(?:l['’]albero\s+|albero\s+)?([A-Z0-9]{1,8}(?:-\d{1,4})?)/i,
            intent: 'LOCATE_TREE',
            params: m => ({ customId: m[1].toUpperCase() })
        },

        // EDIT TREE
        {
            re: /modifica\s+(?:l['’]albero\s+|albero\s+)?([A-Z0-9]{1,8}(?:-\d{1,4})?)/i,
            intent: 'EDIT_TREE',
            params: m => ({ customId: m[1].toUpperCase() })
        },

        // OPEN TREE CARD
        {
            re: /(?:scheda|mostrami|apri|cerca)\s+(?:l['’]albero\s+|albero\s+)?([A-Z0-9]{1,8}(?:-\d{1,4})?)/i,
            intent: 'OPEN_TREE',
            params: m => ({ customId: m[1].toUpperCase() })
        },

        // PROXIMITY RADIUS
        // matches: "nel raggio di 500 metri", "raggio 1 km", "entro 200 m",
        //          "entro un raggio di 500 metri", "a 300 metri da me"
        {
            re: /(?:(?:nel|in\s+un)\s+raggio\s+(?:di\s+)?|(?:entro|a)\s+(?:un\s+raggio\s+di\s+)?|raggio\s+(?:di\s+)?)([\d]+(?:[,.]\d+)?)\s*(km|chilometr\w*|kilo\w*|m\b|metr\w*)/i,
            intent: 'NEARBY_RADIUS',
            params: m => {
                const val = parseFloat(m[1].replace(',', '.'));
                return { radius: /k/i.test(m[2]) ? val * 1000 : val };
            }
        },

        // FILTER BY CONDITION
        {
            re: /(?:filtra|mostrami|alberi|condizione)\s+(?:per\s+condizione\s+|condizione\s+|in\s+stato\s+)?(ottim[oi]|eccellent\w+|buon[oia]|discret[oi]|mediocer\w+|scars[aoi]|critic[oi]|mort[oi]|abbattut[oi])/i,
            intent: 'FILTER_CONDITION',
            params: m => ({ word: m[1].toLowerCase() })
        },

        // RESET FILTERS
        {
            re: /(?:rimuovi|togli|cancella)\s+(?:i\s+)?filtri|tutti\s+gli\s+alberi|\breset\b/i,
            intent: 'RESET_FILTERS',
            params: () => ({})
        },

        // ADD TREE
        {
            re: /(?:aggiungi|nuovo|inserisci|crea)\s+(?:un\s+)?albero/i,
            intent: 'ADD_TREE',
            params: () => ({})
        },

        // SWITCH TO MAP
        {
            re: /(?:vai\s+alla|mostrami\s+la|apri\s+la)\s+mappa|vai\s+a\s+mappa/i,
            intent: 'SWITCH_MAP',
            params: () => ({})
        },

        // SWITCH TO LIST
        {
            re: /(?:vai\s+alla|mostrami\s+la|torna\s+alla)\s+lista|vai\s+a\s+lista|torna\s+agli\s+alberi/i,
            intent: 'SWITCH_LIST',
            params: () => ({})
        },

        // COUNT TREES
        {
            re: /quanti\s+(?:alberi|ne\s+abbiamo|ce\s+ne\s+sono)/i,
            intent: 'COUNT_TREES',
            params: () => ({})
        },

        // NEARBY TOGGLE (no radius)
        {
            re: /vicino\s+a\s+me|alberi\s+vicini|attiva\s+(?:la\s+)?posizione|mostrami\s+(?:gli\s+alberi\s+)?vicini/i,
            intent: 'NEARBY_TOGGLE',
            params: () => ({})
        },
    ];

    function parseIntent(rawText) {
        const text = normalizeText(rawText);
        for (const def of INTENTS) {
            const m = text.match(def.re);
            if (m) return { intent: def.intent, params: def.params(m), raw: rawText };
        }
        return null;
    }

    // ── Condition map ─────────────────────────────────────────────────────────
    const COND_MAP = [
        { re: /ottim[oi]|eccellent/,  label: 'Ottimo',    cls: 'tr-good' },
        { re: /buon[oia]/,            label: 'Buono',     cls: 'tr-good' },
        { re: /discret[oi]/,          label: 'Discreto',  cls: 'tr-fair' },
        { re: /mediocer/,             label: 'Mediocre',  cls: 'tr-fair' },
        { re: /scars/,                label: 'Scarso',    cls: 'tr-poor' },
        { re: /critic/,               label: 'Critico',   cls: 'tr-poor' },
        { re: /mort/,                 label: 'Morto',     cls: 'tr-poor' },
        { re: /abbattut/,             label: 'Abbattuto', cls: 'tr-poor' },
    ];

    function resolveCond(word) {
        return COND_MAP.find(c => c.re.test(word)) || null;
    }

    // ── Dispatcher ────────────────────────────────────────────────────────────
    function dispatchIntent({ intent, params }) {

        if (intent === 'NEARBY_RADIUS') {
            const r = Math.round(params.radius);
            if (!navigator.geolocation) { voiceFeedback('Geolocalizzazione non disponibile', 'warning'); return; }
            navigator.geolocation.getCurrentPosition(pos => {
                state.userLat     = pos.coords.latitude;
                state.userLon     = pos.coords.longitude;
                state.nearbyMode  = true;
                state.nearbyRadius = r;
                state.currentPage = 1;
                const btn = document.getElementById('nearbyBtn');
                if (btn) { btn.classList.remove('btn-outline'); btn.classList.add('btn-primary'); }
                renderPage();
                const label = r >= 1000 ? (r / 1000) + ' km' : r + ' m';
                voiceFeedback('Mostro gli alberi entro ' + label + ' da te');
            }, () => voiceFeedback('Impossibile ottenere la posizione', 'danger'));
            return;
        }

        if (intent === 'NEARBY_TOGGLE') {
            toggleNearby();
            voiceFeedback(state.nearbyMode ? 'Modalità vicino a me attivata' : 'Modalità vicino a me disattivata');
            return;
        }

        if (intent === 'OPEN_TREE' || intent === 'EDIT_TREE') {
            const tree = findTree(params.customId);
            if (!tree) { voiceFeedback('Albero ' + params.customId + ' non trovato', 'warning'); return; }
            openEditForm(tree.id);
            voiceFeedback('Apro ' + tree.custom_id);
            return;
        }

        if (intent === 'OPEN_HISTORY') {
            const tree = findTree(params.customId);
            if (!tree) { voiceFeedback('Albero ' + params.customId + ' non trovato', 'warning'); return; }
            openHistory(tree.id, tree.custom_id);
            voiceFeedback('Storico di ' + tree.custom_id);
            return;
        }

        if (intent === 'LOCATE_TREE') {
            const tree = findTree(params.customId);
            if (!tree) { voiceFeedback('Albero ' + params.customId + ' non trovato', 'warning'); return; }
            if (!tree.latitude || !tree.longitude) { voiceFeedback(tree.custom_id + ': coordinate non disponibili', 'warning'); return; }
            switchTab('map');
            setTimeout(() => {
                const m = state.map;
                if (!m) return;
                m.setView([parseFloat(tree.latitude), parseFloat(tree.longitude)], 18);
                const mk = state.markers.find(x => x.treeId === tree.id);
                if (mk) mk.openPopup();
            }, 350);
            voiceFeedback('Trovo ' + tree.custom_id + ' sulla mappa');
            return;
        }

        if (intent === 'FILTER_CONDITION') {
            const cond = resolveCond(params.word);
            if (!cond) { voiceFeedback('Condizione non riconosciuta', 'warning'); return; }
            state.filteredTrees = state.allTrees.filter(t => condClass(t.condition) === cond.cls);
            state.currentPage = 1;
            renderPage();
            voiceFeedback('Filtro ' + cond.label + ': ' + state.filteredTrees.length + ' alberi');
            return;
        }

        if (intent === 'RESET_FILTERS') {
            state.filteredTrees = state.allTrees;
            state.nearbyMode    = false;
            state.nearbyRadius  = null;
            state.userLat       = null;
            state.userLon       = null;
            state.currentPage   = 1;
            const idEl = document.getElementById('idFilter');
            if (idEl) idEl.value = '';
            const btn = document.getElementById('nearbyBtn');
            if (btn) { btn.classList.remove('btn-primary'); btn.classList.add('btn-outline'); }
            renderPage();
            voiceFeedback('Filtri rimossi. ' + state.allTrees.length + ' alberi');
            return;
        }

        if (intent === 'ADD_TREE') {
            switchTab('trees');
            resetForm();
            showTreeView('edit');
            voiceFeedback('Modulo nuovo albero aperto');
            return;
        }

        if (intent === 'SWITCH_MAP') {
            switchTab('map');
            voiceFeedback('Mappa');
            return;
        }

        if (intent === 'SWITCH_LIST') {
            switchTab('trees');
            showTreeView('list');
            voiceFeedback('Lista alberi');
            return;
        }

        if (intent === 'COUNT_TREES') {
            const n = state.allTrees.length;
            const f = state.filteredTrees.length;
            const msg = f < n
                ? f + ' alberi filtrati su ' + n + ' totali'
                : n + ' alber' + (n !== 1 ? 'i' : 'o') + ' censit' + (n !== 1 ? 'i' : 'o');
            voiceFeedback(msg);
            return;
        }
    }

    // ── Groq NLU fallback ─────────────────────────────────────────────────────
    async function callGroqFallback(transcript) {
        showStatus('🎤 …', 'info');
        try {
            const res = await fetch('/api/voice_intent', {
                method: 'POST',
                headers: Object.assign({ 'Content-Type': 'application/json' }, authHeader()),
                body: JSON.stringify({ transcript }),
            });
            if (!res.ok) throw new Error('server error');
            const data = await res.json();
            if (data.intent) {
                dispatchIntent({ intent: data.intent, params: data.params || {}, raw: transcript });
            } else {
                showStatus('Non capito: "' + transcript + '"', 'warning');
            }
        } catch (_) {
            showStatus('Non capito: "' + transcript + '"', 'warning');
        }
    }

    // ── Public API ────────────────────────────────────────────────────────────
    window.voiceInit      = voiceInit;
    window.startListening = startListening;
    window.voiceSpeechEnabled = v => { speechOn = v; };

}());

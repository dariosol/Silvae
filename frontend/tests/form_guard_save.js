
/* ===== «Salva e esci»: usa il salvataggio vero, con fetch finto ===== */
(async () => {
    const ok = [], ko = [];
    const check = (nome, cond) => (cond ? ok : ko).push(nome);
    const E = id => document.getElementById(id);
    let chiamate = [], esitoServer = true, uscito = false;

    window.fetch = async (url, opt = {}) => {
        chiamate.push({ url: String(url), method: opt.method || 'GET', body: opt.body });
        if (String(url).includes('/trees')) return { ok: true, json: async () => [] };
        return { ok: esitoServer, json: async () => (esitoServer ? { tree_id: 7 } : { message: 'rifiutato' }) };
    };
    state.token = 'x'; state.activeTab = 'trees';
    E('view-edit').classList.add('active');
    // campi obbligatori: senza questi reportValidity() blocca il salvataggio
    E('custom_id').value = 'T-1'; E('city').value = 'Bra';

    // --- modifica di un albero esistente, salvataggio riuscito
    E('editTreeId').value = '42';
    markFormClean();
    E('species').value = 'Tilia cordata';
    chiamate = []; uscito = false;
    leaveEditView(() => { uscito = true; });
    await unsavedSaveAndLeave();
    const salva = chiamate.find(c => c.url.includes('/tree/42'));
    check('Salva e esci: invia PATCH sull\'albero giusto', !!salva && salva.method === 'PATCH');
    check('Salva e esci: manda la modifica nel corpo',
          !!salva && JSON.parse(salva.body).species === 'Tilia cordata');
    check('Salva e esci: esce dopo il salvataggio', uscito === true);
    check('Salva e esci: popup chiuso', !E('unsavedModal').classList.contains('open'));
    check('Salva e esci: form pulito dopo il salvataggio', isFormDirty() === false);

    // --- nuovo albero: POST su /add_tree
    E('editTreeId').value = '';
    E('custom_id').value = 'T-2'; E('city').value = 'Bra';
    markFormClean(); E('species').value = 'Acer campestre';
    chiamate = []; uscito = false;
    leaveEditView(() => { uscito = true; });
    await unsavedSaveAndLeave();
    check('Salva e esci: nuovo albero -> POST /add_tree',
          chiamate.some(c => c.url.endsWith('/add_tree') && c.method === 'POST'));

    // --- server che rifiuta: non si esce, le modifiche restano
    esitoServer = false;
    E('view-edit').classList.add('active');   // il salvataggio precedente era tornato alla lista
    E('editTreeId').value = '42';
    E('custom_id').value = 'T-3'; E('city').value = 'Bra';
    markFormClean(); E('species').value = 'Fraxinus';
    uscito = false;
    leaveEditView(() => { uscito = true; });
    await unsavedSaveAndLeave();
    check('salvataggio rifiutato: NON esce', uscito === false);
    check('salvataggio rifiutato: modifica conservata', E('species').value === 'Fraxinus');

    // --- campi obbligatori mancanti: non si salva e non si esce
    esitoServer = true;
    resetForm(); E('view-edit').classList.add('active'); E('editTreeId').value = '42';
    markFormClean(); E('species').value = 'Senza comune';   // custom_id e city vuoti
    chiamate = []; uscito = false;
    leaveEditView(() => { uscito = true; });
    await unsavedSaveAndLeave();
    check('campi obbligatori mancanti: non salva', chiamate.length === 0);
    check('campi obbligatori mancanti: non esce',  uscito === false);
    check('campi obbligatori mancanti: modifica conservata', E('species').value === 'Senza comune');

    ok.forEach(n => console.log('  OK       ' + n));
    ko.forEach(n => console.log('  FALLITO  ' + n));
    console.log(`\n${ok.length} verifiche passate, ${ko.length} fallite`);
    globalThis.__falliti2 = ko.length;
})();

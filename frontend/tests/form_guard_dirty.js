
/* ===== verifiche della guardia (eseguite nello stesso scope di app.js) ===== */
(() => {
    const ok = [], ko = [];
    const check = (nome, cond) => (cond ? ok : ko).push(nome);
    const E = id => document.getElementById(id);
    const aperto = () => E('unsavedModal').classList.contains('open');
    let uscito = false;
    const esci = () => { uscito = true; };

    state.activeTab = 'trees';
    E('view-edit').classList.add('active');

    markFormClean();
    check("form appena aperto non e' sporco", isFormDirty() === false);

    uscito = false; leaveEditView(esci);
    check('senza modifiche esce subito', uscito === true);
    check('senza modifiche nessun popup', !aperto());

    E('species').value = 'Quercus robur';
    check("una modifica rende il form sporco", isFormDirty() === true);

    uscito = false; leaveEditView(esci);
    check('con modifiche compare il popup', aperto());
    check("con modifiche l'uscita e' sospesa", uscito === false);

    const testo = E('unsavedModal').textContent.replace(/\s+/g, ' ');
    check('popup: titolo «Uscire senza salvare?»', testo.includes('Uscire senza salvare?'));
    ['Salva e esci', 'Esci senza salvare', 'Annulla'].forEach(t =>
        check(`popup: pulsante «${t}»`, testo.includes(t)));

    closeUnsavedModal();
    check('Annulla chiude il popup', !aperto());
    check("Annulla non esegue l'uscita", uscito === false);
    check('Annulla conserva la modifica', E('species').value === 'Quercus robur');

    leaveEditView(esci);
    unsavedDiscardAndLeave();
    check('Esci senza salvare: esce', uscito === true);
    check('Esci senza salvare: popup chiuso', !aperto());
    check('Esci senza salvare: form svuotato', E('species').value === '');

    E('view-edit').classList.remove('active');
    markFormClean(); E('species').value = 'Altro';
    uscito = false; leaveEditView(esci);
    check('fuori dal form nessun popup', uscito === true && !aperto());

    ok.forEach(n => console.log('  OK       ' + n));
    ko.forEach(n => console.log('  FALLITO  ' + n));
    console.log(`\n${ok.length} verifiche passate, ${ko.length} fallite`);
    globalThis.__falliti = ko.length;
})();

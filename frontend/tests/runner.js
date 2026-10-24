// Carica index.html e app.js in jsdom, poi esegue i file di verifica nello
// stesso scope (le `const`/`let` di app.js non sopravvivono a un secondo eval).
const fs = require('fs');
const { JSDOM } = require('jsdom');

const dom = new JSDOM(fs.readFileSync('/w/index.html', 'utf8'),
                      { runScripts: 'outside-only', url: 'http://localhost/' });
const win = dom.window;
win.console = console;
win.L = { map: () => ({ setView: () => {} }), tileLayer: () => ({}), latLng: v => v };
win.fetch = async () => ({ ok: true, json: async () => [] });
win.voiceInit = () => {};

const verifiche = ['form_guard_dirty.js', 'form_guard_save.js']
    .map(f => fs.readFileSync('/t/' + f, 'utf8')).join('\n');
win.eval(fs.readFileSync('/w/app.js', 'utf8') + verifiche);

setTimeout(() => {
    const falliti = (win.__falliti || 0) + (win.__falliti2 || 0);
    console.log(falliti ? `\n${falliti} VERIFICHE FALLITE` : '\nTutte le verifiche passate');
    process.exit(falliti ? 1 : 0);
}, 2000);

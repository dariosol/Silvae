#!/usr/bin/env python3
"""
test_locale.py — Avvia Silvae Pro in locale per test rapidi.

Uso:
    python test_locale.py                 # usa PostgreSQL (DATABASE_URL o default del progetto)
    python test_locale.py --sqlite        # zero-setup: usa un file SQLite locale (test_locale.db)
    python test_locale.py --port 8000     # porta diversa (default 5000)
    python test_locale.py --no-browser    # non aprire il browser automaticamente
    python test_locale.py --host 127.0.0.1

Note:
- Le variabili d'ambiente vanno impostate PRIMA di importare app.py, perché app.py
  legge DATABASE_URL / SECRET_KEY a livello di modulo (all'import).
- La modalità --sqlite è comoda per provare l'interfaccia (es. la nuova selezione
  ad area sulla mappa) senza installare PostgreSQL. Per la piena fedeltà usa Postgres.
"""

import argparse
import os
import sys
import threading
import webbrowser

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_args():
    p = argparse.ArgumentParser(description="Avvia Silvae Pro in locale.")
    p.add_argument('--sqlite', action='store_true',
                   help="Usa un database SQLite locale (test_locale.db) invece di PostgreSQL.")
    p.add_argument('--host', default='127.0.0.1',
                   help="Host su cui esporre il server (default 127.0.0.1).")
    p.add_argument('--port', type=int, default=5000,
                   help="Porta del server (default 5000).")
    p.add_argument('--no-browser', action='store_true',
                   help="Non aprire automaticamente il browser.")
    p.add_argument('--no-debug', action='store_true',
                   help="Disattiva la modalità debug di Flask.")
    return p.parse_args()


def setup_env(args):
    """Imposta le variabili d'ambiente PRIMA dell'import di app.py."""
    # Database
    if args.sqlite:
        db_path = os.path.join(PROJECT_DIR, 'test_locale.db')
        os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'
        print(f"[DB] SQLite locale: {db_path}")
    elif os.environ.get('DATABASE_URL'):
        print(f"[DB] PostgreSQL da DATABASE_URL (ambiente)")
    else:
        print("[DB] PostgreSQL (default del progetto: localhost/trees_db)")

    # Segreto di sviluppo (non usare in produzione)
    os.environ.setdefault('SECRET_KEY', 'dev-secret-solo-per-test-locale')
    # Registrazione pubblica disabilitata in locale (default dell'app)
    os.environ.setdefault('REGISTRATION_ENABLED', 'false')
    # URL base per gli eventuali link di reset password stampati in console
    os.environ.setdefault('APP_BASE_URL', f'http://{args.host}:{args.port}')


def check_dependencies():
    """Verifica che le dipendenze chiave siano installate (venv attivo)."""
    try:
        import flask  # noqa: F401
        import flask_sqlalchemy  # noqa: F401
    except ImportError as e:
        sys.exit(
            f"\n[ERRORE] Dipendenza mancante: {e.name}\n"
            "Attiva l'ambiente virtuale e installa le dipendenze:\n"
            "    source flaskenv/bin/activate\n"
            "    pip install -r requirements.txt\n"
        )


def check_postgres(args):
    """Preflight di connessione a PostgreSQL: errore chiaro se non raggiungibile."""
    if args.sqlite:
        return
    dsn = os.environ.get(
        'DATABASE_URL',
        'postgresql://postgres:c0st4m4gn4@localhost/trees_db',
    )
    if dsn.startswith('postgres://'):
        dsn = dsn.replace('postgres://', 'postgresql://', 1)
    if not dsn.startswith('postgresql'):
        return
    try:
        import psycopg2
    except ImportError:
        return  # se manca psycopg2, sarà app.py a segnalarlo
    try:
        conn = psycopg2.connect(dsn)
        conn.close()
        print("[DB] Connessione a PostgreSQL OK")
    except Exception as e:
        sys.exit(
            f"\n[ERRORE] Impossibile connettersi a PostgreSQL:\n    {e}\n"
            "Opzioni:\n"
            "  1) Avvia PostgreSQL e crea il database 'trees_db', oppure\n"
            "  2) Imposta DATABASE_URL con le tue credenziali, oppure\n"
            "  3) Prova senza database esterno:  python test_locale.py --sqlite\n"
        )


def open_browser_later(url):
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()


def main():
    args = parse_args()
    os.chdir(PROJECT_DIR)  # così app.py trova ./frontend e ./tools

    setup_env(args)
    check_dependencies()
    check_postgres(args)

    # Import DOPO aver impostato l'ambiente: app.py legge le env all'import
    # e al bootstrap crea l'utente admin e gli account demo.
    import app as app_module

    url = f'http://{args.host}:{args.port}'
    print("\n" + "=" * 56)
    print("  Silvae Pro — avvio in locale")
    print("=" * 56)
    print(f"  URL:        {url}")
    print("  Admin:      admin / admin")
    print(f"  Demo user:  {os.environ.get('DEMO_USERNAME', 'demo_user')} / "
          f"{os.environ.get('DEMO_PASSWORD', 'demo_password')}")
    print(f"  Demo city:  {os.environ.get('DEMO_CITY_USERNAME', 'demo_city')} / "
          f"{os.environ.get('DEMO_CITY_PASSWORD', 'demo_city_password')}")
    print("  Ctrl+C per fermare il server.")
    print("=" * 56 + "\n")

    if not args.no_browser:
        open_browser_later(url)

    # use_reloader=False: evita il doppio avvio (e doppia apertura del browser)
    app_module.app.run(
        host=args.host,
        port=args.port,
        debug=not args.no_debug,
        use_reloader=False,
    )


if __name__ == '__main__':
    main()

import os, sqlite3, json, time
from contextlib import contextmanager

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "app.db")

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            exchange TEXT DEFAULT 'BINANCE_UM',
            api_key_enc TEXT NOT NULL,
            api_secret_enc TEXT NOT NULL,
            testnet INTEGER DEFAULT 1,
            active INTEGER DEFAULT 1,
            futures_balance REAL DEFAULT 0,
            created_at INTEGER,
            updated_at INTEGER
        );""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            symbol TEXT,
            long_enabled INTEGER DEFAULT 0,
            long_amount REAL DEFAULT 0,
            long_leverage INTEGER DEFAULT 1,
            short_enabled INTEGER DEFAULT 0,
            short_amount REAL DEFAULT 0,
            short_leverage INTEGER DEFAULT 1,
            r_points_json TEXT DEFAULT '[]',
            cond_sl_close INTEGER DEFAULT 1,
            cond_trailing INTEGER DEFAULT 1,
            cond_close_last INTEGER DEFAULT 0,
            created_at INTEGER
        );""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            long_enabled INTEGER DEFAULT 0,
            long_amount REAL DEFAULT 0,
            long_leverage INTEGER DEFAULT 1,
            short_enabled INTEGER DEFAULT 0,
            short_amount REAL DEFAULT 0,
            short_leverage INTEGER DEFAULT 1,
            r_points_json TEXT DEFAULT '[]',
            cond_sl_close INTEGER DEFAULT 1,
            cond_trailing INTEGER DEFAULT 1,
            cond_close_last INTEGER DEFAULT 0,
            start_time INTEGER,
            long_entry_price REAL,
            short_entry_price REAL,
            long_status TEXT DEFAULT 'No trade',
            short_status TEXT DEFAULT 'No trade',
            long_sl_point REAL,
            short_sl_point REAL,
            testnet INTEGER DEFAULT 1
        );""")
        con.commit()

@contextmanager
def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()

def now(): return int(time.time())
def to_dict(row): return dict(row) if row else None
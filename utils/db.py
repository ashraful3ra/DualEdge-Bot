import sqlite3, os, time

DB_FILE = os.path.join('data', 'app.db')
SCHEMA_VERSION = 4

def now(): return int(time.time())

def connect():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    return con

def to_dict(row):
    if not row: return None
    return dict(row)

def init_db():
    if not os.path.exists('data'):
        os.makedirs('data')
    
    con = connect()
    cur = con.cursor()

    cur.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL PRIMARY KEY);")
    
    cur.execute("SELECT version FROM schema_version;")
    r = cur.fetchone()
    current_version = r['version'] if r else 0

    if current_version < 1:
        cur.execute("""CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            exchange TEXT NOT NULL,
            api_key_enc TEXT NOT NULL,
            api_secret_enc TEXT NOT NULL,
            testnet INTEGER DEFAULT 1,
            active INTEGER DEFAULT 1,
            futures_balance REAL,
            created_at INTEGER,
            updated_at INTEGER
        );""")
        cur.execute("""CREATE TABLE IF NOT EXISTS bots (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            long_enabled INTEGER,
            long_amount REAL,
            long_leverage INTEGER,
            short_enabled INTEGER,
            short_amount REAL,
            short_leverage INTEGER,
            r_points_json TEXT,
            cond_sl_close INTEGER,
            cond_trailing INTEGER,
            cond_close_last INTEGER,
            start_time INTEGER,
            long_entry_price REAL,
            short_entry_price REAL,
            long_status TEXT,
            short_status TEXT,
            long_sl_point REAL,
            short_sl_point REAL,
            testnet INTEGER,
            long_final_roi REAL DEFAULT 0.0,
            short_final_roi REAL DEFAULT 0.0
        );""")
        cur.execute("""CREATE TABLE IF NOT EXISTS templates (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            symbol TEXT,
            long_enabled INTEGER,
            long_amount REAL,
            long_leverage INTEGER,
            short_enabled INTEGER,
            short_amount REAL,
            short_leverage INTEGER,
            r_points_json TEXT,
            cond_sl_close INTEGER,
            cond_trailing INTEGER,
            cond_close_last INTEGER,
            created_at INTEGER
        );""")
    
    if current_version == 0:
        cur.execute("INSERT INTO schema_version (version) VALUES (?);", (SCHEMA_VERSION,))
    else:
        cur.execute("UPDATE schema_version SET version=?;", (SCHEMA_VERSION,))

    con.commit()
    con.close()
    print('DB init OK')
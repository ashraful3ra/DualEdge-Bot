import os, time
# Using PyMySQL for MySQL connection
import pymysql
import pymysql.cursors

# --- MySQL Configuration from Environment Variables ---
# Note: os.environ must be loaded via load_dotenv() in app.py before this module is used
MYSQL_HOST = os.environ.get('MYSQL_HOST', 'utradebot.com')
MYSQL_USER = os.environ.get('MYSQL_USER', 'dualedge')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'm[xffKB4/T[jkS6b')
MYSQL_DB = os.environ.get('MYSQL_DB', 'dualedge')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))

SCHEMA_VERSION = 5 # Incremented schema version

def now(): 
    return int(time.time())

def connect():
    """Establishes a connection to the MySQL database."""
    # PyMySQL uses DictCursor to return dictionary-like rows, replacing sqlite3.Row
    con = pymysql.connect(
        host=MYSQL_HOST, 
        user=MYSQL_USER, 
        password=MYSQL_PASSWORD, 
        database=MYSQL_DB, 
        port=MYSQL_PORT,
        cursorclass=pymysql.cursors.DictCursor,
    )
    return con

def to_dict(row):
    # PyMySQL DictCursor already returns a dictionary, so this is for compatibility
    if not row: return None
    return dict(row)

def init_db():
    try:
        # Attempt to connect to the configured MySQL database
        con = connect()
    except Exception as e:
        print(f"ERROR: Could not connect to MySQL database '{MYSQL_DB}'. Please check your .env configuration and ensure the database exists. Error: {e}")
        raise

    cur = con.cursor()

    # --- SQL Translation: SQLite to MySQL ---
    # INTEGER PRIMARY KEY AUTOINCREMENT -> INT PRIMARY KEY AUTO_INCREMENT
    # REAL -> DOUBLE
    # INTEGER -> TINYINT/INT
    # TEXT -> TEXT / VARCHAR(255)

    # 1. Create schema_version table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INT NOT NULL PRIMARY KEY
        );
    """)
    con.commit()

    # Check current schema version
    cur.execute("SELECT version FROM schema_version;")
    r = cur.fetchone()
    current_version = r['version'] if r else 0

    if current_version < 1:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(255) NOT NULL,
                exchange VARCHAR(255) NOT NULL,
                api_key_enc TEXT NOT NULL,
                api_secret_enc TEXT NOT NULL,
                testnet TINYINT DEFAULT 1,
                active TINYINT DEFAULT 1,
                futures_balance DOUBLE,
                created_at INT,
                updated_at INT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bots (
                id INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(255) NOT NULL,
                account_id INT NOT NULL,
                symbol VARCHAR(255) NOT NULL,
                long_enabled TINYINT,
                long_amount DOUBLE,
                long_leverage INT,
                short_enabled TINYINT,
                short_amount DOUBLE,
                short_leverage INT,
                r_points_json TEXT,
                cond_sl_close TINYINT,
                cond_trailing TINYINT,
                cond_close_last TINYINT,
                start_time INT,
                long_entry_price DOUBLE,
                short_entry_price DOUBLE,
                long_status VARCHAR(255),
                short_status VARCHAR(255),
                long_sl_point DOUBLE,
                short_sl_point DOUBLE,
                testnet TINYINT,
                margin_type VARCHAR(255) DEFAULT 'ISOLATED',
                long_final_roi DOUBLE DEFAULT 0.0,
                short_final_roi DOUBLE DEFAULT 0.0
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(255) NOT NULL,
                symbol VARCHAR(255),
                long_enabled TINYINT,
                long_amount DOUBLE,
                long_leverage INT,
                short_enabled TINYINT,
                short_amount DOUBLE,
                short_leverage INT,
                r_points_json TEXT,
                cond_sl_close TINYINT,
                cond_trailing TINYINT,
                cond_close_last TINYINT,
                created_at INT,
                margin_type VARCHAR(255) DEFAULT 'ISOLATED' 
            );
        """)
        # Insert initial version. PyMySQL uses %s as the default placeholder.
        cur.execute("INSERT INTO schema_version (version) VALUES (%s);", (SCHEMA_VERSION,))

    elif current_version < SCHEMA_VERSION:
        # --- Schema Migrations ---
        if current_version < 5:
            # Migration logic from SQLite v1 to v5
            try:
                cur.execute("ALTER TABLE templates ADD COLUMN margin_type VARCHAR(255) DEFAULT 'ISOLATED'")
            except pymysql.err.OperationalError as e:
                # Error 1060: Duplicate column name 'margin_type' is the expected error if the column already exists
                if e.args[0] != 1060:
                    raise
        
        # Update the schema version if it's lower than the target version
        cur.execute("UPDATE schema_version SET version=%s;", (SCHEMA_VERSION,))

    con.commit()
    con.close()
    print('DB init OK (MySQL)')
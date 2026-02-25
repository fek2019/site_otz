import os
import sqlite3
from collections.abc import Mapping

from werkzeug.security import generate_password_hash

try:
    import psycopg
except ImportError:  # pragma: no cover - depends on environment
    psycopg = None

DB_PATH = os.environ.get('SQLITE_DB_PATH', os.path.join(os.path.dirname(__file__), 'database.db'))
ADMIN_EMAIL = 'admin@admin.admin'
ADMIN_PASSWORD = 'admin123admin'


def _database_url():
    return os.environ.get('DATABASE_URL', '').strip()


def _use_postgres():
    db_url = _database_url().lower()
    return db_url.startswith('postgres://') or db_url.startswith('postgresql://')


def _normalized_database_url():
    db_url = _database_url()
    if db_url.startswith('postgres://'):
        return db_url.replace('postgres://', 'postgresql://', 1)
    return db_url


class RowProxy(Mapping):
    def __init__(self, columns, values):
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._mapping = dict(zip(self._columns, self._values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self):
        return iter(self._mapping)

    def __len__(self):
        return len(self._mapping)


class PostgresCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    @staticmethod
    def _adapt_query(query):
        return (
            query.replace("datetime('now')", 'CURRENT_TIMESTAMP')
            .replace('datetime("now")', 'CURRENT_TIMESTAMP')
            .replace('?', '%s')
        )

    def execute(self, query, params=None):
        self._cursor.execute(self._adapt_query(query), params or ())
        return self

    def executemany(self, query, param_sets):
        self._cursor.executemany(self._adapt_query(query), param_sets)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        columns = [column.name for column in self._cursor.description]
        return RowProxy(columns, row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not rows:
            return []
        columns = [column.name for column in self._cursor.description]
        return [RowProxy(columns, row) for row in rows]

    def __getattr__(self, item):
        return getattr(self._cursor, item)


class PostgresConnectionWrapper:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self):
        return PostgresCursorWrapper(self._connection.cursor())

    def execute(self, query, params=None):
        cursor = self.cursor()
        return cursor.execute(query, params)

    def executemany(self, query, param_sets):
        cursor = self.cursor()
        return cursor.executemany(query, param_sets)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def __getattr__(self, item):
        return getattr(self._connection, item)


def get_db():
    if _use_postgres():
        if psycopg is None:
            raise RuntimeError('DATABASE_URL points to PostgreSQL, but psycopg is not installed.')
        conn = psycopg.connect(_normalized_database_url())
        return PostgresConnectionWrapper(conn)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')
    conn.execute('PRAGMA busy_timeout = 5000')
    return conn


def _column_exists(cursor, table, column):
    if _use_postgres():
        exists = cursor.execute(
            '''
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ?
              AND column_name = ?
            ''',
            (table, column),
        ).fetchone()
        return bool(exists)

    rows = cursor.execute(f'PRAGMA table_info({table})').fetchall()
    return any(row[1] == column for row in rows)


def _ensure_column(cursor, table, ddl):
    column = ddl.split()[0]
    if _use_postgres():
        cursor.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {ddl}')
        return
    if not _column_exists(cursor, table, column):
        cursor.execute(f'ALTER TABLE {table} ADD COLUMN {ddl}')


def _create_tables_sqlite(cursor):
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            username       TEXT    NOT NULL,
            email          TEXT    NOT NULL UNIQUE,
            password       TEXT    NOT NULL,
            is_blacklisted INTEGER NOT NULL DEFAULT 0,
            blacklisted_at TEXT,
            created_at     TEXT    DEFAULT (datetime('now'))
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS organizations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            description TEXT,
            contacts    TEXT,
            logo_path   TEXT,
            logo_data   TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS reviews (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          INTEGER NOT NULL,
            organization_id  INTEGER NOT NULL,
            text             TEXT    NOT NULL,
            rating           INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            is_hidden        INTEGER NOT NULL DEFAULT 0,
            admin_reply      TEXT,
            admin_reply_at   TEXT,
            created_at       TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (organization_id) REFERENCES organizations(id),
            UNIQUE (user_id, organization_id)
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS organization_photos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            image_path      TEXT,
            image_data      TEXT,
            created_at      TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (organization_id) REFERENCES organizations(id)
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS admin_credentials (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            email      TEXT NOT NULL UNIQUE,
            password   TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS email_verification_codes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT    NOT NULL UNIQUE,
            username      TEXT    NOT NULL,
            password_hash TEXT    NOT NULL,
            code          TEXT    NOT NULL,
            expires_at    TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
        '''
    )


def _create_tables_postgres(cursor):
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS users (
            id             SERIAL PRIMARY KEY,
            username       TEXT NOT NULL,
            email          TEXT NOT NULL UNIQUE,
            password       TEXT NOT NULL,
            is_blacklisted SMALLINT NOT NULL DEFAULT 0,
            blacklisted_at TIMESTAMP,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS organizations (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            category    TEXT NOT NULL,
            description TEXT,
            contacts    TEXT,
            logo_path   TEXT,
            logo_data   TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS reviews (
            id               SERIAL PRIMARY KEY,
            user_id          INTEGER NOT NULL REFERENCES users(id),
            organization_id  INTEGER NOT NULL REFERENCES organizations(id),
            text             TEXT NOT NULL,
            rating           INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            is_hidden        SMALLINT NOT NULL DEFAULT 0,
            admin_reply      TEXT,
            admin_reply_at   TIMESTAMP,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, organization_id)
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS organization_photos (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id),
            image_path      TEXT,
            image_data      TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS admin_credentials (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            email      TEXT NOT NULL UNIQUE,
            password   TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )

    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS email_verification_codes (
            id            SERIAL PRIMARY KEY,
            email         TEXT NOT NULL UNIQUE,
            username      TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            code          TEXT NOT NULL,
            expires_at    TIMESTAMP NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    if _use_postgres():
        _create_tables_postgres(cursor)
    else:
        _create_tables_sqlite(cursor)

    _ensure_column(cursor, 'organizations', 'contacts TEXT')
    _ensure_column(cursor, 'organizations', 'logo_path TEXT')
    _ensure_column(cursor, 'organizations', 'logo_data TEXT')
    _ensure_column(cursor, 'users', 'is_blacklisted INTEGER NOT NULL DEFAULT 0')
    _ensure_column(cursor, 'users', 'blacklisted_at TEXT')
    _ensure_column(cursor, 'reviews', 'is_hidden INTEGER NOT NULL DEFAULT 0')
    _ensure_column(cursor, 'reviews', 'admin_reply TEXT')
    _ensure_column(cursor, 'reviews', 'admin_reply_at TEXT')
    _ensure_column(cursor, 'organization_photos', 'image_path TEXT')
    _ensure_column(cursor, 'organization_photos', 'image_data TEXT')

    cursor.execute(
        'CREATE INDEX IF NOT EXISTS idx_reviews_org_hidden_created ON reviews (organization_id, is_hidden, created_at DESC)'
    )
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reviews_user ON reviews (user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_org_name_lower ON organizations (LOWER(name))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email))')

    cursor.execute("DELETE FROM email_verification_codes WHERE expires_at <= datetime('now')")

    admin_row = cursor.execute('SELECT id, email FROM admin_credentials WHERE id = 1').fetchone()
    if not admin_row:
        cursor.execute(
            'INSERT INTO admin_credentials (id, email, password) VALUES (1, ?, ?)',
            (ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD)),
        )
    elif str(admin_row['email']).strip().lower() == 'admin@example.com':
        cursor.execute(
            '''
            UPDATE admin_credentials
            SET email = ?, password = ?, updated_at = datetime('now')
            WHERE id = 1
            ''',
            (ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD)),
        )

    org_count_row = cursor.execute('SELECT COUNT(*) AS total FROM organizations').fetchone()
    organizations_total = int(org_count_row['total']) if org_count_row else 0
    if organizations_total == 0:
        sample_orgs = [
            ('Клиника Здоровье', 'Клиники', 'Современная клиника с опытными врачами.', '+7 (900) 111-11-11', None, None),
            ('Стоматология на Ленина', 'Клиники', 'Безболезненное лечение зубов.', '+7 (900) 222-22-22', None, None),
            ('Автосервис Умелец', 'Автосервисы', 'Ремонт любой сложности за 1 день.', '+7 (900) 333-33-33', None, None),
            ('АвтоМастер Плюс', 'Автосервисы', 'Бесплатная диагностика при ремонте.', '+7 (900) 444-44-44', None, None),
            ('Бьюти-студия Мария', 'Салоны красоты', 'Маникюр, педикюр, наращивание.', '+7 (900) 555-55-55', None, None),
            ('Салон Glamour', 'Салоны красоты', 'Окрашивание профессиональными красками.', '+7 (900) 666-66-66', None, None),
            ('Ресторан Уют', 'Рестораны', 'Уютная атмосфера и вкусная кухня.', '+7 (900) 777-77-77', None, None),
            ('Кафе Восток', 'Рестораны', 'Настоящая восточная кухня.', '+7 (900) 888-88-88', None, None),
            ('Супермаркет Близко', 'Магазины', 'Свежие продукты рядом с домом.', '+7 (900) 999-99-99', None, None),
            ('Электроника MaxTech', 'Магазины', 'Широкий выбор техники с гарантией.', '+7 (900) 000-00-00', None, None),
        ]
        cursor.executemany(
            '''
            INSERT INTO organizations (name, category, description, contacts, logo_path, logo_data)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            sample_orgs,
        )

    conn.commit()
    conn.close()

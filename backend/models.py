import os
import sqlite3

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')
ADMIN_EMAIL = 'admin@admin.admin'
ADMIN_PASSWORD = 'admin123admin'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def _column_exists(cursor, table, column):
    rows = cursor.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _ensure_column(cursor, table, ddl):
    column = ddl.split()[0]
    if not _column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db():
    conn = get_db()
    cursor = conn.cursor()

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
            image_data      TEXT    NOT NULL,
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

    # Lightweight migration for already created DBs.
    _ensure_column(cursor, 'organizations', 'contacts TEXT')
    _ensure_column(cursor, 'organizations', 'logo_data TEXT')
    _ensure_column(cursor, 'users', 'is_blacklisted INTEGER NOT NULL DEFAULT 0')
    _ensure_column(cursor, 'users', 'blacklisted_at TEXT')
    _ensure_column(cursor, 'reviews', 'is_hidden INTEGER NOT NULL DEFAULT 0')
    _ensure_column(cursor, 'reviews', 'admin_reply TEXT')
    _ensure_column(cursor, 'reviews', 'admin_reply_at TEXT')

    cursor.execute("DELETE FROM email_verification_codes WHERE expires_at <= datetime('now')")

    admin_row = cursor.execute('SELECT id, email FROM admin_credentials WHERE id = 1').fetchone()
    if not admin_row:
        cursor.execute(
            'INSERT INTO admin_credentials (id, email, password) VALUES (1, ?, ?)',
            (ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD)),
        )
    elif str(admin_row['email']).strip().lower() == 'admin@example.com':
        # One-time migration from old default admin credentials.
        cursor.execute(
            '''
            UPDATE admin_credentials
            SET email = ?, password = ?, updated_at = datetime('now')
            WHERE id = 1
            ''',
            (ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD)),
        )

    cursor.execute('SELECT COUNT(*) FROM organizations')
    if cursor.fetchone()[0] == 0:
        sample_orgs = [
            ('Клиника Здоровье', 'Клиники', 'Современная клиника с опытными врачами.', '+7 (900) 111-11-11', None),
            ('Стоматология на Ленина', 'Клиники', 'Безболезненное лечение зубов.', '+7 (900) 222-22-22', None),
            ('Автосервис Умелец', 'Автосервисы', 'Ремонт любой сложности за 1 день.', '+7 (900) 333-33-33', None),
            ('АвтоМастер Плюс', 'Автосервисы', 'Бесплатная диагностика при ремонте.', '+7 (900) 444-44-44', None),
            ('Бьюти-студия Мария', 'Салоны красоты', 'Маникюр, педикюр, наращивание.', '+7 (900) 555-55-55', None),
            ('Салон Glamour', 'Салоны красоты', 'Окрашивание профессиональными красками.', '+7 (900) 666-66-66', None),
            ('Ресторан Уют', 'Рестораны', 'Уютная атмосфера и вкусная кухня.', '+7 (900) 777-77-77', None),
            ('Кафе Восток', 'Рестораны', 'Настоящая восточная кухня.', '+7 (900) 888-88-88', None),
            ('Супермаркет Близко', 'Магазины', 'Свежие продукты рядом с домом.', '+7 (900) 999-99-99', None),
            ('Электроника MaxTech', 'Магазины', 'Широкий выбор техники с гарантией.', '+7 (900) 000-00-00', None),
        ]
        cursor.executemany(
            '''
            INSERT INTO organizations (name, category, description, contacts, logo_data)
            VALUES (?, ?, ?, ?, ?)
            ''',
            sample_orgs,
        )

    conn.commit()
    conn.close()

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import limiter
from models import get_db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/register', methods=['POST'])
@limiter.limit('10 per minute')
def register():
    data = request.get_json(silent=True) or {}

    username = str(data.get('username', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', '')).strip()

    if not username or not email or not password:
        return jsonify({'error': 'Заполните все поля'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Пароль минимум 6 символов'}), 400

    if '@' not in email or '.' not in email:
        return jsonify({'error': 'Укажите корректный email'}), 400

    conn = get_db()
    try:
        admin = conn.execute(
            'SELECT email FROM admin_credentials WHERE LOWER(email) = LOWER(?)',
            (email,),
        ).fetchone()
        if admin:
            return jsonify({'error': 'Этот email зарезервирован для админ-панели'}), 409

        existing = conn.execute(
            'SELECT id, is_blacklisted FROM users WHERE LOWER(email) = LOWER(?)',
            (email,),
        ).fetchone()
        if existing:
            if existing['is_blacklisted']:
                return jsonify({'error': 'Этот аккаунт заблокирован'}), 403
            return jsonify({'error': 'Email уже зарегистрирован'}), 409

        cursor = conn.execute(
            'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
            (username, email, generate_password_hash(password)),
        )
        conn.commit()

        session.clear()
        session['user_id'] = cursor.lastrowid
        session['username'] = username

        return jsonify(
            {
                'message': 'Регистрация прошла успешно',
                'user_id': cursor.lastrowid,
                'username': username,
                'is_admin': False,
            }
        ), 201

    finally:
        conn.close()


@auth_bp.route('/api/login', methods=['POST'])
@limiter.limit('15 per minute')
def login():
    data = request.get_json(silent=True) or {}

    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', '')).strip()

    if not email or not password:
        return jsonify({'error': 'Заполните все поля'}), 400

    conn = get_db()
    try:
        admin = conn.execute(
            'SELECT email, password FROM admin_credentials WHERE LOWER(email) = LOWER(?)',
            (email,),
        ).fetchone()
        if admin:
            if not check_password_hash(admin['password'], password):
                return jsonify({'error': 'Неверный email или пароль'}), 401

            session.clear()
            session['is_admin'] = True
            session['admin_email'] = admin['email']
            return jsonify({'message': 'Вход выполнен', 'is_admin': True, 'admin_email': admin['email']})

        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if not user or not check_password_hash(user['password'], password):
            return jsonify({'error': 'Неверный email или пароль'}), 401

        if user['is_blacklisted']:
            return jsonify({'error': 'Ваш аккаунт заблокирован администратором'}), 403

        session.clear()
        session['user_id'] = user['id']
        session['username'] = user['username']

        return jsonify(
            {
                'message': 'Вход выполнен',
                'user_id': user['id'],
                'username': user['username'],
                'is_admin': False,
            }
        )

    finally:
        conn.close()


@auth_bp.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Выход выполнен'})


@auth_bp.route('/api/me', methods=['GET'])
def me():
    if session.get('is_admin'):
        return jsonify({'user': None, 'admin': {'email': session.get('admin_email')}})

    if 'user_id' not in session:
        return jsonify({'user': None, 'admin': None})

    conn = get_db()
    try:
        user = conn.execute(
            'SELECT id, username, email, created_at, is_blacklisted FROM users WHERE id = ?',
            (session['user_id'],),
        ).fetchone()

        if not user:
            session.clear()
            return jsonify({'user': None, 'admin': None})

        if user['is_blacklisted']:
            session.clear()
            return jsonify({'user': None, 'admin': None})

        return jsonify({'user': dict(user), 'admin': None})

    finally:
        conn.close()

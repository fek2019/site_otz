from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from models import get_db

profile_bp = Blueprint('profile', __name__)
ADMIN_EMAIL = 'admin@admin.admin'


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Необходима авторизация'}), 401

        conn = get_db()
        try:
            user = conn.execute(
                'SELECT id, is_blacklisted FROM users WHERE id = ?',
                (session['user_id'],),
            ).fetchone()
        finally:
            conn.close()

        if not user:
            session.clear()
            return jsonify({'error': 'Необходима авторизация'}), 401

        if user['is_blacklisted']:
            session.clear()
            return jsonify({'error': 'Аккаунт заблокирован администратором'}), 403

        return fn(*args, **kwargs)

    return wrapper


@profile_bp.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    conn = get_db()
    try:
        user = conn.execute(
            'SELECT id, username, email, created_at FROM users WHERE id = ?',
            (session['user_id'],),
        ).fetchone()

        if not user:
            session.clear()
            return jsonify({'error': 'Необходима авторизация'}), 401

        reviews = conn.execute(
            '''
            SELECT
                r.id,
                r.text,
                r.rating,
                r.is_hidden,
                r.created_at,
                o.name AS organization_name,
                o.id   AS organization_id
            FROM reviews r
            JOIN organizations o ON o.id = r.organization_id
            WHERE r.user_id = ?
            ORDER BY r.created_at DESC
            ''',
            (session['user_id'],),
        ).fetchall()

        result = dict(user)
        result['reviews'] = [dict(rv) for rv in reviews]

        return jsonify(result)

    finally:
        conn.close()


@profile_bp.route('/api/profile/credentials', methods=['PATCH'])
@login_required
def change_profile_credentials():
    data = request.get_json(silent=True) or {}

    current_password = str(data.get('current_password', '')).strip()
    new_email = str(data.get('new_email', '')).strip().lower()
    new_password = str(data.get('new_password', '')).strip()

    if not current_password:
        return jsonify({'error': 'Введите текущий пароль'}), 400

    if not new_email and not new_password:
        return jsonify({'error': 'Укажите новый логин или новый пароль'}), 400

    if new_password and len(new_password) < 6:
        return jsonify({'error': 'Новый пароль минимум 6 символов'}), 400

    conn = get_db()
    try:
        user = conn.execute(
            'SELECT id, email, password FROM users WHERE id = ?',
            (session['user_id'],),
        ).fetchone()

        if not user:
            session.clear()
            return jsonify({'error': 'Необходима авторизация'}), 401

        if not check_password_hash(user['password'], current_password):
            return jsonify({'error': 'Текущий пароль неверный'}), 401

        email_to_save = new_email or user['email']

        if new_email and new_email != user['email']:
            duplicate_user = conn.execute(
                'SELECT id FROM users WHERE email = ? AND id != ?',
                (new_email, user['id']),
            ).fetchone()
            if duplicate_user:
                return jsonify({'error': 'Этот логин уже занят'}), 409

            if new_email == ADMIN_EMAIL:
                return jsonify({'error': 'Этот логин зарезервирован для админ-панели'}), 409

            admin_dup = conn.execute(
                'SELECT id FROM admin_credentials WHERE LOWER(email) = LOWER(?)',
                (new_email,),
            ).fetchone()
            if admin_dup:
                return jsonify({'error': 'Этот логин зарезервирован для админ-панели'}), 409

        password_to_save = generate_password_hash(new_password) if new_password else user['password']

        conn.execute(
            'UPDATE users SET email = ?, password = ? WHERE id = ?',
            (email_to_save, password_to_save, user['id']),
        )
        conn.commit()

        return jsonify({'message': 'Логин и пароль обновлены', 'email': email_to_save})

    finally:
        conn.close()

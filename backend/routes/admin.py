from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from models import get_db

admin_bp = Blueprint('admin', __name__)


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({'error': 'Необходим вход в админ-панель'}), 401
        return fn(*args, **kwargs)

    return wrapper


def _is_valid_data_url(value):
    return bool(value) and value.startswith('data:image/') and ';base64,' in value


@admin_bp.route('/api/admin/me', methods=['GET'])
@admin_required
def admin_me():
    return jsonify({'admin': {'email': session.get('admin_email')}})


@admin_bp.route('/api/admin/overview', methods=['GET'])
@admin_required
def admin_overview():
    conn = get_db()
    try:
        organizations_total = conn.execute('SELECT COUNT(*) FROM organizations').fetchone()[0]
        reviews_total = conn.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]
        visible_reviews = conn.execute('SELECT COUNT(*) FROM reviews WHERE is_hidden = 0').fetchone()[0]
        hidden_reviews = reviews_total - visible_reviews

        avg_by_category = conn.execute(
            '''
            SELECT
                o.category,
                ROUND(AVG(r.rating), 2) AS avg_rating,
                COUNT(r.id)             AS reviews_count
            FROM organizations o
            LEFT JOIN reviews r ON r.organization_id = o.id AND r.is_hidden = 0
            GROUP BY o.category
            ORDER BY o.category
            '''
        ).fetchall()

        reviews_by_day = conn.execute(
            '''
            SELECT
                DATE(created_at) AS day,
                COUNT(*)         AS reviews_count
            FROM reviews
            GROUP BY DATE(created_at)
            ORDER BY day DESC
            LIMIT 30
            '''
        ).fetchall()

        result = {
            'organizations_total': organizations_total,
            'reviews_total': reviews_total,
            'visible_reviews': visible_reviews,
            'hidden_reviews': hidden_reviews,
            'avg_by_category': [dict(row) for row in avg_by_category],
            'reviews_by_day': [dict(row) for row in reversed(reviews_by_day)],
        }
        return jsonify(result)

    finally:
        conn.close()


@admin_bp.route('/api/admin/organizations', methods=['GET'])
@admin_required
def admin_get_organizations():
    conn = get_db()
    try:
        rows = conn.execute(
            '''
            SELECT
                o.id,
                o.name,
                o.category,
                o.description,
                o.contacts,
                o.logo_data,
                o.created_at,
                ROUND(AVG(CASE WHEN r.is_hidden = 0 THEN r.rating END), 1) AS avg_rating,
                COUNT(r.id)                                                AS reviews_total,
                SUM(CASE WHEN r.is_hidden = 1 THEN 1 ELSE 0 END)          AS hidden_reviews
            FROM organizations o
            LEFT JOIN reviews r ON r.organization_id = o.id
            GROUP BY o.id
            ORDER BY o.id DESC
            '''
        ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item['hidden_reviews'] = item['hidden_reviews'] or 0
            item['reviews_total'] = item['reviews_total'] or 0
            result.append(item)

        return jsonify(result)

    finally:
        conn.close()


@admin_bp.route('/api/admin/organization', methods=['POST'])
@admin_required
def admin_create_organization():
    data = request.get_json(silent=True) or {}

    name = str(data.get('name', '')).strip()
    category = str(data.get('category', '')).strip()
    description = str(data.get('description', '')).strip()
    contacts = str(data.get('contacts', '')).strip()
    logo_data = str(data.get('logo_data', '')).strip()

    if not name or not category:
        return jsonify({'error': 'Укажите название и категорию'}), 400

    if len(name) > 120 or len(category) > 80:
        return jsonify({'error': 'Название или категория слишком длинные'}), 400

    if len(description) > 2000 or len(contacts) > 500:
        return jsonify({'error': 'Описание или контакты слишком длинные'}), 400

    if logo_data and not _is_valid_data_url(logo_data):
        return jsonify({'error': 'Логотип должен быть data URL изображения'}), 400

    conn = get_db()
    try:
        existing = conn.execute(
            'SELECT id FROM organizations WHERE LOWER(name) = LOWER(?)',
            (name,),
        ).fetchone()
        if existing:
            return jsonify({'error': 'Организация с таким названием уже существует'}), 409

        cursor = conn.execute(
            '''
            INSERT INTO organizations (name, category, description, contacts, logo_data)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (name, category, description, contacts, logo_data or None),
        )
        conn.commit()

        return jsonify({'message': 'Организация добавлена', 'organization_id': cursor.lastrowid}), 201

    finally:
        conn.close()


@admin_bp.route('/api/admin/organization/<int:org_id>', methods=['PUT'])
@admin_required
def admin_update_organization(org_id):
    data = request.get_json(silent=True) or {}

    name = str(data.get('name', '')).strip()
    category = str(data.get('category', '')).strip()
    description = str(data.get('description', '')).strip()
    contacts = str(data.get('contacts', '')).strip()
    logo_data = str(data.get('logo_data', '')).strip()

    if not name or not category:
        return jsonify({'error': 'Укажите название и категорию'}), 400

    if len(name) > 120 or len(category) > 80:
        return jsonify({'error': 'Название или категория слишком длинные'}), 400

    if len(description) > 2000 or len(contacts) > 500:
        return jsonify({'error': 'Описание или контакты слишком длинные'}), 400

    if logo_data and not _is_valid_data_url(logo_data):
        return jsonify({'error': 'Логотип должен быть data URL изображения'}), 400

    conn = get_db()
    try:
        org = conn.execute('SELECT id FROM organizations WHERE id = ?', (org_id,)).fetchone()
        if not org:
            return jsonify({'error': 'Организация не найдена'}), 404

        duplicate = conn.execute(
            'SELECT id FROM organizations WHERE LOWER(name) = LOWER(?) AND id != ?',
            (name, org_id),
        ).fetchone()
        if duplicate:
            return jsonify({'error': 'Другая организация уже имеет это название'}), 409

        conn.execute(
            '''
            UPDATE organizations
            SET name = ?, category = ?, description = ?, contacts = ?, logo_data = ?
            WHERE id = ?
            ''',
            (name, category, description, contacts, logo_data or None, org_id),
        )
        conn.commit()

        return jsonify({'message': 'Организация обновлена'})

    finally:
        conn.close()


@admin_bp.route('/api/admin/organization/<int:org_id>', methods=['DELETE'])
@admin_required
def admin_delete_organization(org_id):
    conn = get_db()
    try:
        org = conn.execute('SELECT id FROM organizations WHERE id = ?', (org_id,)).fetchone()
        if not org:
            return jsonify({'error': 'Организация не найдена'}), 404

        conn.execute('DELETE FROM organization_photos WHERE organization_id = ?', (org_id,))
        conn.execute('DELETE FROM reviews WHERE organization_id = ?', (org_id,))
        conn.execute('DELETE FROM organizations WHERE id = ?', (org_id,))
        conn.commit()

        return jsonify({'message': 'Организация удалена'})

    finally:
        conn.close()


@admin_bp.route('/api/admin/reviews', methods=['GET'])
@admin_required
def admin_get_reviews():
    org_id = request.args.get('organization_id', '').strip()

    conn = get_db()
    try:
        query = '''
            SELECT
                r.id,
                r.text,
                r.rating,
                r.is_hidden,
                r.admin_reply,
                r.admin_reply_at,
                r.created_at,
                u.id   AS user_id,
                u.username AS user_name,
                o.id   AS organization_id,
                o.name AS organization_name,
                o.category AS organization_category
            FROM reviews r
            JOIN users u ON u.id = r.user_id
            JOIN organizations o ON o.id = r.organization_id
        '''
        params = []

        if org_id:
            query += ' WHERE o.id = ? '
            params.append(org_id)

        query += ' ORDER BY r.created_at DESC, r.id DESC '

        rows = conn.execute(query, params).fetchall()
        return jsonify([dict(row) for row in rows])

    finally:
        conn.close()


@admin_bp.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    conn = get_db()
    try:
        rows = conn.execute(
            '''
            SELECT
                u.id,
                u.username,
                u.email,
                u.is_blacklisted,
                u.blacklisted_at,
                u.created_at,
                COUNT(r.id) AS reviews_count
            FROM users u
            LEFT JOIN reviews r ON r.user_id = u.id
            GROUP BY u.id
            ORDER BY u.created_at DESC, u.id DESC
            '''
        ).fetchall()

        return jsonify([dict(row) for row in rows])

    finally:
        conn.close()


@admin_bp.route('/api/admin/user/<int:user_id>/blacklist', methods=['PATCH'])
@admin_required
def admin_toggle_user_blacklist(user_id):
    data = request.get_json(silent=True) or {}
    blacklisted = bool(data.get('blacklisted'))

    conn = get_db()
    try:
        user = conn.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            return jsonify({'error': 'Пользователь не найден'}), 404

        conn.execute(
            '''
            UPDATE users
            SET is_blacklisted = ?,
                blacklisted_at = CASE WHEN ? = 1 THEN datetime('now') ELSE NULL END
            WHERE id = ?
            ''',
            (1 if blacklisted else 0, 1 if blacklisted else 0, user_id),
        )
        conn.commit()

        return jsonify({'message': 'Статус пользователя обновлён'})

    finally:
        conn.close()


@admin_bp.route('/api/admin/user/<int:user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    conn = get_db()
    try:
        user = conn.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            return jsonify({'error': 'Пользователь не найден'}), 404

        conn.execute('DELETE FROM reviews WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()

        return jsonify({'message': 'Пользователь удалён'})

    finally:
        conn.close()


@admin_bp.route('/api/admin/review/<int:review_id>/visibility', methods=['PATCH'])
@admin_required
def admin_set_review_visibility(review_id):
    data = request.get_json(silent=True) or {}
    hidden = bool(data.get('hidden', False))

    conn = get_db()
    try:
        review = conn.execute('SELECT id FROM reviews WHERE id = ?', (review_id,)).fetchone()
        if not review:
            return jsonify({'error': 'Отзыв не найден'}), 404

        conn.execute('UPDATE reviews SET is_hidden = ? WHERE id = ?', (1 if hidden else 0, review_id))
        conn.commit()

        return jsonify({'message': 'Статус отзыва обновлён'})

    finally:
        conn.close()


@admin_bp.route('/api/admin/review/<int:review_id>/reply', methods=['PATCH'])
@admin_required
def admin_reply_review(review_id):
    data = request.get_json(silent=True) or {}
    reply_text = str(data.get('reply_text', '')).strip()

    if len(reply_text) > 2000:
        return jsonify({'error': 'Ответ слишком длинный'}), 400

    conn = get_db()
    try:
        review = conn.execute('SELECT id FROM reviews WHERE id = ?', (review_id,)).fetchone()
        if not review:
            return jsonify({'error': 'Отзыв не найден'}), 404

        conn.execute(
            '''
            UPDATE reviews
            SET admin_reply = ?, admin_reply_at = CASE WHEN ? = '' THEN NULL ELSE datetime('now') END
            WHERE id = ?
            ''',
            (reply_text, reply_text, review_id),
        )
        conn.commit()

        return jsonify({'message': 'Ответ сохранён'})

    finally:
        conn.close()


@admin_bp.route('/api/admin/review/<int:review_id>', methods=['DELETE'])
@admin_required
def admin_delete_review(review_id):
    conn = get_db()
    try:
        review = conn.execute('SELECT id FROM reviews WHERE id = ?', (review_id,)).fetchone()
        if not review:
            return jsonify({'error': 'Отзыв не найден'}), 404

        conn.execute('DELETE FROM reviews WHERE id = ?', (review_id,))
        conn.commit()

        return jsonify({'message': 'Отзыв удалён'})

    finally:
        conn.close()


@admin_bp.route('/api/admin/credentials', methods=['PATCH'])
@admin_required
def admin_change_credentials():
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
        admin = conn.execute('SELECT * FROM admin_credentials WHERE id = 1').fetchone()
        if not admin:
            return jsonify({'error': 'Админ-аккаунт не найден'}), 404

        if not check_password_hash(admin['password'], current_password):
            return jsonify({'error': 'Текущий пароль неверный'}), 401

        email_to_save = new_email or admin['email']
        password_to_save = generate_password_hash(new_password) if new_password else admin['password']

        if new_email and new_email.lower() != admin['email'].lower():
            duplicate_user = conn.execute(
                'SELECT id FROM users WHERE LOWER(email) = LOWER(?)',
                (new_email,),
            ).fetchone()
            if duplicate_user:
                return jsonify({'error': 'Этот логин уже используется пользователем'}), 409

        conn.execute(
            '''
            UPDATE admin_credentials
            SET email = ?, password = ?, updated_at = datetime('now')
            WHERE id = 1
            ''',
            (email_to_save, password_to_save),
        )
        conn.commit()

        session['admin_email'] = email_to_save
        return jsonify({'message': 'Данные админа обновлены', 'email': email_to_save})

    finally:
        conn.close()

from functools import wraps

from flask import Blueprint, jsonify, request, session

from models import get_db

reviews_bp = Blueprint('reviews', __name__)


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


@reviews_bp.route('/api/review', methods=['POST'])
@login_required
def add_review():
    data = request.get_json(silent=True) or {}

    org_id = data.get('organization_id')
    text = str(data.get('text', '')).strip()
    rating = data.get('rating')

    if not org_id or not text or rating is None:
        return jsonify({'error': 'Заполните все поля'}), 400

    if not isinstance(rating, int) or not (1 <= rating <= 5):
        return jsonify({'error': 'Оценка должна быть от 1 до 5'}), 400

    conn = get_db()
    try:
        org = conn.execute('SELECT id FROM organizations WHERE id = ?', (org_id,)).fetchone()
        if not org:
            return jsonify({'error': 'Организация не найдена'}), 404

        existing = conn.execute(
            'SELECT id FROM reviews WHERE user_id = ? AND organization_id = ?',
            (session['user_id'], org_id),
        ).fetchone()
        if existing:
            return jsonify({'error': 'Вы уже оставили отзыв об этой организации'}), 409

        cursor = conn.execute(
            '''
            INSERT INTO reviews (user_id, organization_id, text, rating)
            VALUES (?, ?, ?, ?)
            ''',
            (session['user_id'], org_id, text, rating),
        )
        conn.commit()

        return jsonify({'message': 'Отзыв добавлен', 'review_id': cursor.lastrowid}), 201

    finally:
        conn.close()


@reviews_bp.route('/api/review/<int:review_id>', methods=['DELETE'])
@login_required
def delete_review(review_id):
    conn = get_db()
    try:
        review = conn.execute('SELECT * FROM reviews WHERE id = ?', (review_id,)).fetchone()
        if not review:
            return jsonify({'error': 'Отзыв не найден'}), 404

        if review['user_id'] != session['user_id']:
            return jsonify({'error': 'Нет доступа'}), 403

        conn.execute('DELETE FROM reviews WHERE id = ?', (review_id,))
        conn.commit()

        return jsonify({'message': 'Отзыв удалён'})

    finally:
        conn.close()

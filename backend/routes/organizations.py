from flask import Blueprint, jsonify, request

from models import get_db

organizations_bp = Blueprint('organizations', __name__)


def _is_valid_data_url(value):
    return bool(value) and value.startswith('data:image/') and ';base64,' in value


@organizations_bp.route('/api/organizations', methods=['GET'])
def get_organizations():
    conn = get_db()
    try:
        orgs = conn.execute(
            '''
            SELECT
                o.id,
                o.name,
                o.category,
                o.description,
                o.contacts,
                o.logo_data,
                o.created_at,
                ROUND(AVG(r.rating), 1) AS avg_rating,
                COUNT(r.id)             AS reviews_count
            FROM organizations o
            LEFT JOIN reviews r ON r.organization_id = o.id AND r.is_hidden = 0
            GROUP BY o.id
            ORDER BY o.id
            '''
        ).fetchall()

        return jsonify([dict(org) for org in orgs])

    finally:
        conn.close()


@organizations_bp.route('/api/organization', methods=['POST'])
def create_organization():
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

        return jsonify(
            {
                'message': 'Организация добавлена',
                'organization': {
                    'id': cursor.lastrowid,
                    'name': name,
                    'category': category,
                    'description': description,
                    'contacts': contacts,
                    'logo_data': logo_data or None,
                },
            }
        ), 201

    finally:
        conn.close()


@organizations_bp.route('/api/organization/<int:org_id>', methods=['GET'])
def get_organization(org_id):
    conn = get_db()
    try:
        org = conn.execute(
            '''
            SELECT
                o.id,
                o.name,
                o.category,
                o.description,
                o.contacts,
                o.logo_data,
                o.created_at,
                ROUND(AVG(r.rating), 1) AS avg_rating,
                COUNT(r.id)             AS reviews_count
            FROM organizations o
            LEFT JOIN reviews r ON r.organization_id = o.id AND r.is_hidden = 0
            WHERE o.id = ?
            GROUP BY o.id
            ''',
            (org_id,),
        ).fetchone()

        if not org:
            return jsonify({'error': 'Организация не найдена'}), 404

        reviews = conn.execute(
            '''
            SELECT
                r.id,
                r.text,
                r.rating,
                r.created_at,
                r.admin_reply,
                r.admin_reply_at,
                u.username AS author,
                u.id       AS user_id
            FROM reviews r
            JOIN users u ON u.id = r.user_id
            WHERE r.organization_id = ? AND r.is_hidden = 0
            ORDER BY r.created_at DESC
            ''',
            (org_id,),
        ).fetchall()

        photos = conn.execute(
            '''
            SELECT id, image_data, created_at
            FROM organization_photos
            WHERE organization_id = ?
            ORDER BY created_at DESC, id DESC
            ''',
            (org_id,),
        ).fetchall()

        result = dict(org)
        result['reviews'] = [dict(rv) for rv in reviews]
        result['photos'] = [dict(ph) for ph in photos]

        return jsonify(result)

    finally:
        conn.close()


@organizations_bp.route('/api/organization/<int:org_id>/photo', methods=['POST'])
def upload_organization_photo(org_id):
    data = request.get_json(silent=True) or {}
    image_data = str(data.get('image_data', '')).strip()

    if not _is_valid_data_url(image_data):
        return jsonify({'error': 'Передайте фото в формате data URL'}), 400

    if len(image_data) > 3_000_000:
        return jsonify({'error': 'Фото слишком большое. Максимум около 2 МБ'}), 413

    conn = get_db()
    try:
        org = conn.execute('SELECT id FROM organizations WHERE id = ?', (org_id,)).fetchone()
        if not org:
            return jsonify({'error': 'Организация не найдена'}), 404

        cursor = conn.execute(
            'INSERT INTO organization_photos (organization_id, image_data) VALUES (?, ?)',
            (org_id, image_data),
        )
        conn.commit()

        return jsonify({'message': 'Фото добавлено', 'photo_id': cursor.lastrowid}), 201

    finally:
        conn.close()

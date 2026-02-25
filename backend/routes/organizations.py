from functools import wraps

from flask import Blueprint, jsonify, request, session

from media_storage import is_data_url_image, is_media_url, save_binary_image, save_data_url_image
from models import get_db
from pagination import build_pagination_payload, parse_limit_offset

organizations_bp = Blueprint('organizations', __name__)


def _prepare_logo_url(value):
    raw = str(value or '').strip()
    if not raw:
        return None

    if is_media_url(raw):
        return raw

    if not is_data_url_image(raw):
        raise ValueError('invalid_data_url')

    return save_data_url_image(raw, folder='logos')


def registered_user_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Только зарегистрированные пользователи могут добавлять организации'}), 401

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


@organizations_bp.route('/api/organizations', methods=['GET'])
def get_organizations():
    limit, offset = parse_limit_offset(default_limit=20, max_limit=100)

    conn = get_db()
    try:
        total_row = conn.execute('SELECT COUNT(*) AS total FROM organizations').fetchone()
        total = int(total_row['total']) if total_row else 0

        orgs = conn.execute(
            '''
            SELECT
                o.id,
                o.name,
                o.category,
                o.description,
                o.contacts,
                COALESCE(o.logo_path, o.logo_data) AS logo_data,
                o.created_at,
                ROUND(AVG(r.rating), 1) AS avg_rating,
                COUNT(r.id)             AS reviews_count
            FROM organizations o
            LEFT JOIN reviews r ON r.organization_id = o.id AND r.is_hidden = 0
            GROUP BY o.id
            ORDER BY o.id
            LIMIT ? OFFSET ?
            ''',
            (limit, offset),
        ).fetchall()

        return jsonify(
            {
                'items': [dict(org) for org in orgs],
                'pagination': build_pagination_payload(total, limit, offset),
            }
        )

    finally:
        conn.close()


@organizations_bp.route('/api/organization', methods=['POST'])
@registered_user_required
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

    try:
        logo_url = _prepare_logo_url(logo_data)
    except ValueError as exc:
        if str(exc) == 'file_too_large':
            return jsonify({'error': 'Логотип слишком большой. Максимум 2 МБ'}), 413
        return jsonify({'error': 'Логотип должен быть data URL изображения'}), 400

    conn = get_db()
    try:
        existing = conn.execute(
            'SELECT id FROM organizations WHERE LOWER(name) = LOWER(?)',
            (name,),
        ).fetchone()
        if existing:
            return jsonify({'error': 'Организация с таким названием уже существует'}), 409

        conn.execute(
            '''
            INSERT INTO organizations (name, category, description, contacts, logo_path, logo_data)
            VALUES (?, ?, ?, ?, ?, NULL)
            ''',
            (name, category, description, contacts, logo_url),
        )

        created = conn.execute(
            'SELECT id FROM organizations WHERE LOWER(name) = LOWER(?) ORDER BY id DESC LIMIT 1',
            (name,),
        ).fetchone()
        conn.commit()

        return jsonify(
            {
                'message': 'Организация добавлена',
                'organization': {
                    'id': created['id'] if created else None,
                    'name': name,
                    'category': category,
                    'description': description,
                    'contacts': contacts,
                    'logo_data': logo_url,
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
                COALESCE(o.logo_path, o.logo_data) AS logo_data,
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
            SELECT id, COALESCE(image_path, image_data) AS image_data, created_at
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
    upload = request.files.get('photo')
    if upload:
        if not str(upload.mimetype or '').startswith('image/'):
            return jsonify({'error': 'Можно загружать только изображения'}), 400
        try:
            image_url = save_binary_image(upload.read(), upload.mimetype, folder='photos')
        except ValueError as exc:
            if str(exc) == 'file_too_large':
                return jsonify({'error': 'Фото слишком большое. Максимум 2 МБ'}), 413
            return jsonify({'error': 'Не удалось обработать фото'}), 400
    else:
        data = request.get_json(silent=True) or {}
        image_data = str(data.get('image_data', '')).strip()
        if not is_data_url_image(image_data):
            return jsonify({'error': 'Передайте фото файлом или в формате data URL'}), 400
        try:
            image_url = save_data_url_image(image_data, folder='photos')
        except ValueError as exc:
            if str(exc) == 'file_too_large':
                return jsonify({'error': 'Фото слишком большое. Максимум 2 МБ'}), 413
            return jsonify({'error': 'Не удалось обработать фото'}), 400

    conn = get_db()
    try:
        org = conn.execute('SELECT id FROM organizations WHERE id = ?', (org_id,)).fetchone()
        if not org:
            return jsonify({'error': 'Организация не найдена'}), 404

        conn.execute(
            'INSERT INTO organization_photos (organization_id, image_path, image_data) VALUES (?, ?, ?)',
            (org_id, image_url, image_url),
        )
        created = conn.execute(
            'SELECT id FROM organization_photos WHERE organization_id = ? ORDER BY id DESC LIMIT 1',
            (org_id,),
        ).fetchone()
        conn.commit()

        return jsonify({'message': 'Фото добавлено', 'photo_id': created['id'] if created else None, 'image_data': image_url}), 201

    finally:
        conn.close()

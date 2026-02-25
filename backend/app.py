import os

from flask import Flask, redirect, send_from_directory, session
from flask_cors import CORS

from extensions import limiter
from media_storage import ensure_media_directories, get_media_root
from models import init_db
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.organizations import organizations_bp
from routes.profile import profile_bp
from routes.reviews import reviews_bp


def _resolve_frontend_dir():
    backend_dir = os.path.dirname(__file__)
    frontend_dir = os.path.join(backend_dir, '..', 'frontend')
    if os.path.isdir(frontend_dir):
        return frontend_dir
    return os.path.join(backend_dir, '..')


def _parse_origins():
    origins = os.environ.get('CORS_ORIGINS', 'http://localhost:5000,http://127.0.0.1:5000')
    return [origin.strip() for origin in origins.split(',') if origin.strip()]


def _is_secure_cookie_enabled():
    explicit = os.environ.get('SESSION_COOKIE_SECURE', '').strip().lower()
    if explicit in {'1', 'true', 'yes'}:
        return True
    if explicit in {'0', 'false', 'no'}:
        return False
    return os.environ.get('APP_ENV', 'development').lower() == 'production'


def create_app():
    app = Flask(
        __name__,
        static_folder=_resolve_frontend_dir(),
        static_url_path='',
    )

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '').strip()
    if not app.config['SECRET_KEY']:
        if os.environ.get('APP_ENV', 'development').lower() == 'production':
            raise RuntimeError('SECRET_KEY is required in production.')
        app.config['SECRET_KEY'] = os.urandom(32).hex()

    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    app.config['SESSION_COOKIE_SECURE'] = _is_secure_cookie_enabled()
    app.config['RATELIMIT_STORAGE_URI'] = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')

    CORS(app, supports_credentials=True, origins=_parse_origins())
    limiter.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(organizations_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(admin_bp)

    ensure_media_directories()
    init_db()

    def _serve_frontend(filename):
        response = send_from_directory(app.static_folder, filename)
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    @app.route('/media/<path:filename>')
    def media_file(filename):
        return send_from_directory(get_media_root(), filename)

    @app.route('/')
    def index_page():
        return _serve_frontend('index.html')

    @app.route('/profile')
    def profile_page():
        if 'user_id' not in session:
            return redirect('/login')
        return _serve_frontend('profile.html')

    @app.route('/login')
    def login_page():
        if session.get('is_admin'):
            return redirect('/admin')
        if 'user_id' in session:
            return redirect('/profile')
        return _serve_frontend('login.html')

    @app.route('/organization/<int:org_id>')
    def organization_page(org_id):
        return _serve_frontend('organization.html')

    @app.route('/admin')
    def admin_page():
        if not session.get('is_admin'):
            return redirect('/login')
        return _serve_frontend('admin.html')

    return app


app = create_app()


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_DEBUG', '').strip() == '1',
    )

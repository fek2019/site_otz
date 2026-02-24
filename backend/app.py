import os

from flask import Flask, redirect, send_from_directory, session
from flask_cors import CORS

from models import init_db
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.organizations import organizations_bp
from routes.profile import profile_bp
from routes.reviews import reviews_bp

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), '..', 'frontend'),
    static_url_path='',
)

app.secret_key = 'change-this-secret-key-in-production'
CORS(app, supports_credentials=True, origins=['http://localhost:5000', 'http://127.0.0.1:5000'])

app.register_blueprint(auth_bp)
app.register_blueprint(organizations_bp)
app.register_blueprint(reviews_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(admin_bp)


def _serve_frontend(filename):
    response = send_from_directory(app.static_folder, filename)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


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


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)

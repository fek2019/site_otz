# Народный рейтинг (Flask + HTML/CSS/JS)

Веб-приложение каталога организаций с отзывами, модерацией и админ-панелью.

## Что реализовано

- Пользователи:
  - регистрация, вход, выход (`/api/register`, `/api/login`, `/api/logout`)
  - сессии через Flask session (cookie)
  - профиль и смена логина/пароля
- Организации:
  - список организаций с рейтингом
  - создание организации только авторизованным зарегистрированным пользователем
  - карточка организации с отзывами и фотографиями
- Фото:
  - хранение файлов на сервере (не base64 в БД)
  - загрузка через `multipart/form-data` (`photo`) и обратная совместимость с `image_data` (data URL)
  - просмотр фото по клику в интерфейсе
- Отзывы:
  - только для авторизованных
  - один пользователь -> один отзыв на организацию
  - удаление своего отзыва
- Админ-панель:
  - управление организациями, отзывами, пользователями
  - черный список пользователей
  - статистика по категориям и дням
- Production-hardening:
  - `SECRET_KEY` из env
  - поддержка PostgreSQL через `DATABASE_URL` (SQLite остается fallback)
  - rate limiting на логин/регистрацию и админ API
  - пагинация для тяжелых списков API

## Структура проекта

```text
site_otz/
  backend/
    app.py
    wsgi.py
    models.py
    media_storage.py
    pagination.py
    extensions.py
    database.db
    media/
      logos/
      photos/
    routes/
      auth.py
      organizations.py
      reviews.py
      profile.py
      admin.py
  index.html
  login.html
  profile.html
  organization.html
  admin.html
  requirements.txt
  README.md
```

## Установка и запуск (dev)

1. Перейдите в проект:

```powershell
cd "C:\Users\user\OneDrive\Рабочий стол\сайт\site_otz"
```

2. Создайте и активируйте виртуальное окружение:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Установите зависимости:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4. Запуск:

```powershell
python backend\app.py
```

Откройте:
- `http://127.0.0.1:5000/`
- `http://127.0.0.1:5000/login`
- `http://127.0.0.1:5000/profile`
- `http://127.0.0.1:5000/admin`

## Запуск в production

Пример (Linux server):

```bash
export APP_ENV=production
export SECRET_KEY='your-strong-secret'
export DATABASE_URL='postgresql://user:pass@host:5432/dbname'
gunicorn -w 4 -b 0.0.0.0:5000 backend.wsgi:app
```

## Основные переменные окружения

- `APP_ENV`: `development` или `production`
- `SECRET_KEY`: обязательна в production
- `DATABASE_URL`: PostgreSQL DSN; если не задана, используется SQLite
- `SQLITE_DB_PATH`: путь к sqlite-файлу (по умолчанию `backend/database.db`)
- `CORS_ORIGINS`: список origin через запятую
- `PORT`: порт приложения
- `FLASK_DEBUG`: `1` для debug-режима
- `SESSION_COOKIE_SECURE`: `true/false`
- `SESSION_COOKIE_SAMESITE`: `Lax`/`Strict`/`None`
- `MEDIA_ROOT`: директория хранения фото/логотипов
- `RATELIMIT_STORAGE_URI`: backend для лимитера (по умолчанию `memory://`)

## Дефолтный админ

После инициализации БД создается учетка:

- Логин: `admin@admin.admin`
- Пароль: `admin123admin`

Рекомендуется сразу сменить в админ-панели.

## API (кратко)

Публичные и пользовательские:
- `POST /api/register`
- `POST /api/login`
- `POST /api/logout`
- `GET /api/me`
- `GET /api/organizations?limit=20&offset=0`
- `POST /api/organization` (только зарегистрированный пользователь)
- `GET /api/organization/<id>`
- `POST /api/organization/<id>/photo` (`multipart/form-data` с полем `photo`)
- `POST /api/review`
- `DELETE /api/review/<id>`
- `GET /api/profile`
- `PATCH /api/profile/credentials`

Админские:
- `GET /api/admin/me`
- `GET /api/admin/overview`
- `GET /api/admin/organizations?limit=20&offset=0`
- `POST /api/admin/organization`
- `PUT /api/admin/organization/<id>`
- `DELETE /api/admin/organization/<id>`
- `GET /api/admin/reviews?limit=20&offset=0&organization_id=<id>`
- `PATCH /api/admin/review/<id>/visibility`
- `PATCH /api/admin/review/<id>/reply`
- `DELETE /api/admin/review/<id>`
- `GET /api/admin/users?limit=20&offset=0`
- `PATCH /api/admin/user/<id>/blacklist`
- `DELETE /api/admin/user/<id>`
- `PATCH /api/admin/credentials`

### Формат пагинированных ответов

Для списков возвращается объект:

```json
{
  "items": [...],
  "pagination": {
    "total": 123,
    "limit": 20,
    "offset": 0,
    "has_more": true
  }
}
```

## Хранение данных

- Основные данные: БД (`users`, `organizations`, `reviews`, `admin_credentials`, и т.д.)
- Фото/логотипы: файловое хранилище в `backend/media` (или `MEDIA_ROOT`)
- URL файлов: `/media/...`

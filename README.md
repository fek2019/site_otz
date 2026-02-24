# Народный рейтинг (Flask + HTML/CSS/JS)

Демо-проект каталога организаций с отзывами.
Фронтенд на чистом HTML/CSS/JS, бэкенд на Flask + SQLite.

## Что реализовано

- Пользователи:
  - регистрация, вход, выход (`/api/register`, `/api/login`, `/api/logout`)
  - сессии через Flask session
  - личный кабинет `/profile`
  - смена логина и пароля в личном кабинете
- Организации:
  - список организаций на главной (`GET /api/organizations`)
  - создание организации (доступно всем)
  - страница организации `/organization/<id>`
  - загрузка фото организации
- Отзывы:
  - добавление только для авторизованных пользователей
  - правило "один пользователь -> один отзыв на организацию"
  - удаление своего отзыва
  - ответы от организации (через админ-панель)
- Админ-панель `/admin`:
  - вход через обычную форму логина
  - управление организациями (добавить/изменить/удалить)
  - модерация отзывов (скрыть/показать/удалить, ответить)
  - управление пользователями (удаление, черный список)
  - статистика (кол-во организаций, отзывов, рейтинг по категориям, активность по дням)

## Структура проекта

```text
/backend
  app.py
  models.py
  database.db
  /routes
    auth.py
    organizations.py
    profile.py
    reviews.py
    admin.py
/frontend
  index.html
  login.html
  profile.html
  organization.html
  admin.html
requirements.txt
README.md
```

## Установка и запуск

1. Откройте проект:

```powershell
cd "C:\Users\user\OneDrive\Рабочий стол\трай\кворк\отз"
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

4. Запустите сервер:

```powershell
python backend\app.py
```

5. Откройте в браузере:

- Главная: `http://127.0.0.1:5000/`
- Вход/регистрация: `http://127.0.0.1:5000/login`
- Личный кабинет: `http://127.0.0.1:5000/profile`
- Админ-панель: `http://127.0.0.1:5000/admin`
- Пример организации: `http://127.0.0.1:5000/organization/1`

## Дефолтный админ

После первого запуска создается админ-аккаунт:

- Логин: `admin@admin.admin`
- Пароль: `admin123admin`

Если вы уже поменяли логин/пароль в админке, используйте обновленные данные.

## Основные API

Публичные и пользовательские:

- `POST /api/register` — регистрация
- `POST /api/login` — вход
- `POST /api/logout` — выход
- `GET /api/me` — текущая сессия
- `GET /api/organizations` — список организаций
- `POST /api/organization` — создать организацию
- `GET /api/organization/<id>` — карточка организации + отзывы + фото
- `POST /api/organization/<id>/photo` — загрузить фото
- `POST /api/review` — добавить отзыв
- `DELETE /api/review/<id>` — удалить свой отзыв
- `GET /api/profile` — профиль + отзывы пользователя
- `PATCH /api/profile/credentials` — смена логина/пароля пользователя

Админские:

- `GET /api/admin/me`
- `GET /api/admin/overview`
- `GET /api/admin/organizations`
- `POST /api/admin/organization`
- `PUT /api/admin/organization/<id>`
- `DELETE /api/admin/organization/<id>`
- `GET /api/admin/reviews`
- `PATCH /api/admin/review/<id>/visibility`
- `PATCH /api/admin/review/<id>/reply`
- `DELETE /api/admin/review/<id>`
- `GET /api/admin/users`
- `PATCH /api/admin/user/<id>/blacklist`
- `DELETE /api/admin/user/<id>`
- `PATCH /api/admin/credentials`

## База данных

SQLite файл: `backend/database.db`.

Таблицы создаются/обновляются автоматически через `init_db()` при запуске `backend/app.py`.

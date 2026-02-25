import base64
import binascii
import os
import re
import uuid
from pathlib import Path

DATA_URL_RE = re.compile(r'^data:(image/[a-zA-Z0-9.+-]+);base64,([A-Za-z0-9+/=\n\r]+)$')
MIME_TO_EXT = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/gif': 'gif',
}
DEFAULT_MAX_IMAGE_BYTES = 2 * 1024 * 1024


def get_media_root():
    configured = os.environ.get('MEDIA_ROOT', '').strip()
    if configured:
        return Path(configured).resolve()
    return (Path(__file__).resolve().parent / 'media').resolve()


def ensure_media_directories():
    root = get_media_root()
    (root / 'logos').mkdir(parents=True, exist_ok=True)
    (root / 'photos').mkdir(parents=True, exist_ok=True)


def is_data_url_image(value):
    return bool(value) and bool(DATA_URL_RE.match(value))


def is_media_url(value):
    return bool(value) and str(value).startswith('/media/')


def _save_binary(binary, mime_type, folder, max_bytes):
    extension = MIME_TO_EXT.get((mime_type or '').lower())
    if not extension:
        raise ValueError('unsupported_image_type')

    if len(binary) > max_bytes:
        raise ValueError('file_too_large')

    ensure_media_directories()
    filename = f'{uuid.uuid4().hex}.{extension}'
    relative_path = f'{folder}/{filename}'
    file_path = get_media_root() / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(binary)
    return f'/media/{relative_path}'


def save_binary_image(binary, mime_type, folder, max_bytes=DEFAULT_MAX_IMAGE_BYTES):
    return _save_binary(binary, mime_type, folder, max_bytes)


def save_data_url_image(data_url, folder, max_bytes=DEFAULT_MAX_IMAGE_BYTES):
    match = DATA_URL_RE.match(data_url or '')
    if not match:
        raise ValueError('invalid_data_url')

    mime_type = match.group(1).lower()
    payload = match.group(2).replace('\n', '').replace('\r', '')
    extension = MIME_TO_EXT.get(mime_type)
    if not extension:
        raise ValueError('unsupported_image_type')

    try:
        binary = base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('invalid_base64') from exc

    return _save_binary(binary, mime_type, folder, max_bytes)


def delete_media_url(media_url):
    if not is_media_url(media_url):
        return

    relative = media_url[len('/media/') :]
    root = get_media_root()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return

    if candidate.is_file():
        candidate.unlink(missing_ok=True)

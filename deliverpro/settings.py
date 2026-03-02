"""
DeliverPro — Django Settings
"""
from pathlib import Path
from decouple import config
from datetime import timedelta
from urllib.parse import parse_qs, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def get_env_bool(var_name, default=False):
    raw_value = config(var_name, default=str(default))
    value = str(raw_value).strip().lower()
    if value in {'1', 'true', 'yes', 'on', 'y', 't'}:
        return True
    if value in {'0', 'false', 'no', 'off', 'n', 'f', 'release', 'prod', 'production'}:
        return False
    return bool(default)


def get_env_list(var_name, default=''):
    raw_value = config(var_name, default=default)
    return [item.strip() for item in str(raw_value).split(',') if item.strip()]


SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me-in-production')
DEBUG = get_env_bool('DEBUG', default=True)
ALLOWED_HOSTS = get_env_list('ALLOWED_HOSTS', default='localhost,127.0.0.1,.onrender.com')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'channels',
    # Local
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'deliverpro.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'deliverpro.wsgi.application'
ASGI_APPLICATION = 'deliverpro.asgi.application'

DATABASE_URL = config('DATABASE_URL', default='').strip()

if DATABASE_URL:
    parsed_database_url = urlparse(DATABASE_URL)
    query_params = parse_qs(parsed_database_url.query)

    db_options = {}
    if 'sslmode' in query_params:
        db_options['sslmode'] = query_params['sslmode'][0]
    if 'channel_binding' in query_params:
        db_options['channel_binding'] = query_params['channel_binding'][0]

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': parsed_database_url.path.lstrip('/') or config('DB_NAME', default='deliverpro'),
            'USER': (
                unquote(parsed_database_url.username)
                if parsed_database_url.username
                else config('DB_USER', default='deliverpro_user')
            ),
            'PASSWORD': (
                unquote(parsed_database_url.password)
                if parsed_database_url.password
                else config('DB_PASSWORD', default='password')
            ),
            'HOST': parsed_database_url.hostname or config('DB_HOST', default='localhost'),
            'PORT': str(parsed_database_url.port) if parsed_database_url.port else config('DB_PORT', default='5432'),
        }
    }
    if db_options:
        DATABASES['default']['OPTIONS'] = db_options
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='deliverpro'),
            'USER': config('DB_USER', default='deliverpro_user'),
            'PASSWORD': config('DB_PASSWORD', default='password'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }

AUTH_USER_MODEL = 'api.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Cache ────────────────────────────────────────────────────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'deliverpro-cache',
    }
}

# ─── Channels (WebSocket temps réel) ─────────────────────────────────────────
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# ─── REST Framework ───────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# ─── JWT ──────────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ─── CORS ─────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = get_env_list(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:5500'
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = get_env_list('CSRF_TRUSTED_ORIGINS')

# Production security for Render (traffic is proxied over HTTPS)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

if not DEBUG:
    SECURE_SSL_REDIRECT = get_env_bool('SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(config('SECURE_HSTS_SECONDS', default=31536000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = get_env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
    SECURE_HSTS_PRELOAD = get_env_bool('SECURE_HSTS_PRELOAD', default=True)

# ─── DRF Spectacular (Swagger) ────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'DeliverPro API',
    'DESCRIPTION': 'API de gestion de livraison et finance',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

"""Django settings for NutriFarm AI.

Configuration is read from environment variables (optionally loaded from a
``.env`` file). Every ``DJANGO_*`` name also accepts the shorter alias listed
in the README, so existing deployments keep working.
"""

import os
from pathlib import Path

import dj_database_url
from django.contrib.messages import constants as message_constants
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


# --------------------------------------------------------------------------
# Environment helpers
# --------------------------------------------------------------------------


def env_str(*names: str, default: str = '') -> str:
    """Return the first environment variable in ``names`` that is set."""
    for name in names:
        value = os.environ.get(name)
        if value is not None:
            return value
    return default


def env_bool(*names: str, default: bool = False) -> bool:
    value = env_str(*names, default='')
    if not value:
        return default
    return value.strip().lower() in {'true', '1', 'yes', 'on'}


def env_list(*names: str, default: str = '') -> list[str]:
    """Parse a comma-separated variable into a list of non-empty strings."""
    return [item.strip() for item in env_str(*names, default=default).split(',') if item.strip()]


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

DEBUG = env_bool('DEBUG', 'DJANGO_DEBUG', default=True)

SECRET_KEY = env_str('SECRET_KEY', 'DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('SECRET_KEY must be configured when DEBUG is False.')
    SECRET_KEY = 'django-insecure-local-only-key-do-not-deploy'

ALLOWED_HOSTS = env_list(
    'ALLOWED_HOSTS',
    'DJANGO_ALLOWED_HOSTS',
    default='localhost,127.0.0.1' if DEBUG else '',
)
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS', 'CSRF_TRUSTED_ORIGINS')

# Render injects the service's public hostname; trust it automatically.
RENDER_EXTERNAL_HOSTNAME = env_str('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_EXTERNAL_HOSTNAME}')

if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured('Set ALLOWED_HOSTS for production.')

# --------------------------------------------------------------------------
# Production security
# --------------------------------------------------------------------------

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env_str('SECURE_HSTS_SECONDS', default='31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'

# --------------------------------------------------------------------------
# Applications and middleware
# --------------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core.apps.CoreConfig',
    'testing.apps.TestingConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Serves collected static files (admin CSS, site CSS) under gunicorn.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'nutrifarm.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'nutrifarm.wsgi.application'
ASGI_APPLICATION = 'nutrifarm.asgi.application'

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------

# Hosted platforms provide DATABASE_URL (e.g. postgres://user:pass@host/db).
# Without it, a local SQLite file is used, which is fine for development.
DATABASE_URL = env_str('DATABASE_URL')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600, conn_health_checks=True),
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = 'testing:login'
LOGIN_REDIRECT_URL = 'testing:dashboard'
LOGOUT_REDIRECT_URL = 'core:home'

# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
# "Collection date cannot be in the future" is evaluated in this zone, so it
# must match where farmers actually are. With UTC, a farmer east of Greenwich
# gets spurious errors for several hours after local midnight.
TIME_ZONE = env_str('DJANGO_TIME_ZONE', 'TIME_ZONE', default='Asia/Kolkata')
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Static files
# --------------------------------------------------------------------------

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': (
            'django.contrib.staticfiles.storage.StaticFilesStorage'
            if DEBUG
            else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
        ),
    },
}

# --------------------------------------------------------------------------
# Misc
# --------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Map Django message levels to Bootstrap alert colours (error -> danger).
MESSAGE_TAGS = {message_constants.ERROR: 'danger'}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '{asctime} {levelname} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'root': {'handlers': ['console'], 'level': env_str('DJANGO_LOG_LEVEL', default='INFO')},
}

# --------------------------------------------------------------------------
# Application settings
# --------------------------------------------------------------------------

# Submission limits only reject implausible input; they are not quality
# standards. pH (0-14) and moisture (0-100%) limits are physical and live in
# ``testing.models``. Feed quality reference ranges live in ``testing.criteria``.
SAMPLE_TEMPERATURE_MIN_C = -20
SAMPLE_TEMPERATURE_MAX_C = 80

# Number of samples shown per page in the sample history.
SAMPLE_HISTORY_PAGE_SIZE = 10

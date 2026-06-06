from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Sécurité ───────────────────────────────────────────────────────────────
_secret_key = os.getenv('SECRET_KEY')
if not _secret_key:
    raise ValueError("SECRET_KEY n'est pas définie. Ajoutez-la dans .env ou les variables d'environnement.")
SECRET_KEY = _secret_key

DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]

# Domaine Vercel automatique
_vercel_url = os.getenv('VERCEL_URL')
if _vercel_url and _vercel_url not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_vercel_url)
if '.vercel.app' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('.vercel.app')

# Domaine custom (ex: conectcredit.com)
_custom_domain = os.getenv('CUSTOM_DOMAIN', '')
if _custom_domain:
    for _d in [_custom_domain, f'www.{_custom_domain}']:
        if _d not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_d)

# ── CSRF Trusted Origins ───────────────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = ['https://*.vercel.app']
if _custom_domain:
    CSRF_TRUSTED_ORIGINS += [f'https://{_custom_domain}', f'https://www.{_custom_domain}']
_vercel_url_full = os.getenv('VERCEL_URL', '')
if _vercel_url_full:
    CSRF_TRUSTED_ORIGINS.append(f'https://{_vercel_url_full}')

# ── Applications ───────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'storages',
    'banks',
    'accounts',
    'transactions',
    'notifications',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'banking_platform.urls'

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

WSGI_APPLICATION = 'banking_platform.wsgi.application'

# ── Base de données ────────────────────────────────────────────────────────
_db_host     = os.getenv('DB_HOST', '')
_db_password = os.getenv('DB_PASSWORD', '')
_db_placeholder = 'METS_TON_MOT_DE_PASSE_ICI'

if _db_host and _db_password and _db_password != _db_placeholder:
    # PostgreSQL Supabase — production
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME':     os.getenv('DB_NAME', 'postgres'),
            'USER':     os.getenv('DB_USER', 'postgres'),
            'PASSWORD': _db_password,
            'HOST':     _db_host,
            'PORT':     os.getenv('DB_PORT', '6543'),
            'OPTIONS':  {'sslmode': 'require'},
            'CONN_MAX_AGE': 0,
            'DISABLE_SERVER_SIDE_CURSORS': True,
        }
    }
else:
    # SQLite local — développement uniquement
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME':    BASE_DIR / 'db.sqlite3',
        }
    }

# ── Authentification ───────────────────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.BankUser'
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 6},
    },
]

# ── Internationalisation ───────────────────────────────────────────────────
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE     = 'Europe/Paris'
USE_I18N      = True
USE_TZ        = True

# ── Fichiers statiques ─────────────────────────────────────────────────────
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

# ── Fichiers media (Supabase Storage) ──────────────────────────────────────
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

_supabase_url         = os.getenv('SUPABASE_URL', '')
_supabase_service_key = os.getenv('SUPABASE_SERVICE_KEY', '')
_bucket               = os.getenv('STORAGE_BUCKET_NAME', 'media')

if _supabase_service_key and _supabase_url:
    STORAGES = {
        "default": {
            "BACKEND": "banking_platform.storage.SupabaseStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    MEDIA_URL = f"{_supabase_url}/storage/v1/object/public/{_bucket}/"
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Email — Brevo SMTP ─────────────────────────────────────────────────────
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = 'smtp-relay.brevo.com'
EMAIL_PORT          = 587
EMAIL_USE_TLS       = True
EMAIL_HOST_USER     = os.getenv('BREVO_SMTP_LOGIN', '')
EMAIL_HOST_PASSWORD = os.getenv('BREVO_SMTP_KEY', '')
DEFAULT_FROM_EMAIL  = os.getenv('DEFAULT_FROM_EMAIL', 'no_reply@mutuelspace.com')
SITE_URL            = os.getenv('SITE_URL', 'http://localhost:8000')
EMAIL_TIMEOUT       = 8

# ── Chiffrement champs sensibles (Fernet) ─────────────────────────────────
FIELD_ENCRYPTION_KEY = os.getenv('FIELD_ENCRYPTION_KEY', '')

# ── Session ────────────────────────────────────────────────────────────────
SESSION_COOKIE_AGE          = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY     = True
SESSION_COOKIE_SAMESITE     = 'Lax'

# ── Sécurité production ────────────────────────────────────────────────────
if not DEBUG:
    SECURE_PROXY_SSL_HEADER      = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT          = True
    SECURE_HSTS_SECONDS          = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD          = True
    SESSION_COOKIE_SECURE        = True
    CSRF_COOKIE_SECURE           = True
    SECURE_BROWSER_XSS_FILTER   = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS              = 'DENY'

# ── Cache ──────────────────────────────────────────────────────────────────
# En serverless Vercel, LocMemCache ne se partage pas entre instances.
if DEBUG:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'banking-platform',
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        }
    }

# ── Logging ────────────────────────────────────────────────────────────────
_log_handlers: list = ['console']
_handlers_cfg: dict = {
    'console': {
        'class': 'logging.StreamHandler',
        'formatter': 'verbose',
    },
}

if DEBUG:
    _log_dir = BASE_DIR / 'logs'
    _log_dir.mkdir(exist_ok=True)
    _log_handlers.append('file')
    _handlers_cfg['file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(_log_dir / 'banking.log'),
        'maxBytes': 10 * 1024 * 1024,
        'backupCount': 5,
        'formatter': 'verbose',
    }

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} — {message}',
            'style': '{',
        },
    },
    'handlers': _handlers_cfg,
    'loggers': {
        'banking': {
            'handlers': _log_handlers,
            'level': 'INFO',
            'propagate': False,
        },
        'django.security': {
            'handlers': _log_handlers,
            'level': 'WARNING',
        },
    },
}

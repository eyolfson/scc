import os, sys

sys.path.append(os.path.join(os.path.dirname(__file__), "apps"))

TIME_ZONE = 'America/Toronto'
LANGUAGE_CODE = 'en-us'

USE_I18N = False
USE_L10N = False

TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

ROOT_URLCONF = 'scc_website.urls'

TEMPLATE_DIRS = [os.path.join(os.path.dirname(__file__), "templates")]

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.admin',
    'scc',
)

from settings_local import *

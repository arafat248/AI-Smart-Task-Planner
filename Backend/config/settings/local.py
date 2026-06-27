from .base import *

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
INSTALLED_APPS += ['debug_toolbar', 'django_extensions'] 
MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')  
INTERNAL_IPS = ['127.0.0.1']
LOGGING['loggers']['django.db.backends']['level'] = 'DEBUG' 
SIMPLE_JWT['ROTATE_REFRESH_TOKENS'] = False 

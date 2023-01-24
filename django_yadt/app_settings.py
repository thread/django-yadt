from django.conf import settings

DJANGO_YADT_CACHEBUST_QUERY_PARAMETER_KEY = getattr(
    settings,
    'DJANGO_YADT_CACHEBUST_QUERY_PARAMETER_KEY',
    '_',
)

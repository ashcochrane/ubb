from django.apps import AppConfig


class GatingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing.gating'
    label = 'gating'

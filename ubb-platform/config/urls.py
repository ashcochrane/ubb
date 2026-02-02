from django.contrib import admin
from django.urls import path
from api.v1.endpoints import api
from api.v1.webhooks import stripe_webhook

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", api.urls),
    path("api/v1/webhooks/stripe", stripe_webhook),
]

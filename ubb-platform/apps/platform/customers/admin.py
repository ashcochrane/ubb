from django.contrib import admin

from apps.platform.customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("external_id", "tenant", "status", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("external_id",)

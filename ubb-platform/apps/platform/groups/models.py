from django.db import models

from core.models import BaseModel


GROUP_STATUS_CHOICES = [
    ("active", "Active"),
    ("archived", "Archived"),
]


class Group(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="groups"
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    margin_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=GROUP_STATUS_CHOICES,
        default="active",
    )

    class Meta:
        db_table = "ubb_group"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                condition=models.Q(status="active"),
                name="uq_group_active_tenant_slug",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status"],
                name="idx_group_tenant_status",
            ),
        ]

    def __str__(self):
        return f"Group({self.slug})"
